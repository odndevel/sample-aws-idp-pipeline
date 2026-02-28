import json
import os
from typing import Callable

import boto3
from strands import tool

_s3_client = boto3.client('s3')
_prompt_cache = {}


def _load_prompt_from_s3(prompt_name: str) -> str:
    if prompt_name in _prompt_cache:
        return _prompt_cache[prompt_name]
    bucket = os.environ.get('AGENT_STORAGE_BUCKET_NAME', '')
    if not bucket:
        return ''
    s3_key = f'__prompts/analysis/{prompt_name}.txt'
    try:
        resp = _s3_client.get_object(Bucket=bucket, Key=s3_key)
        content = resp['Body'].read().decode('utf-8')
        _prompt_cache[prompt_name] = content
        return content
    except Exception as e:
        print(f'Failed to load prompt from S3 ({s3_key}): {e}')
        return ''


def create_video_analyzer_tool(
    video_uri_getter: Callable[[], str],
    analysis_steps: list,
    model_id: str,
    bedrock_client,
    bucket_owner_account_id: str,
    language: str = 'English'
):
    """Create a video analyzer tool with context.

    Args:
        video_uri_getter: Function to get video S3 URI
        analysis_steps: List to append analysis steps
        model_id: Bedrock model ID for TwelveLabs Pegasus
        bedrock_client: Bedrock client
        bucket_owner_account_id: AWS account ID that owns the S3 bucket
        language: Language for analysis output (e.g., 'Korean', 'English')
    """

    @tool
    def analyze_video(question: str) -> str:
        """Analyze the video segment with a specific question.

        Use this tool to examine specific aspects of the video content.
        Ask targeted questions about visual content, actions, scenes,
        objects, people, text overlays, or any other details you need to understand.

        The video segment is already defined by start and end timecodes from the
        chapter information. This tool will analyze that specific portion of the video.

        Args:
            question: The specific question to ask about the video content.
                      Be specific - e.g., "What actions are being performed in this segment?"
                      or "Describe the main subjects and their activities."
        """
        video_uri = video_uri_getter()
        if not video_uri:
            return 'No video available for analysis.'

        try:
            prompt_template = _load_prompt_from_s3('video_analysis_prompt')

            if prompt_template:
                analysis_prompt = prompt_template.format(
                    query=question,
                    language=language
                )
            else:
                analysis_prompt = f"""Analyze this video segment and answer the following question.

Question: {question}

Provide detailed, professional analysis in {language}."""

            # TwelveLabs Pegasus API format
            request_body = {
                'inputPrompt': analysis_prompt,
                'mediaSource': {
                    's3Location': {
                        'uri': video_uri
                    }
                }
            }

            if bucket_owner_account_id:
                request_body['mediaSource']['s3Location']['bucketOwner'] = bucket_owner_account_id

            print(f'Analyzing video: {video_uri}')

            response = bedrock_client.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body),
                contentType='application/json'
            )

            result = json.loads(response['body'].read().decode('utf-8'))
            # TwelveLabs Pegasus returns response in 'message' field
            answer = result.get('message', '')

            analysis_steps.append({
                'step': len(analysis_steps) + 1,
                'tool': 'analyze_video',
                'question': question,
                'answer': answer[:3000]
            })

            return answer

        except Exception as e:
            error_msg = f'Error analyzing video: {e}'
            print(error_msg)
            return error_msg

    return analyze_video
