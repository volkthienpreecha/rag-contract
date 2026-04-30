# Contributing

Thanks for taking a look at `rag-contract`.

This project is meant to stay small. The goal is not to become a full RAG eval framework. The goal is:

```txt
golden queries -> retriever output -> retrieval metrics -> pass/fail
```

If a change helps teams catch broken retrieval in CI, it probably fits. If it turns this into a dashboard, hosted service, LLM judge, or framework-specific eval suite, it probably does not fit yet.

## Good first contributions

Useful changes right now:

```txt
clearer error messages
more tests for weird JSONL input
better report formatting
small metric fixes
docs that show real usage
CI examples for common setups
```

Please keep PRs narrow. One behavior change per PR is much easier to review than a big cleanup mixed with a feature.

## Local setup

Clone the repo:

```bash
git clone https://github.com/volkthienpreecha/rag-contract.git
cd rag-contract
```

Install locally:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest
```

Try the example failure:

```bash
rag-contract check \
  --golden examples/golden.jsonl \
  --run examples/current_fail.jsonl \
  --baseline examples/baseline.json \
  --config examples/ragcontract.yml
```

That command should exit with code `1`.

Try the example pass:

```bash
rag-contract check \
  --golden examples/golden.jsonl \
  --run examples/current_pass.jsonl \
  --baseline examples/baseline.json \
  --config examples/ragcontract.yml
```

That command should exit with code `0`.

## Code style

Use plain Python. Prefer readable branches over clever one-liners.

Keep the public file contracts stable:

```txt
golden.jsonl
run JSONL
baseline.json
ragcontract.yml
report.md
report.json
junit.xml
```

If a change breaks one of those formats, call it out clearly in the PR.

## Tests

Add or update tests when changing behavior. At minimum, cover:

```txt
the metric result
the contract verdict
the CLI exit code if relevant
```

For docs-only changes, tests are not required.

## Pull requests

In the PR description, include:

```txt
What changed
Why it changed
How you tested it
```

Example:

```txt
What changed:
- Added validation for duplicate query IDs in run files.

Why:
- Duplicate rows make contract results ambiguous.

Tested:
- python -m pytest
```

## What probably does not belong yet

Please open an issue before adding:

```txt
LLM answer grading
synthetic question generation
hosted dashboards
database clients in core
LangChain-only or LlamaIndex-only APIs
large dependency additions
```

Adapters and examples are welcome, but the core package should stay framework-neutral.
