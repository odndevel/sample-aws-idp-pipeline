import { useState, useEffect, useCallback } from 'react';

interface GraphNode {
  id: string;
  label: string;
  type: string;
  properties: Record<string, unknown>;
}

interface GraphEdge {
  source: string;
  target: string;
  label: string;
  properties: Record<string, unknown> | null;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface UseGraphDataOptions {
  fetchApi: (path: string, options?: RequestInit) => Promise<Response>;
  projectId: string;
  documentId?: string;
}

export function useGraphData({
  fetchApi,
  projectId,
  documentId,
}: UseGraphDataOptions) {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const path = documentId
        ? `projects/${projectId}/graph/documents/${documentId}`
        : `projects/${projectId}/graph`;
      const response = await fetchApi(path);
      if (!response.ok) {
        if (response.status === 404) {
          setData({ nodes: [], edges: [] });
          return;
        }
        throw new Error(`Failed to fetch graph: ${response.status}`);
      }
      const result = await response.json();
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load graph');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [fetchApi, projectId, documentId]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  return { data, loading, error, refetch: fetchGraph };
}

export type { GraphNode, GraphEdge, GraphData };
