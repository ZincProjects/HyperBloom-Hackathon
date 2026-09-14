"""MIRAGE extraction eval: the production extraction call scored against hand-labeled transcripts.

Run from the repo root with the backend virtualenv's Python:

    python eval/run_eval.py                  # live Claude if ANTHROPIC_API_KEY is set, else the offline mock
    python eval/run_eval.py --mock           # force the offline heuristic baseline (no API calls)
    python eval/run_eval.py --repeat 3       # run every case 3 times; reports mean and run-to-run stability
    python eval/run_eval.py --update-readme  # also write the result block into README.md
    python eval/run_eval.py --json out.json  # also save per-case results

Scoring (see eval/README.md):
  technique    exact match of the MITRE technique ID
  IOC types    Jaccard overlap between expected and extracted IOC *types* (values are not compared)
  tactics      Jaccard overlap between expected and extracted manipulation tactics
Extractions that end in needs_review or an API error score 0 on every metric and stay in the denominator.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "eval" / "fixtures"
README = ROOT / "README.md"
README_START, README_END = "<!-- EVAL:START -->", "<!-- EVAL:END -->"

# A case "passes" when the technique matches exactly and both set overlaps reach this level.
MIN_OVERLAP_TO_PASS = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mock", action="store_true", help="use the offline heuristic extractor (no API calls)")
    parser.add_argument("--repeat", type=int, default=1, help="runs per case (default 1)")
    parser.add_argument("--update-readme", action="store_true", help="write the result block into README.md")
    parser.add_argument("--json", type=Path, help="save per-case results to this file")
    return parser.parse_args()


args = parse_args()
if args.mock:
    os.environ["MIRAGE_LLM_MODE"] = "mock"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
sys.path.insert(0, str(ROOT / "backend"))

try:
    from app import llm  # noqa: E402
    from app.config import llm_mode  # noqa: E402
    from app.mitre import TACTICS, TECHNIQUES  # noqa: E402
    from app.schemas import IOC_TYPES  # noqa: E402
except ImportError as exc:
    sys.exit(f"Could not import the backend ({exc}). Run with the backend virtualenv, e.g. backend/.venv/Scripts/python eval/run_eval.py")


def jaccard(expected: set, actual: set) -> float:
    if not expected and not actual:
        return 1.0
    return len(expected & actual) / len(expected | actual)


def load_fixtures() -> list[dict]:
    fixtures = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        exp = fixture["expected"]
        problems = []
        if exp["mitre_technique"] not in TECHNIQUES:
            problems.append(f"unknown technique {exp['mitre_technique']}")
        problems += [f"unknown tactic {t}" for t in exp["manipulation_tactics"] if t not in TACTICS]
        problems += [f"unknown IOC type {t}" for t in exp["ioc_types"] if t not in IOC_TYPES]
        if not fixture["messages"] or fixture["messages"][0]["sender"] != "attacker":
            problems.append("transcript must start with an attacker message")
        if problems:
            sys.exit(f"Invalid fixture {path.name}: {'; '.join(problems)}")
        fixtures.append(fixture)
    if not fixtures:
        sys.exit(f"No fixtures found in {FIXTURES_DIR}")
    return fixtures


def run_case(fixture: dict) -> dict:
    messages = [SimpleNamespace(sender=m["sender"], content=m["content"]) for m in fixture["messages"]]
    expected = fixture["expected"]
    result = {"id": fixture["id"], "difficulty": fixture["difficulty"], "expected": expected,
              "technique_match": False, "ioc_type_overlap": 0.0, "tactic_overlap": 0.0, "passed": False}
    started = time.perf_counter()
    try:
        profile, _ = llm.extract_profile(messages)
    except llm.ExtractionValidationError as exc:
        result.update(outcome="needs_review", error=str(exc))
    except llm.LLMError as exc:
        result.update(outcome="error", error=str(exc))
    else:
        actual = {
            "mitre_technique": profile.mitre_technique,
            "ioc_types": sorted({ioc.type for ioc in profile.iocs}),
            "manipulation_tactics": sorted(set(profile.manipulation_tactics)),
            "attacker_goal": profile.attacker_goal,
            "attacker_goal_confidence": profile.attacker_goal_confidence,
        }
        technique_match = actual["mitre_technique"] == expected["mitre_technique"]
        ioc_overlap = jaccard(set(expected["ioc_types"]), set(actual["ioc_types"]))
        tactic_overlap = jaccard(set(expected["manipulation_tactics"]), set(actual["manipulation_tactics"]))
        result.update(
            outcome="scored", actual=actual, technique_match=technique_match,
            ioc_type_overlap=ioc_overlap, tactic_overlap=tactic_overlap,
            passed=technique_match and ioc_overlap >= MIN_OVERLAP_TO_PASS and tactic_overlap >= MIN_OVERLAP_TO_PASS,
        )
    result["seconds"] = round(time.perf_counter() - started, 2)
    return result


def print_case(r: dict, run_label: str) -> None:
    exp = r["expected"]
    if r["outcome"] != "scored":
        tag = "NEEDS_REVIEW" if r["outcome"] == "needs_review" else "ERROR"
        print(f"[{tag:4}] {r['id']:<13} {r['difficulty']:<9} {run_label}{r['error']}")
        return
    act = r["actual"]
    op = "==" if r["technique_match"] else "!="
    print(
        f"[{'PASS' if r['passed'] else 'FAIL'}] {r['id']:<13} {r['difficulty']:<9} {run_label}"
        f"technique {act['mitre_technique']:<9} {op} {exp['mitre_technique']:<9}  "
        f"ioc-types {r['ioc_type_overlap']:>4.0%}  tactics {r['tactic_overlap']:>4.0%}  "
        f"goal-confidence={act['attacker_goal_confidence']}  ({r['seconds']}s)"
    )
    if not r["passed"]:
        if set(act["ioc_types"]) != set(exp["ioc_types"]):
            print(f"{'':25}ioc types  expected {sorted(exp['ioc_types'])}  got {act['ioc_types']}")
        if set(act["manipulation_tactics"]) != set(exp["manipulation_tactics"]):
            print(f"{'':25}tactics    expected {sorted(exp['manipulation_tactics'])}  got {act['manipulation_tactics']}")


def run_stats(results: list[dict]) -> dict:
    return {
        "technique_matches": sum(r["technique_match"] for r in results),
        "ioc_type_overlap": mean(r["ioc_type_overlap"] for r in results),
        "tactic_overlap": mean(r["tactic_overlap"] for r in results),
        "passed": sum(r["passed"] for r in results),
        "needs_review": sum(r["outcome"] == "needs_review" for r in results),
        "errors": sum(r["outcome"] == "error" for r in results),
        "n": len(results),
    }


def fmt_count(values: list[float]) -> str:
    """A count, or the mean count across repeated runs ('7', '7.5')."""
    return f"{mean(values):.1f}".rstrip("0").rstrip(".")


def summarize(runs: list[list[dict]], fixtures: list[dict], settings: dict) -> list[str]:
    n, repeats = len(fixtures), len(runs)
    analyzer = settings["analyzer"]
    stats = [run_stats(results) for results in runs]
    tech = [s["technique_matches"] for s in stats]
    runs_note = f" (per run: {', '.join(str(t) for t in tech)})" if repeats > 1 else ""
    sample = f"n={n}" + (f" x {repeats} runs" if repeats > 1 else "")
    headline = (
        f"{fmt_count(tech)}/{n} technique matches{runs_note}, "
        f"{mean(s['ioc_type_overlap'] for s in stats):.0%} IOC-type overlap, "
        f"{mean(s['tactic_overlap'] for s in stats):.0%} tactic-tag overlap, "
        f"{sum(s['needs_review'] for s in stats)}/{n * repeats} needs_review "
        f"(held-out eval, {sample}, analyzer={analyzer})"
    )
    lines = [f"RESULT: {headline}"]

    by_difficulty = []
    for difficulty in sorted({f["difficulty"] for f in fixtures}):
        subset = [[r for r in results if r["difficulty"] == difficulty] for results in runs]
        sub_stats = [run_stats(s) for s in subset]
        by_difficulty.append(
            f"{difficulty} (n={sub_stats[0]['n']}): {fmt_count([s['technique_matches'] for s in sub_stats])}/{sub_stats[0]['n']} technique, "
            f"{mean(s['ioc_type_overlap'] for s in sub_stats):.0%} IOC-type, {mean(s['tactic_overlap'] for s in sub_stats):.0%} tactics"
        )
    lines.append("by difficulty: " + " | ".join(by_difficulty))
    lines.append(f"cases passing all checks: {fmt_count([s['passed'] for s in stats])}/{n} "
                 f"(technique exact + IOC-type and tactic overlap >= {MIN_OVERLAP_TO_PASS:.0%})")

    confidence = Counter(r["actual"]["attacker_goal_confidence"] for results in runs for r in results if r["outcome"] == "scored")
    lines.append("attacker_goal_confidence: " + ", ".join(f"{level} {confidence.get(level, 0)}" for level in ("high", "medium", "low")))
    if repeats > 1:
        stable = sum(
            len({(r.get("actual") or {}).get("mitre_technique") for r in case_runs}) == 1
            for case_runs in zip(*runs)
        )
        lines.append(f"technique identical across all {repeats} runs: {stable}/{n} cases")
    errors = sum(s["errors"] for s in stats)
    if errors:
        lines.append(f"API errors: {errors} (scored as misses)")
    return lines


def readme_block(lines: list[str], settings: dict, fixtures: list[dict]) -> str:
    difficulties = Counter(f["difficulty"] for f in fixtures)
    mix = ", ".join(f"{count} {name}" for name, count in sorted(difficulties.items()))
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    config = ", ".join(f"{k}={v}" for k, v in settings.items() if k != "analyzer")
    block = [
        README_START,
        f"Measured with `python eval/run_eval.py` on {date}. Analyzer: `{settings['analyzer']}` ({config}).",
        "",
        "```text",
        *lines,
        "```",
        "",
        f"What this measures: agreement with our own labels on n={len(fixtures)} hand-labeled transcripts ({mix}). "
        "It is a small, fixed test set, not a guarantee of accuracy on live or unseen attacker traffic.",
    ]
    if settings["analyzer"] == "mock-heuristic":
        block += ["", "> **Note:** this block was produced by the offline regex/keyword baseline, not by Claude. "
                      "Re-run with `ANTHROPIC_API_KEY` set and `--update-readme` to record the Claude number."]
    block.append(README_END)
    return "\n".join(block)


def update_readme(block: str) -> None:
    text = README.read_text(encoding="utf-8")
    start, end = text.find(README_START), text.find(README_END)
    if start == -1 or end == -1:
        sys.exit(f"README.md has no {README_START} / {README_END} markers")
    README.write_text(text[:start] + block + text[end + len(README_END):], encoding="utf-8")
    print(f"\nUpdated the eval block in {README.relative_to(ROOT)}")


def main() -> None:
    fixtures = load_fixtures()
    settings = llm.extraction_settings()
    print("MIRAGE extraction eval")
    print(f"mode: {llm_mode()} | extraction settings: {settings}")
    print(f"fixtures: {len(fixtures)} from {FIXTURES_DIR.relative_to(ROOT)}  | runs per case: {args.repeat}")
    if llm_mode() == "mock":
        print("NOTE: offline heuristic baseline - no Claude calls are made in this run.")
    print()

    runs = []
    for run in range(1, args.repeat + 1):
        results = []
        for fixture in fixtures:
            result = run_case(fixture)
            print_case(result, f"run {run}  " if args.repeat > 1 else "")
            results.append(result)
        runs.append(results)
        if all(r["outcome"] == "error" for r in results):
            sys.exit(f"\nEvery case failed with an API error - no score produced. First error: {results[0]['error']}")

    lines = summarize(runs, fixtures, settings)
    print()
    print("\n".join(lines))

    if args.json:
        args.json.write_text(json.dumps({"settings": settings, "summary": lines, "runs": runs}, indent=2), encoding="utf-8")
        print(f"\nSaved per-case results to {args.json}")
    if args.update_readme:
        update_readme(readme_block(lines, settings, fixtures))


if __name__ == "__main__":
    main()
