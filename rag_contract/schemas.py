from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class RagContractError(ValueError):
    """Raised when an input contract file cannot be used."""


def normalize_doc_id(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("doc_id values must not be empty")
    return text


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


class GoldenQuery(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    query: str
    relevant_doc_ids: list[str] = Field(min_length=1)
    must_rank_at_most: int | None = None
    must_include_any: bool = False
    forbidden_doc_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "query")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("relevant_doc_ids", "forbidden_doc_ids", mode="before")
    @classmethod
    def _list_required(cls, value: Any) -> Any:
        if isinstance(value, str):
            raise ValueError("must be a list of strings, not a string")
        return value

    @field_validator("relevant_doc_ids", "forbidden_doc_ids")
    @classmethod
    def _normalize_doc_ids(cls, values: list[Any]) -> list[str]:
        return _dedupe([normalize_doc_id(value) for value in values])

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_list_required(cls, value: Any) -> Any:
        if isinstance(value, str):
            raise ValueError("tags must be a list of strings, not a string")
        return value

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, values: list[Any]) -> list[str]:
        tags = [str(value).strip() for value in values if str(value).strip()]
        return _dedupe(tags)

    @field_validator("must_rank_at_most")
    @classmethod
    def _positive_rank(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("must_rank_at_most must be at least 1")
        return value

    @field_validator("weight")
    @classmethod
    def _positive_weight(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("weight must be greater than 0")
        return value


class RunResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    doc_id: str
    chunk_id: str | None = None
    score: float | None = None
    rank: int | None = None
    text_preview: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("doc_id")
    @classmethod
    def _normalize_doc_id(cls, value: Any) -> str:
        return normalize_doc_id(value)

    @field_validator("rank")
    @classmethod
    def _positive_rank(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("rank must be at least 1")
        return value


class RunRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    query_id: str
    results: list[RunResult]
    latency_ms: float | None = None
    retriever_version: str | None = None
    embedding_model: str | None = None
    index_version: str | None = None
    chunking_version: str | None = None

    @field_validator("query_id")
    @classmethod
    def _non_empty_query_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query_id must not be empty")
        return value


class ValidationSummary(BaseModel):
    golden_count: int
    run_count: int
    missing_query_ids: list[str] = Field(default_factory=list)
    extra_query_ids: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_query_ids


class BaselineQuery(BaseModel):
    id: str
    query: str
    relevant_doc_ids: list[str]
    retrieved_doc_ids: list[str]
    metrics: dict[str, float]
    ranks: dict[str, int]
    tags: list[str] = Field(default_factory=list)
    weight: float = 1.0
    must_rank_at_most: int | None = None
    must_include_any: bool = False
    forbidden_doc_ids: list[str] = Field(default_factory=list)


class BaselineFile(BaseModel):
    version: str = "1"
    created_at: str
    k: int
    aggregate_metrics: dict[str, float]
    tag_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)
    per_query: list[BaselineQuery]


T = TypeVar("T", bound=BaseModel)


def _load_jsonl(path: Path, model_type: type[T], label: str) -> list[T]:
    if not path.exists():
        raise RagContractError(f"{label} file not found: {path}")

    rows: list[T] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            rows.append(model_type.model_validate(data))
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
        except ValidationError as exc:
            errors.append(f"line {line_number}: {exc.errors()[0]['msg']}")

    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise RagContractError(f"{label} validation failed:\n{joined}")

    if not rows:
        raise RagContractError(f"{label} file has no rows: {path}")

    return rows


def _duplicate_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def load_golden(path: Path) -> list[GoldenQuery]:
    queries = _load_jsonl(path, GoldenQuery, "golden")
    duplicates = _duplicate_ids([query.id for query in queries])
    if duplicates:
        raise RagContractError(f"golden contains duplicate query ids: {', '.join(duplicates)}")
    return queries


def load_run(path: Path) -> list[RunRow]:
    rows = _load_jsonl(path, RunRow, "run")
    duplicates = _duplicate_ids([row.query_id for row in rows])
    if duplicates:
        raise RagContractError(f"run contains duplicate query ids: {', '.join(duplicates)}")
    return rows


def load_baseline(path: Path) -> BaselineFile:
    if not path.exists():
        raise RagContractError(f"baseline file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return BaselineFile.model_validate(data)
    except json.JSONDecodeError as exc:
        raise RagContractError(f"baseline is not valid JSON: {exc.msg}") from exc
    except ValidationError as exc:
        raise RagContractError(f"baseline validation failed: {exc.errors()[0]['msg']}") from exc


def run_map(rows: list[RunRow]) -> dict[str, RunRow]:
    return {row.query_id: row for row in rows}


def validate_run_against_golden(golden: list[GoldenQuery], run_rows: list[RunRow]) -> ValidationSummary:
    golden_ids = [query.id for query in golden]
    run_ids = [row.query_id for row in run_rows]
    run_id_set = set(run_ids)
    golden_id_set = set(golden_ids)
    return ValidationSummary(
        golden_count=len(golden),
        run_count=len(run_rows),
        missing_query_ids=[query_id for query_id in golden_ids if query_id not in run_id_set],
        extra_query_ids=[query_id for query_id in run_ids if query_id not in golden_id_set],
    )


def rows_from_baseline(baseline: BaselineFile) -> list[RunRow]:
    rows: list[RunRow] = []
    for query in baseline.per_query:
        rows.append(
            RunRow(
                query_id=query.id,
                results=[RunResult(doc_id=doc_id) for doc_id in query.retrieved_doc_ids],
            )
        )
    return rows
