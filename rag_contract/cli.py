from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rag_contract.contracts import ContractConfig, evaluate_contracts, load_config
from rag_contract.diff import build_query_diffs
from rag_contract.metrics import METRIC_LABELS, METRIC_ORDER, ScoreResult, score_run
from rag_contract.reports import render_terminal_report, write_reports
from rag_contract.schemas import (
    BaselineFile,
    BaselineQuery,
    GoldenQuery,
    RagContractError,
    RunRow,
    load_baseline,
    load_golden,
    load_run,
    rows_from_baseline,
    run_map,
    validate_run_against_golden,
)


app = typer.Typer(
    no_args_is_help=True,
    help="Fail CI when your RAG retriever gets worse.",
)
console = Console()


def _die(message: str, code: int = 2) -> None:
    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code)


def _load_config_or_default(config_path: Path | None) -> ContractConfig:
    if config_path is None:
        default_path = Path("ragcontract.yml")
        if default_path.exists():
            config_path = default_path
    return load_config(config_path)


def _load_inputs(golden_path: Path, run_path: Path) -> tuple[list[GoldenQuery], list[RunRow]]:
    golden = load_golden(golden_path)
    run_rows = load_run(run_path)
    validation = validate_run_against_golden(golden, run_rows)
    if validation.missing_query_ids:
        missing = ", ".join(validation.missing_query_ids)
        raise RagContractError(f"run is missing query ids from golden: {missing}")
    return golden, run_rows


def _print_metric_table(score: ScoreResult) -> None:
    table = Table()
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for metric in METRIC_ORDER:
        table.add_row(METRIC_LABELS[metric].format(k=score.k), f"{score.aggregate_metrics[metric]:.3f}")
    console.print(table)


def _baseline_from_score(golden: list[GoldenQuery], run_rows: list[RunRow], score: ScoreResult) -> BaselineFile:
    rows_by_id = run_map(run_rows)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    per_query: list[BaselineQuery] = []
    for query in golden:
        query_score = score.per_query[query.id]
        per_query.append(
            BaselineQuery(
                id=query.id,
                query=query.query,
                relevant_doc_ids=list(query.relevant_doc_ids),
                retrieved_doc_ids=[result.doc_id for result in rows_by_id[query.id].results],
                metrics=query_score.metrics,
                ranks=query_score.ranks,
                tags=list(query.tags),
                weight=query.weight,
                must_rank_at_most=query.must_rank_at_most,
                must_include_any=query.must_include_any,
                forbidden_doc_ids=list(query.forbidden_doc_ids),
            )
        )

    return BaselineFile(
        created_at=created_at,
        k=score.k,
        aggregate_metrics=score.aggregate_metrics,
        tag_metrics=score.tag_metrics,
        per_query=per_query,
    )


@app.command()
def validate(
    golden: Path = typer.Option(..., "--golden", help="Path to golden JSONL file."),
    run: Path = typer.Option(..., "--run", help="Path to retriever output JSONL file."),
) -> None:
    """Validate golden and run file contracts."""
    try:
        golden_rows = load_golden(golden)
        run_rows = load_run(run)
        summary = validate_run_against_golden(golden_rows, run_rows)
    except RagContractError as exc:
        _die(str(exc))

    console.print(f"[green]PASS[/green] {golden} valid: {summary.golden_count} queries")
    console.print(f"[green]PASS[/green] {run} valid: {summary.run_count} result rows")
    if summary.extra_query_ids:
        console.print(f"[yellow]WARN[/yellow] extra run query ids ignored: {', '.join(summary.extra_query_ids)}")
    if summary.missing_query_ids:
        console.print(f"[red]FAIL[/red] missing query ids: {', '.join(summary.missing_query_ids)}")
        raise typer.Exit(2)
    console.print("[green]PASS[/green] all golden query IDs matched")


@app.command()
def score(
    golden: Path = typer.Option(..., "--golden", help="Path to golden JSONL file."),
    run: Path = typer.Option(..., "--run", help="Path to retriever output JSONL file."),
    k: int = typer.Option(5, "--k", min=1, help="Evaluate top-k retrieval results."),
) -> None:
    """Score one retrieval run without a baseline."""
    try:
        golden_rows, run_rows = _load_inputs(golden, run)
        result = score_run(golden_rows, run_rows, k)
    except (RagContractError, ValueError) as exc:
        _die(str(exc))
    _print_metric_table(result)


