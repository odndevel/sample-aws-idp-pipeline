import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { invokeGraphService, invokeLanceDB, bedrockClient } from './clients.js';
import type { GraphSearchInput, GraphSearchAnswer } from './types.js';

const HAIKU_MODEL_ID = 'global.anthropic.claude-haiku-4-5-20251001-v1:0';

interface SegmentContent {
  segment_id: string;
  qa_id?: string;
  document_id: string;
  segment_index: number;
  qa_index?: number;
  question?: string;
  content: string;
}

interface EntityInfo {
  name: string;
  type: string;
}

function buildPrompt(
  query: string,
  segments: SegmentContent[],
  entities: EntityInfo[],
): string {
  const resultsText = segments
    .map(
      (s, i) =>
        `[${i + 1}] document_id: ${s.document_id}, segment_id: ${s.segment_id}\n${s.content}`,
    )
    .join('\n\n');

  const entitiesText = entities
    .map((e) => `- ${e.name} (${e.type})`)
    .join('\n');

  return `You are an assistant that organizes document search results found through knowledge graph traversal.

<query>
${query}
</query>

<connected_entities>
${entitiesText}
</connected_entities>

<graph_traversal_results>
${resultsText}
</graph_traversal_results>

These results were discovered by traversing entity connections in a knowledge graph. The entities listed above are the shared connections that linked the original search results to these additional pages.

Organize the information related to the query.

Rules:
1. Start with a brief explanation of which entities connected the original results to these pages (e.g. "Connected via: entity1, entity2").
2. Preserve the original document's expressions and content as much as possible.
3. Exclude results that are not related to the query.
4. If related information is found from multiple documents, organize them by source.
5. Always specify the source (document_id, segment_id) for each piece of information.
6. If no related information is found, respond with "No related information found."
7. Respond in the same language as the document content.

Output format:
**Connected via:** entity1, entity2, ...

[Source: document_id=xxx, segment_id=yyy]
(Information based on original content)`;
}

export async function graphSearch(
  input: GraphSearchInput,
): Promise<GraphSearchAnswer> {
  const {
    project_id,
    query,
    document_id,
    depth = 2,
    limit = 10,
    qa_ids,
  } = input;

  // 1. Graph traversal to find related segments
  const result = await invokeGraphService('search_graph', {
    project_id,
    query,
    document_id,
    depth,
    entity_limit: 10,
    segment_limit: limit,
    qa_ids: qa_ids ?? [],
  });

  const entities = (result.entities ?? []) as Array<{
    id: string;
    name: string;
    type: string;
    description?: string;
  }>;

  const segments = (result.segments ?? []) as Array<{
    id: string;
    workflow_id: string;
    document_id: string;
    segment_index: number;
    match_type: string;
  }>;

  const sources = segments.map((s) => ({
    document_id: s.document_id,
    segment_id: s.id,
    segment_index: s.segment_index,
    match_type: s.match_type,
    source: 'graph' as const,
  }));

  const entityList = entities.map((e) => ({
    name: e.name,
    type: e.type,
    description: e.description,
  }));

  // 2. Fetch segment content from LanceDB
  const traversalSegmentIds = segments.map((s) => s.id);
  if (traversalSegmentIds.length === 0) {
    return { sources, entities: entityList };
  }

  const lanceResult = await invokeLanceDB('get_by_segment_ids', {
    project_id,
    segment_ids: traversalSegmentIds,
  });

  const segmentContents = (lanceResult.segments ?? []) as SegmentContent[];
  if (segmentContents.length === 0) {
    return { sources, entities: entityList };
  }

  // 3. Summarize with Haiku
  const prompt = buildPrompt(query, segmentContents, entityList);
  const command = new ConverseCommand({
    modelId: HAIKU_MODEL_ID,
    messages: [{ role: 'user', content: [{ text: prompt }] }],
    inferenceConfig: { maxTokens: 2048 },
  });

  const response = await bedrockClient.send(command);
  const answer = response.output?.message?.content?.[0]?.text ?? '';

  return { answer, sources, entities: entityList };
}
