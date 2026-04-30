from __future__ import annotations

from dataclasses import dataclass

from rag_contract.schemas import GoldenQuery, RunRow, run_map


METRIC_ORDER = ["mrr", "recall", "precision", "hitrate"]
METRIC_LABELS = {
    "mrr": "MRR@{k}",
    "recall": "Recall@{k}",
    "precision": "Precision@{k}",
    "hitrate": "HitRate@{k}",
}
CONFIG_METRIC_KEYS = {
    "mrr_at_k": "mrr",
    "recall_at_k": "recall",
    "precision_at_k": "precision",
    "hitrate_at_k": "hitrate",
}


@dataclass(frozen=True)
class QueryScore:
    query_id: str
    query: str
    weight: float
    tags: list[str]
    relevant_doc_ids: list[str]
    retrieved_doc_ids: list[str]
    ranks: dict[str, int]
    mrr: float
    recall: float
    precision: float
    hitrate: float

    @property
    def metrics(self) -> dict[str, float]:
        return {
            "mrr": self.mrr,
            "recall": self.recall,
            "precision": self.precision,
            "hitrate": self.hitrate,
        }


@dataclass(frozen=True)
class ScoreResult:
    k: int
    per_query: dict[str, QueryScore]
    aggregate_metrics: dict[str, float]
    tag_metrics: dict[str, dict[str, float]]


def _rank_by_doc(doc_ids: list[str]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for index, doc_id in enumerate(doc_ids, start=1):
        ranks.setdefault(doc_id, index)
    return ranks


def score_query(golden: GoldenQuery, row: RunRow, k: int) -> QueryScore:
    if k < 1:
        raise ValueError("k must be at least 1")

    retrieved_doc_ids = [result.doc_id for result in row.results]
    top_doc_ids = retrieved_doc_ids[:k]
    relevant = set(golden.relevant_doc_ids)
    top_relevant = relevant.intersection(top_doc_ids)
    ranks = _rank_by_doc(retrieved_doc_ids)
    relevant_ranks = [rank for doc_id, rank in ranks.items() if doc_id in relevant and rank <= k]
    first_rank = min(relevant_ranks) if relevant_ranks else None

    return QueryScore(
        query_id=golden.id,
        query=golden.query,
        weight=golden.weight,
        tags=list(golden.tags),
        relevant_doc_ids=list(golden.relevant_doc_ids),
        retrieved_doc_ids=retrieved_doc_ids,
        ranks={doc_id: rank for doc_id, rank in ranks.items() if doc_id in relevant},
        mrr=(1.0 / first_rank) if first_rank else 0.0,
        recall=len(top_relevant) / len(relevant),
        precision=len(top_relevant) / k,
        hitrate=1.0 if top_relevant else 0.0,
    )


def _weighted_average(scores: list[QueryScore]) -> dict[str, float]:
    total_weight = sum(score.weight for score in scores)
    if total_weight <= 0:
        return {metric: 0.0 for metric in METRIC_ORDER}

    metrics: dict[str, float] = {}
    for metric in METRIC_ORDER:
        metrics[metric] = sum(score.metrics[metric] * score.weight for score in scores) / total_weight
    return metrics


def _tag_metrics(scores: list[QueryScore]) -> dict[str, dict[str, float]]:
    by_tag: dict[str, list[QueryScore]] = {}
    for score in scores:
        for tag in score.tags:
            by_tag.setdefault(tag, []).append(score)
    return {tag: _weighted_average(tag_scores) for tag, tag_scores in sorted(by_tag.items())}


def score_run(golden: list[GoldenQuery], run_rows: list[RunRow], k: int) -> ScoreResult:
    rows_by_id = run_map(run_rows)
    query_scores = [score_query(query, rows_by_id[query.id], k) for query in golden]
    return ScoreResult(
        k=k,
        per_query={score.query_id: score for score in query_scores},
        aggregate_metrics=_weighted_average(query_scores),
        tag_metrics=_tag_metrics(query_scores),
    )
