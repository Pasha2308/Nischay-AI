"""Persist scan pipeline output to PostgreSQL (best-effort, optional)."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Defect, PageFingerprint, RiskSnapshot, Scan
from backend.db.session import ensure_schema, get_async_session_maker, init_db_engine
from shared.models.site_model import SiteModel
from shared.models.test_result import RunResult

logger = logging.getLogger(__name__)


def _fingerprint_hash(url: str, page_id: str = "", title: str = "") -> str:
    raw = f"{url}|{page_id}|{title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _scan_status(structured: dict[str, Any]) -> str:
    if structured.get("status") == "partial":
        return "partial"
    if structured.get("partial"):
        return "partial"
    issues = structured.get("issues") or []
    if any(i.get("type") == "pipeline_error" for i in issues):
        return "failed"
    return "complete"


def _page_url_for_issue(
    issue: dict[str, Any],
    run_result: RunResult | None,
    site_model: SiteModel | None,
    fallback_url: str,
) -> str:
    tid = issue.get("test_id")
    if run_result and isinstance(tid, str):
        for tr in run_result.test_results:
            if tr.test_id == tid:
                u = (tr.actual_url or "").strip()
                if u:
                    return u
                if site_model and tr.target_page_id:
                    for p in site_model.pages:
                        if p.page_id == tr.target_page_id and p.url:
                            return p.url
    return fallback_url or ""


def _risk_score_value(structured: dict[str, Any]) -> float | None:
    rs = structured.get("risk_score")
    if rs is None:
        return None
    try:
        return float(rs)
    except (TypeError, ValueError):
        return None


def _risk_int(r: float | None) -> int | None:
    if r is None:
        return None
    try:
        return int(round(float(r)))
    except (TypeError, ValueError):
        return None


def _defect_signature(page_url: str, issue_type: str, description: str) -> str:
    p = (page_url or "").strip().lower()[:2048]
    t = (issue_type or "").strip().lower()[:256]
    d = (description or "").strip()[:500]
    raw = f"{p}|{t}|{d}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _defect_signatures_for_scan(session: AsyncSession, scan_id: int) -> set[str]:
    stmt = select(Defect).where(Defect.scan_id == scan_id)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return {_defect_signature(r.page_url, r.issue_type, r.description) for r in rows}


async def _count_defects_for_scan(session: AsyncSession, scan_id: int) -> int:
    q = select(func.count()).select_from(Defect).where(Defect.scan_id == scan_id)
    return int((await session.execute(q)).scalar_one() or 0)


async def compute_delta_report(
    session: AsyncSession,
    url: str,
    current_scan_id: int,
    structured: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Compare current scan to the prior scan for the same URL (anomaly / trend).

    Returns delta_report with new_issues, resolved_issues, risk_change, recent_scans (last 3).
    """
    try:
        stmt_recent = (
            select(Scan)
            .where(Scan.url == url)
            .order_by(Scan.created_at.desc())
            .limit(3)
        )
        scans = list((await session.execute(stmt_recent)).scalars().all())

        stmt_prev = (
            select(Scan)
            .where(Scan.url == url, Scan.id < current_scan_id)
            .order_by(Scan.id.desc())
            .limit(1)
        )
        prev = (await session.execute(stmt_prev)).scalars().first()
    except Exception as e:
        logger.debug("compute_delta_report scan query failed: %s", e)
        return None

    if not scans:
        return None

    current_sigs = await _defect_signatures_for_scan(session, current_scan_id)
    current_risk = _risk_int(_risk_score_value(structured))
    if current_risk is None:
        cur_row = next((s for s in scans if s.id == current_scan_id), None)
        if cur_row is not None:
            current_risk = _risk_int(cur_row.risk_score)

    recent_scans: list[dict[str, Any]] = []
    for s in scans:
        try:
            recent_scans.append(
                {
                    "scan_id": s.id,
                    "risk_score": _risk_int(s.risk_score),
                    "defect_count": await _count_defects_for_scan(session, s.id),
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
            )
        except Exception:
            continue

    base: dict[str, Any] = {
        "new_issues": 0,
        "resolved_issues": 0,
        "risk_change": None,
        "previous_risk_score": None,
        "current_risk_score": current_risk,
        "previous_defect_count": None,
        "current_defect_count": len(current_sigs),
        "compared_to_scan_id": None,
        "recent_scans": recent_scans,
        "trend_direction": "unknown",
    }

    if prev is None:
        base["new_issues"] = len(current_sigs)
        base["resolved_issues"] = 0
        base["trend_direction"] = "unknown"
        return base

    prev_sigs = await _defect_signatures_for_scan(session, prev.id)
    prev_risk = _risk_int(prev.risk_score)
    prev_count = len(prev_sigs)

    new_issues = len(current_sigs - prev_sigs)
    resolved_issues = len(prev_sigs - current_sigs)
    risk_change: int | None = None
    if current_risk is not None and prev_risk is not None:
        risk_change = current_risk - prev_risk

    if risk_change is None:
        trend_direction = "unknown"
    elif risk_change > 0:
        trend_direction = "worse"
    elif risk_change < 0:
        trend_direction = "better"
    else:
        trend_direction = "stable"

    base.update(
        {
            "new_issues": new_issues,
            "resolved_issues": resolved_issues,
            "risk_change": risk_change,
            "previous_risk_score": prev_risk,
            "current_risk_score": current_risk,
            "previous_defect_count": prev_count,
            "current_defect_count": len(current_sigs),
            "compared_to_scan_id": prev.id,
            "trend_direction": trend_direction,
        }
    )
    return base


def _ensure_report_id(structured: dict[str, Any]) -> str:
    rid = (structured.get("report_id") or "").strip()
    if not rid:
        rid = str(uuid.uuid4())
    structured["report_id"] = rid
    return rid


def _build_result_snapshot(
    structured: dict[str, Any], delta_report: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "summary": structured.get("summary"),
        "issues": structured.get("issues") or [],
        "risk_score": structured.get("risk_score"),
        "delta": delta_report if isinstance(delta_report, dict) else structured.get("delta_report"),
    }


async def fetch_report_by_id(report_id: str) -> dict[str, Any] | None:
    """
    Load shareable payload for GET /report/{report_id}.

    Returns dict with keys summary, issues, risk_score, delta, or None if not found / DB off.
    """
    init_db_engine()
    maker = get_async_session_maker()
    if maker is None:
        return None
    engine = init_db_engine()
    if engine is None:
        return None
    try:
        await ensure_schema(engine)
    except Exception as e:
        logger.warning("DB schema ensure failed: %s", e)
        return None

    rid = (report_id or "").strip()
    if not rid:
        return None

    try:
        async with maker() as session:
            stmt = (
                select(Scan)
                .where(Scan.report_id == rid)
                .options(selectinload(Scan.defects))
            )
            row = (await session.execute(stmt)).scalars().first()
            if row is None:
                return None
            snap = row.result_snapshot
            if isinstance(snap, dict) and snap:
                out = {
                    "report_id": row.report_id,
                    "summary": snap.get("summary"),
                    "issues": snap.get("issues") or [],
                    "risk_score": snap.get("risk_score"),
                    "delta": snap.get("delta"),
                }
                return out
            # Fallback: minimal reconstruction from stored scan row + defects
            issues: list[dict[str, Any]] = []
            for d in row.defects or []:
                issues.append(
                    {
                        "type": d.issue_type,
                        "severity": d.severity,
                        "message": d.description,
                        "page_url": d.page_url,
                    }
                )
            return {
                "report_id": row.report_id,
                "summary": {},
                "issues": issues,
                "risk_score": row.risk_score,
                "delta": None,
            }
    except Exception as e:
        logger.warning("fetch_report_by_id failed: %s", e)
        return None


async def persist_pipeline_result(
    target_url: str,
    structured: dict[str, Any],
    site_model: SiteModel | None,
    run_result: RunResult | None,
) -> tuple[int | None, dict[str, Any] | None, str | None]:
    """
    Save Scan, Defects, RiskSnapshot, and PageFingerprints.

    Returns (scan_id, delta_report, report_id).
    On DB disabled or error: (None, None, report_id) with report_id still set on structured.
    delta_report compares this run to the prior scan for the same URL (when available).
    """
    report_id = _ensure_report_id(structured)

    init_db_engine()
    maker = get_async_session_maker()
    if maker is None:
        return None, None, report_id

    engine = init_db_engine()
    if engine is None:
        return None, None, report_id

    try:
        await ensure_schema(engine)
    except Exception as e:
        logger.warning("DB schema ensure failed: %s", e)
        return None, None, report_id

    status = _scan_status(structured)
    risk = _risk_score_value(structured)
    issues = structured.get("issues") or []
    fallback = (run_result.target_url if run_result else "") or target_url

    try:
        async with maker() as session:
            scan = Scan(
                report_id=report_id,
                url=target_url,
                status=status,
                risk_score=risk,
            )
            session.add(scan)
            await session.flush()

            for issue in issues:
                try:
                    page_url = _page_url_for_issue(issue, run_result, site_model, fallback)
                    issue_type = str(
                        issue.get("type") or issue.get("defect") or "unknown"
                    )[:256]
                    severity = str(issue.get("severity") or "medium")[:64]
                    desc = str(issue.get("message") or "")[:50000]
                    session.add(
                        Defect(
                            scan_id=scan.id,
                            page_url=page_url[:2048],
                            issue_type=issue_type,
                            severity=severity,
                            description=desc,
                        )
                    )
                except Exception as ie:
                    logger.debug("Skip defect row: %s", ie)

            if risk is not None:
                session.add(
                    RiskSnapshot(
                        scan_id=scan.id,
                        risk_score=risk,
                        timestamp=datetime.now(timezone.utc),
                    )
                )

            if site_model and site_model.pages:
                for page in site_model.pages:
                    try:
                        u = (page.url or "").strip()
                        if not u:
                            continue
                        h = _fingerprint_hash(u, page.page_id, page.title or "")
                        stmt = (
                            pg_insert(PageFingerprint.__table__)
                            .values(url=u[:2048], hash=h)
                            .on_conflict_do_update(
                                index_elements=[PageFingerprint.__table__.c.url],
                                set_={"hash": h},
                            )
                        )
                        await session.execute(stmt)
                    except Exception as pe:
                        logger.debug("Page fingerprint upsert skipped: %s", pe)

            delta_report: dict[str, Any] | None = None
            try:
                delta_report = await compute_delta_report(
                    session, target_url, scan.id, structured
                )
            except Exception as de:
                logger.debug("Delta report skipped: %s", de)

            if delta_report is not None:
                structured["delta_report"] = delta_report
            scan.result_snapshot = _build_result_snapshot(structured, delta_report)

            await session.commit()
            return scan.id, delta_report, report_id
    except Exception as e:
        logger.warning("Scan persistence failed (non-fatal): %s", e)
        return None, None, report_id
