"""Small, quota-aware client for the new JSON API."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

import requests


API_BASE = os.environ.get("BB_V1_API_BASE", "https://sb1-api.buzzerbeater.com/v1").rstrip("/")


@dataclass
class V1ApiError(Exception):
    status: int
    code: str
    description: str
    retry_after: int | None = None
    reset_at: int | None = None

    def __str__(self) -> str:
        return self.description or f"BuzzerBeater API error {self.status}"


class V1Client:
    def __init__(self, token: str, *, session: requests.Session | None = None, base_url: str = API_BASE, on_unauthorized: Callable[[str], str | None] | None = None):
        if not token:
            raise ValueError("A v1 bearer token is required.")
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
        self.base_url = base_url.rstrip("/")
        self.last_limits: dict[str, str] = {}
        self.on_unauthorized = on_unauthorized

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("API path must be relative to the v1 base URL.")
        refreshed = False
        for attempt in range(4):
            try:
                response = self.session.get(self.base_url + path, params=params, timeout=25)
            except requests.RequestException as exc:
                raise V1ApiError(503, "NetworkError", "Could not reach the BuzzerBeater API.") from exc
            self.last_limits = {
                name: response.headers.get(name, "")
                for name in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset")
            }
            if response.ok:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise V1ApiError(response.status_code, "InvalidResponse", "The API returned invalid JSON.") from exc
                if not isinstance(payload, dict):
                    raise V1ApiError(response.status_code, "InvalidResponse", "The API returned an unexpected response.")
                return payload
            if response.status_code == 401 and self.on_unauthorized and not refreshed:
                old_token = self.session.headers["Authorization"].removeprefix("Bearer ")
                new_token = self.on_unauthorized(old_token)
                refreshed = True
                if new_token:
                    self.session.headers["Authorization"] = f"Bearer {new_token}"
                    continue
            try:
                error = response.json().get("error", {})
            except ValueError:
                error = {}
            if not isinstance(error, dict):
                error = {}
            code = str(error.get("code") or "ApiError")
            description = str(error.get("description") or f"The API returned HTTP {response.status_code}.")
            retry = response.headers.get("Retry-After", "")
            reset = response.headers.get("X-RateLimit-Reset", "")
            retry_after = int(retry) if retry.isdigit() else None
            reset_at = int(reset) if reset.isdigit() else None
            retryable_limit = response.status_code == 429 and code == "RateLimited" and (retry_after is None or retry_after <= 10)
            if attempt < 3 and (retryable_limit or response.status_code == 503):
                time.sleep(retry_after if retry_after is not None else min(2 ** attempt, 10))
                continue
            raise V1ApiError(response.status_code, code, description, retry_after, reset_at)
        raise AssertionError("unreachable")


def segment(value: str) -> str:
    """Quote one opaque API identifier without assuming an integer format."""
    if not value or "/" in value or "\\" in value:
        raise ValueError("Invalid API identifier.")
    return quote(value, safe="")


def pages(client: V1Client, path: str, collection: str, *, params: dict[str, Any] | None = None, max_items: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while offset < max_items:
        limit = min(30, max_items - offset)
        page = client.get(path, {**(params or {}), "offset": offset, "limit": limit})
        batch = page.get(collection, [])
        if not isinstance(batch, list):
            raise V1ApiError(200, "InvalidResponse", f"Expected {collection} to be a list.")
        rows.extend(row for row in batch if isinstance(row, dict))
        if len(batch) < limit:
            break
        offset += limit
    return rows
