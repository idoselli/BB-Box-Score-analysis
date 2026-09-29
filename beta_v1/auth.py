"""OAuth PKCE and encrypted, server-side v1 token sessions."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlencode

import requests
from flask import request

from .api import API_BASE, V1Client


AUTHORIZE_URL = os.environ.get("BB_V1_AUTHORIZE_URL", "https://sb1.buzzerbeater.com/oauth/authorize")
SCOPES = {"Public", "Team", "National", "Market"}
FEATURE_SCOPES = {
    "public": {"Public"},
    "training": {"Public", "Team"},
    "national": {"Public", "National"},
    "market": {"Public", "Market"},
}
_local_sessions: dict[str, dict[str, Any]] = {}
_local_lock = threading.Lock()


def configured() -> bool:
    return all(os.environ.get(key) for key in ("BB_V1_CLIENT_ID", "BB_V1_CLIENT_SECRET", "BB_V1_REDIS_URL", "BB_V1_TOKEN_ENCRYPTION_KEY"))


def token_signin_available() -> bool:
    if os.environ.get("BB_V1_REDIS_URL") and os.environ.get("BB_V1_TOKEN_ENCRYPTION_KEY"):
        return True
    return os.environ.get("BB_V1_ALLOW_INMEMORY_TOKEN_LOGIN") == "true" and request.host.split(":", 1)[0] in {"localhost", "127.0.0.1"} and request.remote_addr in {"localhost", "127.0.0.1", "::1"}


def _use_redis() -> bool:
    return bool(os.environ.get("BB_V1_REDIS_URL") and os.environ.get("BB_V1_TOKEN_ENCRYPTION_KEY"))


def _redis():
    import redis

    return redis.Redis.from_url(os.environ["BB_V1_REDIS_URL"], decode_responses=False)


def _fernet():
    from cryptography.fernet import Fernet

    return Fernet(os.environ["BB_V1_TOKEN_ENCRYPTION_KEY"].encode("ascii"))


def _key(kind: str, identifier: str) -> str:
    return f"bb-v1:{kind}:{identifier}"


def save_session(sid: str, value: dict[str, Any]) -> None:
    if not _use_redis() and not token_signin_available():
        raise RuntimeError("Encrypted server-side token storage is not configured.")
    lifetime = 86400 if value.get("kind") == "personal" else 90 * 86400
    value["session_expires_at"] = time.time() + lifetime
    if _use_redis():
        encrypted = _fernet().encrypt(json.dumps(value).encode("utf-8"))
        _redis().set(_key("session", sid), encrypted, ex=lifetime)
    else:
        with _local_lock:
            _local_sessions[sid] = value.copy()


def load_session(sid: str) -> dict[str, Any] | None:
    if not sid:
        return None
    if _use_redis():
        encrypted = _redis().get(_key("session", sid))
        if not encrypted:
            return None
        try:
            result = json.loads(_fernet().decrypt(encrypted))
        except Exception:
            return None
    else:
        with _local_lock:
            result = _local_sessions.get(sid)
    if result and result.get("session_expires_at", 0) <= time.time():
        delete_session(sid)
        return None
    return result if isinstance(result, dict) else None


def delete_session(sid: str) -> None:
    if sid:
        if _use_redis():
            _redis().delete(_key("session", sid))
        else:
            with _local_lock:
                _local_sessions.pop(sid, None)


def sign_in_with_token(token: str) -> tuple[str, dict[str, Any]]:
    if not token_signin_available():
        raise RuntimeError("Encrypted server-side token storage is not configured.")
    token = token.strip()
    if not token or len(token) > 4096:
        raise ValueError("Enter a valid API token.")
    me = V1Client(token).get("/me")
    if "Public" not in me.get("scopes", []):
        raise ValueError("This token needs Public access to use the beta site.")
    sid = secrets.token_hex(32)
    record = {"kind": "personal", "access_token": token, "scopes": me.get("scopes", []), "me": me, "csrf": secrets.token_urlsafe(32)}
    save_session(sid, record)
    return sid, record


def sid_from_request() -> str:
    sid = request.cookies.get("bb_beta_sid", "")
    return sid if len(sid) == 64 and all(c in "0123456789abcdef" for c in sid) else ""


def cookie_secure() -> bool:
    return request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip() == "https"


def redirect_uri() -> str:
    configured_uri = os.environ.get("BB_V1_REDIRECT_URI")
    if configured_uri:
        return configured_uri
    return request.url_root.rstrip("/") + "/beta/oauth/callback"


def start_authorization(feature: str) -> tuple[str, str]:
    if not configured():
        raise RuntimeError("Beta OAuth is not configured.")
    requested = FEATURE_SCOPES.get(feature)
    if requested is None:
        raise ValueError("Unknown beta feature.")
    requested = set(requested)
    existing = load_session(sid_from_request())
    if existing:
        requested |= set(existing.get("scopes", [])) & SCOPES
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    _redis().set(
        _key("oauth", state),
        json.dumps({"verifier": verifier, "feature": feature, "scope": sorted(requested)}),
        ex=600,
    )
    query = urlencode({
        "response_type": "code",
        "client_id": os.environ["BB_V1_CLIENT_ID"],
        "redirect_uri": redirect_uri(),
        "scope": " ".join(scope.lower() for scope in sorted(requested)),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{AUTHORIZE_URL}?{query}", state


def exchange_code(code: str, state: str) -> tuple[str, dict[str, Any], str]:
    raw = _redis().getdel(_key("oauth", state))
    if not raw:
        raise ValueError("This sign-in attempt expired. Please try again.")
    pending = json.loads(raw)
    response = requests.post(
        API_BASE + "/oauth/token",
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(), "code_verifier": pending["verifier"]},
        auth=(os.environ["BB_V1_CLIENT_ID"], os.environ["BB_V1_CLIENT_SECRET"]),
        timeout=25,
    )
    if not response.ok:
        raise ValueError("BuzzerBeater did not complete sign-in. Please try again.")
    tokens = response.json()
    me = V1Client(tokens["access_token"]).get("/me")
    sid = secrets.token_hex(32)
    record = {
        "kind": "oauth",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_at": time.time() + int(tokens.get("expires_in", 3600)),
        "scopes": me.get("scopes", []),
        "me": me,
        "csrf": secrets.token_urlsafe(32),
    }
    save_session(sid, record)
    return sid, record, pending["feature"]


def current_session() -> tuple[V1Client, dict[str, Any]] | None:
    sid = sid_from_request()
    record = load_session(sid)
    if not record:
        return None
    if record.get("kind") == "personal":
        return V1Client(record["access_token"]), record
    if record.get("expires_at", 0) <= time.time() + 30:
        token = refresh_session(sid, record["access_token"], force=False)
        if not token:
            return None
        record = load_session(sid)
        if not record:
            return None
    return V1Client(record["access_token"], on_unauthorized=lambda old: refresh_session(sid, old, force=True)), record


def refresh_session(sid: str, failed_token: str, *, force: bool) -> str | None:
    """Refresh once under a distributed lock, storing the rotated pair first."""
    lock = _redis().lock(_key("refresh-lock", sid), timeout=30, blocking_timeout=15)
    with lock:
        record = load_session(sid)
        if not record:
            return None
        if record["access_token"] != failed_token:
            return record["access_token"]
        if not force and record.get("expires_at", 0) > time.time() + 30:
            return record["access_token"]
        response = requests.post(
            API_BASE + "/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": record["refresh_token"]},
            auth=(os.environ["BB_V1_CLIENT_ID"], os.environ["BB_V1_CLIENT_SECRET"]),
            timeout=25,
        )
        if not response.ok:
            delete_session(sid)
            return None
        tokens = response.json()
        record["access_token"] = tokens["access_token"]
        record["refresh_token"] = tokens["refresh_token"]
        record["expires_at"] = time.time() + int(tokens.get("expires_in", 3600))
        save_session(sid, record)
        return record["access_token"]


def revoke(record: dict[str, Any]) -> None:
    if record.get("kind") == "personal":
        delete_session(sid_from_request())
        return
    try:
        requests.post(
            API_BASE + "/oauth/revoke",
            data={"token": record["refresh_token"]},
            auth=(os.environ["BB_V1_CLIENT_ID"], os.environ["BB_V1_CLIENT_SECRET"]),
            timeout=20,
        )
    finally:
        delete_session(sid_from_request())