@app.command()
def baseline(
    golden: Path = typer.Option(..., "--golden", help="Path to golden JSONL file."),
    run: Path = typer.Option(..., "--run", help="Path to retriever output JSONL file."),
    out: Path = typer.Option(Path("baseline.json"), "--out", help="Baseline JSON output path."),
    k: int = typer.Option(5, "--k", min=1, help="Evaluate top-k retrieval results."),
) -> None:
    """Create a baseline JSON file from a known-good retrieval run."""
    try:
        golden_rows, run_rows = _load_inputs(golden, run)
        score_result = score_run(golden_rows, run_rows, k)
        baseline_file = _baseline_from_score(golden_rows, run_rows, score_result)
    except (RagContractError, ValueError) as exc:
        _die(str(exc))

    out.write_text(json.dumps(baseline_file.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    console.print(f"[green]PASS[/green] wrote baseline: {out}")


@app.command()
def check(
    golden: Path = typer.Option(..., "--golden", help="Path to golden JSONL file."),
    run: Path = typer.Option(..., "--run", help="Path to current retriever output JSONL file."),
    baseline_path: Path = typer.Option(..., "--baseline", help="Path to baseline JSON file."),
    config: Path | None = typer.Option(None, "--config", help="Path to ragcontract.yml."),
    report_md: Path | None = typer.Option(Path("report.md"), "--report-md", help="Markdown report output path."),
    report_json: Path | None = typer.Option(Path("report.json"), "--report-json", help="JSON report output path."),
    junit_xml: Path | None = typer.Option(Path("junit.xml"), "--junit", help="JUnit XML output path."),
) -> None:
    """Compare current retrieval against a baseline and enforce contracts."""
    try:
        contract_config = _load_config_or_default(config)
        golden_rows, current_rows = _load_inputs(golden, run)
        baseline_file = load_baseline(baseline_path)
        baseline_rows = rows_from_baseline(baseline_file)
        baseline_score = score_run(golden_rows, baseline_rows, contract_config.k)
        current_score = score_run(golden_rows, current_rows, contract_config.k)
        result = evaluate_contracts(golden_rows, baseline_score, current_score, contract_config)
        diffs = build_query_diffs(golden_rows, baseline_score, current_score, contract_config.k)
        render_terminal_report(result, console)
        write_reports(result, baseline_score, current_score, diffs, report_md, report_json, junit_xml)
    except (RagContractError, ValueError) as exc:
        _die(str(exc))

    raise typer.Exit(1 if result.failed else 0)


@app.command("diff")
def diff_command(
    golden: Path = typer.Option(..., "--golden", help="Path to golden JSONL file."),
    run: Path = typer.Option(..., "--run", help="Path to current retriever output JSONL file."),
    baseline_path: Path = typer.Option(..., "--baseline", help="Path to baseline JSON file."),
    k: int | None = typer.Option(None, "--k", min=1, help="Evaluate top-k retrieval results."),
) -> None:
    """Show query-level rank movement from baseline to current run."""
    try:
        golden_rows, current_rows = _load_inputs(golden, run)
        baseline_file = load_baseline(baseline_path)
        selected_k = k or baseline_file.k
        baseline_score = score_run(golden_rows, rows_from_baseline(baseline_file), selected_k)
        current_score = score_run(golden_rows, current_rows, selected_k)
        diffs = build_query_diffs(golden_rows, baseline_score, current_score, selected_k)
    except (RagContractError, ValueError) as exc:
        _die(str(exc))

    console.print("Worst regressions:")
    console.print()
    regressions = [row for row in diffs if row.mrr_change < 0 or row.violated_must_rank_at_most]
    if not regressions:
        console.print("None.")
        return

    for index, row in enumerate(regressions[:10], start=1):
        console.print(f"{index}. {row.query_id}")
        console.print(f"   expected {', '.join(row.expected_doc_ids)}")
        console.print(f"   {row.baseline_rank_label} -> {row.current_rank_label}")
        console.print(f"   MRR contribution {row.baseline_mrr:.2f} -> {row.current_mrr:.2f}")
        if row.violated_must_rank_at_most:
            console.print("   violated must_rank_at_most")
        console.print()


if __name__ == "__main__":
    app()
