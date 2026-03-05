export interface GraphSearchInput {
  project_id: string;
  query: string;
  document_id?: string;
  depth?: number;
  limit?: number;
  qa_ids?: string[];
}

export interface GraphSearchAnswer {
  answer?: string;
  sources: Array<{
    document_id: string;
    segment_id: string;
    qa_id?: string;
    segment_index: number;
    qa_index?: number;
    match_type: string;
    source: 'graph';
  }>;
  entities: Array<{
    name: string;
    type: string;
    description?: string;
  }>;
}

export interface LinkDocumentsInput {
  project_id: string;
  document_id_1: string;
  document_id_2: string;
  reason?: string;
  label?: string;
}

export interface UnlinkDocumentsInput {
  project_id: string;
  document_id_1: string;
  document_id_2: string;
}

export interface GetLinkedDocumentsInput {
  project_id: string;
  document_id?: string;
}

export interface LinkDocumentsAnswer {
  success: boolean;
  links?: Array<{
    document_id: string;
    file_name: string;
    reason?: string;
    label?: string;
  }>;
}
