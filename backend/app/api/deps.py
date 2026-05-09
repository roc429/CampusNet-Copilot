"""路由层依赖注入（数据库会话等）。"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_db
from app.core.security import decode_access_token

__all__ = ["get_db", "get_current_user_id"]

_bearer = HTTPBearer()


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    try:
        return decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的登录令牌",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
