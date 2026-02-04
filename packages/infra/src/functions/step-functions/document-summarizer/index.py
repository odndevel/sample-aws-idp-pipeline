import json
import os
import traceback

import boto3
import yaml

from shared.ddb_client import (
    update_workflow_status,
    record_step_start,
    record_step_complete,
    record_step_error,
    get_project_language,
    StepName,
    WorkflowStatus,
)
from shared.s3_analysis import get_all_segment_analyses, save_summary

PHASE1_BATCH_SIZE = 10
PHASE2_BATCH_SIZE = 150
PHASE2_OVERLAP = 30
PROMPTS = None

bedrock_client = None

# Tool schemas for structured output (Anthropic format)
PAGE_DESCRIPTIONS_TOOL = {
    'name': 'save_page_descriptions',
    'description': 'Save the generated page descriptions. You MUST include exactly one entry per page.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'page_descriptions': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'page': {'type': 'integer', 'description': 'Page number'},
                        'description': {'type': 'string', 'description': 'Detailed 5+ sentence description'}
                    },
                    'required': ['page', 'description']
                }
            }
        },
        'required': ['page_descriptions']
    }
}

RELATED_PAGES_TOOL = {
    'name': 'save_related_pages',
    'description': 'Save the related pages analysis. Include every page, use empty arrays when no strong relationship exists.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'pages': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'page': {'type': 'integer', 'description': 'Page number'},
                        'related_pages': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'description': 'Pages that share the same actual content (empty array if none)'
                        }
                    },
                    'required': ['page', 'related_pages']
                }
            }
        },
        'required': ['pages']
    }
}


def get_bedrock_client():
    global bedrock_client
    if bedrock_client is None:
        bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
    return bedrock_client


def get_prompts():
    global PROMPTS
    if PROMPTS is None:
        path = os.path.join(os.path.dirname(__file__), 'prompts', 'summarizer.yaml')
        with open(path, 'r') as f:
            PROMPTS = yaml.safe_load(f)
    return PROMPTS


def build_page_content(segment):
    """Build full page content from segment data - no truncation."""
    parts = []
    if bda := segment.get('bda_indexer', ''):
        parts.append(f'[BDA]\n{bda}')
    if pdf := segment.get('format_parser', ''):
        parts.append(f'[PDF Text]\n{pdf}')
    for a in segment.get('ai_analysis', []):
        if content := a.get('content', ''):
            parts.append(f'[AI: {a.get("analysis_query", "")}]\n{content}')
    return '\n\n'.join(parts)


def invoke_anthropic_tool(client, model_id, system_text, user_text, tool, max_tokens=64000, use_cache=False):
    """Call Anthropic model with forced tool use for structured output."""
    system_block = {'type': 'text', 'text': system_text}
    if use_cache:
        system_block['cache_control'] = {'type': 'ephemeral'}

    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps({
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': max_tokens,
            'system': [system_block],
            'messages': [
                {'role': 'user', 'content': user_text}
            ],
            'tools': [tool],
            'tool_choice': {'type': 'tool', 'name': tool['name']}
        }),
        contentType='application/json'
    )
    result = json.loads(response['body'].read())
    stop_reason = result.get('stop_reason', '')
    if stop_reason == 'max_tokens':
        print(f'[WARN] invoke_anthropic_tool: response truncated (max_tokens)')
    for block in result.get('content', []):
        if block.get('type') == 'tool_use':
            return block.get('input', {})
    print(f'[WARN] invoke_anthropic_tool: no tool_use block found. stop_reason={stop_reason}')
    return {}


def invoke_anthropic_text(client, model_id, system_text, user_text, max_tokens=8192, use_cache=False):
    """Call Anthropic model for plain text response."""
    system_block = {'type': 'text', 'text': system_text}
    if use_cache:
        system_block['cache_control'] = {'type': 'ephemeral'}

    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps({
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': max_tokens,
            'system': [system_block],
            'messages': [
                {'role': 'user', 'content': user_text}
            ],
        }),
        contentType='application/json'
    )
    result = json.loads(response['body'].read())
    for block in result.get('content', []):
        if block.get('type') == 'text':
            return block.get('text', '')
    return ''


def format_descriptions_for_input(page_descriptions):
    """Format page descriptions as text for Phase 2 input."""
    parts = []
    for pd in page_descriptions:
        page = pd.get('page', 0)
        desc = pd.get('description', '')
        parts.append(f'Page {page}: {desc}')
    return '\n\n'.join(parts)


def batch_with_overlap(items, batch_size, overlap):
    """Split items into batches with overlap between consecutive batches."""
    if len(items) <= batch_size:
        return [items]
    batches = []
    step = batch_size - overlap
    for start in range(0, len(items), step):
        end = min(start + batch_size, len(items))
        batches.append(items[start:end])
        if end >= len(items):
            break
    return batches


