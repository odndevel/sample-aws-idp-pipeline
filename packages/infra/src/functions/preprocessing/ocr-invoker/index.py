"""OCR Invoker Lambda

Receives PDF/Image files from SQS queue and routes to the appropriate backend:
- pp-ocrv5, pp-structurev3 -> Lambda async invoke (CPU-only, no SageMaker needed)
- paddleocr-vl -> SageMaker async inference (GPU required)

For large PDFs (>200 pages), splits into chunks and invokes parallel Lambda processors.
"""
import json
import os
import io
import tempfile
from datetime import datetime, timezone

import boto3

from shared.ddb_client import (
    update_preprocess_status,
    PreprocessStatus,
    PreprocessType,
    record_step_start,
    record_step_skipped,
    record_step_error,
    StepName,
)
from shared.s3_analysis import get_s3_client, parse_s3_uri

SAGEMAKER_ENDPOINT_NAME = os.environ.get('SAGEMAKER_ENDPOINT_NAME', '')
OUTPUT_BUCKET = os.environ.get('OUTPUT_BUCKET', '')
OCR_LAMBDA_FUNCTION_NAME = os.environ.get('OCR_LAMBDA_FUNCTION_NAME', '')
CHUNK_PAGE_SIZE = int(os.environ.get('CHUNK_PAGE_SIZE', '30'))

# Models that run on Lambda (CPU-only) instead of SageMaker (GPU)
LAMBDA_OCR_MODELS = {'pp-ocrv5', 'pp-structurev3'}

SUPPORTED_MIME_TYPES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/tiff',
    'image/gif',
    'image/bmp',
    'image/webp',
}

sagemaker_runtime = None
sagemaker_client = None
lambda_client = None


