"""
verify_agent.py — Pass-2 independent verification agent.

Draws a stratified random sample (~18 apps) from results_raw.json,
re-runs independent research for each sampled app, diffs pass-1 vs pass-2,
and produces an accuracy report with three accuracy numbers.

Usage:
    python verify_agent.py
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from schema import AppResearch, VerificationDiff, AccuracyReport

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

RESULTS_RAW = Path("output/results_raw.json")
RESULTS_VERIFIED = Path("output/results_verified.json")
ACCURACY_REPORT_FILE = Path("output/accuracy_report.json")

# Fields to compare between pass-1 and pass-2
FIELDS_TO_CHECK = ["auth_methods", "access_model", "mcp_exists", "buildability_verdict"]

SAMPLE_SIZE = 18  # at least 1 per category (10 cats → 18 gives breathing room)

# ---------------------------------------------------------------------------
# Verification prompt — explicitly must NOT see pass-1 answer
# ---------------------------------------------------------------------------

VERIFY_PROMPT = """\
You are an independent verification agent. Your ONLY task is to research \
the following app from scratch and answer specific questions. You do NOT \
have access to any previous research — start fresh.

App name: {name}
Starting URL: {hint_url}

Search the official developer documentation for "{name}" and determine:
1. What authentication method(s) does it use? (OAuth2, API key, Bearer token, Basic auth, etc.)
2. Access model: can a developer get credentials for free (self-serve-free),
   requires paid plan (self-serve-paid), needs admin/company approval (gated-approval),
   or needs to contact sales (gated-partnership)? Use not-applicable for open-source CLI tools.
3. Does an official MCP (Model Context Protocol) server exist for this tool? (true/false)
4. Buildability verdict: could an AI agent use this TODAY (ready-today) or is it blocked?

Return ONLY valid JSON (no markdown, no prose):
{{
  "name": "{name}",
  "auth_methods": ["OAuth2"],
  "access_model": "self-serve-free",
  "mcp_exists": false,
  "buildability_verdict": "ready-today",
  "evidence_urls": ["https://..."],
  "confidence": 0.8,
  "raw_notes": "..."
}}

