"""
schema.py — Pydantic models for the Composio App Research pipeline.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums for controlled vocabulary fields
# ---------------------------------------------------------------------------

class AccessModel(str, Enum):
    SELF_SERVE_FREE = "self-serve-free"
    SELF_SERVE_PAID = "self-serve-paid"
    GATED_APPROVAL = "gated-approval"
    GATED_PARTNERSHIP = "gated-partnership"
    NOT_APPLICABLE = "not-applicable"


class ApiSurface(str, Enum):
    REST = "REST"
    GRAPHQL = "GraphQL"
    REST_WEBHOOKS = "REST+Webhooks"
    REST_GRAPHQL = "REST+GraphQL"
    SDK_ONLY = "SDK-only"
    NONE_FOUND = "none-found"


class ApiBreadth(str, Enum):
    BROAD = "broad"
    NARROW = "narrow"
    UNDOCUMENTED = "undocumented"
    NOT_APPLICABLE = "not-applicable"


class BuildabilityVerdict(str, Enum):
    READY_TODAY = "ready-today"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Primary model: one record per researched app
# ---------------------------------------------------------------------------

class AppResearch(BaseModel):
    name: str
    category: str
    one_liner: str
    auth_methods: list[str]
    access_model: str          # self-serve-free | self-serve-paid | gated-approval | gated-partnership | not-applicable
    api_surface: str           # REST | GraphQL | REST+Webhooks | REST+GraphQL | SDK-only | none-found
    api_breadth: str           # broad | narrow | undocumented | not-applicable
    mcp_exists: bool
    mcp_source: Optional[str]
    buildability_verdict: str  # ready-today | blocked
    blocker: Optional[str]
    evidence_urls: list[str]
    confidence: float          # 0.0 – 1.0
    raw_notes: str
    needs_human_review: bool = False

    @field_validator("access_model")
    @classmethod
    def validate_access_model(cls, v: str) -> str:
        valid = {e.value for e in AccessModel}
        if v not in valid:
            raise ValueError(
                f"access_model must be one of {sorted(valid)}, got '{v}'"
            )
        return v

    @field_validator("buildability_verdict")
    @classmethod
    def validate_buildability_verdict(cls, v: str) -> str:
        valid = {e.value for e in BuildabilityVerdict}
        if v not in valid:
            raise ValueError(
                f"buildability_verdict must be one of {sorted(valid)}, got '{v}'"
            )
        return v

    @field_validator("api_surface")
    @classmethod
    def validate_api_surface(cls, v: str) -> str:
        valid = {e.value for e in ApiSurface}
        if v not in valid:
            raise ValueError(
                f"api_surface must be one of {sorted(valid)}, got '{v}'"
            )
        return v

    @field_validator("api_breadth")
    @classmethod
    def validate_api_breadth(cls, v: str) -> str:
        valid = {e.value for e in ApiBreadth}
        if v not in valid:
            raise ValueError(
                f"api_breadth must be one of {sorted(valid)}, got '{v}'"
            )
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return round(v, 3)

    @field_validator("evidence_urls")
    @classmethod
    def validate_evidence_urls(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("evidence_urls must contain at least one URL")
        for url in v:
            if not (url.startswith("http://") or url.startswith("https://")):
                raise ValueError(f"Invalid URL format: {url}")
        return v

    @field_validator("auth_methods")
    @classmethod
    def validate_auth_methods(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("auth_methods must contain at least one entry")
        return v

    @model_validator(mode="after")
    def check_blocked_has_blocker(self) -> "AppResearch":
        if self.buildability_verdict == "blocked" and not self.blocker:
            raise ValueError("blocker must be set when buildability_verdict is 'blocked'")
        if self.mcp_exists and not self.mcp_source:
            raise ValueError("mcp_source must be set when mcp_exists is True")
        return self


# ---------------------------------------------------------------------------
# Verification model: diff between pass-1 and pass-2 for a single field
# ---------------------------------------------------------------------------

class VerificationDiff(BaseModel):
    app_name: str
    field: str
    pass1_value: str
    pass2_value: str
    agrees: bool
    human_resolved_value: Optional[str] = None
    human_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Accuracy report container
# ---------------------------------------------------------------------------

class AccuracyReport(BaseModel):
    sampled_apps: list[str]
    diffs: list[VerificationDiff]
    needs_human_review_apps: list[str]
    pass1_raw_accuracy: float        # fraction of sampled fields where pass-1 == pass-2
    pass2_agreement_rate: float      # same as pass1_raw_accuracy (alias for clarity)
    final_human_corrected_accuracy: float   # computed after human resolution
    total_fields_checked: int
    total_disagreements: int
    human_corrections_count: int
