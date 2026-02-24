"""OCR Lambda Processor

Processes PDF/Image files using pp-ocrv5 or pp-structurev3 (CPU-only).
Invoked asynchronously by ocr-invoker Lambda. Writes results directly to S3 and DDB.
"""
import json
import os
import tempfile
import tarfile
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.ddb_client import (
    update_preprocess_status,
    PreprocessStatus,
    PreprocessType,
    record_step_complete,
    record_step_error,
    StepName,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_BUCKET = os.environ.get('OUTPUT_BUCKET', '')
MODEL_CACHE_BUCKET = os.environ.get('MODEL_CACHE_BUCKET', '')
MODEL_CACHE_PREFIX = os.environ.get('MODEL_CACHE_PREFIX', 'paddleocr/models')

PADDLEOCR_HOME = '/tmp/.paddleocr'
PADDLEX_HOME = '/tmp/.paddlex'
os.environ['PADDLEOCR_HOME'] = PADDLEOCR_HOME
os.environ['PADDLEX_HOME'] = PADDLEX_HOME
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

s3_client = None


def get_s3_client():
    global s3_client
    if s3_client is None:
        s3_client = boto3.client('s3')
    return s3_client


def parse_s3_uri(uri: str) -> tuple[str, str]:
    clean = uri.replace('s3://', '')
    bucket = clean.split('/')[0]
    key = '/'.join(clean.split('/')[1:])
    return bucket, key


# ========================================
# S3 Model Cache (same pattern as inference.py)
# ========================================

def s3_cache_exists(model_key: str) -> bool:
    if not MODEL_CACHE_BUCKET:
        return False
    try:
        s3 = get_s3_client()
        response = s3.head_object(
            Bucket=MODEL_CACHE_BUCKET,
            Key=f'{MODEL_CACHE_PREFIX}/{model_key}.tar.gz',
        )
        content_length = response.get('ContentLength', 0)
        if content_length < 1024 * 1024:
            logger.warning(f'S3 cache for {model_key} too small ({content_length} bytes), treating as missing')
            return False
        return True
    except ClientError:
        return False


def download_from_s3_cache(model_key: str) -> bool:
    if not MODEL_CACHE_BUCKET:
        return False
    try:
        s3 = get_s3_client()
        cache_path = f'{MODEL_CACHE_PREFIX}/{model_key}.tar.gz'
        local_tar = f'/tmp/{model_key}.tar.gz'

        logger.info(f'Downloading model cache from s3://{MODEL_CACHE_BUCKET}/{cache_path}')
        s3.download_file(MODEL_CACHE_BUCKET, cache_path, local_tar)

        file_size = os.path.getsize(local_tar)
        if file_size < 1000:
            logger.warning(f'Cache file too small ({file_size} bytes)')
            os.unlink(local_tar)
            return False

        os.makedirs(PADDLEOCR_HOME, exist_ok=True)
        os.makedirs(PADDLEX_HOME, exist_ok=True)

        with tarfile.open(local_tar, 'r:gz') as tar:
            for member in tar.getmembers():
                if member.name.startswith('root_paddlex'):
                    # Redirect /root/.paddlex -> /tmp/.paddlex (Lambda has no /root write access)
                    member.name = member.name.replace('root_paddlex', '.paddlex', 1)
                    tar.extract(member, '/tmp')
                else:
                    tar.extract(member, '/tmp')

        os.unlink(local_tar)
        logger.info('Model cache extracted')
        return True
    except Exception as e:
        logger.warning(f'Failed to download from S3 cache: {e}')
        return False


def upload_to_s3_cache(model_key: str) -> bool:
    if not MODEL_CACHE_BUCKET:
        return False
    try:
        s3 = get_s3_client()
        cache_path = f'{MODEL_CACHE_PREFIX}/{model_key}.tar.gz'
        local_tar = f'/tmp/{model_key}_upload.tar.gz'

        logger.info('Creating model cache archive...')
        with tarfile.open(local_tar, 'w:gz') as tar:
            if os.path.exists(PADDLEOCR_HOME):
                tar.add(PADDLEOCR_HOME, arcname='.paddleocr')
            if os.path.exists(PADDLEX_HOME):
                tar.add(PADDLEX_HOME, arcname='.paddlex')

        file_size = os.path.getsize(local_tar)
        logger.info(f'Cache archive size: {file_size / (1024 * 1024):.2f} MB')

        s3.upload_file(local_tar, MODEL_CACHE_BUCKET, cache_path)
        os.unlink(local_tar)
        logger.info('Model cache uploaded')
        return True
    except Exception as e:
        logger.warning(f'Failed to upload to S3 cache: {e}')
        return False


# ========================================
# Model Loading and Prediction
# ========================================

_loaded_model = None
_loaded_model_name = None
_loaded_model_lang = None


def load_model(model_name: str, options: dict | None = None):
    """Load OCR model with S3 cache support."""
    global _loaded_model, _loaded_model_name, _loaded_model_lang

    opts = options or {}
    lang = opts.get('lang') or None

    # Reuse if already loaded with same config
    if _loaded_model is not None and _loaded_model_name == model_name and _loaded_model_lang == lang:
        return _loaded_model

    cache_key = f'{model_name}-{lang or "default"}'

    if s3_cache_exists(cache_key):
        logger.info(f'Found S3 cache for {cache_key}, downloading...')
        download_from_s3_cache(cache_key)
    else:
        logger.info(f'No S3 cache for {cache_key}, will download from HuggingFace')

    os.makedirs(PADDLEOCR_HOME, exist_ok=True)
    os.makedirs(PADDLEX_HOME, exist_ok=True)

    if model_name == 'pp-ocrv5':
        from paddleocr import PaddleOCR
        ocr_kwargs = {
            'use_doc_orientation_classify': opts.get('use_doc_orientation_classify', False),
            'use_doc_unwarping': opts.get('use_doc_unwarping', False),
            'use_textline_orientation': opts.get('use_textline_orientation', False),
        }
        if lang:
            ocr_kwargs['lang'] = lang
        model = PaddleOCR(**ocr_kwargs)
    elif model_name == 'pp-structurev3':
        from paddleocr import PPStructureV3
        ocr_kwargs = {
            'use_doc_orientation_classify': opts.get('use_doc_orientation_classify', False),
            'use_doc_unwarping': opts.get('use_doc_unwarping', False),
        }
        if lang:
            ocr_kwargs['lang'] = lang
        model = PPStructureV3(**ocr_kwargs)
    else:
        raise ValueError(f'Unsupported model: {model_name}')

    logger.info(f'{model_name} loaded')

    # Cache to S3 if not already cached
    if not s3_cache_exists(cache_key):
        logger.info(f'Caching {cache_key} to S3...')
        upload_to_s3_cache(cache_key)

    _loaded_model = model
    _loaded_model_name = model_name
    _loaded_model_lang = lang
    return model


def format_pp_ocrv5_output(results: list[Any]) -> dict:
    """Format PP-OCRv5 results into pages/blocks/content structure."""
    pages = []
    all_content = []

    for page_idx, res in enumerate(results):
        if not hasattr(res, 'json'):
            continue

        res_data = res.json.get('res', {})
        rec_texts = res_data.get('rec_texts', [])
        rec_polys = res_data.get('rec_polys', [])
        rec_boxes = res_data.get('rec_boxes', [])
        width = res_data.get('width')
        height = res_data.get('height')

        content = '\n'.join(t for t in rec_texts if t.strip())
        blocks = []

        for idx, text in enumerate(rec_texts):
            bbox = []
            if rec_polys and idx < len(rec_polys):
                poly = rec_polys[idx]
                if poly and len(poly) == 4:
                    xs = [p[0] for p in poly]
                    ys = [p[1] for p in poly]
                    bbox = [min(xs), min(ys), max(xs), max(ys)]
            elif rec_boxes and idx < len(rec_boxes):
                box = rec_boxes[idx]
                if len(box) == 4:
                    bbox = box
                elif len(box) == 8:
                    xs = [box[i] for i in range(0, 8, 2)]
                    ys = [box[i] for i in range(1, 8, 2)]
                    bbox = [min(xs), min(ys), max(xs), max(ys)]

            blocks.append({
                'block_id': idx,
                'block_label': 'text',
                'block_content': text,
                'block_bbox': bbox,
                'block_order': idx,
                'group_id': 0,
            })

        pages.append({
            'page_index': page_idx,
            'content': content,
            'blocks': blocks,
            'width': width,
            'height': height,
            'results': [res.json],
        })
        all_content.append(content)

    return {
        'pages': pages,
        'page_count': len(pages),
        'content': '\n\n---\n\n'.join(all_content),
    }


def format_pp_structurev3_output(results: list[Any]) -> dict:
    """Format PP-StructureV3 results into pages/blocks/content structure."""
    pages = []
    all_content = []

    for page_idx, res in enumerate(results):
        if not hasattr(res, 'json'):
            continue

        res_data = res.json.get('res', res.json)
        parsing_list = res_data.get('parsing_res_list', [])
        width = res_data.get('width')
        height = res_data.get('height')

        blocks = []
        content_parts = []

        for block in parsing_list:
            blocks.append({
                'block_id': block.get('block_id', 0),
                'block_label': block.get('block_label', 'text'),
                'block_content': block.get('block_content', ''),
                'block_bbox': block.get('block_bbox', []),
                'block_order': block.get('block_order'),
                'group_id': block.get('group_id', 0),
            })

            block_content = block.get('block_content', '').strip()
            if not block_content:
                continue

            block_label = block.get('block_label', 'text')
            if block_label == 'doc_title':
                content_parts.append(f'# {block_content}')
            elif block_label == 'paragraph_title':
                content_parts.append(f'## {block_content}')
            else:
                content_parts.append(block_content)

        content = '\n\n'.join(content_parts)
        pages.append({
            'page_index': page_idx,
            'content': content,
            'blocks': blocks,
            'width': width,
            'height': height,
            'results': [res.json],
        })
        all_content.append(content)

    return {
        'pages': pages,
        'page_count': len(pages),
        'content': '\n\n---\n\n'.join(all_content),
    }


# ========================================
# Main Processing
# ========================================

def process_file(
    file_uri: str,
    workflow_id: str,
    document_id: str,
    ocr_model: str,
    ocr_options: dict | None = None,
) -> dict:
    """Download file from S3, run OCR, save result.json, update DDB."""
    s3 = get_s3_client()
    bucket, key = parse_s3_uri(file_uri)

    # Determine document base path
    key_parts = key.split('/')
    if 'documents' in key_parts:
        doc_idx = key_parts.index('documents')
        base_path = '/'.join(key_parts[:doc_idx + 2])
    else:
        base_path = '/'.join(key_parts[:-1])

    # Download file to /tmp
    suffix = os.path.splitext(key)[1].lower() or '.jpg'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir='/tmp') as tmp:
        s3.download_file(bucket, key, tmp.name)
        tmp_path = tmp.name

    try:
        # Load model and run prediction
        model = load_model(ocr_model, ocr_options)
        logger.info(f'Processing file: {tmp_path} (model={ocr_model})')
        results = model.predict(input=tmp_path)

        # Format output (same structure as SageMaker)
        if ocr_model == 'pp-ocrv5':
            formatted = format_pp_ocrv5_output(results)
        else:
            formatted = format_pp_structurev3_output(results)

        output = {
            'success': True,
            'format': 'markdown',
            'model': ocr_model,
            'model_options': ocr_options or {},
            **formatted,
        }

        # Save result.json to S3
        output_key = f'{base_path}/paddleocr/result.json'
        s3.put_object(
            Bucket=bucket,
            Key=output_key,
            Body=json.dumps(output, ensure_ascii=False, indent=2),
            ContentType='application/json',
        )
        ocr_output_uri = f's3://{bucket}/{output_key}'
        logger.info(f'Result saved to: {ocr_output_uri}')

        # Update DDB status
        page_count = formatted.get('page_count', 1)
        update_preprocess_status(
            document_id=document_id,
            workflow_id=workflow_id,
            processor=PreprocessType.OCR,
            status=PreprocessStatus.COMPLETED,
            output_uri=ocr_output_uri,
            page_count=page_count,
        )
        record_step_complete(workflow_id, StepName.PADDLEOCR_PROCESSOR)
        logger.info(f'OCR completed: {page_count} pages')

        return {'status': 'completed', 'output_uri': ocr_output_uri, 'page_count': page_count}

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def handler(event, _context):
    """Lambda handler - invoked asynchronously by ocr-invoker."""
    logger.info(f'Event: {json.dumps(event)}')

    workflow_id = event.get('workflow_id')
    document_id = event.get('document_id')
    file_uri = event.get('file_uri')
    ocr_model = event.get('ocr_model', 'pp-ocrv5')
    ocr_options = event.get('ocr_options', {})

    try:
        result = process_file(
            file_uri=file_uri,
            workflow_id=workflow_id,
            document_id=document_id,
            ocr_model=ocr_model,
            ocr_options=ocr_options,
        )
        return {'statusCode': 200, 'body': json.dumps(result)}

    except Exception as e:
        logger.error(f'OCR processing failed: {e}')
        import traceback
        traceback.print_exc()

        # Update DDB with failure
        update_preprocess_status(
            document_id=document_id,
            workflow_id=workflow_id,
            processor=PreprocessType.OCR,
            status=PreprocessStatus.FAILED,
            error=str(e),
        )
        record_step_error(workflow_id, StepName.PADDLEOCR_PROCESSOR, str(e))
        raise
