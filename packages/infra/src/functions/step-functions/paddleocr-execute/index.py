"""PaddleOCR Execute Lambda

Executes OCR processing after EC2 is confirmed running:
- Health check polling (should be fast since EC2 is already running)
- HTTP POST to /predict endpoint
- Saves result to S3

EC2 lifecycle is handled by Step Functions, so this Lambda
doesn't need to worry about starting or waiting for EC2.
"""
import json
import os
import time
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import boto3

from shared.s3_analysis import (
    get_s3_client,
    parse_s3_uri,
)


def wait_for_ec2_ready(private_ip: str, timeout: int = 120) -> bool:
    """Wait for EC2 health endpoint to be ready.

    Timeout is shorter since EC2 should already be running.
    """
    url = f'http://{private_ip}:8080/health'
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            req = Request(url, method='GET')
            with urlopen(req, timeout=10) as response:
                if response.status == 200:
                    print(f'EC2 server ready at {private_ip}')
                    return True
        except (URLError, HTTPError) as e:
            print(f'Waiting for EC2 server... ({e})')
            time.sleep(5)

    raise TimeoutError(f'EC2 server not ready after {timeout}s')


def call_ec2_predict(private_ip: str, request_data: dict, timeout: int = 600) -> dict:
    """Call EC2 predict endpoint."""
    url = f'http://{private_ip}:8080/predict'

    data = json.dumps(request_data).encode('utf-8')
    req = Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    with urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read().decode('utf-8'))
        return result


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


def save_ocr_output(file_uri: str, ocr_result: dict) -> str:
    """Save OCR result to paddleocr/ folder under document path."""
    s3 = get_s3_client()
    bucket, base_path = get_document_base_path(file_uri)

    output_key = f'{base_path}/paddleocr/result.json'

    s3.put_object(
        Bucket=bucket,
        Key=output_key,
        Body=json.dumps(ocr_result, ensure_ascii=False, indent=2),
        ContentType='application/json'
    )

    output_uri = f's3://{bucket}/{output_key}'
    print(f'OCR result saved to: {output_uri}')
    return output_uri


def handler(event, _context):
    print(f'Event: {json.dumps(event)}')

    workflow_id = event.get('workflow_id')
    project_id = event.get('project_id', 'default')
    file_uri = event.get('file_uri')

    # OCR settings from PrepareOcr Lambda
    ocr_model = event.get('ocr_model', 'paddleocr-vl')
    ocr_options = event.get('ocr_options', {})

    # EC2 private IP from Step Functions EC2 lifecycle
    private_ip = event.get('ec2_private_ip')

    if not private_ip:
        raise ValueError('ec2_private_ip is required')

    try:
        start_time = time.time()

        # Wait for server to be ready (should be quick since EC2 is already running)
        wait_for_ec2_ready(private_ip)
        ready_time = time.time() - start_time
        print(f'EC2 ready in {ready_time:.1f}s')

        # Prepare inference request
        inference_request = {
            's3_uri': file_uri,
            'model': ocr_model,
            'model_options': ocr_options,
            'metadata': {
                'workflow_id': workflow_id,
                'project_id': project_id,
            }
        }

        # Call EC2 predict endpoint
        print(f'Calling EC2 predict endpoint with model={ocr_model}...')
        inference_start = time.time()
        result = call_ec2_predict(private_ip, inference_request)
        inference_time = time.time() - inference_start
        print(f'Inference completed in {inference_time:.1f}s')

        if result.get('success'):
            # Save OCR result to S3
            ocr_output_uri = save_ocr_output(file_uri, result)

            # Count pages for reporting
            page_count = len(result.get('pages', [])) or 1

            total_time = time.time() - start_time
            print(f'OCR completed: {page_count} pages in {total_time:.1f}s')

            return {
                **event,
                'paddleocr_status': 'success',
                'paddleocr_model': ocr_model,
                'paddleocr_output_uri': ocr_output_uri,
                'paddleocr_page_count': page_count
            }
        else:
            error_msg = result.get('error', 'Unknown error')
            print(f'OCR failed: {error_msg}')
            return {
                **event,
                'paddleocr_status': 'failed',
                'paddleocr_error': error_msg
            }

    except Exception as e:
        error_msg = str(e)
        print(f'Error processing document: {error_msg}')
        return {
            **event,
            'paddleocr_status': 'error',
            'paddleocr_error': error_msg
        }
