"""
Database connection and session management (async SQLAlchemy).
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create tables if they don't exist (for dev; prod uses migrations)."""
    # Tables are created by 001_init.sql loaded by Docker
    # This is a no-op fallback for local dev without Docker
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS order_plans (
            id UUID PRIMARY KEY, status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
            raw_user_message TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            approved_at TIMESTAMPTZ, completed_at TIMESTAMPTZ
        )"""))
        await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS plan_id UUID REFERENCES order_plans(id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_plan_id ON orders(plan_id)"))


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
