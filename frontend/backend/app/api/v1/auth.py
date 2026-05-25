from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, MessageResponse, RegisterRequest, TokenResponse, UserPublic
from app.services.auth_service import create_registered_user, get_user_for_login

router = APIRouter()


@router.post("/register", response_model=MessageResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> MessageResponse:
    user = create_registered_user(db, body)
    return MessageResponse(
        message="注册成功",
        user=UserPublic.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = get_user_for_login(db, body)
    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)
