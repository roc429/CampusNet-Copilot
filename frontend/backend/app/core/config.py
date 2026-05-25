import os
from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = ""

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "campusnet-copilot"

    secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # 百炼 DashScope（OpenAI 兼容模式），密钥勿提交到 Git
    dashscope_api_key: str = ""
    dashscope_chat_url: str = (
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    )

    @property
    def database_url_resolved(self) -> str:
        if self.database_url:
            return self.database_url

        user = quote_plus(self.mysql_user)
        pwd = quote_plus(self.mysql_password)
        return (
            f"mysql+pymysql://{user}:{pwd}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )




@lru_cache
def get_settings() -> Settings:
    return Settings()
