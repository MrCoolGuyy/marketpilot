"""Tests for Database Migration."""

import pytest
from sqlalchemy import text

from marketpilot.storage.database import DatabaseManager
from marketpilot.config.settings import StorageSettings
from marketpilot.storage.tables import Base

@pytest.mark.asyncio
async def test_migration_idempotent(tmp_path):
    db_path = tmp_path / "test_migration.db"
    settings = StorageSettings(url=f"sqlite+aiosqlite:///{db_path}")
    db = DatabaseManager(settings)
    
    # 1. Initialize tables (creates paper_trades with exit_reason due to updated SQLAlchemy model)
    await db.initialize(create_tables=True)
    
    # Check that it recognizes it has the column
    has_column = await db.check_migration_status()
    assert has_column is True
    
    # Run migration (should be a no-op and not crash)
    await db.migrate_paper_trades()
    
    await db.close()

@pytest.mark.asyncio
async def test_migration_adds_column_safely(tmp_path):
    db_path = tmp_path / "test_migration_old.db"
    settings = StorageSettings(url=f"sqlite+aiosqlite:///{db_path}")
    db = DatabaseManager(settings)
    
    # Manually create table without exit_reason
    await db.initialize(create_tables=False)
    async with db._engine.begin() as conn:
        await conn.execute(text('''
            CREATE TABLE paper_trades (
                id VARCHAR(64) PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                direction VARCHAR(16) NOT NULL,
                quantity VARCHAR(32) NOT NULL,
                entry_price VARCHAR(32) NOT NULL,
                entry_fee VARCHAR(32) NOT NULL,
                exit_price VARCHAR(32),
                exit_fee VARCHAR(32),
                opened_at DATETIME NOT NULL,
                closed_at DATETIME,
                realized_pnl VARCHAR(32),
                status VARCHAR(16) NOT NULL
            )
        '''))
        
        # Insert a fake trade
        await conn.execute(text('''
            INSERT INTO paper_trades (id, symbol, direction, quantity, entry_price, entry_fee, opened_at, status)
            VALUES ('123', 'BTCUSDT', 'LONG', '1', '1000', '1', '2025-01-01 00:00:00', 'OPEN')
        '''))
        
    has_column = await db.check_migration_status()
    assert has_column is False
    
    # Migrate
    await db.migrate_paper_trades()
    
    has_column = await db.check_migration_status()
    assert has_column is True
    
    # Verify row is preserved
    async with db.session() as session:
        result = await session.execute(text("SELECT id, symbol, exit_reason FROM paper_trades"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == '123'
        assert row[1] == 'BTCUSDT'
        assert row[2] is None
        
    await db.close()
