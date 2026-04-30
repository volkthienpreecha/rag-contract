from rag_contract.metrics import score_query, score_run
from rag_contract.schemas import GoldenQuery, RunResult, RunRow


def test_metrics_match_known_example() -> None:
    golden = GoldenQuery(
        id="refund_policy",
        query="What is the refund policy?",
        relevant_doc_ids=["doc_refund_policy"],
    )
    row = RunRow(
        query_id="refund_policy",
        results=[
            RunResult(doc_id="doc_pricing"),
            RunResult(doc_id="doc_refund_policy"),
            RunResult(doc_id="doc_terms"),
        ],
    )

    score = score_query(golden, row, k=3)

    assert score.hitrate == 1
    assert score.recall == 1
    assert score.precision == 1 / 3
    assert score.mrr == 1 / 2


def test_score_run_uses_query_weights() -> None:
    golden = [
        GoldenQuery(id="q1", query="one", relevant_doc_ids=["a"], weight=3),
        GoldenQuery(id="q2", query="two", relevant_doc_ids=["b"], weight=1),
    ]
    rows = [
        RunRow(query_id="q1", results=[RunResult(doc_id="a")]),
        RunRow(query_id="q2", results=[RunResult(doc_id="x")]),
    ]

    score = score_run(golden, rows, k=1)

    assert score.aggregate_metrics["hitrate"] == 0.75
    assert score.aggregate_metrics["mrr"] == 0.75
