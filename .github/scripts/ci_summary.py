"""Generate GitHub Actions job summary from pytest junit XML and coverage JSON."""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def test_summary(junit_path: Path) -> str:
    tree = ET.parse(junit_path)
    root = tree.getroot()
    # pytest wraps results in <testsuites><testsuite .../>; attributes live on <testsuite>
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    tests = suite.get("tests", "?")
    failures = suite.get("failures", "0")
    errors = suite.get("errors", "0")
    skipped = suite.get("skipped", "0")
    time = f"{float(suite.get('time', 0)):.1f}s"

    lines = [
        "| Metric | Count |",
        "|--------|------:|",
        f"| Tests | {tests} |",
        f"| Failures | {failures} |",
        f"| Errors | {errors} |",
        f"| Skipped | {skipped} |",
        f"| Time | {time} |",
    ]
    return "\n".join(lines)


def coverage_summary(cov_path: Path) -> str:
    data = json.loads(cov_path.read_text())
    totals = data["totals"]
    pct = totals["percent_covered_display"]

    lines = [
        "### Coverage",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| **Coverage** | **{pct}%** |",
        f"| Statements | {totals['num_statements']} |",
        f"| Covered | {totals['covered_lines']} |",
        f"| Missing | {totals['missing_lines']} |",
        "",
        "<details><summary>Per-file coverage</summary>",
        "",
        "| File | Stmts | Cover |",
        "|------|------:|------:|",
    ]

    for path, info in sorted(data["files"].items()):
        s = info["summary"]
        lines.append(f"| `{path}` | {s['num_statements']} | {s['percent_covered_display']}% |")

    lines.append("")
    lines.append("</details>")
    return "\n".join(lines)


def main() -> None:
    python_version = os.environ.get("PYTHON_VERSION", "?")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        print("GITHUB_STEP_SUMMARY not set, printing to stdout", file=sys.stderr)
        summary_file = "/dev/stdout"

    parts: list[str] = [f"## Test Results \u2014 Python {python_version}", ""]

    junit_path = Path("junit.xml")
    if junit_path.exists():
        parts.append(test_summary(junit_path))
        parts.append("")

    cov_path = Path("coverage.json")
    if cov_path.exists():
        parts.append(coverage_summary(cov_path))

    output = "\n".join(parts) + "\n"
    Path(summary_file).open("a").write(output)
    print(f"Summary written ({len(output)} bytes)")


if __name__ == "__main__":
    main()
