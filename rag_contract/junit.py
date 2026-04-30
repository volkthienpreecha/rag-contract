from __future__ import annotations

from collections import defaultdict
from xml.etree import ElementTree as ET

from rag_contract.contracts import ContractResult


def build_junit_xml(result: ContractResult) -> str:
    failures_by_query: dict[str, list[str]] = defaultdict(list)
    for failure in result.query_failures:
        failures_by_query[failure.query_id].append(f"{failure.rule}: {failure.message}")

    testcases: list[ET.Element] = []
    for row in result.metric_comparisons:
        case = ET.Element("testcase", {"classname": "rag_contract.global", "name": row.label})
        if row.status == "FAIL":
            failure = ET.SubElement(case, "failure", {"message": "; ".join(row.reasons)})
            failure.text = "\n".join(row.reasons)
        testcases.append(case)

    for query_id in result.query_ids:
        case = ET.Element("testcase", {"classname": "rag_contract.query", "name": query_id})
        if failures_by_query[query_id]:
            failure = ET.SubElement(case, "failure", {"message": "; ".join(failures_by_query[query_id])})
            failure.text = "\n".join(failures_by_query[query_id])
        testcases.append(case)

    suite = ET.Element(
        "testsuite",
        {
            "name": "rag-contract",
            "tests": str(len(testcases)),
            "failures": str(sum(1 for case in testcases if case.find("failure") is not None)),
        },
    )
    for case in testcases:
        suite.append(case)

    ET.indent(suite, space="  ")
    return ET.tostring(suite, encoding="unicode") + "\n"
