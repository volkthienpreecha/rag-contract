from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from rag_contract.metrics import CONFIG_METRIC_KEYS, METRIC_LABELS, METRIC_ORDER, ScoreResult
from rag_contract.schemas import GoldenQuery, RagContractError


class FailOnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mrr_drop_gt: float | None = None
    recall_drop_gt: float | None = None
    precision_drop_gt: float | None = None
    hitrate_drop_gt: float | None = None

    @field_validator("*")
    @classmethod
    def _non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("drop thresholds must be non-negative")
        return value


class MinimumsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mrr_at_k: float | None = None
    recall_at_k: float | None = None
    precision_at_k: float | None = None
    hitrate_at_k: float | None = None

    @field_validator("*")
    @classmethod
    def _between_zero_and_one(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("minimum thresholds must be between 0 and 1")
        return value


class PerQueryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enforce_must_rank_at_most: bool = True
    enforce_must_include: bool = True
    enforce_forbidden_docs: bool = True


class ContractConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    k: int = 5
    fail_on: FailOnConfig = Field(default_factory=FailOnConfig)
    minimums: MinimumsConfig = Field(default_factory=MinimumsConfig)
    per_query: PerQueryConfig = Field(default_factory=PerQueryConfig)

    @field_validator("k")
    @classmethod
    def _positive_k(cls, value: int) -> int:
        if value < 1:
            raise ValueError("k must be at least 1")
        return value


@dataclass(frozen=True)
class MetricComparison:
    metric: str
    label: str
    baseline: float
    current: float
    absolute_change: float
    relative_change: float | None
    status: str
    reasons: list[str]


@dataclass(frozen=True)
class QueryContractFailure:
    query_id: str
    query: str
    expected_doc_ids: list[str]
    baseline_rank: int | None
    current_rank: int | None
    baseline_rank_label: str
    current_rank_label: str
    rule: str
    message: str
    likely_cause: str


@dataclass(frozen=True)
class ContractResult:
    status: str
    k: int
    query_ids: list[str]
    metric_comparisons: list[MetricComparison]
    query_failures: list[QueryContractFailure]

    @property
    def failed(self) -> bool:
        return self.status == "FAIL"


def load_config(path: Path | None) -> ContractConfig:
    if path is None:
        return ContractConfig()
    if not path.exists():
        raise RagContractError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return ContractConfig.model_validate(data)
    except yaml.YAMLError as exc:
        raise RagContractError(f"config is not valid YAML: {exc}") from exc
    except ValidationError as exc:
        raise RagContractError(f"config validation failed: {exc.errors()[0]['msg']}") from exc


def rank_label(rank: int | None, k: int) -> str:
    if rank is None:
        return f"missing from top {k}"
    return f"rank {rank}"


def _relative_change(baseline: float, current: float) -> float | None:
    if baseline == 0:
        if current == 0:
            return 0.0
        return None
    return (current - baseline) / abs(baseline)


def _drop_ratio(baseline: float, current: float) -> float:
    if baseline == 0:
        return 0.0 if current >= baseline else float("inf")
    return max(0.0, (baseline - current) / abs(baseline))


def evaluate_global_gates(
    baseline_metrics: dict[str, float],
    current_metrics: dict[str, float],
    config: ContractConfig,
) -> list[MetricComparison]:
    rows: list[MetricComparison] = []
    fail_on = config.fail_on.model_dump()
    minimums = config.minimums.model_dump()

    for metric in METRIC_ORDER:
        baseline = baseline_metrics.get(metric, 0.0)
        current = current_metrics.get(metric, 0.0)
        reasons: list[str] = []

        minimum_key = next(key for key, value in CONFIG_METRIC_KEYS.items() if value == metric)
        minimum = minimums.get(minimum_key)
        if minimum is not None and current < minimum:
            reasons.append(f"{minimum_key} {current:.3f} is below minimum {minimum:.3f}")

        drop_key = f"{metric}_drop_gt"
        drop_threshold = fail_on.get(drop_key)
        if drop_threshold is not None and _drop_ratio(baseline, current) > drop_threshold:
            reasons.append(f"{drop_key} exceeded: drop {_drop_ratio(baseline, current):.1%} > {drop_threshold:.1%}")

        rows.append(
            MetricComparison(
                metric=metric,
                label=METRIC_LABELS[metric].format(k=config.k),
                baseline=baseline,
                current=current,
                absolute_change=current - baseline,
                relative_change=_relative_change(baseline, current),
                status="FAIL" if reasons else "PASS",
                reasons=reasons,
            )
        )

    return rows


def _best_rank(ranks: dict[str, int], expected: list[str]) -> int | None:
    found = [rank for doc_id, rank in ranks.items() if doc_id in expected]
    return min(found) if found else None


def _missing_expected(query: GoldenQuery, current_top_doc_ids: list[str]) -> list[str]:
    top_doc_set = set(current_top_doc_ids)
    expected = list(query.relevant_doc_ids)
    if query.must_include_any:
        return [] if any(doc_id in top_doc_set for doc_id in expected) else expected
    return [doc_id for doc_id in expected if doc_id not in top_doc_set]


def evaluate_query_contracts(
    golden: list[GoldenQuery],
    baseline_score: ScoreResult,
    current_score: ScoreResult,
    config: ContractConfig,
) -> list[QueryContractFailure]:
    failures: list[QueryContractFailure] = []
    for query in golden:
        current = current_score.per_query[query.id]
        baseline = baseline_score.per_query[query.id]
        top_doc_ids = current.retrieved_doc_ids[: config.k]
        expected = list(query.relevant_doc_ids)
        baseline_rank = _best_rank(baseline.ranks, expected)
        current_rank = _best_rank(current.ranks, expected)

        if config.per_query.enforce_forbidden_docs and query.forbidden_doc_ids:
            forbidden_in_top_k = [doc_id for doc_id in query.forbidden_doc_ids if doc_id in set(top_doc_ids)]
            if forbidden_in_top_k:
                failures.append(
                    QueryContractFailure(
                        query_id=query.id,
                        query=query.query,
                        expected_doc_ids=expected,
                        baseline_rank=baseline_rank,
                        current_rank=current_rank,
                        baseline_rank_label=rank_label(baseline_rank, config.k),
                        current_rank_label=rank_label(current_rank, config.k),
                        rule="forbidden_doc_ids",
                        message=f"Forbidden docs appeared in top {config.k}: {', '.join(forbidden_in_top_k)}.",
                        likely_cause="A metadata filter, access-control filter, or corpus boundary may have regressed.",
                    )
                )
                continue

        if (
            config.per_query.enforce_must_rank_at_most
            and query.must_rank_at_most is not None
            and current_rank is not None
            and current_rank > query.must_rank_at_most
        ):
            failures.append(
                QueryContractFailure(
                    query_id=query.id,
                    query=query.query,
                    expected_doc_ids=expected,
                    baseline_rank=baseline_rank,
                    current_rank=current_rank,
                    baseline_rank_label=rank_label(baseline_rank, config.k),
                    current_rank_label=rank_label(current_rank, config.k),
                    rule="must_rank_at_most",
                    message=f"Expected doc must appear at rank {query.must_rank_at_most} or better.",
                    likely_cause="The retriever found a relevant document, but rank quality dropped below the contract.",
                )
            )
            continue

        if config.per_query.enforce_must_include:
            missing = _missing_expected(query, top_doc_ids)
            if missing:
                rule = "must_include_any" if query.must_include_any else "must_include_expected"
                failures.append(
                    QueryContractFailure(
                        query_id=query.id,
                        query=query.query,
                        expected_doc_ids=expected,
                        baseline_rank=baseline_rank,
                        current_rank=current_rank,
                        baseline_rank_label=rank_label(baseline_rank, config.k),
                        current_rank_label=rank_label(current_rank, config.k),
                        rule=rule,
                        message=f"Expected docs missing from top {config.k}: {', '.join(missing)}.",
                        likely_cause="Relevant document disappeared, doc ID changed, or chunking/indexing changed.",
                    )
                )
                continue

        if (
            config.per_query.enforce_must_rank_at_most
            and query.must_rank_at_most is not None
            and current_rank is None
        ):
            failures.append(
                QueryContractFailure(
                    query_id=query.id,
                    query=query.query,
                    expected_doc_ids=expected,
                    baseline_rank=baseline_rank,
                    current_rank=current_rank,
                    baseline_rank_label=rank_label(baseline_rank, config.k),
                    current_rank_label=rank_label(current_rank, config.k),
                    rule="must_rank_at_most",
                    message=f"Expected doc must appear at rank {query.must_rank_at_most} or better.",
                    likely_cause="Relevant document disappeared, doc ID changed, or chunking/indexing changed.",
                )
            )

    return failures


def evaluate_contracts(
    golden: list[GoldenQuery],
    baseline_score: ScoreResult,
    current_score: ScoreResult,
    config: ContractConfig,
) -> ContractResult:
    metric_comparisons = evaluate_global_gates(
        baseline_score.aggregate_metrics,
        current_score.aggregate_metrics,
        config,
    )
    query_failures = evaluate_query_contracts(golden, baseline_score, current_score, config)
    failed = any(row.status == "FAIL" for row in metric_comparisons) or bool(query_failures)
    return ContractResult(
        status="FAIL" if failed else "PASS",
        k=config.k,
        query_ids=[query.id for query in golden],
        metric_comparisons=metric_comparisons,
        query_failures=query_failures,
    )
