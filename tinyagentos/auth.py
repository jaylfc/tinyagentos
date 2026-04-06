from __future__ import annotations
import hashlib
import json
import secrets
import time
from collections.abc import Iterator
from pathlib import Path


class _PersistentSessions:
    """Dict-like wrapper that reads/writes sessions from a JSON file on every access."""

    def __init__(self, path: Path):
        self._path = path

    def _load(self) -> dict[str, float]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, float]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data))

    def __getitem__(self, key: str) -> float:
        return self._load()[key]

    def __setitem__(self, key: str, value: float) -> None:
        data = self._load()
        data[key] = value
        self._save(data)

    def __delitem__(self, key: str) -> None:
        data = self._load()
        del data[key]
        self._save(data)

    def __contains__(self, key: object) -> bool:
        return key in self._load()

    def __iter__(self) -> Iterator[str]:
        return iter(self._load())

    def get(self, key: str, default: float | None = None) -> float | None:
        return self._load().get(key, default)

    def pop(self, key: str, *args: float) -> float:
        data = self._load()
        result = data.pop(key, *args)
        self._save(data)
        return result

    def items(self) -> list[tuple[str, float]]:
        return list(self._load().items())


def hash_password(password: str, salt: str = "") -> str:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password: str, stored: str) -> bool:
    salt = stored.split(":")[0]
    return hash_password(password, salt) == stored


class AuthManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._password_file = data_dir / ".auth_password"
        self._sessions_file = data_dir / ".auth_sessions"
        self._sessions = _PersistentSessions(self._sessions_file)
        self.session_ttl = 86400 * 7  # 7 days

    def is_configured(self) -> bool:
        return self._password_file.exists()

    def set_password(self, password: str) -> None:
        self._password_file.parent.mkdir(parents=True, exist_ok=True)
        self._password_file.write_text(hash_password(password))

    def check_password(self, password: str) -> bool:
        if not self.is_configured():
            return False
        stored = self._password_file.read_text().strip()
        return verify_password(password, stored)

    def create_session(self) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = time.time() + self.session_ttl
        return token

    def validate_session(self, token: str) -> bool:
        expiry = self._sessions.get(token)
        if expiry is None:
            return False
        if time.time() >= expiry:
            try:
                del self._sessions[token]
            except (KeyError, Exception):
                pass
            return False
        return True

    def revoke_session(self, token: str) -> None:
        self._sessions.pop(token, None)

    def cleanup_sessions(self) -> None:
        now = time.time()
        expired = [t for t, exp in self._sessions.items() if now >= exp]
        for t in expired:
            del self._sessions[t]
