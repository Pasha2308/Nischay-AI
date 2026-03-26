"""URL normalization and stable page IDs."""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication (scheme/host/lowercase, trim fragments)."""
    if not url:
        return ""
    p = urlparse(url)
    scheme = (p.scheme or "http").lower()
    netloc = (p.netloc or "").lower()
    path = p.path or "/"
    # keep query (can identify distinct pages), drop fragments
    normalized = urlunparse((scheme, netloc, path, "", p.query or "", ""))
    # remove trailing slash except for root
    if normalized.endswith("/") and path != "/":
        normalized = normalized[:-1]
    return normalized


def page_id_from_url(url: str) -> str:
    """Generate a stable, filesystem-safe ID for a URL."""
    n = normalize_url(url)
    digest = hashlib.sha256(n.encode("utf-8")).hexdigest()[:12]
    p = urlparse(n)
    host = (p.netloc or "site").replace(":", "_")
    return f"page_{host}_{digest}"

