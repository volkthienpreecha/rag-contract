# rag-contract

Fail CI when your RAG app stops retrieving the right documents for important test questions.

`rag-contract` compares expected document IDs with the document IDs your retriever actually returned. It returns pass or fail.

A retriever is the part of a RAG system that finds documents before the LLM writes an answer.

A golden query is a saved test question with the document IDs that should be returned. It works like an answer key for retrieval.

A baseline is a known-good retrieval run. Future runs are compared against it.

Use `rag-contract` when you change:

```txt
chunking
embeddings
reranking
filters
document parsing
vector database settings
indexed documents
```

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

## Install

```bash
pip install rag-contract
```

## Setup

You need four files:

```txt
golden.jsonl
baseline_run.jsonl
baseline.json
ragcontract.yml
```

### 1. Create `golden.jsonl`

This file contains your test questions and the document IDs that should be retrieved.

Example:

```json
{"id":"refund_policy","query":"What is the refund policy for enterprise customers?","relevant_doc_ids":["doc_refund_policy"],"must_rank_at_most":3}
{"id":"hipaa_baa","query":"Do we offer a BAA for HIPAA customers?","relevant_doc_ids":["doc_hipaa_compliance","doc_baa_terms"],"must_rank_at_most":5}
```

Each row is one test case.

### 2. Export a known-good retrieval run

Run your retriever on the golden queries and save what it returned.

Example `baseline_run.jsonl`:

```json
{"query_id":"refund_policy","results":[{"doc_id":"doc_refund_policy","score":0.92},{"doc_id":"doc_terms","score":0.74},{"doc_id":"doc_pricing","score":0.61}]}
{"query_id":"hipaa_baa","results":[{"doc_id":"doc_baa_terms","score":0.89},{"doc_id":"doc_hipaa_compliance","score":0.82},{"doc_id":"doc_security","score":0.64}]}
```

The run file can come from any retriever. The only required fields are:

```txt
query_id
results[].doc_id
```

### 3. Create a baseline

```bash
rag-contract baseline \
  --golden golden.jsonl \
  --run baseline_run.jsonl \
  --out baseline.json
```

This saves the known-good retrieval scores.

### 4. Create `ragcontract.yml`

```yaml
k: 5

fail_on:
  mrr_drop_gt: 0.10
  recall_drop_gt: 0.10
  hitrate_drop_gt: 0.05

minimums:
  mrr_at_k: 0.70
  recall_at_k: 0.80
  hitrate_at_k: 0.90

per_query:
  enforce_must_rank_at_most: true
  enforce_must_include: true
  enforce_forbidden_docs: true
```

### 5. Check a new retrieval run

After changing your RAG pipeline, export a new run.

Example `current_run.jsonl`:

```json
{"query_id":"refund_policy","results":[{"doc_id":"doc_pricing","score":0.81},{"doc_id":"doc_terms","score":0.72},{"doc_id":"doc_support","score":0.66}]}
{"query_id":"hipaa_baa","results":[{"doc_id":"doc_baa_terms","score":0.87},{"doc_id":"doc_security","score":0.68},{"doc_id":"doc_hipaa_compliance","score":0.62}]}
```

Run the check:

```bash
rag-contract check \
  --golden golden.jsonl \
  --run current_run.jsonl \
  --baseline baseline.json \
  --config ragcontract.yml
```

Exit codes:

```txt
0 = pass
1 = retrieval check failed
2 = invalid input
```

## Input files

`rag-contract` uses two JSONL input files.

JSONL means one JSON object per line.

### Golden file

The golden file contains the expected retrieval behavior.

Example:

```json
{"id":"refund_policy","query":"What is the refund policy for enterprise customers?","relevant_doc_ids":["doc_refund_policy"],"must_rank_at_most":3,"tags":["policy"],"weight":2}
```

Required fields:

```txt
id
query
relevant_doc_ids
```

Optional fields:

```txt
must_rank_at_most
must_include_any
forbidden_doc_ids
weight
tags
metadata
```

Field meanings:

```txt
id                  stable ID for the test query
query               the question being tested
relevant_doc_ids    document IDs that should be retrieved
must_rank_at_most   highest allowed rank for the expected document
must_include_any    pass if at least one relevant document appears
forbidden_doc_ids   document IDs that should not appear in retrieval
weight              importance of this query in aggregate metrics
tags                labels used for grouped reporting
metadata            extra information saved with the test case
```

### Retriever run file

The run file contains the documents returned by your retriever.

Example:

```json
{"query_id":"refund_policy","results":[{"doc_id":"doc_pricing","score":0.81},{"doc_id":"doc_refund_policy","score":0.77},{"doc_id":"doc_terms","score":0.61}],"latency_ms":42}
```

Required fields:

```txt
query_id
results[].doc_id
```

Optional fields:

```txt
results[].score
results[].chunk_id
results[].metadata
latency_ms
embedding_model
index_version
chunking_version
retriever_version
```

Field meanings:

