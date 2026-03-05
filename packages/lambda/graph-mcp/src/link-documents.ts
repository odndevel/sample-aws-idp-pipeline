import { invokeGraphService } from './clients.js';
import type {
  LinkDocumentsInput,
  UnlinkDocumentsInput,
  GetLinkedDocumentsInput,
  LinkDocumentsAnswer,
} from './types.js';

export async function linkDocuments(
  input: LinkDocumentsInput,
): Promise<{ success: boolean }> {
  const { project_id, document_id_1, document_id_2, reason, label } = input;

  await invokeGraphService('link_documents', {
    project_id,
    document_id_1,
    document_id_2,
    reason: reason ?? '',
    label: label ?? '',
  });

  return { success: true };
}

export async function unlinkDocuments(
  input: UnlinkDocumentsInput,
): Promise<{ success: boolean }> {
  const { project_id, document_id_1, document_id_2 } = input;

  await invokeGraphService('unlink_documents', {
    project_id,
    document_id_1,
    document_id_2,
  });

  return { success: true };
}

export async function getLinkedDocuments(
  input: GetLinkedDocumentsInput,
): Promise<LinkDocumentsAnswer> {
  const { project_id, document_id } = input;

  const result = await invokeGraphService('get_linked_documents', {
    project_id,
    document_id,
  });

  const links = (result.links ?? []) as Array<Record<string, string>>;

  if (document_id) {
    return {
      success: true,
      links: links.map((l) => ({
        document_id: l.id,
        file_name: l.file_name,
        reason: l.reason,
        label: l.label,
      })),
    };
  }

  return {
    success: true,
    links: links.map((l) => ({
      document_id: `${l.doc1} <-> ${l.doc2}`,
      file_name: `${l.name1} <-> ${l.name2}`,
      reason: l.reason,
    })),
  };
}
