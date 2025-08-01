"""Database setup and configuration using async SQLAlchemy."""

from __future__ import annotations

import logging
import ssl
from datetime import datetime
from typing import AsyncGenerator
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from sqlalchemy import DateTime
from sqlalchemy import MetaData
from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.pool import NullPool
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import func

from smarter_dev.shared.config import Settings
from smarter_dev.shared.config import get_settings

logger = logging.getLogger(__name__)


def convert_postgres_url_for_asyncpg(database_url: str) -> tuple[str, dict]:
    """Convert PostgreSQL URL with sslmode to asyncpg-compatible format.
    
    Args:
        database_url: Database URL that may contain sslmode parameter
        
    Returns:
        Tuple of (cleaned_url, connect_args) for asyncpg
    """
    if not database_url.startswith(('postgresql+asyncpg://', 'postgresql://')):
        return database_url, {}
    
    parsed = urlparse(database_url)
    query_params = parse_qs(parsed.query)
    connect_args = {}
    
    # Handle sslmode parameter
    if 'sslmode' in query_params:
        sslmode = query_params.pop('sslmode')[0]
        if sslmode in ('require', 'prefer'):
            # Create SSL context that allows self-signed certificates
            # This is needed for DigitalOcean managed PostgreSQL
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connect_args['ssl'] = ssl_context
        elif sslmode == 'disable':
            connect_args['ssl'] = False
        # For 'allow' and other modes, let asyncpg decide
    
    # Rebuild URL without sslmode
    if query_params:
        query_string = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=query_string)
    else:
        new_parsed = parsed._replace(query='')
    
    cleaned_url = urlunparse(new_parsed)
    return cleaned_url, connect_args


# Database naming convention for consistent constraint names
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all database models with common timestamp fields."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    
    # Common timestamp fields for all models
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when the record was created"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        doc="Timestamp when the record was last updated"
    )


# Global engine and session maker
_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def create_engine(settings: Settings) -> AsyncEngine:
    """Create async SQLAlchemy engine with proper configuration."""
    database_url = settings.effective_database_url
    
    # Convert PostgreSQL URL to asyncpg-compatible format
    cleaned_url, pg_connect_args = convert_postgres_url_for_asyncpg(database_url)
    
    # Engine configuration
    engine_kwargs = {
        "echo": settings.debug and settings.log_level == "DEBUG",
        "echo_pool": settings.debug and settings.log_level == "DEBUG",
        "future": True,
    }
    
    # Pool configuration based on environment
    if settings.is_testing:
        # Use StaticPool for testing to maintain connections
        test_connect_args = {"check_same_thread": False}
        test_connect_args.update(pg_connect_args)
        engine_kwargs.update({
            "poolclass": StaticPool,
            "pool_pre_ping": True,
            "pool_recycle": -1,
            "connect_args": test_connect_args,
        })
    else:
        # Production/development pool configuration
        engine_kwargs.update({
            "pool_size": 20,
            "max_overflow": 30,
            "pool_pre_ping": True,
            "pool_recycle": 3600,  # 1 hour
        })
        
        # Add PostgreSQL connection args for production
        if pg_connect_args:
            engine_kwargs["connect_args"] = pg_connect_args
    
    engine = create_async_engine(cleaned_url, **engine_kwargs)
    
    # Set up event listeners
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """Set SQLite pragmas for better performance and reliability."""
        if "sqlite" in database_url:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
            cursor.close()
    
    return engine


def get_engine() -> AsyncEngine:
    """Get the global database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings)
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get the global session maker."""
    global _session_maker
    if _session_maker is None:
        engine = get_engine()
        _session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_maker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for dependency injection."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_db_session_context():
    """Get a database session context manager."""
    session_maker = get_session_maker()
    return session_maker()


async def init_database() -> None:
    """Initialize database connection and create tables if needed."""
    global _engine, _session_maker
    
    settings = get_settings()
    logger.info(f"Initializing database connection to {settings.effective_database_url}")
    
    # Create engine and session maker
    _engine = create_engine(settings)
    _session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    
    # Test connection
    try:
        async with _engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: sync_conn.execute(text("SELECT 1")))
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


async def close_database() -> None:
    """Close database connections."""
    global _engine, _session_maker
    
    if _engine:
        logger.info("Closing database connections")
        await _engine.dispose()
        _engine = None
        _session_maker = None


async def create_tables() -> None:
    """Create all database tables."""
    logger.info("Creating database tables")
    engine = get_engine()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables created successfully")


async def drop_tables() -> None:
    """Drop all database tables."""
    logger.info("Dropping database tables")
    engine = get_engine()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    logger.info("Database tables dropped successfully")


class DatabaseManager:
    """Database manager for handling connections and sessions."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine: Optional[AsyncEngine] = None
        self.session_maker: Optional[async_sessionmaker[AsyncSession]] = None

    async def init(self) -> None:
        """Initialize database connection."""
        logger.info("Initializing database manager")
        self.engine = create_engine(self.settings)
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            logger.info("Closing database manager")
            await self.engine.dispose()
            self.engine = None
            self.session_maker = None

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if not self.session_maker:
            raise RuntimeError("Database manager not initialized")
        
        async with self.session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_tables(self) -> None:
        """Create all database tables."""
        if not self.engine:
            raise RuntimeError("Database manager not initialized")
        
        logger.info("Creating database tables")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """Drop all database tables."""
        if not self.engine:
            raise RuntimeError("Database manager not initialized")
        
        logger.info("Dropping database tables")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# Utility functions for testing
async def create_test_engine(database_url: str) -> AsyncEngine:
    """Create a test engine with appropriate configuration."""
    return create_async_engine(
        database_url,
        poolclass=NullPool,
        echo=False,
        future=True,
    )


async def create_test_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a test session maker."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )