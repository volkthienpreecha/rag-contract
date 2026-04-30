from pathlib import Path

from rag_contract.contracts import evaluate_contracts, load_config
from rag_contract.metrics import score_run
from rag_contract.schemas import load_baseline, load_golden, load_run, rows_from_baseline


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _evaluate(run_name: str):
    golden = load_golden(EXAMPLES / "golden.jsonl")
    baseline = load_baseline(EXAMPLES / "baseline.json")
    config = load_config(EXAMPLES / "ragcontract.yml")
    baseline_score = score_run(golden, rows_from_baseline(baseline), config.k)
    current_score = score_run(golden, load_run(EXAMPLES / run_name), config.k)
    return evaluate_contracts(golden, baseline_score, current_score, config)


def test_current_pass_satisfies_contracts() -> None:
    result = _evaluate("current_pass.jsonl")

    assert result.status == "PASS"
    assert not result.query_failures


def test_current_fail_breaks_global_and_query_contracts() -> None:
    result = _evaluate("current_fail.jsonl")

    assert result.status == "FAIL"
    assert any(row.status == "FAIL" for row in result.metric_comparisons)
    assert {failure.query_id for failure in result.query_failures} == {
        "refund_policy",
        "sku_b4920",
        "hipaa_baa",
        "public_pricing",
    }