Valid values:
- access_model: self-serve-free | self-serve-paid | gated-approval | gated-partnership | not-applicable
- buildability_verdict: ready-today | blocked
"""


def _extract_json(text: str) -> Optional[str]:
    import re
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return None


def verify_app_sync(
    name: str,
    hint_url: str,
    gemini_client,
) -> dict:
    """Run independent pass-2 research for a single app."""
    import re
    prompt = VERIFY_PROMPT.format(name=name, hint_url=hint_url)

    for attempt in range(1, 4):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            json_str = _extract_json(response.text or "")
            if not json_str:
                raise ValueError("No JSON in response")
            data = json.loads(json_str)
            data["name"] = name
            logger.info(f"[verify/{name}] [OK] Pass-2 complete (attempt {attempt})")
            return data
        except Exception as e:
            logger.warning(f"[verify/{name}] Attempt {attempt} failed: {e}")
            import time
            time.sleep(2 ** attempt)

    return {
        "name": name,
        "auth_methods": ["unknown"],
        "access_model": "not-applicable",
        "mcp_exists": False,
        "buildability_verdict": "blocked",
        "evidence_urls": [hint_url],
        "confidence": 0.0,
        "raw_notes": "Pass-2 verification failed",
    }


def _normalise_for_compare(value) -> str:
    """Normalise a field value to string for comparison."""
    if isinstance(value, list):
        return json.dumps(sorted(str(v).lower() for v in value))
    if isinstance(value, bool):
        return str(value).lower()
    return str(value).lower().strip()


def _stratified_sample(records: list[dict], n: int) -> list[dict]:
    """Draw a stratified sample ensuring at least 1 app per category."""
    by_category: dict[str, list[dict]] = {}
    for r in records:
        cat = r.get("category", "unknown")
        by_category.setdefault(cat, []).append(r)

    sample: list[dict] = []
    # First, guarantee at least one per category
    for cat, apps in by_category.items():
        sample.append(random.choice(apps))

    # Fill remaining slots from all records not already chosen
    chosen_names = {r["name"] for r in sample}
    remaining = [r for r in records if r["name"] not in chosen_names]
    random.shuffle(remaining)
    slots_left = max(0, n - len(sample))
    sample.extend(remaining[:slots_left])

    return sample


def run_verification() -> AccuracyReport:
    """Main verification pipeline."""
    from google import genai

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise EnvironmentError("GEMINI_API_KEY not set")

    gemini_client = genai.Client(api_key=gemini_api_key)

    # Load pass-1 results
    if not RESULTS_RAW.exists():
        raise FileNotFoundError(
            f"{RESULTS_RAW} not found. Run the research agent first."
        )
    with open(RESULTS_RAW, "r", encoding="utf-8") as f:
        records: list[dict] = json.load(f)

    # Build a lookup from apps.json for hint_urls
    apps_file = Path("apps.json")
    hint_url_map: dict[str, str] = {}
    if apps_file.exists():
        with open(apps_file, "r", encoding="utf-8") as f:
            for cat_block in json.load(f):
                for app in cat_block["apps"]:
                    hint_url_map[app["name"]] = app["hint_url"]

    # Stratified sample
    sample = _stratified_sample(records, SAMPLE_SIZE)
    sampled_names = [r["name"] for r in sample]
    logger.info(f"Sampled {len(sample)} apps for verification: {sampled_names}")

    # Run pass-2 for each sampled app
    all_diffs: list[VerificationDiff] = []
    needs_review: list[str] = []

    for record in sample:
        name = record["name"]
        hint_url = hint_url_map.get(name, record.get("evidence_urls", [""])[0])

        pass2 = verify_app_sync(name, hint_url, gemini_client)

        app_disagrees = False
        for field in FIELDS_TO_CHECK:
            p1_val = _normalise_for_compare(record.get(field))
            p2_val = _normalise_for_compare(pass2.get(field))
            agrees = p1_val == p2_val

            diff = VerificationDiff(
                app_name=name,
                field=field,
                pass1_value=p1_val,
                pass2_value=p2_val,
                agrees=agrees,
            )
            all_diffs.append(diff)

            if not agrees:
                app_disagrees = True
                logger.warning(
                    f"[{name}] DISAGREEMENT on '{field}': "
                    f"pass1={p1_val!r} vs pass2={p2_val!r}"
                )

        if app_disagrees:
            needs_review.append(name)

    # Update needs_human_review flag on records
    for record in records:
        if record["name"] in needs_review:
            record["needs_human_review"] = True

    # Compute pass-1 raw accuracy
    total_fields = len(all_diffs)
    agreements = sum(1 for d in all_diffs if d.agrees)
    pass1_raw = round(agreements / total_fields, 4) if total_fields > 0 else 0.0

    # final_human_corrected_accuracy starts the same — updated after human resolves
    # (human fills in human_resolved_value on disagreements; script recomputes)
    human_corrections = sum(
        1 for d in all_diffs
        if not d.agrees and d.human_resolved_value is not None
    )
    # After human resolution, fields where human agreed with pass-1 add to correct count
    human_correct_additions = sum(
        1 for d in all_diffs
        if not d.agrees
        and d.human_resolved_value is not None
        and d.human_resolved_value == d.pass1_value
    )
    final_accuracy = round(
        (agreements + human_correct_additions) / total_fields, 4
    ) if total_fields > 0 else 0.0

    report = AccuracyReport(
        sampled_apps=sampled_names,
        diffs=[d for d in all_diffs],
        needs_human_review_apps=needs_review,
        pass1_raw_accuracy=pass1_raw,
        pass2_agreement_rate=pass1_raw,
        final_human_corrected_accuracy=final_accuracy,
        total_fields_checked=total_fields,
        total_disagreements=total_fields - agreements,
        human_corrections_count=human_corrections,
    )

    # Save outputs
    ACCURACY_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ACCURACY_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, default=str)

    # Save updated records (with needs_human_review flags) as results_verified.json
    RESULTS_VERIFIED.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_VERIFIED, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    logger.info(
        f"\n{'='*60}\n"
        f"VERIFICATION COMPLETE\n"
        f"  Sampled:           {len(sample)} apps\n"
        f"  Fields checked:    {total_fields}\n"
        f"  Disagreements:     {total_fields - agreements}\n"
        f"  Needs review:      {len(needs_review)} apps\n"
        f"  Pass-1 accuracy:   {pass1_raw:.1%}\n"
        f"  Final accuracy:    {final_accuracy:.1%}\n"
        f"{'='*60}"
    )

    return report


if __name__ == "__main__":
    run_verification()