def generate_page_descriptions(client, model_id, language, segments):
    """Phase 1: Generate per-page descriptions using Haiku in batches with forced tool use."""
    prompts = get_prompts()
    system_text = prompts['page_description_system'].format(language=language)

    all_descriptions = []
    total = len(segments)
    total_batches = (total + PHASE1_BATCH_SIZE - 1) // PHASE1_BATCH_SIZE
    use_cache = total_batches > 1

    for batch_start in range(0, total, PHASE1_BATCH_SIZE):
        batch_end = min(batch_start + PHASE1_BATCH_SIZE, total)
        batch_segments = segments[batch_start:batch_end]

        page_nums = []
        pages_content_parts = []
        for seg in batch_segments:
            page_num = seg.get('segment_index', 0) + 1
            page_nums.append(page_num)
            content = build_page_content(seg)
            if content:
                pages_content_parts.append(f'--- Page {page_num} ---\n{content}')
            else:
                pages_content_parts.append(f'--- Page {page_num} ---\n[Empty page]')

        pages_content = '\n\n'.join(pages_content_parts)
        user_text = prompts['page_description_user'].format(
            pages_content=pages_content,
            page_count=len(batch_segments),
            page_list=', '.join(str(p) for p in page_nums)
        )

        batch_num = batch_start // PHASE1_BATCH_SIZE + 1
        print(f'Phase 1: Processing batch {batch_num}/{total_batches} (pages {batch_start + 1}-{batch_end})')

        try:
            result = invoke_anthropic_tool(
                client, model_id, system_text, user_text,
                PAGE_DESCRIPTIONS_TOOL, use_cache=use_cache
            )
            descriptions = result.get('page_descriptions', [])
            print(f'Phase 1 batch {batch_num}: got {len(descriptions)}/{len(batch_segments)} descriptions')
            all_descriptions.extend(descriptions)
        except Exception as e:
            print(f'Phase 1 batch {batch_num} failed: {e}')
            traceback.print_exc()
            for seg in batch_segments:
                page_num = seg.get('segment_index', 0) + 1
                all_descriptions.append({'page': page_num, 'description': ''})

    return all_descriptions


def enrich_related_pages(client, model_id, language, page_descriptions, total_pages):
    """Phase 2a: Identify related pages using Sonnet with batching + overlap."""
    prompts = get_prompts()
    system_text = prompts['related_pages_system']

    batches = batch_with_overlap(page_descriptions, PHASE2_BATCH_SIZE, PHASE2_OVERLAP)
    total_batches = len(batches)
    use_cache = total_batches > 1

    related_map = {}

    for batch_idx, batch in enumerate(batches):
        batch_text = format_descriptions_for_input(batch)
        batch_page_nums = [pd.get('page', 0) for pd in batch]
        user_text = prompts['related_pages_user'].format(
            total_pages=len(batch),
            page_descriptions=batch_text
        )

        print(f'Phase 2a: Batch {batch_idx + 1}/{total_batches} '
              f'({len(batch)} pages: {batch_page_nums[0]}-{batch_page_nums[-1]})')

        try:
            result = invoke_anthropic_tool(
                client, model_id, system_text, user_text,
                RELATED_PAGES_TOOL, max_tokens=8192, use_cache=use_cache
            )
            pages = result.get('pages', [])
            for item in pages:
                if isinstance(item, dict) and 'page' in item:
                    page_num = item['page']
                    new_related = item.get('related_pages', [])
                    if page_num in related_map:
                        existing = set(related_map[page_num])
                        existing.update(new_related)
                        related_map[page_num] = sorted(existing)
                    else:
                        related_map[page_num] = new_related
        except Exception as e:
            print(f'Phase 2a batch {batch_idx + 1} failed: {e}')
            traceback.print_exc()

    return related_map


def generate_document_summary(client, model_id, language, page_descriptions, total_pages):
    """Phase 2b: Generate document summary using Sonnet with batching for large documents."""
    prompts = get_prompts()
    system_text = prompts['document_summary_system']

    batches = batch_with_overlap(page_descriptions, PHASE2_BATCH_SIZE, PHASE2_OVERLAP)

    if len(batches) == 1:
        descriptions_text = format_descriptions_for_input(page_descriptions)
        user_text = prompts['document_summary_user'].format(
            total_pages=total_pages,
            language=language,
            page_descriptions=descriptions_text
        )

        print(f'Phase 2b: Single call for document summary')

        try:
            return invoke_anthropic_text(
                client, model_id, system_text, user_text, max_tokens=8192
            ).strip()
        except Exception as e:
            print(f'Phase 2b failed: {e}')
            return ''

    use_cache = True
    partial_summaries = []

    for batch_idx, batch in enumerate(batches):
        batch_text = format_descriptions_for_input(batch)
        batch_page_nums = [pd.get('page', 0) for pd in batch]
        user_text = prompts['document_summary_user'].format(
            total_pages=f'{batch_page_nums[0]}-{batch_page_nums[-1]} of {total_pages}',
            language=language,
            page_descriptions=batch_text
        )

        print(f'Phase 2b: Batch {batch_idx + 1}/{len(batches)} '
              f'(pages {batch_page_nums[0]}-{batch_page_nums[-1]})')

        try:
            partial = invoke_anthropic_text(
                client, model_id, system_text, user_text,
                max_tokens=4096, use_cache=use_cache
            ).strip()
            if partial:
                partial_summaries.append(
                    f'[Pages {batch_page_nums[0]}-{batch_page_nums[-1]}]\n{partial}'
                )
        except Exception as e:
            print(f'Phase 2b batch {batch_idx + 1} failed: {e}')

    if not partial_summaries:
        return ''

    if len(partial_summaries) == 1:
        return partial_summaries[0]

    merge_text = '\n\n'.join(partial_summaries)
    merge_user = (
        f'Below are section summaries of a {total_pages}-page document. '
        f'Write a unified comprehensive summary.\n'
        f'Respond ONLY in: {language}\n\n{merge_text}'
    )

    print(f'Phase 2b: Merging {len(partial_summaries)} partial summaries')

    try:
        return invoke_anthropic_text(
            client, model_id, system_text, merge_user, max_tokens=8192
        ).strip()
    except Exception as e:
        print(f'Phase 2b merge failed: {e}')
        return '\n\n'.join(partial_summaries)


