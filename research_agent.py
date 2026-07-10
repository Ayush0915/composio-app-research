"""
research_agent.py — Pass-1 research agent.

Uses Google Gemini + Tavily (via Composio SDK) to research each app and
produce a structured AppResearch record with full citation of evidence URLs.

Usage (direct):
    python research_agent.py --limit 3
    python research_agent.py           # all 100 apps
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import argparse
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# Lazy imports — only load SDK when needed so tests that mock can run
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

CHECKPOINT_FILE = Path("checkpoints/progress.json")
OUTPUT_FILE = Path("output/results_raw.json")
APPS_FILE = Path("apps.json")

CONCURRENCY = int(os.getenv("RESEARCH_CONCURRENCY", "6"))
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

RESEARCH_PROMPT = """\
You are a developer-focused research agent. Your task is to research the \
following app/tool and return structured JSON about its developer API.

App name: {name}
Starting hint URL: {hint_url}

Search the web for the official developer documentation for "{name}".
Look specifically for:
1. What the app/tool does (one-line description)
2. Authentication method(s): OAuth2, API key, Bearer token, Basic auth, etc.
3. Whether a developer can get credentials for free/trial (self-serve-free),
   requires a paid plan (self-serve-paid), needs admin approval (gated-approval),
   or needs to contact sales / partnership (gated-partnership).
   If it's an open-source CLI tool with no hosted auth, use: not-applicable
4. API surface: REST, GraphQL, REST+Webhooks, REST+GraphQL, SDK-only, or none-found
5. API breadth: broad (many resources), narrow (few endpoints), or undocumented
6. Whether an official MCP (Model Context Protocol) server exists for this tool
7. Whether the app could be used as an AI agent toolkit TODAY
8. The main blocker if it cannot (e.g. no public API, gated access, etc.)

IMPORTANT RULES:
- Do NOT fabricate information. If you cannot find the docs, say so in raw_notes.
- For open-source CLI tools (e.g. shell scripts, local tools), set:
    access_model: "not-applicable"
    api_surface: "none-found"
  and explain in raw_notes why standard hosted API concepts don't apply.
- Set confidence honestly: 0.3-0.5 if unsure, 0.7-0.9 if docs are clear.
- evidence_urls MUST be real URLs you actually visited, not guessed.

Return ONLY valid JSON matching this exact schema (no markdown, no explanation):
{{
  "name": "{name}",
  "category": "{category}",
  "one_liner": "...",
  "auth_methods": ["OAuth2"],
  "access_model": "self-serve-free",
  "api_surface": "REST",
  "api_breadth": "broad",
  "mcp_exists": false,
  "mcp_source": null,
  "buildability_verdict": "ready-today",
  "blocker": null,
  "evidence_urls": ["https://..."],
  "confidence": 0.85,
  "raw_notes": "...",
  "needs_human_review": false
}}

Valid values:
- access_model: self-serve-free | self-serve-paid | gated-approval | gated-partnership | not-applicable
- api_surface: REST | GraphQL | REST+Webhooks | REST+GraphQL | SDK-only | none-found
- api_breadth: broad | narrow | undocumented | not-applicable
- buildability_verdict: ready-today | blocked
"""

# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def load_checkpoint() -> dict[str, dict]:
    """Load existing checkpoint data, return dict keyed by app name."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            records = json.load(f)
        return {r["name"]: r for r in records}
    return {}


