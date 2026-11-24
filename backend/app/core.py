from datetime import datetime, timezone
import os
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from sqlalchemy import create_engine, String, Text, JSON, DateTime, ForeignKey, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.environ.get('WARDROBE_ENV_FILE', '.env'), extra='ignore')
    database_url: str = 'mysql+pymysql://wardrobe:wardrobe@mysql:3306/wardrobe'
    redis_url: str = 'redis://redis:6379/0'
    jwt_secret: str
    deepseek_api_key: str = ''
    deepseek_base_url: str = 'https://api.deepseek.com'
    deepseek_model: str = 'deepseek-flash'
    ark_api_key: str = ''
    ark_base_url: str = 'https://ark.cn-beijing.volces.com/api/v3'
    ark_image_model: str = 'doubao-seedream-5-0-flash-260915'
    ark_response_format: Literal['url', 'b64_json'] = 'url'
    tryon_max_attempts: int = Field(2, ge=1, le=3)
    s3_endpoint: str = 'http://objectstore:9000'
    s3_access_key: str = 'wardrobe'
    s3_secret_key: str
    s3_bucket: str = 'wardrobe'
    cookie_secure: bool = False


@lru_cache
def settings():
    return Settings()


class Base(DeclarativeBase):
    pass


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password: Mapped[str] = mapped_column(String(300))
    profile: Mapped[dict] = mapped_column(JSON, default=dict)


class Item(Base):
    __tablename__ = 'items'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(30), default='unknown')
    color: Mapped[str] = mapped_column(String(80), default='')
    season: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default='available')
    image_key: Mapped[str] = mapped_column(String(300))
    tags: Mapped[dict] = mapped_column(JSON, default=dict)


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    messages: Mapped[list] = mapped_column(JSON, default=list)


class Recommendation(Base):
    __tablename__ = 'recommendations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey('conversations.id'))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default='queued')
    payload: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default='')
    trace: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Feedback(Base):
    __tablename__ = 'feedback'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey('recommendations.id'))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(String(500), default='')


@lru_cache
def engine():
    return create_engine(settings().database_url, pool_pre_ping=True)


def session():
    return sessionmaker(engine(), expire_on_commit=False)()
