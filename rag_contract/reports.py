from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from rag_contract.contracts import ContractResult
from rag_contract.diff import QueryDiff
from rag_contract.junit import build_junit_xml
from rag_contract.metrics import ScoreResult


def _metric_value(value: float) -> str:
    return f"{value:.3f}"


def _change_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.1%}"


def _status_markup(status: str) -> str:
    return "[red]FAIL[/red]" if status == "FAIL" else "[green]PASS[/green]"


def report_dict(
    result: ContractResult,
    baseline_score: ScoreResult,
    current_score: ScoreResult,
    diffs: list[QueryDiff],
) -> dict[str, object]:
    return {
        "status": result.status,
        "k": result.k,
        "global_metrics": [asdict(row) for row in result.metric_comparisons],
        "failed_contracts": [asdict(failure) for failure in result.query_failures],
        "query_diffs": [asdict(row) for row in diffs],
        "baseline": {
            "aggregate_metrics": baseline_score.aggregate_metrics,
            "tag_metrics": baseline_score.tag_metrics,
        },
        "current": {
            "aggregate_metrics": current_score.aggregate_metrics,
            "tag_metrics": current_score.tag_metrics,
        },
    }


def render_terminal_report(result: ContractResult, console: Console | None = None) -> None:
    console = console or Console()
    console.print("RAG Contract Report")
    console.print()
    console.print(f"Status: {_status_markup(result.status)}")
    console.print()

    table = Table(title="Global metrics")
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("Status")
    for row in result.metric_comparisons:
        table.add_row(
            row.label,
            _metric_value(row.baseline),
            _metric_value(row.current),
            _change_value(row.relative_change),
            _status_markup(row.status),
        )
    console.print(table)

    if result.query_failures:
        console.print()
        console.print("[bold]Failed contracts:[/bold]")
        for failure in result.query_failures:
            console.print(f"- {failure.query_id}")
            console.print(f"  Expected: {', '.join(failure.expected_doc_ids)}")
            console.print(f"  Before: {failure.baseline_rank_label}")
            console.print(f"  After: {failure.current_rank_label}")
            console.print(f"  Contract: {failure.message}")


def markdown_report(
    result: ContractResult,
    baseline_score: ScoreResult,
    current_score: ScoreResult,
    diffs: list[QueryDiff],
) -> str:
    lines: list[str] = []
    lines.append("# RAG Contract Report")
    lines.append("")
    lines.append(f"Status: {result.status}")
    lines.append("")
    lines.append("## Global metrics")
    lines.append("")
    lines.append("| Metric | Baseline | Current | Change | Status |")
    lines.append("|---|---:|---:|---:|---|")
    for row in result.metric_comparisons:
        lines.append(
            f"| {row.label} | {_metric_value(row.baseline)} | {_metric_value(row.current)} | "
            f"{_change_value(row.relative_change)} | {row.status} |"
        )
    lines.append("")

    if result.query_failures:
        lines.append("## Failed query contracts")
        lines.append("")
        for failure in result.query_failures:
            lines.append(f"### {failure.query_id}")
            lines.append("")
            lines.append("Query:")
            lines.append("")
            lines.append(f"> {failure.query}")
            lines.append("")
            lines.append("Expected:")
            lines.append("")
            lines.append("```txt")
            lines.append("\n".join(failure.expected_doc_ids))
            lines.append("```")
            lines.append("")
            lines.append("Baseline:")
            lines.append("")
            lines.append("```txt")
            lines.append(failure.baseline_rank_label)
            lines.append("```")
            lines.append("")
            lines.append("Current:")
            lines.append("")
            lines.append("```txt")
            lines.append(failure.current_rank_label)
            lines.append("```")
            lines.append("")
            lines.append("Failure:")
            lines.append("")
            lines.append("```txt")
            lines.append(failure.message)
            lines.append("```")
            lines.append("")
            lines.append("Likely cause:")
            lines.append("")
            lines.append("```txt")
            lines.append(failure.likely_cause)
            lines.append("```")
            lines.append("")
    else:
        lines.append("## Failed query contracts")
        lines.append("")
        lines.append("None.")
        lines.append("")

    regressions = [row for row in diffs if row.mrr_change < 0]
    if regressions:
        lines.append("## Worst regressions")
        lines.append("")
        for index, row in enumerate(regressions[:10], start=1):
            lines.append(f"{index}. `{row.query_id}`: {row.baseline_rank_label} -> {row.current_rank_label}")
        lines.append("")

    return "\n".join(lines)


def write_reports(
    result: ContractResult,
    baseline_score: ScoreResult,
    current_score: ScoreResult,
    diffs: list[QueryDiff],
    report_md: Path | None,
    report_json: Path | None,
    junit_xml: Path | None,
) -> None:
    if report_md is not None:
        report_md.write_text(markdown_report(result, baseline_score, current_score, diffs), encoding="utf-8")
    if report_json is not None:
        payload = report_dict(result, baseline_score, current_score, diffs)
        report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if junit_xml is not None:
        junit_xml.write_text(build_junit_xml(result), encoding="utf-8")
