"""Enrich defects with recurrence detection, severity bump, LLM fix hints, and business impact."""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Defect
from backend.services.llm_client import LLMClient, _is_placeholder_api_key

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = ("low", "medium", "high", "critical")


def _normalize_severity(raw: str | None) -> str:
    s = (raw or "medium").strip().lower()
    if s in _SEVERITY_ORDER:
        return s
    if s in ("crit", "sev1", "blocker"):
        return "critical"
    if s in ("error", "errors"):
        return "high"
    if s in ("warn", "warning", "moderate"):
        return "medium"
    if s in ("info", "note", "minor"):
        return "low"
    return "medium"


def _bump_severity(current: str) -> str:
    cur = _normalize_severity(current)
    try:
        i = _SEVERITY_ORDER.index(cur)
    except ValueError:
        i = 1
    if i >= len(_SEVERITY_ORDER) - 1:
        return "critical"
    return _SEVERITY_ORDER[i + 1]


def _llm_configured() -> bool:
    key = (os.environ.get("LLM_API_KEY") or "").strip()
    return bool(key) and not _is_placeholder_api_key(key)


def _tag_business_impact(page_url: str, issue_type: str, description: str) -> str:
    u = (page_url or "").lower()
    t = (issue_type or "").lower()
    d = (description or "").lower()
    combined = f"{u} {t} {d}"

    if "checkout" in u or "checkout" in combined:
        return "revenue"
    if "payment" in u or "cart" in u or "purchase" in u or "order" in combined:
        return "revenue"
    if "login" in u or "signin" in u or "sign-in" in u or "auth" in t:
        return "trust"
    if (
        "performance" in t
        or "performance" in d
        or "slow" in d
        or "latency" in d
        or "lcp" in d
        or "load time" in d
    ):
        return "performance"
    return "general"


def issue_dict_to_defect_mapping(issue: Mapping[str, Any] | dict[str, Any], page_url: str) -> dict[str, Any]:
    """Map a pipeline issue dict (structured_run_output) to the shape expected by enrich_defect."""
    if not isinstance(issue, Mapping):
        issue = {}
    return {
        "id": None,
        "scan_id": None,
        "page_url": str(page_url or ""),
        "issue_type": str(issue.get("defect") or issue.get("type") or "unknown"),
        "severity": str(issue.get("severity") or "medium"),
        "description": str(issue.get("message") or "")[:8000],
    }


def _defect_as_mapping(defect: Any) -> dict[str, Any]:
    if isinstance(defect, Defect):
        return {
            "id": defect.id,
            "scan_id": defect.scan_id,
            "page_url": defect.page_url,
            "issue_type": defect.issue_type,
            "severity": defect.severity,
            "description": defect.description,
        }
    if isinstance(defect, Mapping):
        return dict(defect)
    raise TypeError(f"defect must be a Defect ORM instance or mapping, got {type(defect)!r}")


class DefectIntelligenceService:
    """Augment defect records with recurrence, severity, LLM fix text, and impact tags."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    async def _count_prior_same_signature(
        self,
        session: AsyncSession,
        page_url: str,
        issue_type: str,
        exclude_defect_id: int | None,
    ) -> int:
        stmt = select(func.count()).select_from(Defect).where(
            Defect.page_url == page_url,
            Defect.issue_type == issue_type,
        )
        if exclude_defect_id is not None:
            stmt = stmt.where(Defect.id != exclude_defect_id)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def _generate_fix_suggestion(
        self,
        page_url: str,
        issue_type: str,
        severity: str,
        description: str,
        recurring: bool,
    ) -> str:
        if not _llm_configured():
            return ""
        try:
            llm = self._get_llm()
            sys = (
                "You are a senior QA engineer. Respond with 1–3 short, actionable sentences. "
                "No markdown fences."
            )
            user = (
                f"Issue type: {issue_type}\n"
                f"Severity: {severity}\n"
                f"Page: {page_url}\n"
                f"Recurring: {recurring}\n"
                f"Details: {description[:4000]}\n\n"
                "Suggest a concrete fix or verification step."
            )
            text = await llm.complete(sys, user)
            return (text or "").strip()
        except Exception as e:
            logger.debug("Fix suggestion LLM failed: %s", e)
            return ""

    async def enrich_defect(
        self,
        defect: Any,
        db_session: AsyncSession | None,
    ) -> dict[str, Any]:
        """
        Return original defect fields plus:
        recurring, fix_suggestion, business_impact, severity (possibly bumped).

        If ``db_session`` is None, recurrence is not queried (recurring=False) and
        enrichment still applies business impact and optional LLM fix text.
        """
        base = _defect_as_mapping(defect)
        page_url = str(base.get("page_url") or "")
        issue_type = str(base.get("issue_type") or "")
        description = str(base.get("description") or "")
        raw_severity = base.get("severity")

        exclude_id: int | None = None
        raw_id = base.get("id")
        if isinstance(raw_id, int):
            exclude_id = raw_id
        elif raw_id is not None:
            try:
                exclude_id = int(raw_id)
            except (TypeError, ValueError):
                exclude_id = None

        prior = 0
        if db_session is not None:
            try:
                prior = await self._count_prior_same_signature(
                    db_session,
                    page_url=page_url,
                    issue_type=issue_type,
                    exclude_defect_id=exclude_id,
                )
            except Exception as e:
                logger.debug("Prior defect count failed (DB): %s", e)
                prior = 0
        recurring = prior > 0

        severity = _normalize_severity(str(raw_severity) if raw_severity is not None else None)
        if recurring:
            severity = _bump_severity(severity)

        business_impact = _tag_business_impact(page_url, issue_type, description)

        fix_suggestion = await self._generate_fix_suggestion(
            page_url=page_url,
            issue_type=issue_type,
            severity=severity,
            description=description,
            recurring=recurring,
        )

        out: dict[str, Any] = {**base, "severity": severity}
        out["recurring"] = recurring
        out["fix_suggestion"] = fix_suggestion
        out["business_impact"] = business_impact
        return out
