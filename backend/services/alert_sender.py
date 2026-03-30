from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AlertConfig, Notification

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _risk_level(score: int) -> str:
    s = max(0, min(100, int(score)))
    if s >= 75:
        return "CRITICAL"
    if s >= 50:
        return "HIGH"
    if s >= 30:
        return "MEDIUM"
    return "LOW"


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _issues(scan_result: dict[str, Any]) -> list[dict[str, Any]]:
    raw = scan_result.get("issues") or scan_result.get("defects") or []
    return [dict(x) for x in raw if isinstance(x, dict)]


def _count_critical(issues: list[dict[str, Any]]) -> int:
    return sum(1 for d in issues if str(d.get("severity") or "").lower() == "critical")


def _top_issue_title(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No issues detected"
    d0 = issues[0]
    return str(d0.get("title") or d0.get("message") or d0.get("description") or "Issue")[:200]


async def get_enabled_alert_configs(db_session: AsyncSession) -> list[AlertConfig]:
    rows = (await db_session.execute(select(AlertConfig).where(AlertConfig.is_enabled == 1))).scalars().all()
    return list(rows)


def _should_send(rules: dict[str, Any], scan_result: dict[str, Any], issues: list[dict[str, Any]]) -> tuple[bool, str]:
    # Returns (should_send, reason)
    risk_score = int(scan_result.get("risk_score") or 0)
    if bool(rules.get("on_run_complete")):
        return True, "on_run_complete"
    thr = rules.get("risk_score_above")
    if thr is not None:
        try:
            thr_i = int(thr)
            if risk_score > thr_i:
                return True, f"risk_score_above:{thr_i}"
        except (TypeError, ValueError):
            pass
    if bool(rules.get("on_critical_defect")) and any(str(d.get("severity") or "").lower() == "critical" for d in issues):
        return True, "on_critical_defect"
    return False, ""


async def send_slack_alert(config: AlertConfig, scan_result: dict[str, Any], reason: str) -> tuple[bool, str]:
    cfg = config.config or {}
    webhook_url = str(cfg.get("webhook_url") or "").strip()
    if not webhook_url:
        return False, "missing slack webhook_url"

    issues = _issues(scan_result)
    risk_score = int(scan_result.get("risk_score") or 0)
    url = str(scan_result.get("target_url") or scan_result.get("url") or "")
    scan_id = str(scan_result.get("scan_id") or scan_result.get("job_id") or "")
    level = _risk_level(risk_score)
    title = _top_issue_title(issues)
    duration = scan_result.get("duration")
    try:
        duration_s = f"{int(duration)}s" if duration is not None else "—"
    except Exception:
        duration_s = "—"

    frontend_base = (os.environ.get("FRONTEND_BASE_URL") or "http://localhost:5173").strip().rstrip("/")
    view_url = f"{frontend_base}/results/{scan_id}" if scan_id else f"{frontend_base}/results"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🔴 {level}: Risk Score {risk_score} on {_domain(url)}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*URL:*\n{url or '—'}"},
                    {"type": "mrkdwn", "text": f"*Risk Level:*\n{level}"},
                    {"type": "mrkdwn", "text": f"*Issues Found:*\n{len(issues)} ({_count_critical(issues)} critical)"},
                    {"type": "mrkdwn", "text": f"*Scan Duration:*\n{duration_s}"},
                ],
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Top Issue:* {title}"}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Full Report"},
                        "url": view_url,
                        "style": "primary",
                    }
                ],
            },
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            res = await client.post(webhook_url, json=payload)
            if res.status_code >= 400:
                return False, f"slack webhook error {res.status_code}: {res.text[:200]}"
    except Exception as e:
        return False, str(e)
    return True, f"sent (reason={reason})"


async def send_webhook_alert(config: AlertConfig, scan_result: dict[str, Any], reason: str) -> tuple[bool, str]:
    cfg = config.config or {}
    url = str(cfg.get("url") or "").strip()
    if not url:
        return False, "missing webhook url"
    secret = str(cfg.get("secret") or "").strip()
    body = json.dumps(scan_result, default=str).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if secret:
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Nischay-Signature"] = sig
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            res = await client.post(url, content=body, headers=headers)
            if res.status_code >= 400:
                return False, f"webhook error {res.status_code}: {res.text[:200]}"
    except Exception as e:
        return False, str(e)
    return True, f"sent (reason={reason})"


