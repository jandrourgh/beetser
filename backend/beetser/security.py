"""Password hashing, signed sessions and login throttling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .settings_store import SettingsStore

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        ]
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not password:
        return False
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def load_or_create_secret(path: Path, override: str | None = None) -> str:
    if override:
        return override
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return value


class AuthService:
    """Single-admin authentication.

    Priority for the configured password: a hash saved through the UI, then
    ``BEETSER_PASSWORD_HASH``, then ``BEETSER_PASSWORD``. When none is present
    the UI offers a first-run setup screen.
    """

    def __init__(
        self,
        settings_store: SettingsStore,
        *,
        env_password: str | None,
        env_password_hash: str | None,
        secret: str,
        max_age: int,
        cookie_secure: bool,
    ):
        self.store = settings_store
        self.env_password = env_password
        self.env_password_hash = env_password_hash
        self.serializer = URLSafeTimedSerializer(secret, salt="beetser-session")
        self.max_age = max_age
        self.cookie_secure = cookie_secure
        self.cookie_name = "beetser_session"
        self._attempts: dict[str, list[float]] = {}

    # -- password ---------------------------------------------------------

    def active_hash(self) -> str | None:
        stored = self.store.get("admin_password_hash")
        if stored:
            return str(stored)
        return self.env_password_hash

    def setup_required(self) -> bool:
        return not (self.active_hash() or self.env_password)

    def check_password(self, password: str) -> bool:
        if verify_password(password, self.active_hash()):
            return True
        if self.env_password and hmac.compare_digest(password, self.env_password):
            return True
        return bool(
            self.env_password_hash and verify_password(password, self.env_password_hash)
        )

    def change_password(self, new_password: str) -> None:
        self.store.set("admin_password_hash", hash_password(new_password))

    # -- sessions ---------------------------------------------------------

    def _secret_version(self) -> str:
        material = self.active_hash() or f"env:{self.env_password or ''}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def create_token(self) -> str:
        return self.serializer.dumps({"sub": "admin", "v": self._secret_version()})

    def validate_token(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            data = self.serializer.loads(token, max_age=self.max_age)
        except (BadSignature, SignatureExpired):
            return False
        return (
            isinstance(data, dict)
            and data.get("sub") == "admin"
            and data.get("v") == self._secret_version()
        )

    # -- throttling -------------------------------------------------------

    def is_locked(self, client: str) -> int:
        """Return seconds until the client may retry, or 0."""
        now = time.monotonic()
        attempts = [t for t in self._attempts.get(client, []) if now - t < 300]
        self._attempts[client] = attempts
        if len(attempts) >= 5:
            return max(1, int(300 - (now - attempts[-1])))
        return 0

    def record_failure(self, client: str) -> None:
        self._attempts.setdefault(client, []).append(time.monotonic())

    def clear_failures(self, client: str) -> None:
        self._attempts.pop(client, None)
