from __future__ import annotations
import hashlib
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
        self._sessions: dict[str, float] = {}  # token -> expiry timestamp
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
        if not expiry:
            return False
        if time.time() > expiry:
            del self._sessions[token]
            return False
        return True

    def revoke_session(self, token: str) -> None:
        self._sessions.pop(token, None)

    def cleanup_sessions(self) -> None:
        now = time.time()
        expired = [t for t, exp in self._sessions.items() if now > exp]
        for t in expired:
            del self._sessions[t]
