from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings


def _password_bytes(plain: str) -> bytes:
    """bcrypt 仅哈希前 72 字节；与哈希、校验使用同一规则。"""
    raw = plain.encode("utf-8")
    return raw[:72] if len(raw) > 72 else raw


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_password_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """解析 JWT，返回 subject（用户 id 字符串）。校验失败抛出 ValueError。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise ValueError("invalid token") from exc
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise ValueError("invalid subject")
    return sub
