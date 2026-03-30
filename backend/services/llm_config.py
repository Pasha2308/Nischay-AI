from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LLMConfig

logger = logging.getLogger(__name__)

Provider = Literal["groq", "openai", "anthropic"]

PROVIDER_MODELS: dict[str, list[dict[str, Any]]] = {
    "groq": [
        {
            "id": "llama-3.3-70b-versatile",
            "label": "Llama 3.3 70B",
            "speed": "fast",
            "tier": "free",
            "recommended": True,
        },
        {
            "id": "llama-3.1-8b-instant",
            "label": "Llama 3.1 8B Instant",
            "speed": "very fast",
            "tier": "free",
            "recommended": False,
        },
        {
            "id": "gemma2-9b-it",
            "label": "Gemma 2 9B",
            "speed": "fast",
            "tier": "free",
            "recommended": False,
        },
    ],
    "openai": [
        {
            "id": "gpt-4o",
            "label": "GPT-4o",
            "speed": "medium",
            "tier": "paid",
            "recommended": True,
        },
        {
            "id": "gpt-4o-mini",
            "label": "GPT-4o Mini",
            "speed": "fast",
            "tier": "paid",
            "recommended": False,
        },
        {
            "id": "gpt-3.5-turbo",
            "label": "GPT-3.5 Turbo",
            "speed": "very fast",
            "tier": "paid",
            "recommended": False,
        },
    ],
    "anthropic": [
        {
            "id": "claude-sonnet-4-20250514",
            "label": "Claude Sonnet 4",
            "speed": "medium",
            "tier": "paid",
            "recommended": True,
        },
        {
            "id": "claude-haiku-4-5-20251001",
            "label": "Claude Haiku 4.5",
            "speed": "fast",
            "tier": "paid",
            "recommended": False,
        },
    ],
}


def _fernet_from_secret() -> Fernet:
    secret = (os.environ.get("SECRET_KEY") or "").strip()
    if not secret:
        raise ValueError("SECRET_KEY is not set (required for encrypting LLM API keys)")
    # Derive a 32-byte key for Fernet
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_key(plaintext: str) -> str:
    f = _fernet_from_secret()
    return f.encrypt((plaintext or "").encode("utf-8")).decode("utf-8")


def decrypt_key(ciphertext: str) -> str:
    f = _fernet_from_secret()
    return f.decrypt((ciphertext or "").encode("utf-8")).decode("utf-8")


def mask_key(plaintext: str) -> str:
    k = (plaintext or "").strip()
    if len(k) <= 12:
        return (k[:4] + "...") if k else ""
    return f"{k[:8]}...{k[-4:]}"


async def get_active_llm_config(db: AsyncSession) -> LLMConfig | None:
    return (await db.execute(select(LLMConfig).where(LLMConfig.is_active == 1))).scalars().first()


def provider_base_url(provider: str) -> str:
    p = (provider or "").strip().lower()
    if p == "groq":
        return "https://api.groq.com/openai/v1"
    if p == "openai":
        return "https://api.openai.com/v1"
    if p == "anthropic":
        return "https://api.anthropic.com"
    return ""


async def verify_llm_key(provider: Provider, api_key: str, model_name: str) -> tuple[bool, str | None, int]:
    """
    Returns (valid, error, models_available_count).
    """
    key = (api_key or "").strip()
    if not key:
        return False, "api_key is empty", 0
    base = provider_base_url(provider)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            if provider in ("groq", "openai"):
                res = await client.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
                if res.status_code >= 400:
                    return False, f"{provider} models list failed: {res.status_code} {res.text[:200]}", 0
                data = res.json()
                models = data.get("data") or []
                return True, None, len(models) if isinstance(models, list) else 0
            # anthropic minimal request
            res = await client.post(
                f"{base}/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model_name,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
            if res.status_code >= 400:
                return False, f"anthropic verify failed: {res.status_code} {res.text[:200]}", 0
            return True, None, 1
    except Exception as e:
        return False, str(e), 0


async def save_active_llm_config(
    db: AsyncSession,
    *,
    provider: Provider,
    api_key: str,
    model_name: str,
    verified: bool,
) -> LLMConfig:
    # deactivate all
    await db.execute(update(LLMConfig).values(is_active=0))
    row = LLMConfig(
        id=str(os.urandom(16).hex())[:36],
        provider=str(provider),
        api_key_encrypted=encrypt_key(api_key),
        model_name=str(model_name),
        is_active=1,
        verified_at=datetime.now(tz=timezone.utc) if verified else None,
    )
    db.add(row)
    await db.flush()
    return row