async def send_email_alert(config: AlertConfig, scan_result: dict[str, Any], reason: str) -> tuple[bool, str]:
    # Best-effort: requires SMTP env vars; otherwise returns a clear error.
    cfg = config.config or {}
    recips = cfg.get("recipients") or []
    if not isinstance(recips, list) or not recips:
        return False, "no email recipients configured"
    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()
    smtp_user = (os.environ.get("SMTP_USER") or "").strip()
    smtp_pass = (os.environ.get("SMTP_PASS") or "").strip()
    sender = (os.environ.get("SMTP_SENDER") or smtp_user or "").strip()
    if not smtp_host or not sender:
        return False, "SMTP not configured (set SMTP_HOST/SMTP_SENDER and credentials)"

    # Avoid blocking the event loop with smtplib: we keep this minimal and asynchronous by design
    # (production should use a provider SDK). For now, report configuration required.
    _ = (smtp_user, smtp_pass, reason, scan_result)
    return False, "email sending not configured in this environment"


async def store_in_app_notification(config: AlertConfig, scan_result: dict[str, Any], reason: str, db_session: AsyncSession) -> tuple[bool, str]:
    _ = config
    issues = _issues(scan_result)
    risk_score = int(scan_result.get("risk_score") or 0)
    url = str(scan_result.get("target_url") or scan_result.get("url") or "")
    scan_id = str(scan_result.get("scan_id") or scan_result.get("job_id") or "")
    level = _risk_level(risk_score)
    title = f"{level}: Risk {risk_score} on {_domain(url)}"
    body = _top_issue_title(issues)
    n = Notification(
        id=str(hashlib.sha256(f"{scan_id}|{_now_utc().timestamp()}".encode("utf-8")).hexdigest()[:36]),
        channel="in_app",
        title=title,
        body=body,
        payload={"scan_id": scan_id, "url": url, "risk_score": risk_score, "reason": reason},
    )
    db_session.add(n)
    await db_session.flush()
    return True, "stored"


async def record_alert_event(db_session: AsyncSession, channel: str, scan_result: dict[str, Any], reason: str, success: bool, message: str) -> None:
    # Use Notification table as unified alert history store (non in-app notifications still stored for history).
    url = str(scan_result.get("target_url") or scan_result.get("url") or "")
    scan_id = str(scan_result.get("scan_id") or scan_result.get("job_id") or "")
    risk_score = int(scan_result.get("risk_score") or 0)
    title = f"alert:{channel} {'sent' if success else 'failed'}"
    body = f"{reason} — {url} — risk {risk_score}"
    n = Notification(
        id=str(hashlib.sha256(f"alert|{channel}|{scan_id}|{_now_utc().timestamp()}".encode("utf-8")).hexdigest()[:36]),
        channel=str(channel),
        title=title,
        body=body,
        payload={
            "scan_id": scan_id,
            "url": url,
            "risk_score": risk_score,
            "reason": reason,
            "success": bool(success),
            "message": message,
        },
    )
    db_session.add(n)
    await db_session.flush()


async def send_alerts_for_scan(scan_result: dict[str, Any], db_session: AsyncSession) -> None:
    """Called after every scan completes."""
    configs = await get_enabled_alert_configs(db_session)
    issues = _issues(scan_result)
    for cfg in configs:
        rules = cfg.trigger_rules or {}
        should_send, reason = _should_send(rules if isinstance(rules, dict) else {}, scan_result, issues)
        if not should_send:
            continue

        ok = False
        msg = ""
        try:
            if cfg.channel == "slack":
                ok, msg = await send_slack_alert(cfg, scan_result, reason)
            elif cfg.channel == "email":
                ok, msg = await send_email_alert(cfg, scan_result, reason)
            elif cfg.channel == "webhook":
                ok, msg = await send_webhook_alert(cfg, scan_result, reason)
            elif cfg.channel == "in_app":
                ok, msg = await store_in_app_notification(cfg, scan_result, reason, db_session)
            else:
                ok, msg = False, f"unknown channel {cfg.channel!r}"
        except Exception as e:
            ok, msg = False, str(e)

        try:
            await record_alert_event(db_session, str(cfg.channel), scan_result, reason, ok, msg)
        except Exception:
            pass

