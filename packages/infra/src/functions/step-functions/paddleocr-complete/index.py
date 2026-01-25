"""PaddleOCR Complete Lambda

Completes OCR processing:
- Records step complete/error in DynamoDB

This is a fast Lambda (~5 seconds) that runs after OCR execution.
"""
import json

from shared.ddb_client import (
    record_step_complete,
    record_step_error,
    StepName,
)


def handler(event, _context):
    print(f'Event: {json.dumps(event)}')

    workflow_id = event.get('workflow_id')
    paddleocr_status = event.get('paddleocr_status', 'unknown')

    # Record step completion based on status
    if paddleocr_status == 'success':
        record_step_complete(workflow_id, StepName.PADDLEOCR_PROCESSOR)
    elif paddleocr_status in ('failed', 'error'):
        error_msg = event.get('paddleocr_error', 'Unknown error')
        record_step_error(workflow_id, StepName.PADDLEOCR_PROCESSOR, error_msg)
    elif paddleocr_status == 'skipped':
        # Skipped files still complete the step
        record_step_complete(workflow_id, StepName.PADDLEOCR_PROCESSOR)
    else:
        # Unknown status, record as error
        record_step_error(workflow_id, StepName.PADDLEOCR_PROCESSOR, f'Unknown status: {paddleocr_status}')

    print(f'Step completion recorded: status={paddleocr_status}')

    return event
