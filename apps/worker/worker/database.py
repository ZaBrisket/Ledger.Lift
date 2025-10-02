from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from apps.worker.worker.config import settings
import logging

log=logging.getLogger(__name__)
engine=create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
async_session_factory=async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db_session():
    async with async_session_factory() as session:
        yield session
