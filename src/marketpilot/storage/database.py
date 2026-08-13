"""
MarketPilot Storage — Database manager.

Async SQLAlchemy engine & session lifecycle using ``aiosqlite`` (SQLite)
or ``asyncpg`` (PostgreSQL).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from loguru import logger

from marketpilot.config.settings import StorageSettings
from marketpilot.core.exceptions import StorageConnectionError
from marketpilot.core.interfaces import BaseStorage
from marketpilot.storage.tables import Base


class DatabaseManager(BaseStorage):
    """Manages the async database engine and session factory.

    Usage::

        db = DatabaseManager(settings)
        await db.initialize()

        async with db.session() as session:
            ...

        await db.close()
    """

    def __init__(self, settings: StorageSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    # -- BaseStorage interface -----------------------------------------------

    async def initialize(self, create_tables: bool = True) -> None:
        """Create the engine, session factory, and run DDL."""
        try:
            self._engine = create_async_engine(
                self._settings.url,
                echo=self._settings.echo,
                pool_pre_ping=True,
            )
            self._session_factory = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            if create_tables:
                # Create tables if they don't exist
                async with self._engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)

            logger.info("Database initialised (url={})", self._settings.url)
        except Exception as exc:
            raise StorageConnectionError(
                f"Failed to initialise database: {exc}"
            ) from exc

    async def close(self) -> None:
        """Dispose the engine and release all connections."""
        if self._engine is not None:
            await self._engine.dispose()
            logger.info("Database connections closed")
            self._engine = None
            self._session_factory = None

    async def health_check(self) -> bool:
        """Execute a trivial query to verify connectivity."""
        if self._engine is None:
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(Base.metadata.tables["kline_records"].select().limit(0))
            return True
        except Exception:
            logger.warning("Database health check failed")
            return False

    async def check_migration_status(self) -> bool:
        """Check if paper_trades table has the exit_reason column."""
        if self._engine is None:
            return False
        
        from sqlalchemy import text
        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(text("PRAGMA table_info(paper_trades)"))
                columns = [row[1] for row in result.fetchall()]
                return "exit_reason" in columns
        except Exception as exc:
            logger.error(f"Failed to check migration status: {exc}")
            return False
            
    async def migrate_paper_trades(self) -> None:
        """Add exit_reason column to paper_trades if it doesn't exist."""
        if self._engine is None:
            raise StorageConnectionError("Database not initialised")
            
        from sqlalchemy import text
        has_column = await self.check_migration_status()
        if not has_column:
            try:
                async with self._engine.begin() as conn:
                    await conn.execute(text("ALTER TABLE paper_trades ADD COLUMN exit_reason VARCHAR(32) NULL;"))
                logger.info("Successfully added exit_reason column to paper_trades table")
            except Exception as exc:
                raise StorageConnectionError(f"Failed to migrate database: {exc}") from exc
        else:
            logger.info("Database migration already applied")

    # -- Session helper ------------------------------------------------------

    def session(self) -> AsyncSession:
        """Return a new async session.

        Intended for use as an async context manager::

            async with db.session() as session:
                ...
        """
        if self._session_factory is None:
            raise StorageConnectionError("Database not initialised — call initialize() first")
        return self._session_factory()

    @property
    def engine(self) -> AsyncEngine:
        """Return the underlying async engine (e.g. for Alembic)."""
        if self._engine is None:
            raise StorageConnectionError("Database not initialised — call initialize() first")
        return self._engine
