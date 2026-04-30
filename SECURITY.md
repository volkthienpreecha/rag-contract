# Security

`rag-contract` is a local CLI. It reads files you give it, computes retrieval metrics, and writes reports.

It should not need network access to run checks. It should not need API keys. It should not call your vector database directly.

## Supported versions

Security fixes will target the latest released version.

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## Reporting a vulnerability

If you find a security issue, please do not open a public issue with exploit details.

Email:

```txt
volk_thienpreecha@berkeley.edu
```

Please include:

```txt
what the issue is
how to reproduce it
which version or commit you tested
whether it can expose local files, secrets, or CI data
```

I will try to respond quickly. If the issue is real, I will patch it before public discussion.

## Things worth reporting

Please report issues like:

```txt
arbitrary file writes outside requested report paths
unexpected network calls
secret leakage in reports
unsafe XML output
path traversal
command execution
malicious JSON/YAML input causing dangerous behavior
```

## Things that are usually not security issues

These are still useful bugs, but they are usually not security vulnerabilities:

```txt
wrong metric calculation
bad error message
confusing CLI output
unsupported file format
slow performance on large files
```

Open a normal GitHub issue for those.

## Data handling

`rag-contract` may process queries, document IDs, metadata, scores, and text previews if you put them in the input files.

Be careful with CI artifacts. `report.md`, `report.json`, and `junit.xml` may contain query text, document IDs, and failure details. If those are sensitive, treat the reports as sensitive too.

The tool should not print or upload secrets by itself. Still, do not put API keys, tokens, or private customer data in golden files unless your CI environment is set up to protect those artifacts.
