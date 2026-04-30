# rag-contract

Fail your PR when retrieval gets worse.

`rag-contract` is a tiny CI tool for RAG retrieval regression testing.

It does not grade generated answers.
It does not require an LLM judge.
It does not care what vector database you use.

It checks one thing:

```txt
Do your golden queries still retrieve the right documents?
```

Think:

```txt
pytest for RAG retrieval quality
```

## 30-second quickstart

Install:

```bash
pip install rag-contract
```

Create a baseline from a known-good retrieval run:

```bash
rag-contract baseline \
  --golden examples/golden.jsonl \
  --run examples/baseline_run.jsonl \
  --out examples/baseline.json
```

Check a new run:

```bash
rag-contract check \
  --golden examples/golden.jsonl \
  --run examples/current_fail.jsonl \
  --baseline examples/baseline.json \
  --config examples/ragcontract.yml
```

Exit codes:

```txt
0 = pass
1 = fail
2 = invalid input
```

By default, `check` writes:

```txt
report.md
report.json
junit.xml
```

## Input contracts

Golden file:

```json
{"id":"refund_policy","query":"What is the refund policy for enterprise customers?","relevant_doc_ids":["doc_refund_policy"],"must_rank_at_most":3,"tags":["policy"],"weight":2}
```

Retriever run:

```json
{"query_id":"refund_policy","results":[{"doc_id":"doc_pricing","score":0.81},{"doc_id":"doc_refund_policy","score":0.77},{"doc_id":"doc_terms","score":0.61}],"latency_ms":42}
```

That is the integration boundary. Export JSONL from LangChain, LlamaIndex, Chroma, Pinecone, Weaviate, Postgres, Elasticsearch, or a custom retriever. `rag-contract` only needs query IDs and doc IDs.

## Config

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

## CLI

Validate file contracts:

```bash
rag-contract validate --golden examples/golden.jsonl --run examples/current_pass.jsonl
```

Score one run:

```bash
rag-contract score --golden examples/golden.jsonl --run examples/current_pass.jsonl --k 5
```

Create a baseline:

```bash
rag-contract baseline --golden examples/golden.jsonl --run examples/baseline_run.jsonl --out examples/baseline.json
```

Compare against baseline:

```bash
rag-contract check --golden examples/golden.jsonl --run examples/current_pass.jsonl --baseline examples/baseline.json --config examples/ragcontract.yml
```

Show query-level movement:

```bash
rag-contract diff --golden examples/golden.jsonl --run examples/current_fail.jsonl --baseline examples/baseline.json
```

## Metrics

The MVP computes weighted averages for:

```txt
MRR@k
Recall@k
Precision@k
HitRate@k
```

It also emits tag-level aggregates in `report.json` when golden queries include `tags`.

## Per-query contracts

Supported fields:

```txt
must_rank_at_most
must_include_any
forbidden_doc_ids
weight
tags
metadata
```

Example:

```json
{"id":"public_pricing","query":"What is public pricing?","relevant_doc_ids":["pricing_public"],"forbidden_doc_ids":["internal_discount_policy"],"must_rank_at_most":3}
```

That catches security and compliance regressions where internal-only documents leak into top-k retrieval.

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
        run: python examples/export_retrieval_run.py --out current.jsonl

      - name: Check retrieval contracts
        run: |
          rag-contract check \
            --golden golden.jsonl \
            --run current.jsonl \
            --baseline baseline.json \
            --config ragcontract.yml \
            --report-md report.md \
            --junit junit.xml
```

## Why this is narrow

`rag-contract` is not a full RAG evaluation framework.

No answer grading.
No synthetic question generation.
No hosted dashboard.
No vector database integration.
No framework lock-in.

Just:

```txt
input files -> metrics -> contract verdict -> CI exit code
```
