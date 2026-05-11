"""CLI entry point: python -m eval <run|judge|report>"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from eval.runner import run_scenario, EvalRecord, _judge_transcript, _apply_criteria
from eval.report import markdown_report
from app.agent import LlmAgent


def _load_criteria(scenario_path: Path) -> dict:
    with open(scenario_path) as f:
        return json.load(f)["criteria"]


async def cmd_run() -> int:
    scenario_dir = Path(__file__).parent / "scenarios"
    scenarios = sorted(scenario_dir.glob("*.json"))
    if not scenarios:
        print("No scenarios found in eval/scenarios/")
        return 1

    out_dir = Path("eval-results")
    out_dir.mkdir(exist_ok=True)

    tutor = LlmAgent()
    for path in scenarios:
        slug = path.stem
        out_path = out_dir / f"{slug}.json"
        print(f"  → {slug}  ", end="", flush=True)
        try:
            record = await run_scenario(tutor, path, per_call_timeout=45)
            out_path.write_text(record.model_dump_json(indent=2))
            print(f"saved  turns={record.turn_count} phase={record.final_phase}")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {str(e)[:100]}")
            return 1

    print(f"\nTranscripts saved to {out_dir}/")
    return 0


async def cmd_judge() -> int:
    out_dir = Path("eval-results")
    if not out_dir.exists():
        print("No eval-results/ found. Run `python -m eval run` first.")
        return 1

    paths = sorted(out_dir.glob("*.json"))
    if not paths:
        print("No result JSONs in eval-results/")
        return 1

    scenario_dir = Path(__file__).parent / "scenarios"

    for path in paths:
        slug = path.stem
        record = EvalRecord.model_validate_json(path.read_text())
        if record.socratic_quality is not None:
            print(f"  → {slug}  already judged, skipping")
            continue

        criteria = _load_criteria(scenario_dir / f"{slug}.json")
        print(f"  → {slug}  judging transcript ({len(record.transcript)} chars) ...", end=" ", flush=True)
        try:
            verdict = await _judge_transcript(record.transcript, timeout=45)
            record.socratic_quality = verdict.socratic_quality
            record.scaffolding_adherence = verdict.scaffolding_adherence
            record.never_reveals_answer = verdict.never_reveals_answer
            record.diagnoses_specifically = verdict.diagnoses_specifically
            record.overall_pass = verdict.overall_pass
            record.rationale = verdict.rationale
            record.failure_reason = _apply_criteria(record, criteria)
            path.write_text(record.model_dump_json(indent=2))
            print(f" judged  quality={verdict.socratic_quality}/5 overall={verdict.overall_pass}")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {str(e)[:100]}")
            return 1

    print("\nJudging complete.")
    return 0


async def cmd_report() -> int:
    out_dir = Path("eval-results")
    if not out_dir.exists():
        print("No eval-results/ found. Run `run` then `judge` first.")
        return 1

    records = []
    for path in sorted(out_dir.glob("*.json")):
        record = EvalRecord.model_validate_json(path.read_text())
        records.append(record)

    report = markdown_report(records)
    report_path = Path("eval-report.md")
    report_path.write_text(report)
    print(f"\nReport written to {report_path}")

    passed = sum(1 for r in records if not r.failure_reason)
    print(f"Result: {passed}/{len(records)} scenarios passed strongly")
    return 0 if passed == len(records) else 1


async def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m eval <run|judge|report>")
        return 1

    cmd = sys.argv[1]
    if cmd == "run":
        return await cmd_run()
    elif cmd == "judge":
        return await cmd_judge()
    elif cmd == "report":
        return await cmd_report()
    else:
        print(f"Unknown command: {cmd}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
