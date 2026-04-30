from pathlib import Path

from typer.testing import CliRunner

from rag_contract.cli import app


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _clean(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def test_check_pass_exit_zero_and_writes_reports() -> None:
    runner = CliRunner()
    outputs = [
        ROOT / "_test_report_pass.md",
        ROOT / "_test_report_pass.json",
        ROOT / "_test_junit_pass.xml",
    ]
    _clean(outputs)

    try:
        result = runner.invoke(
            app,
            [
                "check",
                "--golden",
                str(EXAMPLES / "golden.jsonl"),
                "--run",
                str(EXAMPLES / "current_pass.jsonl"),
                "--baseline",
                str(EXAMPLES / "baseline.json"),
                "--config",
                str(EXAMPLES / "ragcontract.yml"),
                "--report-md",
                str(outputs[0]),
                "--report-json",
                str(outputs[1]),
                "--junit",
                str(outputs[2]),
            ],
        )

        assert result.exit_code == 0
        assert outputs[0].exists()
        assert outputs[1].exists()
        assert outputs[2].exists()
    finally:
        _clean(outputs)


def test_check_fail_exit_one_and_writes_reports() -> None:
    runner = CliRunner()
    outputs = [
        ROOT / "_test_report_fail.md",
        ROOT / "_test_report_fail.json",
        ROOT / "_test_junit_fail.xml",
    ]
    _clean(outputs)

    try:
        result = runner.invoke(
            app,
            [
                "check",
                "--golden",
                str(EXAMPLES / "golden.jsonl"),
                "--run",
                str(EXAMPLES / "current_fail.jsonl"),
                "--baseline",
                str(EXAMPLES / "baseline.json"),
                "--config",
                str(EXAMPLES / "ragcontract.yml"),
                "--report-md",
                str(outputs[0]),
                "--report-json",
                str(outputs[1]),
                "--junit",
                str(outputs[2]),
            ],
        )

        assert result.exit_code == 1
        assert "Status: FAIL" in result.output
        assert outputs[0].exists()
        assert outputs[1].exists()
        assert outputs[2].exists()
    finally:
        _clean(outputs)
