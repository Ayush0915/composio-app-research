"""
run_pipeline.py — Orchestrator CLI for the Composio App Research pipeline.

Usage:
    python run_pipeline.py --stage test
    python run_pipeline.py --stage research --limit 3
    python run_pipeline.py --stage verify
    python run_pipeline.py --stage analyze
    python run_pipeline.py --stage all
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure the script directory is in sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

load_dotenv()


def run_tests() -> bool:
    """Run pytest suite."""
    print("\n>>> Stage: Running Unit and Integration Tests...")
    cmd = [sys.executable, "-m", "pytest", "tests/", "-v"]
    try:
        res = subprocess.run(cmd, check=False)
        if res.returncode == 0:
            print("[OK] Tests passed successfully.")
            return True
        else:
            print("[FAIL] Tests failed!")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to run tests: {e}")
        return False


def run_research_stage(limit: int | None = None):
    """Run Phase 3: Research Agent (Pass 1)."""
    print("\n>>> Stage: App Research (Pass 1)...")
    from research_agent import load_apps, run_research, OUTPUT_FILE
    
    apps = load_apps()
    if not apps:
        print("[ERROR] No apps found in apps.json!")
        sys.exit(1)
        
    print(f"Loaded {len(apps)} total apps from apps.json")
    results = asyncio.run(run_research(apps, limit=limit))
    
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"[OK] Completed Pass-1 research. Raw results saved to {OUTPUT_FILE}")


def run_verify_stage():
    """Run Phase 5: Verification Agent (Pass 2)."""
    print("\n>>> Stage: Verification Agent (Pass 2) & Accuracy Diffs...")
    from verify_agent import run_verification
    try:
        report = run_verification()
        print(f"[OK] Verification completed. Accuracy report saved to output/accuracy_report.json")
        return report
    except FileNotFoundError as e:
        print(f"[ERROR] Verification failed: {e}")
        print("Please run the research stage first.")
        sys.exit(1)


def run_analyze_stage():
    """Run Phase 6: Pattern Extraction."""
    print("\n>>> Stage: Pattern Extraction & Analysis...")
    from analyze_patterns import run_analysis
    try:
        patterns = run_analysis()
        
        # Automatically generate HTML page
        print("\n>>> Generating HTML Deliverable (site/index.html)...")
        import generate_site
        generate_site.main()
        
        return patterns
    except FileNotFoundError as e:
        print(f"[ERROR] Analysis failed: {e}")
        print("Please run the research (and verification) stages first.")
        sys.exit(1)


def print_final_summary_report():
    """Prints a clean summary of access models, auth methods, top blockers, and accuracy metrics."""
    results_file = Path("output/results_verified.json")
    if not results_file.exists():
        results_file = Path("output/results_raw.json")
    
    if not results_file.exists():
        return
        
    with open(results_file, "r", encoding="utf-8") as f:
        records = json.load(f)
        
    from collections import Counter
    
    # Access models
    access_counter = Counter(r.get("access_model", "unknown") for r in records)
    # Auth methods
    auth_counter = Counter()
    for r in records:
        for m in r.get("auth_methods", []):
            auth_counter[m] += 1
            
    # Blockers
    blockers = Counter(r.get("blocker") for r in records if r.get("buildability_verdict") == "blocked" and r.get("blocker"))
    
    print("\n" + "=" * 60)
    print("                FINAL PIPELINE SUMMARY REPORT")
    print("=" * 60)
    
    print("\n[Access Models]")
    for am, count in access_counter.most_common():
        print(f"  {am:<25} : {count}")
        
    print("\n[Top Auth Methods]")
    for am, count in auth_counter.most_common(5):
        print(f"  {am:<25} : {count}")
        
    if blockers:
        print("\n[Top Blockers]")
        for blk, count in blockers.most_common(5):
            print(f"  {blk[:45]:<45} : {count}")
            
    # Accuracy Report
    acc_report_file = Path("output/accuracy_report.json")
    if acc_report_file.exists():
        with open(acc_report_file, "r", encoding="utf-8") as f:
            acc = json.load(f)
        print("\n[Verification & Accuracy Metrics]")
        print(f"  Pass-1 Raw Accuracy        : {acc.get('pass1_raw_accuracy', 0.0):.1%}")
        print(f"  Pass-2 Agreement Rate      : {acc.get('pass2_agreement_rate', 0.0):.1%}")
        print(f"  Final Human Corrected Acc   : {acc.get('final_human_corrected_accuracy', 0.0):.1%}")
        print(f"  Needs Human Review count   : {len(acc.get('needs_human_review_apps', []))}")
        
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Composio App Research Pipeline Orchestrator")
    parser.add_argument(
        "--stage",
        choices=["research", "test", "verify", "analyze", "all"],
        required=True,
        help="Specify the pipeline stage to run",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process this many apps during research stage (e.g. for quick testing)",
    )
    args = parser.parse_args()

    # Ensure required directories exist
    Path("checkpoints").mkdir(exist_ok=True)
    Path("output").mkdir(exist_ok=True)

    stage = args.stage

    if stage == "test":
        success = run_tests()
        sys.exit(0 if success else 1)

    elif stage == "research":
        run_research_stage(limit=args.limit)

    elif stage == "verify":
        run_verify_stage()

    elif stage == "analyze":
        run_analyze_stage()

    elif stage == "all":
        # 1. Run tests
        if not run_tests():
            print("[ERROR] Pipeline execution aborted because tests failed.")
            sys.exit(1)
            
        # 2. Run research
        run_research_stage(limit=args.limit)
        
        # 3. Run verify
        run_verify_stage()
        
        # 4. Run analyze
        run_analyze_stage()
        
        # 5. Show final orchestrator summary
        print_final_summary_report()
        
        print("[OK] Full pipeline execution completed successfully!")


if __name__ == "__main__":
    main()
