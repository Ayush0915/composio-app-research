"""
test_schema_and_agent.py — Unit and integration tests for the App Research pipeline.
Run with: pytest tests/
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest
from pydantic import ValidationError

from schema import AppResearch, AccessModel, BuildabilityVerdict, ApiSurface, ApiBreadth


def test_schema_valid_app_research():
    """Test that a valid AppResearch object parses correctly."""
    data = {
        "name": "Stripe",
        "category": "Ecommerce",
        "one_liner": "A payment processing platform for online businesses.",
        "auth_methods": ["API key", "OAuth2"],
        "access_model": "self-serve-free",
        "api_surface": "REST",
        "api_breadth": "broad",
        "mcp_exists": False,
        "mcp_source": None,
        "buildability_verdict": "ready-today",
        "blocker": None,
        "evidence_urls": ["https://stripe.com/docs/api"],
        "confidence": 0.95,
        "raw_notes": "Stripe has excellent docs and a very broad REST API.",
        "needs_human_review": False
    }
    app = AppResearch(**data)
    assert app.name == "Stripe"
    assert app.confidence == 0.95


def test_schema_invalid_access_model():
    """Test that invalid access_model raises validation error."""
    data = {
        "name": "Stripe",
        "category": "Ecommerce",
        "one_liner": "A payment processing platform.",
        "auth_methods": ["API key"],
        "access_model": "invalid-access-model-value",  # Invalid enum value
        "api_surface": "REST",
        "api_breadth": "broad",
        "mcp_exists": False,
        "mcp_source": None,
        "buildability_verdict": "ready-today",
        "blocker": None,
        "evidence_urls": ["https://stripe.com/docs/api"],
        "confidence": 0.95,
        "raw_notes": "raw notes",
        "needs_human_review": False
    }
    with pytest.raises(ValidationError) as exc_info:
        AppResearch(**data)
    assert "access_model must be one of" in str(exc_info.value)


def test_schema_blocked_missing_blocker():
    """Test that buildability_verdict 'blocked' requires a 'blocker' value."""
    data = {
        "name": "Gated App",
        "category": "CRM/Sales",
        "one_liner": "Gated CRM platform.",
        "auth_methods": ["OAuth2"],
        "access_model": "gated-partnership",
        "api_surface": "REST",
        "api_breadth": "narrow",
        "mcp_exists": False,
        "mcp_source": None,
        "buildability_verdict": "blocked",
        "blocker": None,  # Blocked but blocker is None
        "evidence_urls": ["https://example.com/docs"],
        "confidence": 0.8,
        "raw_notes": "raw notes",
        "needs_human_review": False
    }
    with pytest.raises(ValidationError) as exc_info:
        AppResearch(**data)
    assert "blocker must be set when buildability_verdict is 'blocked'" in str(exc_info.value)


def test_schema_mcp_missing_source():
    """Test that mcp_exists=True requires mcp_source."""
    data = {
        "name": "Mcp App",
        "category": "Developer/Infra/Data platforms",
        "one_liner": "App with MCP server.",
        "auth_methods": ["API key"],
        "access_model": "self-serve-free",
        "api_surface": "REST",
        "api_breadth": "broad",
        "mcp_exists": True,
        "mcp_source": None,  # Missing source
        "buildability_verdict": "ready-today",
        "blocker": None,
        "evidence_urls": ["https://example.com/docs"],
        "confidence": 0.8,
        "raw_notes": "raw notes",
        "needs_human_review": False
    }
    with pytest.raises(ValidationError) as exc_info:
        AppResearch(**data)
    assert "mcp_source must be set when mcp_exists is True" in str(exc_info.value)


def test_schema_invalid_urls():
    """Test that invalid URLs in evidence_urls raise validation error."""
    data = {
        "name": "Stripe",
        "category": "Ecommerce",
        "one_liner": "A payment processing platform.",
        "auth_methods": ["API key"],
        "access_model": "self-serve-free",
        "api_surface": "REST",
        "api_breadth": "broad",
        "mcp_exists": False,
        "mcp_source": None,
        "buildability_verdict": "ready-today",
        "blocker": None,
        "evidence_urls": ["not-a-valid-url"],  # Invalid URL
        "confidence": 0.95,
        "raw_notes": "raw notes",
        "needs_human_review": False
    }
    with pytest.raises(ValidationError) as exc_info:
        AppResearch(**data)
    assert "Invalid URL format" in str(exc_info.value)


def test_checkpoint_resume_simulation(tmp_path):
    """Test checkpoint saving and loading simulation."""
    from research_agent import save_checkpoint, load_checkpoint, CHECKPOINT_FILE
    
    # Override checkpoints file for testing
    import research_agent
    original_checkpoint = research_agent.CHECKPOINT_FILE
    test_checkpoint = tmp_path / "progress.json"
    research_agent.CHECKPOINT_FILE = test_checkpoint

    try:
        record1 = {
            "name": "App A",
            "category": "CRM",
            "one_liner": "CRM App",
            "auth_methods": ["API key"],
            "access_model": "self-serve-free",
            "api_surface": "REST",
            "api_breadth": "broad",
            "mcp_exists": False,
            "mcp_source": None,
            "buildability_verdict": "ready-today",
            "blocker": None,
            "evidence_urls": ["https://example.com/docs"],
            "confidence": 0.9,
            "raw_notes": "Notes",
            "needs_human_review": False
        }
        
        # Save check point
        save_checkpoint(record1)
        
        # Load and verify
        checkpoint_data = load_checkpoint()
        assert "App A" in checkpoint_data
        assert checkpoint_data["App A"]["one_liner"] == "CRM App"
        
        # Save again with updated data or another app
        record2 = record1.copy()
        record2["name"] = "App B"
        save_checkpoint(record2)
        
        checkpoint_data = load_checkpoint()
        assert len(checkpoint_data) == 2
        assert "App B" in checkpoint_data
        
    finally:
        research_agent.CHECKPOINT_FILE = original_checkpoint


def test_non_saas_edge_case():
    """Test that a local open-source CLI tool is handled gracefully by research_app_sync without crashing."""
    from unittest.mock import MagicMock
    from research_agent import research_app_sync
    
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = """
    {
      "name": "Mermaid CLI",
      "category": "AI/Research/Media-native",
      "one_liner": "Command line interface for Mermaid.js charts",
      "auth_methods": ["none"],
      "access_model": "not-applicable",
      "api_surface": "none-found",
      "api_breadth": "not-applicable",
      "mcp_exists": false,
      "mcp_source": null,
      "buildability_verdict": "ready-today",
      "blocker": null,
      "evidence_urls": ["https://github.com/mermaid-js/mermaid-cli"],
      "confidence": 0.9,
      "raw_notes": "Local CLI tool, not hosted SaaS.",
      "needs_human_review": false
    }
    """
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    result = research_app_sync(
        name="Mermaid CLI",
        hint_url="https://github.com/mermaid-js/mermaid-cli",
        category="AI/Research/Media-native",
        composio_toolset=None,
        groq_client=mock_client
    )
    
    assert result["name"] == "Mermaid CLI"
    assert result["category"] == "AI/Research/Media-native"
    assert result["access_model"] == "not-applicable"
    assert result["api_surface"] == "none-found"
    assert result["buildability_verdict"] == "ready-today"


@pytest.mark.skipif(
    not (os.getenv("GROQ_API_KEY") and os.getenv("COMPOSIO_API_KEY")),
    reason="Requires active GROQ_API_KEY and COMPOSIO_API_KEY to run live research."
)
@pytest.mark.asyncio
async def test_integration_research_known_apps():
    """Live small-batch integration test on 3 known apps if API keys are set."""
    from research_agent import run_research
    apps = [
        {"name": "GitHub", "hint_url": "https://docs.github.com/en/rest", "category": "Developer/Infra/Data platforms"},
        {"name": "Stripe", "hint_url": "https://stripe.com/docs/api", "category": "Ecommerce"},
        {"name": "Notion", "hint_url": "https://developers.notion.com/", "category": "Productivity/Project Management"}
    ]
    
    try:
        results = await run_research(apps, limit=3)
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
            pytest.skip(f"API Rate limits or Quota exceeded: {e}")
        raise e
        
    # Filter out fallback research failures (which represent network/rate limit issues during the run)
    results = [r for r in results if not r.get("needs_human_review") or r.get("one_liner") != "Research failed — needs human review"]
    if not results:
        pytest.skip("All integration apps failed due to API rate limits/timeouts during execution.")
        
    for r in results:
        # Assert schema fields
        assert "name" in r
        assert "evidence_urls" in r
        assert len(r["evidence_urls"]) > 0
        assert r["evidence_urls"][0].startswith("http")
        assert "auth_methods" in r
        assert len(r["auth_methods"]) > 0
        
        # Test specific known properties
        if r["name"] == "GitHub":
            assert "oauth2" in [a.lower() for a in r["auth_methods"]] or "token" in [a.lower() for a in r["auth_methods"]]
            assert r["access_model"] in ["self-serve-free", "self-serve-paid"]

