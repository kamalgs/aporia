"""Report generator: aggregates EvalRecord results into a markdown summary."""

from __future__ import annotations

from datetime import datetime
from typing import List

from eval.runner import EvalRecord


def markdown_report(records: List[EvalRecord]) -> str:
    total = len(records)
    passed = sum(1 for r in records if not r.failure_reason)
    lines = [
        "# Socratic Tutor Eval Report",
        f"\nGenerated: {datetime.utcnow().isoformat()}Z",
        f"\n## Summary\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Scenarios | {total} |",
        f"| Passed | {passed} / {total} |",
        f"| Failed | {total - passed} / {total} |",
        f"\n## Per-Scenario Results\n",
        "| Scenario | Student Type | Turns | Phase | Quality | Scaffold | Diagnose | Safe | Judge Pass | Result |",
        "|----------|--------------|-------|-------|---------|----------|----------|------|------------|--------|",
    ]

    for r in records:
        ok = "✅ PASS" if not r.failure_reason else "❌ FAIL"
        sq = r.socratic_quality or "—"
        sc = "Y" if r.scaffolding_adherence else ("N" if r.scaffolding_adherence is not None else "—")
        di = "Y" if r.diagnoses_specifically else ("N" if r.diagnoses_specifically is not None else "—")
        nr = "Y" if r.never_reveals_answer else ("N" if r.never_reveals_answer is not None else "—")
        jp = "Y" if r.overall_pass else ("N" if r.overall_pass is not None else "—")
        lines.append(
            f"| {r.name} | {r.student_type} | {r.turn_count} | {r.final_phase} | {sq}/5 | {sc} | {di} | {nr} | {jp} | {ok} |"
        )

    lines.append("\n## Transcripts\n")
    for r in records:
        status = "PASS" if not r.failure_reason else "FAIL"
        lines.append(f"<details>\n<summary>{r.name} — {status}</summary>\n")
        if r.socratic_quality is not None:
            lines.append(f"\n**Judge:** quality={r.socratic_quality}/5, scaffold={r.scaffolding_adherence}, diagnose={r.diagnoses_specifically}, safe={r.never_reveals_answer}, overall={r.overall_pass}\n")
            lines.append(f"**Rationale:** {r.rationale or 'N/A'}\n")
        if r.failure_reason:
            lines.append(f"**Failure:** {r.failure_reason}\n")
        lines.append(f"\n```\n{r.transcript}\n```\n")
        lines.append("</details>\n")

    return "\n".join(lines)
