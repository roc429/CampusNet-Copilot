from fastapi import APIRouter
from app.api.v1 import auth, chat, knowledge, monitor

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(knowledge.router)
api_router.include_router(monitor.router)

