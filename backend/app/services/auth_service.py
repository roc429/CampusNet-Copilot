from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fastapi import HTTPException, status

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest


def create_registered_user(db: Session, body: RegisterRequest) -> User:
    user = User(
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已被注册",
        )
    db.refresh(user)
    return user


def get_user_for_login(db: Session, body: LoginRequest) -> User:
    email = body.email.lower().strip()
    stmt = select(User).where(User.email == email)
    user = db.execute(stmt).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    return user
