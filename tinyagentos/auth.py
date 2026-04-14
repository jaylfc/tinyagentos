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
    """Single-user auth today, multi-user-shaped on disk for tomorrow.

    The user record is stored in ``data/.auth_user.json`` with a top-level
    ``{users: [...], current_user_id: ...}`` envelope so the same file can
    grow to hold multiple users without a migration. Today only one user
    is allowed (setup_user 409s if a user already exists). The legacy
    ``.auth_password`` file is still honoured for installs that predate
    onboarding — it transparently appears as a user with username
    ``admin`` until the user goes through onboarding properly.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._password_file = data_dir / ".auth_password"
        self._user_file = data_dir / ".auth_user.json"
        self._sessions_file = data_dir / ".auth_sessions"
        self._sessions = _PersistentSessions(self._sessions_file)
        self.session_ttl = 86400 * 7  # 7 days

    # ----- profile storage ------------------------------------------------

    def _read_users(self) -> dict:
        if self._user_file.exists():
            try:
                return json.loads(self._user_file.read_text())
            except (json.JSONDecodeError, OSError):
                return {"users": [], "current_user_id": None}
        return {"users": [], "current_user_id": None}

    def _write_users(self, data: dict) -> None:
        self._user_file.parent.mkdir(parents=True, exist_ok=True)
        self._user_file.write_text(json.dumps(data, indent=2))

    def is_configured(self) -> bool:
        # Either the new user file has at least one user, or a legacy
        # password file exists from a pre-onboarding install.
        return bool(self._read_users().get("users")) or self._password_file.exists()

    def needs_onboarding(self) -> bool:
        # Onboarding is required only when nothing at all is set up yet.
        # A legacy password install does NOT require onboarding (the user
        # can still log in with the password and fill profile fields later).
        return not self.is_configured()

    def setup_user(self, username: str, full_name: str, email: str, password: str) -> dict:
        users = self._read_users()
        if users.get("users"):
            raise ValueError("a user is already configured")
        if not username or not password:
            raise ValueError("username and password are required")
        record = {
            "id": secrets.token_urlsafe(8),
            "username": username,
            "full_name": full_name,
            "email": email,
            "password_hash": hash_password(password),
            "created_at": int(time.time()),
        }
        users["users"] = [record]
        users["current_user_id"] = record["id"]
        self._write_users(users)
        return self._public_user(record)

    def get_user(self) -> dict | None:
        users = self._read_users().get("users", [])
        if users:
            return self._public_user(users[0])
        # Legacy single-password install: synthesise a placeholder user so
        # the UI has something to render in the top bar until proper
        # onboarding is run.
        if self._password_file.exists():
            return {"username": "admin", "full_name": "", "email": "", "legacy": True}
        return None

    def _public_user(self, record: dict) -> dict:
        return {
            "username": record.get("username", ""),
            "full_name": record.get("full_name", ""),
            "email": record.get("email", ""),
        }

    # ----- password ops ---------------------------------------------------

    def set_password(self, password: str) -> None:
        # Legacy code path — keeps existing tests + the simple-setup
        # endpoint working. New installs use setup_user instead.
        self._password_file.parent.mkdir(parents=True, exist_ok=True)
        self._password_file.write_text(hash_password(password))

    def check_password(self, password: str, username: str | None = None) -> bool:
        # Try the user record first. If a username is supplied it must
        # match; if not, fall back to the single user on file.
        users = self._read_users().get("users", [])
        if users:
            user = users[0]
            if username and user.get("username") != username:
                return False
            return verify_password(password, user.get("password_hash", ""))
        # Legacy file fallback for pre-onboarding installs.
        if not self._password_file.exists():
            return False
        stored = self._password_file.read_text().strip()
        return verify_password(password, stored)

    # ----- sessions -------------------------------------------------------

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
