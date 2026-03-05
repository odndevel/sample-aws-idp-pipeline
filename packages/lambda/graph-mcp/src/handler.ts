import { graphSearch } from './graph-search.js';
import {
  linkDocuments,
  unlinkDocuments,
  getLinkedDocuments,
} from './link-documents.js';
import type {
  GraphSearchInput,
  LinkDocumentsInput,
  UnlinkDocumentsInput,
  GetLinkedDocumentsInput,
} from './types.js';

interface LambdaContext {
  clientContext?: {
    custom?: {
      bedrockAgentCoreToolName?: string;
    };
  };
}

export const handler = async (event: unknown, context: LambdaContext) => {
  const toolName =
    context.clientContext?.custom?.bedrockAgentCoreToolName ?? '';
  const action = toolName.includes('___')
    ? toolName.split('___').pop()
    : toolName;

  switch (action) {
    case 'graph_search':
      return graphSearch(event as GraphSearchInput);
    case 'link_documents':
      return linkDocuments(event as LinkDocumentsInput);
    case 'unlink_documents':
      return unlinkDocuments(event as UnlinkDocumentsInput);
    case 'get_linked_documents':
      return getLinkedDocuments(event as GetLinkedDocumentsInput);
    default:
      throw new Error(`Unknown tool: ${toolName}`);
  }
};
