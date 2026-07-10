"""
analyze_patterns.py — Pattern extraction from verified research data.

Computes:
  - Auth method distribution
  - Access model distribution
  - Category × access model cross-tab
  - Blocker frequency table
  - MCP prevalence

Outputs: output/patterns.json and a readable summary to stdout.

Usage:
    python analyze_patterns.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tabulate import tabulate

RESULTS_VERIFIED = Path("output/results_verified.json")
RESULTS_RAW = Path("output/results_raw.json")
PATTERNS_FILE = Path("output/patterns.json")


def load_results() -> list[dict]:
    """Load verified results, falling back to raw if verified not found."""
    if RESULTS_VERIFIED.exists():
        with open(RESULTS_VERIFIED, "r", encoding="utf-8") as f:
            return json.load(f)
    if RESULTS_RAW.exists():
        print("[warn] results_verified.json not found, using results_raw.json")
        with open(RESULTS_RAW, "r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(
        "No results file found. Run the research agent first."
    )


def compute_patterns(records: list[dict]) -> dict[str, Any]:
    n = len(records)

    # ----------------------------------------------------------------
    # 1. Auth method distribution
    # ----------------------------------------------------------------
    auth_counter: Counter = Counter()
    for r in records:
        for method in r.get("auth_methods", []):
            auth_counter[method.strip()] += 1

    auth_distribution = {
        method: {
            "count": count,
            "percent": round(count / n * 100, 1),
        }
        for method, count in auth_counter.most_common()
    }

    # ----------------------------------------------------------------
    # 2. Access model distribution
    # ----------------------------------------------------------------
    access_counter: Counter = Counter(
        r.get("access_model", "unknown") for r in records
    )
    access_distribution = {
        model: {
            "count": count,
            "percent": round(count / n * 100, 1),
        }
        for model, count in access_counter.most_common()
    }

    # ----------------------------------------------------------------
    # 3. Category × access model cross-tab
    # ----------------------------------------------------------------
    cat_access: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        cat = r.get("category", "unknown")
        access = r.get("access_model", "unknown")
        cat_access[cat][access] += 1

    cat_access_table: dict[str, dict[str, int]] = {
        cat: dict(counter) for cat, counter in cat_access.items()
    }

    # ----------------------------------------------------------------
    # 4. Blocker frequency (only blocked apps)
    # ----------------------------------------------------------------
    blocked = [
        r for r in records
        if r.get("buildability_verdict") == "blocked"
    ]
    blocker_counter: Counter = Counter()
    for r in blocked:
        blocker = r.get("blocker") or "unspecified"
        blocker_counter[blocker] += 1

    blocker_table = dict(blocker_counter.most_common())

    # ----------------------------------------------------------------
    # 5. MCP prevalence
    # ----------------------------------------------------------------
    mcp_yes = sum(1 for r in records if r.get("mcp_exists") is True)
    mcp_distribution = {
        "mcp_exists": {
            "count": mcp_yes,
            "percent": round(mcp_yes / n * 100, 1),
        },
        "mcp_not_found": {
            "count": n - mcp_yes,
            "percent": round((n - mcp_yes) / n * 100, 1),
        },
    }

    # ----------------------------------------------------------------
    # 6. Buildability summary
    # ----------------------------------------------------------------
    ready = sum(1 for r in records if r.get("buildability_verdict") == "ready-today")
    buildability = {
        "ready_today": {
            "count": ready,
            "percent": round(ready / n * 100, 1),
        },
        "blocked": {
            "count": n - ready,
            "percent": round((n - ready) / n * 100, 1),
        },
    }

    return {
        "total_apps": n,
        "auth_distribution": auth_distribution,
        "access_model_distribution": access_distribution,
        "category_x_access_model": cat_access_table,
        "blocker_frequency": blocker_table,
        "mcp_distribution": mcp_distribution,
        "buildability_summary": buildability,
    }


def print_summary(patterns: dict) -> None:
    """Print a human-readable summary table to stdout."""
    n = patterns["total_apps"]
    print(f"\n{'='*65}")
    print(f"  COMPOSIO APP RESEARCH — PATTERN SUMMARY  ({n} apps)")
    print(f"{'='*65}\n")

    # Auth methods
    print("--- Auth Method Distribution ---------------------------------")
    rows = [
        [method, data["count"], f"{data['percent']}%"]
        for method, data in patterns["auth_distribution"].items()
    ]
    print(tabulate(rows, headers=["Auth Method", "Count", "%"], tablefmt="simple"))
    print()

    # Access model
    print("--- Access Model Distribution --------------------------------")
    rows = [
        [model, data["count"], f"{data['percent']}%"]
        for model, data in patterns["access_model_distribution"].items()
    ]
    print(tabulate(rows, headers=["Access Model", "Count", "%"], tablefmt="simple"))
    print()

    # Buildability
    print("--- Buildability Summary -------------------------------------")
    b = patterns["buildability_summary"]
    print(f"  Ready today:  {b['ready_today']['count']} ({b['ready_today']['percent']}%)")
    print(f"  Blocked:      {b['blocked']['count']} ({b['blocked']['percent']}%)")
    print()

    # MCP
    print("--- MCP Prevalence -------------------------------------------")
    m = patterns["mcp_distribution"]
    print(f"  MCP exists:   {m['mcp_exists']['count']} ({m['mcp_exists']['percent']}%)")
    print(f"  No MCP found: {m['mcp_not_found']['count']} ({m['mcp_not_found']['percent']}%)")
    print()

    # Top blockers
    if patterns["blocker_frequency"]:
        print("--- Top Blockers (blocked apps only) -------------------------")
        rows = [
            [blocker[:60], count]
            for blocker, count in list(patterns["blocker_frequency"].items())[:5]
        ]
        print(tabulate(rows, headers=["Blocker", "Count"], tablefmt="simple"))
    print()

    # Category cross-tab
    print("--- Category x Access Model Cross-Tab -----------------------")
    access_models = ["self-serve-free", "self-serve-paid", "gated-approval", "gated-partnership"]
    headers = ["Category"] + [m.replace("self-serve-", "ss-").replace("gated-", "g-") for m in access_models]
    rows = []
    for cat, counts in sorted(patterns["category_x_access_model"].items()):
        row = [cat] + [counts.get(m, 0) for m in access_models]
        rows.append(row)
    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print(f"\n{'='*65}\n")


def run_analysis() -> dict:
    records = load_results()
    patterns = compute_patterns(records)

    PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(patterns, f, indent=2)

    print_summary(patterns)
    print(f"[OK] Patterns saved to {PATTERNS_FILE}")
    return patterns


if __name__ == "__main__":
    run_analysis()
