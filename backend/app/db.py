from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables on startup. Alembic can take over later; this keeps setup to one command."""
    from app import models  # noqa: F401  (registers the mappers)

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
