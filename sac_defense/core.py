"""Shared configuration, identifiers, and request safety limits."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

MAX_BODY = 1_048_576
COOKIE_NAME = "sac_sid"
DATASET_VERSION = "synthetic-v1"
SESSION_RE = re.compile(r"^[dn]\.[0-9a-f]{32}\.[A-Za-z0-9_-]{22}$")


@dataclass(frozen=True)
class Settings:
    database: Path
    key_file: Path
    kill_switch: Path
    bind: str = "127.0.0.1"
    port: int = 4319
    mode: str = "router"
    upstream: str = ""
    decoy: str = ""
    public_https: bool = False
    never_real_prefixes: tuple[str, ...] = ()
    allow_real_prefixes: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.mode not in {"router", "decoy"}:
            raise ValueError("mode must be router or decoy")
        if not 0 <= self.port <= 65535:
            raise ValueError("invalid port")
        if self.mode == "router" and self.bind not in {"127.0.0.1", "::1", "localhost"} and not self.public_https:
            raise ValueError("non-loopback binding requires public_https behind a TLS proxy")
        for value in (self.upstream, self.decoy):
            if not value:
                continue
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("upstream and decoy must be absolute HTTP URLs")
            if parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError("upstream and decoy must be fixed origins without credentials or paths")
        if self.mode == "router" and not self.decoy:
            raise ValueError("router requires a fixed decoy origin")
        if self.mode == "router" and self.upstream:
            if not self.allow_real_prefixes:
                raise ValueError("router with a real upstream requires --allow-real-prefix")
            real = urlsplit(self.upstream)
            decoy = urlsplit(self.decoy)
            real_identity = (real.scheme, real.hostname, real.port or (443 if real.scheme == "https" else 80))
            decoy_identity = (decoy.scheme, decoy.hostname, decoy.port or (443 if decoy.scheme == "https" else 80))
            if real_identity == decoy_identity:
                raise ValueError("real and decoy origins must differ")
        if self.mode == "decoy" and self.upstream:
            raise ValueError("decoy must not receive a real upstream origin")
        for prefix in (*self.never_real_prefixes, *self.allow_real_prefixes):
            if (not isinstance(prefix, str) or not re.fullmatch(r"/[A-Za-z0-9._~/-]+", prefix)
                    or prefix == "/" or "//" in prefix or prefix.endswith("/")
                    or any(part in {".", ".."} for part in prefix.split("/"))):
                raise ValueError("route prefix must be a canonical non-root path")


def load_key(path: Path) -> bytes:
    key = path.read_bytes()
    if len(key) < 32:
        raise ValueError("deployment key must contain at least 32 random bytes")
    return key


def new_key(path: Path) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(os.urandom(32))
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def digest(key: bytes, label: str) -> bytes:
    return hmac.new(key, label.encode("utf-8"), hashlib.sha256).digest()


def decoy_token(key: bytes) -> str:
    encoded = base64.urlsafe_b64encode(digest(key, "decoy-token:v1")[:24]).decode().rstrip("=")
    return "sac_" + encoded


def new_session(key: bytes, route: str) -> str:
    if route not in {"d", "n"}:
        raise ValueError("invalid session route")
    return sign_session(key, route, uuid.uuid4().hex)


def sign_session(key: bytes, route: str, sid: str) -> str:
    if route not in {"d", "n"} or not re.fullmatch(r"[0-9a-f]{32}", sid):
        raise ValueError("invalid session")
    sig = base64.urlsafe_b64encode(digest(key, f"session:v1:{route}.{sid}")[:16]).decode().rstrip("=")
    return f"{route}.{sid}.{sig}"


def parse_session(key: bytes, cookie: str | None) -> tuple[str, str] | None:
    if not cookie or not SESSION_RE.fullmatch(cookie):
        return None
    route, sid, sig = cookie.split(".")
    expected = base64.urlsafe_b64encode(digest(key, f"session:v1:{route}.{sid}")[:16]).decode().rstrip("=")
    return (route, sid) if hmac.compare_digest(sig, expected) else None


def cookie_value(key: bytes, header: str | None) -> tuple[str, str] | None:
    if not header:
        return None
    candidates: list[tuple[str, str]] = []
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            candidate = parse_session(key, value)
            if candidate:
                candidates.append(candidate)
    return next((candidate for candidate in candidates if candidate[0] == "d"), candidates[0] if candidates else None)


def make_cookie(value: str, secure: bool) -> str:
    flags = "; Path=/; HttpOnly; SameSite=Strict"
    return f"{COOKIE_NAME}={value}{flags}{'; Secure' if secure else ''}"


def is_decoy_token(key: bytes, authorization: str | None) -> bool:
    if not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(authorization[7:], decoy_token(key))
