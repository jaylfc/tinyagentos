from __future__ import annotations
import hashlib
import json
import secrets
import time
from pathlib import Path


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
        self.session_ttl = 86400 * 7  # 7 days

    def _load_sessions(self) -> dict[str, float]:
        """Load sessions from disk, filtering out expired ones."""
        if not self._sessions_file.exists():
            return {}
        try:
            data = json.loads(self._sessions_file.read_text())
            now = time.time()
            return {k: v for k, v in data.items() if v > now}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_sessions(self, sessions: dict[str, float]) -> None:
        """Persist sessions to disk."""
        self._sessions_file.parent.mkdir(parents=True, exist_ok=True)
        self._sessions_file.write_text(json.dumps(sessions))

    @property
    def _sessions(self) -> dict[str, float]:
        """Backward-compatible property for tests that access _sessions directly."""
        return self._load_sessions()

    @_sessions.setter
    def _sessions(self, value: dict[str, float]) -> None:
        """Backward-compatible setter for tests that assign to _sessions."""
        self._save_sessions(value)

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
        sessions = self._load_sessions()
        token = secrets.token_urlsafe(32)
        sessions[token] = time.time() + self.session_ttl
        self._save_sessions(sessions)
        return token

    def validate_session(self, token: str) -> bool:
        sessions = self._load_sessions()
        expiry = sessions.get(token)
        if not expiry:
            return False
        if time.time() > expiry:
            sessions.pop(token, None)
            self._save_sessions(sessions)
            return False
        return True

    def revoke_session(self, token: str) -> None:
        sessions = self._load_sessions()
        sessions.pop(token, None)
        self._save_sessions(sessions)

    def cleanup_sessions(self) -> None:
        now = time.time()
        sessions = self._load_sessions()
        cleaned = {t: exp for t, exp in sessions.items() if now <= exp}
        self._save_sessions(cleaned)