def save_checkpoint(record: dict) -> None:
    """Append or update a single record in the checkpoint file."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = load_checkpoint()
    existing[record["name"]] = record
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(existing.values()), f, indent=2)


# ---------------------------------------------------------------------------
# Core research function
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[str]:
    """Extract JSON object from LLM response, handling markdown fences."""
    # Try to extract from markdown code fences first
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    # Find the first { and last } pair
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return None


def research_app_sync(
    name: str,
    hint_url: str,
    category: str,
    composio_toolset=None,
    groq_client=None,
) -> dict:
    """
    Synchronous version of research_app. Handles retries and schema validation.
    Returns the raw dict (not yet AppResearch to allow checkpoint saving).
    """
    from schema import AppResearch

    prompt = RESEARCH_PROMPT.format(name=name, hint_url=hint_url, category=category)

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"[{name}] Attempt {attempt}/{MAX_RETRIES} ...")

            if groq_client is not None and composio_toolset is not None:
                # Use Composio toolset with Groq
                response_text = _call_groq_with_composio(
                    prompt, name, composio_toolset, groq_client
                )
            else:
                # Fallback: direct Groq call (no search tools)
                response_text = _call_groq_direct(prompt, groq_client)

            # Parse JSON
            json_str = _extract_json(response_text)
            if not json_str:
                raise ValueError(f"No JSON found in response: {response_text[:200]}")

            raw = json.loads(json_str)
            raw["name"] = name      # always enforce correct name
            raw["category"] = category

            # Validate with Pydantic
            record = AppResearch(**raw)
            logger.info(
                f"[{name}] [OK] Done (confidence={record.confidence}, "
                f"verdict={record.buildability_verdict})"
            )
            return record.model_dump()

        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_error = e
            logger.warning(f"[{name}] Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)  # exponential backoff

    # All retries exhausted — return a minimal fallback record flagged for review
    logger.error(f"[{name}] All retries failed. Recording error for human review.")
    return {
        "name": name,
        "category": category,
        "one_liner": "Research failed — needs human review",
        "auth_methods": ["unknown"],
        "access_model": "not-applicable",
        "api_surface": "none-found",
        "api_breadth": "undocumented",
        "mcp_exists": False,
        "mcp_source": None,
        "buildability_verdict": "blocked",
        "blocker": f"Agent research failed after {MAX_RETRIES} attempts: {last_error}",
        "evidence_urls": [hint_url],
        "confidence": 0.0,
        "raw_notes": f"Error: {last_error}",
        "needs_human_review": True,
    }


def _call_groq_with_composio(
    prompt: str, app_name: str, composio_toolset, groq_client
) -> str:
    """Call Groq with Composio's Tavily search tools attached."""
    # Get tools from Composio wrapped for Groq/OpenAI format
    try:
        raw_tools = composio_toolset.tools.get_raw_composio_tools(toolkits=["tavily"])
        groq_tools = composio_toolset.provider.wrap_tools(raw_tools)
    except Exception as e:
        logger.warning(f"[{app_name}] Could not fetch Composio tools ({e}), falling back to direct Groq.")
        return _call_groq_direct(prompt, groq_client)

    try:
        messages = [{"role": "user", "content": prompt}]
        
        # Groq tool execution loop (max 5 tool calls)
        for _ in range(5):
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                tools=groq_tools,
                temperature=0.1
            )
            message = response.choices[0].message
            messages.append(message)

            if not message.tool_calls:
                return message.content or ""

            # Execute tool calls
            for tool_call in message.tool_calls:
                result = composio_toolset.provider.execute_tool_call(
                    user_id="default",
                    tool_call=tool_call
                )
                
                output = result.model_dump() if hasattr(result, "model_dump") else result
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": json.dumps(output) if isinstance(output, dict) else str(output)
                })

        return messages[-1].content if messages[-1].get("role") == "assistant" else ""

    except Exception as e:
        logger.warning(f"[{app_name}] Composio Groq tool call loop failed ({e}), falling back.")
        return _call_groq_direct(prompt, groq_client)


def _call_groq_direct(prompt: str, groq_client) -> str:
    """Direct Groq call without search tools (fallback)."""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Async orchestration
# ---------------------------------------------------------------------------

async def research_app_async(
    name: str,
    hint_url: str,
    category: str,
    semaphore: asyncio.Semaphore,
    composio_toolset,
    groq_client,
) -> dict:
    """Async wrapper around synchronous research_app_sync."""
    async with semaphore:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            research_app_sync,
            name,
            hint_url,
            category,
            composio_toolset,
            groq_client,
        )
        save_checkpoint(result)
        return result


async def run_research(apps: list[dict], limit: Optional[int] = None) -> list[dict]:
    """
    Main async research runner.

    Args:
        apps: list of {"name": ..., "hint_url": ..., "category": ...}
        limit: if set, only process this many apps (for testing)
    """
    from groq import Groq
    from composio import Composio
    from composio_groq import GroqProvider

    # Initialise clients
    groq_api_key = os.getenv("GROQ_API_KEY")
    composio_api_key = os.getenv("COMPOSIO_API_KEY")

    if not groq_api_key:
        raise EnvironmentError("GROQ_API_KEY not set in environment")
    if not composio_api_key:
        raise EnvironmentError("COMPOSIO_API_KEY not set in environment")

    # groq Client
    groq_client = Groq(api_key=groq_api_key)
    composio_toolset = Composio(api_key=composio_api_key, provider=GroqProvider())

    # Load checkpoint — skip already-done apps
    done = load_checkpoint()
    pending = [a for a in apps if a["name"] not in done]

    if limit:
        pending = pending[:limit]

    logger.info(
        f"Research run: {len(done)} already done, {len(pending)} pending "
        f"(limit={limit or 'none'})"
    )

    if not pending:
        logger.info("All apps already checkpointed. Loading from checkpoint.")
        return list(done.values())

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        research_app_async(
            a["name"], a["hint_url"], a["category"],
            semaphore, composio_toolset, groq_client
        )
        for a in pending
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge with checkpoint
    all_results = list(done.values())
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Unexpected exception during research: {r}")
        else:
            all_results.append(r)

    return all_results


# ---------------------------------------------------------------------------
# Flat app list helper
# ---------------------------------------------------------------------------

def load_apps(apps_file: Path = APPS_FILE) -> list[dict]:
    """Load apps.json and flatten into a list of dicts with category field."""
    with open(apps_file, "r", encoding="utf-8") as f:
        categories = json.load(f)

    flat: list[dict] = []
    for cat_block in categories:
        category = cat_block["category"]
        for app in cat_block["apps"]:
            flat.append({
                "name": app["name"],
                "hint_url": app["hint_url"],
                "category": category,
            })
    return flat


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Research Agent — Pass 1")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process this many apps (for testing)",
    )
    args = parser.parse_args()

    apps = load_apps()
    results = asyncio.run(run_research(apps, limit=args.limit))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logger.info(f"[OK] Saved {len(results)} records to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
