"""Shared pytest fixtures.

Integration tests run against a dedicated Postgres database (per
.claude/rules/testing.md), created on demand from the models. Each test runs
inside a transaction that is rolled back afterwards, so nothing it writes
survives and the dev database is never touched.

Set TEST_DATABASE_URL to override; the default appends "_test" to the database
name in DATABASE_URL.
"""
from __future__ import annotations

import asyncio
import os
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.business_deps import BUSINESS_TOKEN_SCOPE
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import BUSINESS_ROLE, create_access_token, hash_password
from app.models.user import User

DEFAULT_PASSWORD = "secret123"


def _test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit

    from app.core.config import settings

    parsed = urlparse(settings.DATABASE_URL)
    return urlunparse(parsed._replace(path=parsed.path.rstrip("/") + "_test"))


async def _ensure_database_exists(url: str) -> None:
    import asyncpg

    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/")
    admin_dsn = urlunparse(parsed._replace(scheme="postgresql", path="/postgres"))

    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def _create_schema(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Provision the test database once per session."""
    url = _test_database_url()

    async def _prepare() -> None:
        await _ensure_database_exists(url)
        await _create_schema(url)

    try:
        asyncio.run(_prepare())
    except OSError as exc:  # Postgres not reachable
        pytest.skip(f"Test database unavailable at {url}: {exc}")
    return url


@pytest_asyncio.fixture
async def test_db(test_database_url: str) -> AsyncSession:
    """An AsyncSession whose writes are rolled back when the test ends.

    The session joins the outer transaction via a savepoint, so endpoint code
    can call commit() normally and the rollback below still undoes everything.
    """
    engine = create_async_engine(test_database_url)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture
def test_app(test_db: AsyncSession) -> FastAPI:
    """A slim app with the routers under test and the DB dependency overridden.

    Built here rather than importing app.main so tests don't run the real
    lifespan (Postgres/ChromaDB connections, stale-document recovery).
    """
    from app.api.router import api_router
    from app.api_compat import admin_router, auth_router

    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.include_router(auth_router)
    application.include_router(admin_router)

    async def _override_get_db():
        yield test_db

    application.dependency_overrides[get_db] = _override_get_db
    return application


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as async_client:
        yield async_client


@pytest.fixture
def make_user(test_db: AsyncSession):
    """Factory for synthetic users."""

    async def _make(
        *,
        email: str,
        role: str = "Nhân viên",
        name: str = "Test User",
        password: str = DEFAULT_PASSWORD,
        approval_status: str | None = None,
        **columns,
    ) -> User:
        user = User(
            name=name,
            email=email,
            hashed_password=hash_password(password),
            role=role,
            approval_status=approval_status,
            **columns,
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)
        return user

    return _make


@pytest_asyncio.fixture
async def internal_user(make_user) -> User:
    return await make_user(email="employee@example.test", role="Nhân viên", name="Nhân Viên Test")


@pytest_asyncio.fixture
async def business_user(make_user) -> User:
    return await make_user(
        email="business@example.test",
        role=BUSINESS_ROLE,
        name="Nguoi Lien He",
        approval_status="approved",
        company_name="Cong ty TNHH Test",
        phone="0900000000",
        tax_code="0101234567",
        industry="Khai thác đá",
    )


def internal_token(user: User) -> str:
    return create_access_token(data={"sub": user.id})


def business_token(user: User) -> str:
    return create_access_token(data={"sub": user.id, "scope": BUSINESS_TOKEN_SCOPE})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def internal_client(client: AsyncClient, internal_user: User) -> AsyncClient:
    client.headers.update(bearer(internal_token(internal_user)))
    return client


@pytest_asyncio.fixture
async def business_client(client: AsyncClient, business_user: User) -> AsyncClient:
    client.headers.update(bearer(business_token(business_user)))
    return client
