from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a sample rag-contract retrieval run.")
    parser.add_argument("--out", required=True, help="Output JSONL path.")
    parser.add_argument(
        "--fixture",
        choices=["pass", "fail", "baseline"],
        default="pass",
        help="Example fixture to export.",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    source = {
        "pass": here / "current_pass.jsonl",
        "fail": here / "current_fail.jsonl",
        "baseline": here / "baseline_run.jsonl",
    }[args.fixture]
    Path(args.out).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    main()