def extract_document_id_from_uri(file_uri: str) -> str:
    """Extract document_id from file_uri as fallback."""
    if not file_uri:
        return ''
    parts = file_uri.split('/')
    try:
        doc_index = parts.index('documents')
        if doc_index + 1 < len(parts):
            return parts[doc_index + 1]
    except ValueError:
        pass
    return ''


def handler(event, context):
    print(f'Event: {json.dumps(event)}')

    workflow_id = event.get('workflow_id')
    document_id = event.get('document_id')
    project_id = event.get('project_id')
    file_uri = event.get('file_uri')
    segment_count = event.get('segment_count', 0)

    summarizer_model_id = os.environ['SUMMARIZER_MODEL_ID']
    summarizer_lite_model_id = os.environ['SUMMARIZER_LITE_MODEL_ID']

    if not document_id and file_uri:
        document_id = extract_document_id_from_uri(file_uri)
        print(f'Extracted document_id from file_uri: {document_id}')

    record_step_complete(workflow_id, StepName.SEGMENT_ANALYZER, segment_count=segment_count)
    record_step_start(workflow_id, StepName.DOCUMENT_SUMMARIZER)

    try:
        language = 'en'
        if project_id:
            language = get_project_language(project_id)
        print(f'Using language: {language}')

        segments = get_all_segment_analyses(file_uri, segment_count)

        if not segments:
            print(f'No segments found in S3 for file {file_uri}')
            record_step_complete(
                workflow_id,
                StepName.DOCUMENT_SUMMARIZER,
                skipped=True,
                reason='No segments found'
            )
            return {
                'workflow_id': workflow_id,
                'status': 'no_segments',
                'message': 'No segments found for summarization'
            }

        segments_sorted = sorted(segments, key=lambda x: x.get('segment_index', 0))
        total_pages = len(segments_sorted)
        client = get_bedrock_client()

        # Phase 1: Page descriptions (Haiku, forced tool use)
        page_descriptions = generate_page_descriptions(
            client, summarizer_model_id, language, segments_sorted
        )
        print(f'Phase 1 complete: {len(page_descriptions)} page descriptions generated')

        # Phase 2a: Related pages (Sonnet, forced tool use, batched with overlap)
        related_map = enrich_related_pages(
            client, summarizer_lite_model_id, language, page_descriptions, total_pages
        )
        print(f'Phase 2a complete: {len(related_map)} pages with related pages')

        # Phase 2b: Document summary (Sonnet, plain text, batched if needed)
        document_summary = generate_document_summary(
            client, summarizer_lite_model_id, language, page_descriptions, total_pages
        )
        print(f'Phase 2b complete: summary length={len(document_summary)}')

        pages = []
        for pd in page_descriptions:
            page_num = pd.get('page', 0)
            pages.append({
                'page': page_num,
                'description': pd.get('description', ''),
                'related_pages': related_map.get(page_num, [])
            })

        summary_data = {
            'language': language,
            'document_summary': document_summary,
            'total_pages': total_pages,
            'pages': pages
        }

        save_summary(file_uri, summary_data)
        print(f'Saved summary.json to S3 for file {file_uri}')

        record_step_complete(
            workflow_id,
            StepName.DOCUMENT_SUMMARIZER,
            segment_count=total_pages
        )

        update_workflow_status(
            document_id,
            workflow_id,
            WorkflowStatus.COMPLETED,
        )

        print(f'Completed workflow {workflow_id} with {total_pages} pages')

        return {
            'workflow_id': workflow_id,
            'status': 'completed',
            'segment_count': total_pages,
            'summary_pages': len(pages),
        }

    except Exception as e:
        print(f'Error in document summarization: {e}')
        traceback.print_exc()
        record_step_error(workflow_id, StepName.DOCUMENT_SUMMARIZER, str(e))
        update_workflow_status(document_id, workflow_id, WorkflowStatus.FAILED, error=str(e))
        return {
            'workflow_id': workflow_id,
            'status': 'failed',
            'error': str(e)
        }
