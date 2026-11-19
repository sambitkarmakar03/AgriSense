from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_password_hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    if len(settings.jwt_secret.encode("utf-8")) < 32:
        raise ValueError("Set JWT_SECRET to a random value of at least 32 bytes before using authentication.")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, object]:
    settings = get_settings()
    if len(settings.jwt_secret.encode("utf-8")) < 32:
        raise ValueError("JWT_SECRET is not configured.")
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