```txt
query_id             ID from the golden file
results              ranked list of retrieved documents
results[].doc_id     document ID returned by the retriever
results[].score      retriever score, if available
results[].chunk_id   chunk ID, if retrieval happens at chunk level
latency_ms           retrieval latency for the query
embedding_model      embedding model used for this run
index_version        index version used for this run
chunking_version     chunking version used for this run
retriever_version    retriever version used for this run
```

Your RAG stack only needs to export this format.

The retriever can use:

```txt
LangChain
LlamaIndex
Chroma
Pinecone
Weaviate
Postgres
Elasticsearch
custom code
```

## Config

Example `ragcontract.yml`:

```yaml
k: 5

fail_on:
  mrr_drop_gt: 0.10
  recall_drop_gt: 0.10
  hitrate_drop_gt: 0.05

minimums:
  mrr_at_k: 0.70
  recall_at_k: 0.80
  hitrate_at_k: 0.90

per_query:
  enforce_must_rank_at_most: true
  enforce_must_include: true
  enforce_forbidden_docs: true
```

Config fields:

```txt
k                         number of retrieved documents to evaluate
mrr_drop_gt               fail if MRR drops by more than this amount
recall_drop_gt            fail if Recall drops by more than this amount
hitrate_drop_gt           fail if HitRate drops by more than this amount
mrr_at_k                  minimum allowed MRR@k
recall_at_k               minimum allowed Recall@k
hitrate_at_k              minimum allowed HitRate@k
enforce_must_rank_at_most fail when expected docs appear too low
enforce_must_include      fail when expected docs are missing
enforce_forbidden_docs    fail when forbidden docs appear
```

## Metrics

`rag-contract` computes:

```txt
MRR@k
Recall@k
Precision@k
HitRate@k
```

Plain-English meanings:

```txt
MRR@k        how high the first correct document appears
Recall@k     how many expected documents appeared in the top k
Precision@k  how many retrieved documents were expected
HitRate@k    whether at least one expected document appeared in the top k
```

Example metric output:

```txt
MRR@5        0.82 -> 0.68   FAIL
Recall@5     0.91 -> 0.76   FAIL
Precision@5  0.44 -> 0.41   PASS
HitRate@5    0.96 -> 0.84   FAIL
```

When golden queries include tags, `report.json` includes tag-level metrics.

## Per-query checks

You can define query-specific rules.

Example:

```json
{"id":"public_pricing","query":"What is public pricing?","relevant_doc_ids":["pricing_public"],"forbidden_doc_ids":["internal_discount_policy"],"must_rank_at_most":3}
```

This check fails when:

```txt
pricing_public is missing from the top results
pricing_public appears below rank 3
internal_discount_policy appears in the retrieved results
```

## Commands

Validate input files:

```bash
rag-contract validate \
  --golden golden.jsonl \
  --run current_run.jsonl
```

Score one run:

```bash
rag-contract score \
  --golden golden.jsonl \
  --run current_run.jsonl \
  --k 5
```

Create a baseline:

```bash
rag-contract baseline \
  --golden golden.jsonl \
  --run baseline_run.jsonl \
  --out baseline.json
```

Check against a baseline:

```bash
rag-contract check \
  --golden golden.jsonl \
  --run current_run.jsonl \
  --baseline baseline.json \
  --config ragcontract.yml
```

Show query-level changes:

```bash
rag-contract diff \
  --golden golden.jsonl \
  --run current_run.jsonl \
  --baseline baseline.json
```

## GitHub Actions

```yaml
name: RAG Contract Tests

on:
  pull_request:

jobs:
  rag-contract:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Install rag-contract
        run: pip install rag-contract

      - name: Run retriever
        run: python examples/export_retrieval_run.py --out current_run.jsonl

      - name: Check retrieval contracts
        run: |
          rag-contract check \
            --golden golden.jsonl \
            --run current_run.jsonl \
            --baseline baseline.json \
            --config ragcontract.yml \
            --report-md report.md \
            --junit junit.xml
```

## Output files

By default, `check` writes:

```txt
report.md
report.json
junit.xml
```

### `report.md`

Human-readable report for local review or CI artifacts.

### `report.json`

Machine-readable report with:

```txt
global metrics
per-query results
failed checks
tag-level metrics
```

### `junit.xml`

JUnit-compatible test report for CI systems.

## Checked failures

`rag-contract` detects:

```txt
expected document is missing
expected document moved below the allowed rank
forbidden document appeared in retrieved results
MRR@k dropped more than allowed
Recall@k dropped more than allowed
HitRate@k dropped more than allowed
overall metric is below the configured minimum
```

## Scope

`rag-contract` evaluates retrieval output only.

Out of scope:

```txt
generated answer grading
LLM judges
synthetic test question generation
hosted dashboards
document ingestion
direct vector database connections
framework-specific requirements
```

## File format summary

Golden row:

```json
{"id":"query_id","query":"user question","relevant_doc_ids":["doc_id"],"must_rank_at_most":5}
```

Run row:

```json
{"query_id":"query_id","results":[{"doc_id":"doc_id","score":0.91}]}
```

Minimum setup:

```txt
golden.jsonl
baseline_run.jsonl
baseline.json
current_run.jsonl
ragcontract.yml
```
