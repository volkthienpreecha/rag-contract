from __future__ import annotations

from dataclasses import dataclass

from rag_contract.contracts import rank_label
from rag_contract.metrics import ScoreResult
from rag_contract.schemas import GoldenQuery


@dataclass(frozen=True)
class QueryDiff:
    query_id: str
    query: str
    expected_doc_ids: list[str]
    baseline_rank: int | None
    current_rank: int | None
    baseline_rank_label: str
    current_rank_label: str
    baseline_mrr: float
    current_mrr: float
    mrr_change: float
    rank_delta: int | None
    violated_must_rank_at_most: bool


def _best_rank(ranks: dict[str, int], expected: list[str]) -> int | None:
    found = [rank for doc_id, rank in ranks.items() if doc_id in expected]
    return min(found) if found else None


def build_query_diffs(
    golden: list[GoldenQuery],
    baseline_score: ScoreResult,
    current_score: ScoreResult,
    k: int,
) -> list[QueryDiff]:
    rows: list[QueryDiff] = []
    for query in golden:
        baseline = baseline_score.per_query[query.id]
        current = current_score.per_query[query.id]
        expected = list(query.relevant_doc_ids)
        baseline_rank = _best_rank(baseline.ranks, expected)
        current_rank = _best_rank(current.ranks, expected)
        rank_delta = None
        if baseline_rank is not None and current_rank is not None:
            rank_delta = current_rank - baseline_rank

        rows.append(
            QueryDiff(
                query_id=query.id,
                query=query.query,
                expected_doc_ids=expected,
                baseline_rank=baseline_rank,
                current_rank=current_rank,
                baseline_rank_label=rank_label(baseline_rank, k),
                current_rank_label=rank_label(current_rank, k),
                baseline_mrr=baseline.mrr,
                current_mrr=current.mrr,
                mrr_change=current.mrr - baseline.mrr,
                rank_delta=rank_delta,
                violated_must_rank_at_most=(
                    query.must_rank_at_most is not None
                    and (current_rank is None or current_rank > query.must_rank_at_most)
                ),
            )
        )

    return sorted(
        rows,
        key=lambda row: (
            row.mrr_change,
            10_000 if row.current_rank is None else row.current_rank,
        ),
    )
