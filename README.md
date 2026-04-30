# rag-contract

Fail CI when your RAG app stops retrieving the right documents for important test questions.

`rag-contract` compares what your retriever returns today against a saved set of expected results. It is useful when you change chunking, embeddings, reranking, filters, document parsing, vector database settings, or the indexed documents.

A retriever is the part of a RAG system that finds documents before the LLM writes an answer.

A golden query is a saved test question with the document IDs that should be returned. It works like an answer key for retrieval.

A baseline is a known-good retrieval run. Future runs are compared against it.

`rag-contract` reads two files:

1. the expected results
2. the documents your retriever actually returned

Then it reports whether retrieval passed or failed.

## Example

You save this test question:

```json
{"id":"refund_policy","query":"What is the refund policy for enterprise customers?","relevant_doc_ids":["doc_refund_policy"],"must_rank_at_most":3}
```

This means:

```txt
When the query asks about refund policy, doc_refund_policy should appear in the top 3 retrieved documents.
```

After a code change, your retriever returns this:

```json
{"query_id":"refund_policy","results":[{"doc_id":"doc_pricing"},{"doc_id":"doc_terms"},{"doc_id":"doc_support"}]}
```

`doc_refund_policy` is missing, so the check fails:

```txt
FAIL refund_policy
Expected doc_refund_policy in top 3
Found: missing from top 5
```

This catches the retrieval bug before the PR is merged.
