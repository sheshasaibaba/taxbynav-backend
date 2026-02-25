from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.core.config import settings

# Use asyncpg for async FastAPI. asyncpg does not accept psycopg params like sslmode/channel_binding.
# Convert scheme and strip incompatible query params; SSL is enabled via connect_args.
parsed = urlparse(settings.database_url)
scheme = "postgresql+asyncpg" if parsed.scheme == "postgresql" else parsed.scheme
query = parse_qs(parsed.query, keep_blank_values=True)
query.pop("sslmode", None)
query.pop("channel_binding", None)
new_query = urlencode(query, doseq=True)
async_database_url = urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

engine = create_async_engine(
    async_database_url,
    echo=settings.env == "development",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"ssl": True},  # Neon requires SSL; asyncpg uses this instead of sslmode
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables if using create_all; prefer Alembic in production."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