def get_sagemaker_runtime():
    global sagemaker_runtime
    if sagemaker_runtime is None:
        sagemaker_runtime = boto3.client(
            'sagemaker-runtime',
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
    return sagemaker_runtime


def get_sagemaker_client():
    global sagemaker_client
    if sagemaker_client is None:
        sagemaker_client = boto3.client(
            'sagemaker',
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
    return sagemaker_client


def get_lambda_client():
    global lambda_client
    if lambda_client is None:
        lambda_client = boto3.client(
            'lambda',
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
    return lambda_client


def ensure_endpoint_running():
    """Request scale-out to ensure endpoint has at least 1 instance.

    This is idempotent - if already at 1 instance, nothing happens.
    """
    if not SAGEMAKER_ENDPOINT_NAME:
        return

    try:
        client = get_sagemaker_client()
        client.update_endpoint_weights_and_capacities(
            EndpointName=SAGEMAKER_ENDPOINT_NAME,
            DesiredWeightsAndCapacities=[{
                'VariantName': 'AllTraffic',
                'DesiredInstanceCount': 1
            }]
        )
        print(f'Requested scale-out for {SAGEMAKER_ENDPOINT_NAME}')
    except Exception as e:
        # Don't fail the job if scale-out request fails
        print(f'Scale-out request failed (non-fatal): {e}')


def get_document_base_path(file_uri: str) -> tuple[str, str]:
    """Extract bucket and document base path from file URI."""
    bucket, key = parse_s3_uri(file_uri)
    key_parts = key.split('/')

    if 'documents' in key_parts:
        doc_idx = key_parts.index('documents')
        base_path = '/'.join(key_parts[:doc_idx + 2])
    else:
        base_path = '/'.join(key_parts[:-1])

    return bucket, base_path


def get_pdf_page_count(bucket: str, key: str) -> int:
    """Get PDF page count using pypdf. Downloads only to /tmp."""
    from pypdf import PdfReader

    s3 = get_s3_client()
    with tempfile.NamedTemporaryFile(suffix='.pdf', dir='/tmp', delete=True) as tmp:
        s3.download_file(bucket, key, tmp.name)
        reader = PdfReader(tmp.name)
        return len(reader.pages)


def split_and_upload_chunks(
    bucket: str,
    key: str,
    base_path: str,
    workflow_id: str,
    document_id: str,
    ocr_model: str,
    ocr_options: dict,
    chunk_size: int = CHUNK_PAGE_SIZE,
) -> dict:
    """Split PDF into chunks, upload to S3, and write manifest.json.

    Returns manifest dict with total_chunks and chunk metadata.
    """
    from pypdf import PdfReader, PdfWriter

    s3 = get_s3_client()

    with tempfile.NamedTemporaryFile(suffix='.pdf', dir='/tmp', delete=True) as tmp:
        s3.download_file(bucket, key, tmp.name)
        reader = PdfReader(tmp.name)
        total_pages = len(reader.pages)
        chunks = []

        for chunk_idx in range(0, total_pages, chunk_size):
            start_page = chunk_idx
            end_page = min(chunk_idx + chunk_size, total_pages)

            writer = PdfWriter()
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])

            buf = io.BytesIO()
            writer.write(buf)
            buf.seek(0)

            chunk_key = f'{base_path}/paddleocr/chunks/chunk_{chunk_idx // chunk_size:04d}.pdf'
            s3.put_object(Bucket=bucket, Key=chunk_key, Body=buf.read(), ContentType='application/pdf')

            chunks.append({
                'chunk_index': chunk_idx // chunk_size,
                'start_page': start_page,
                'end_page': end_page,
                'page_count': end_page - start_page,
                's3_key': chunk_key,
            })

        manifest = {
            'total_chunks': len(chunks),
            'chunk_size': chunk_size,
            'total_pages': total_pages,
            'workflow_id': workflow_id,
            'document_id': document_id,
            'ocr_model': ocr_model,
            'ocr_options': ocr_options,
            'chunks': chunks,
        }

        manifest_key = f'{base_path}/paddleocr/manifest.json'
        s3.put_object(
            Bucket=bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
            ContentType='application/json',
        )

        print(f'[{workflow_id}] Split {total_pages} pages into {len(chunks)} chunks, manifest saved')
        return manifest


def invoke_async_inference(
    file_uri: str,
    workflow_id: str,
    document_id: str,
    project_id: str,
    ocr_model: str = 'pp-ocrv5',
    ocr_options: dict | None = None,
) -> str:
    """Invoke SageMaker async inference and return immediately."""
    client = get_sagemaker_runtime()
    s3_client = get_s3_client()

    bucket, base_path = get_document_base_path(file_uri)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    inference_id = f'{workflow_id[:16]}-{timestamp}'

    # Prepare inference request with metadata for SNS callback
    inference_request = {
        's3_uri': file_uri,
        'model': ocr_model,
        'model_options': ocr_options or {},
        'metadata': {
            'workflow_id': workflow_id,
            'document_id': document_id,
            'project_id': project_id,
            'file_uri': file_uri,
            'base_path': base_path,
            'bucket': bucket,
        }
    }

    # Upload input request to S3
    input_key = f'{base_path}/paddleocr/input.json'
    s3_client.put_object(
        Bucket=bucket,
        Key=input_key,
        Body=json.dumps(inference_request, ensure_ascii=False, indent=2).encode('utf-8'),
        ContentType='application/json'
    )
    input_location = f's3://{bucket}/{input_key}'

    print(f'Invoking async inference: endpoint={SAGEMAKER_ENDPOINT_NAME}, input={input_location}')

    response = client.invoke_endpoint_async(
        EndpointName=SAGEMAKER_ENDPOINT_NAME,
        ContentType='application/json',
        InputLocation=input_location,
        InvocationTimeoutSeconds=3600,
        InferenceId=inference_id,
    )

    output_location = response.get('OutputLocation', '')
    print(f'Async inference invoked: inference_id={inference_id}, output={output_location}')
    return output_location


def invoke_lambda_async(
    file_uri: str,
    workflow_id: str,
    document_id: str,
    project_id: str,
    ocr_model: str,
    ocr_options: dict | None = None,
    chunk_index: int | None = None,
    start_page: int | None = None,
    total_chunks: int | None = None,
    original_file_uri: str | None = None,
) -> None:
    """Invoke OCR Lambda processor asynchronously (fire-and-forget).

    The Lambda processor handles DDB/S3 writes on completion.
    For chunk mode, additional parameters tell the processor about its chunk context.
    """
    client = get_lambda_client()

    payload = {
        'workflow_id': workflow_id,
        'document_id': document_id,
        'project_id': project_id,
        'file_uri': file_uri,
        'ocr_model': ocr_model,
        'ocr_options': ocr_options or {},
    }

    if chunk_index is not None:
        payload['chunk_index'] = chunk_index
        payload['start_page'] = start_page
        payload['total_chunks'] = total_chunks
        payload['original_file_uri'] = original_file_uri

    print(f'Invoking Lambda async: function={OCR_LAMBDA_FUNCTION_NAME}, model={ocr_model}'
          f'{f", chunk={chunk_index}/{total_chunks}" if chunk_index is not None else ""}')

    client.invoke(
        FunctionName=OCR_LAMBDA_FUNCTION_NAME,
        InvocationType='Event',
        Payload=json.dumps(payload).encode('utf-8'),
    )
    print(f'Lambda async invoked for workflow={workflow_id}')


def process_message(message: dict) -> dict:
    """Process a single message from the queue."""
    workflow_id = message.get('workflow_id')
    document_id = message.get('document_id')
    project_id = message.get('project_id')
    file_uri = message.get('file_uri')
    file_type = message.get('file_type')
    ocr_model = message.get('ocr_model', 'pp-ocrv5')
    ocr_options = message.get('ocr_options', {})

    print(f'Processing OCR job: workflow={workflow_id}, file={file_uri}, model={ocr_model}')

    # Check if file type is supported
    if file_type not in SUPPORTED_MIME_TYPES:
        print(f'Skipping unsupported file type: {file_type}')
        update_preprocess_status(
            document_id=document_id,
            workflow_id=workflow_id,
            processor=PreprocessType.OCR,
            status=PreprocessStatus.SKIPPED,
            reason=f'File type {file_type} not supported'
        )
        record_step_skipped(workflow_id, StepName.PADDLEOCR_PROCESSOR, f'File type {file_type} not supported')
        return {'status': 'skipped', 'reason': f'Unsupported file type: {file_type}'}

    try:
        # Update STEP record to in_progress
        record_step_start(workflow_id, StepName.PADDLEOCR_PROCESSOR)

        # Update preprocess status to processing
        update_preprocess_status(
            document_id=document_id,
            workflow_id=workflow_id,
            processor=PreprocessType.OCR,
            status=PreprocessStatus.PROCESSING
        )

        if ocr_model in LAMBDA_OCR_MODELS:
            # CPU-only models -> Lambda async invoke
            # Check if PDF needs chunking for parallel processing
            if file_type == 'application/pdf':
                try:
                    bucket, base_path = get_document_base_path(file_uri)
                    _, file_key = parse_s3_uri(file_uri)
                    page_count = get_pdf_page_count(bucket, file_key)
                    print(f'[{workflow_id}] PDF has {page_count} pages (chunk threshold: {CHUNK_PAGE_SIZE})')

                    if page_count > CHUNK_PAGE_SIZE:
                        # Split into chunks and invoke parallel Lambdas
                        manifest = split_and_upload_chunks(
                            bucket=bucket,
                            key=file_key,
                            base_path=base_path,
                            workflow_id=workflow_id,
                            document_id=document_id,
                            ocr_model=ocr_model,
                            ocr_options=ocr_options,
                        )

                        for chunk in manifest['chunks']:
                            chunk_file_uri = f's3://{bucket}/{chunk["s3_key"]}'
                            invoke_lambda_async(
                                file_uri=chunk_file_uri,
                                workflow_id=workflow_id,
                                document_id=document_id,
                                project_id=project_id,
                                ocr_model=ocr_model,
                                ocr_options=ocr_options,
                                chunk_index=chunk['chunk_index'],
                                start_page=chunk['start_page'],
                                total_chunks=manifest['total_chunks'],
                                original_file_uri=file_uri,
                            )

                        return {
                            'status': 'invoked',
                            'backend': 'lambda',
                            'mode': 'chunked',
                            'total_chunks': manifest['total_chunks'],
                            'total_pages': manifest['total_pages'],
                        }

                except Exception as e:
                    # pypdf failure -> fallback to single Lambda invoke
                    print(f'[{workflow_id}] PDF chunking failed, falling back to single invoke: {e}')

            # Single Lambda invoke (small PDF, images, or chunking fallback)
            invoke_lambda_async(
                file_uri=file_uri,
                workflow_id=workflow_id,
                document_id=document_id,
                project_id=project_id,
                ocr_model=ocr_model,
                ocr_options=ocr_options,
            )
            return {'status': 'invoked', 'backend': 'lambda'}
        else:
            # GPU models -> SageMaker async inference
            ensure_endpoint_running()
            output_location = invoke_async_inference(
                file_uri=file_uri,
                workflow_id=workflow_id,
                document_id=document_id,
                project_id=project_id,
                ocr_model=ocr_model,
                ocr_options=ocr_options,
            )
            return {'status': 'invoked', 'backend': 'sagemaker', 'output_location': output_location}

    except Exception as e:
        print(f'Error invoking OCR: {e}')
        update_preprocess_status(
            document_id=document_id,
            workflow_id=workflow_id,
            processor=PreprocessType.OCR,
            status=PreprocessStatus.FAILED,
            error=str(e)
        )
        record_step_error(workflow_id, StepName.PADDLEOCR_PROCESSOR, str(e))
        raise


def handler(event, _context):
    print(f'Event: {json.dumps(event)}')

    results = []

    for record in event.get('Records', []):
        try:
            message = json.loads(record.get('body', '{}'))
            result = process_message(message)
            results.append({
                'workflow_id': message.get('workflow_id'),
                **result
            })

        except Exception as e:
            print(f'Error processing record: {e}')
            import traceback
            traceback.print_exc()
            results.append({
                'status': 'failed',
                'error': str(e)
            })

    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': len(results),
            'results': results
        })
    }
