---
name: search
description: "Search strategy guide for finding information from any source."
whenToUse: "MANDATORY. Use for ALL user questions and requests that require information lookup — including questions about uploaded documents, factual questions, explanations, summaries, comparisons, or any query where the answer might exist in the user's documents. Triggers include: asking about document content, asking 'what is', 'tell me about', 'explain', 'how does', 'compare', 'summarize', searching the web, or any question that is not purely about creating/editing files. When in doubt, activate this skill."
---

# Search Skill

## CRITICAL RULE: Document Search is MANDATORY

You MUST ALWAYS perform document search FIRST, regardless of the query type. This is non-negotiable.
- Even if the question seems like general knowledge, search documents first.
- Even if the user asks for web search, search documents first.
- NEVER skip document search. NEVER go directly to web search.

Web search is ONLY a supplementary fallback after document search has been performed and found insufficient results.

## Search Strategy (MANDATORY)

### Step 1: Document Search (ALWAYS REQUIRED)
- For EVERY query, start by searching uploaded documents using `search___summarize`.
- When the user asks about a specific document (by name or ID), what documents are uploaded, or wants a summary/overview, use `search___overview` first.
- Use clear, specific search queries. If one query doesn't return results, try alternative keywords or phrasings before giving up.
- When the user's question is broad, break it into multiple focused search queries.

### Step 2: Graph Search for Related QA Pairs (ALWAYS REQUIRED after Step 1)
- After `search___summarize` returns results, ALWAYS call `graph___graph_search` with the same query AND the `qa_ids` from the search results.
- Extract qa_ids from the `sources` array in the search result (each source has a `qa_id` field).
- Graph search uses those QA pairs as starting points, traverses entity connections (Entity → MENTIONED_IN → Analysis → BELONGS_TO → Segment) to find related QA pairs that keyword/vector search may have missed.
- This discovers content linked through shared entities (e.g., searching "Big River" finds QA pairs about "Pipeline" or "Pump Station" connected via RELATES_TO edges between entities).
- Even if document search returned good results, graph search may reveal additional related QA pairs from other documents.
- Do NOT skip this step. The combination of document search + graph search provides comprehensive results.

### Step 3: Evaluate Results
- Combine results from both document search and graph search.
- If results are sufficient: answer based on those results with citations. Do NOT proceed to web search.
- If both searches return no results or irrelevant results: inform the user that the information was not found in their documents, then proceed to web search as a supplement.

### Step 4: Web Search (Supplementary Fallback ONLY)
- ONLY use web search AFTER document search has been performed and returned insufficient results.
- Use `search` (DuckDuckGo) for web queries when documents don't have the answer.
- Use `fetch_content` to retrieve full page content from promising search results.
- Clearly distinguish between information from the user's documents vs. the web.

## Web Search Guidelines

When performing web searches, you MUST follow these rules strictly:
1. Search with max_results of 10 to get diverse sources
2. You MUST call fetch_content on AT LEAST 3 different URLs - this is a hard requirement, not optional
3. If a website returns an error (403, timeout, etc.), try another URL until you have successfully fetched 3+ pages
4. Do NOT stop after fetching only 1-2 websites - always continue until you have 3+ successful fetches
5. Synthesize information from all fetched sources before responding
6. Always cite the sources you used with their URLs

## Search Tools

- `search___summarize`: Search uploaded documents. Use this FIRST for ANY query.
- `search___overview`: Get an overview of all documents in a project. Use when the user asks what documents are uploaded, what a specific document is about, or wants a summary of their documents.
- `graph___graph_search`: Find related QA pairs via knowledge graph traversal. ALWAYS use after `search___summarize`. Pass `qa_ids` from search results as starting points. Traverses Entity → MENTIONED_IN → Analysis → BELONGS_TO → Segment connections to discover related QA pairs linked through shared entities.
- `graph___link_documents`: Link two documents with a RELATED_TO relationship. Requires `project_id`, `document_id_1`, `document_id_2`. Optional: `reason` (why they are related), `label` (relationship label).
- `graph___unlink_documents`: Remove the RELATED_TO relationship between two documents. Requires `project_id`, `document_id_1`, `document_id_2`.
- `graph___get_linked_documents`: List documents linked via RELATED_TO. Requires `project_id`. Optional: `document_id` to filter links for a specific document; omit to get all links in the project.
- `search`: Web search via DuckDuckGo. ONLY use as fallback after document search.
- `fetch_content`: Fetch full content from a web URL. Use after web search to get detailed information.

## Citations

- When citing document search results, reference the source document name and relevant section.
- When citing web sources, include the URL.
- Use inline citations naturally within the text, not just a list at the end.

## What NOT to Do

- Do NOT skip document search for any reason.
- Do NOT go directly to web search without performing document search first.
- Do NOT make up information or citations that don't exist in search results.
