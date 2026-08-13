"""
MarketPilot Storage — Repository pattern.

Generic async CRUD repository and specialised repositories for
klines and orders.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from marketpilot.storage.tables import Base, KlineRecord, OrderRecord, PaperAccountRecord, PaperPositionRecord, PaperTradeRecord

ModelT = TypeVar("ModelT", bound=Base)


# ---------------------------------------------------------------------------
# Generic base repository
# ---------------------------------------------------------------------------

class BaseRepository(Generic[ModelT]):
    """Async CRUD operations for any SQLAlchemy model.

    Parameters
    ----------
    session:
        An active ``AsyncSession`` instance.
    model:
        The SQLAlchemy ORM class.
    """

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    async def add(self, instance: ModelT) -> ModelT:
        """Add and flush a single record."""
        self._session.add(instance)
        await self._session.flush()
        logger.debug("Added {} (id={})", self._model.__name__, getattr(instance, "id", "?"))
        return instance

    async def add_many(self, instances: list[ModelT]) -> list[ModelT]:
        """Add and flush multiple records."""
        self._session.add_all(instances)
        await self._session.flush()
        logger.debug("Added {} {} records", len(instances), self._model.__name__)
        return instances

    async def get_by_id(self, record_id: int) -> ModelT | None:
        """Fetch a record by primary key."""
        return await self._session.get(self._model, record_id)

    async def delete(self, instance: ModelT) -> None:
        """Delete a single record."""
        await self._session.delete(instance)
        await self._session.flush()


# ---------------------------------------------------------------------------
# Specialised repositories
# ---------------------------------------------------------------------------

class KlineRepository(BaseRepository[KlineRecord]):
    """Repository for kline / candlestick persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, KlineRecord)

    async def get_by_symbol(
        self,
        symbol: str,
        interval: str,
        *,
        since: datetime | None = None,
        limit: int = 500,
    ) -> list[KlineRecord]:
        """Fetch klines for *symbol* / *interval*, optionally filtered by time."""
        stmt = (
            select(KlineRecord)
            .where(KlineRecord.symbol == symbol, KlineRecord.interval == interval)
            .order_by(KlineRecord.open_time.desc())
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(KlineRecord.open_time >= since)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class OrderRepository(BaseRepository[OrderRecord]):
    """Repository for order record persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OrderRecord)

    async def get_by_order_id(self, order_id: str) -> OrderRecord | None:
        """Fetch a single order by its exchange order ID."""
        stmt = select(OrderRecord).where(OrderRecord.order_id == order_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_symbol(
        self,
        symbol: str,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[OrderRecord]:
        """Fetch orders for *symbol*, optionally filtered by status."""
        stmt = (
            select(OrderRecord)
            .where(OrderRecord.symbol == symbol)
            .order_by(OrderRecord.created_at.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(OrderRecord.status == status)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PaperAccountRepository:
    """Repository for managing the paper trading account state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_account(self) -> PaperAccountRecord | None:
        stmt = select(PaperAccountRecord).where(PaperAccountRecord.id == 1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_positions(self) -> list[PaperPositionRecord]:
        stmt = select(PaperPositionRecord)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
        
    async def get_position_by_symbol(self, symbol: str) -> PaperPositionRecord | None:
        stmt = select(PaperPositionRecord).where(PaperPositionRecord.symbol == symbol)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_trades(self) -> list[PaperTradeRecord]:
        stmt = select(PaperTradeRecord).order_by(PaperTradeRecord.opened_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def reset(self, initial_equity: str) -> None:
        """Reset the paper trading account, wiping positions and trades."""
        from sqlalchemy import delete
        await self._session.execute(delete(PaperTradeRecord))
        await self._session.execute(delete(PaperPositionRecord))
        await self._session.execute(delete(PaperAccountRecord))
        
        acc = PaperAccountRecord(
            id=1,
            cash=initial_equity,
            locked_margin="0",
            realized_pnl="0"
        )
        self._session.add(acc)
        await self._session.flush()

    async def save_account(self, account: PaperAccountRecord) -> None:
        self._session.add(account)
        await self._session.flush()

    async def save_position(self, position: PaperPositionRecord) -> None:
        self._session.add(position)
        await self._session.flush()
        
    async def delete_position(self, position: PaperPositionRecord) -> None:
        await self._session.delete(position)
        await self._session.flush()

    async def save_trade(self, trade: PaperTradeRecord) -> None:
        self._session.add(trade)
        await self._session.flush()
