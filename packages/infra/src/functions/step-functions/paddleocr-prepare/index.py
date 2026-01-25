"""PaddleOCR Prepare Lambda

Prepares for OCR processing:
- Records step start in DynamoDB
- Gets project OCR settings

This is a fast Lambda (~5 seconds) that runs before EC2 lifecycle management.
"""
import json

from shared.ddb_client import (
    record_step_start,
    get_project_ocr_settings,
    StepName,
)


def handler(event, _context):
    print(f'Event: {json.dumps(event)}')

    workflow_id = event.get('workflow_id')
    project_id = event.get('project_id', 'default')

    # Record step start
    record_step_start(workflow_id, StepName.PADDLEOCR_PROCESSOR)

    # Get project OCR settings
    ocr_settings = get_project_ocr_settings(project_id)
    ocr_model = ocr_settings.get('ocr_model', 'paddleocr-vl')
    ocr_options = ocr_settings.get('ocr_options', {})

    print(f'Project {project_id} OCR settings: model={ocr_model}, options={ocr_options}')

    return {
        **event,
        'ocr_model': ocr_model,
        'ocr_options': ocr_options,
    }
