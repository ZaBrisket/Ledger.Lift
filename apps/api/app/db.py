import os
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Optional

from sqlalchemy import create_engine, event, pool, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool, QueuePool

from .settings import settings

logger = logging.getLogger(__name__)

# Database configuration with enhanced pooling
DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '20'))
DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '30'))
DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', '30'))
DB_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', '3600'))  # 1 hour

# Create engine with connection pooling
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
    pool_pre_ping=True,  # Verify connections before use
    echo_pool=os.getenv('DEBUG_DB_POOL', 'false').lower() == 'true',
    future=True,
    connect_args={
        'connect_timeout': 10,
        'application_name': 'legalqa-api',
        'options': '-c statement_timeout=30000'  # 30 second statement timeout
    }
)

# Session factory with optimized settings
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True
)

class Base(DeclarativeBase):
    pass

# Connection event listeners for monitoring
@event.listens_for(engine, "connect")
def receive_connect(dbapi_connection, connection_record):
    """Set session parameters on connect"""
    connection_record.info['connect_time'] = datetime.utcnow()
    logger.debug("Database connection established")

@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """Log connection checkout from pool"""
    logger.debug(f"Connection checked out from pool (age: {datetime.utcnow() - connection_record.info.get('connect_time', datetime.utcnow())})")

@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """Log connection return to pool"""
    logger.debug("Connection returned to pool")

class DatabaseManager:
    """Enhanced database manager with health monitoring and connection management"""
    
    def __init__(self):
        self._health_cache = {'status': None, 'timestamp': None}
        self._health_cache_ttl = 30  # seconds
    
    @contextmanager
    def get_db_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions with automatic cleanup.
        
        Usage:
            with db_manager.get_db_session() as session:
                # Your database operations
                session.commit()
        """
        session = SessionLocal()
        try:
            yield session
        except SQLAlchemyError as e:
            logger.error(f"Database error: {str(e)}")
            session.rollback()
            raise
        finally:
            session.close()
    
    def check_health(self) -> dict:
        """
        Check database health with caching to prevent overwhelming the database.
        
        Returns:
            dict: Health status including connection pool stats
        """
        now = datetime.utcnow()
        
        # Return cached result if still valid
        if (self._health_cache['timestamp'] and 
            (now - self._health_cache['timestamp']).total_seconds() < self._health_cache_ttl):
            return self._health_cache['status']
        
        try:
            # Test database connection
            with self.get_db_session() as session:
                result = session.execute(text("SELECT 1")).scalar()
                if result != 1:
                    raise Exception("Unexpected health check result")
            
            # Get pool statistics
            pool_status = engine.pool.status() if hasattr(engine.pool, 'status') else 'Pool status unavailable'
            
            health_status = {
                'healthy': True,
                'timestamp': now.isoformat(),
                'pool_status': pool_status,
                'pool_size': DB_POOL_SIZE,
                'max_overflow': DB_MAX_OVERFLOW,
                'details': {
                    'connections': {
                        'size': engine.pool.size() if hasattr(engine.pool, 'size') else 'unknown',
                        'checked_in': engine.pool.checkedin() if hasattr(engine.pool, 'checkedin') else 'unknown',
                        'checked_out': engine.pool.checkedout() if hasattr(engine.pool, 'checkedout') else 'unknown',
                        'overflow': engine.pool.overflow() if hasattr(engine.pool, 'overflow') else 'unknown',
                        'total': engine.pool.total() if hasattr(engine.pool, 'total') else 'unknown'
                    }
                }
            }
            
            # Cache the result
            self._health_cache = {'status': health_status, 'timestamp': now}
            
            return health_status
            
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            
            health_status = {
                'healthy': False,
                'timestamp': now.isoformat(),
                'error': str(e),
                'pool_status': 'Error checking pool status'
            }
            
            # Cache the error result too (with shorter TTL)
            self._health_cache = {'status': health_status, 'timestamp': now}
            
            return health_status
    
    def execute_with_retry(self, func, max_retries: int = 3, session: Optional[Session] = None):
        """
        Execute a database operation with retry logic.
        
        Args:
            func: Function to execute (should accept session as parameter)
            max_retries: Maximum number of retry attempts
            session: Optional existing session to use
            
        Returns:
            Result of the function execution
        """
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                if session:
                    return func(session)
                else:
                    with self.get_db_session() as db_session:
                        return func(db_session)
                        
            except DBAPIError as e:
                # Connection errors are retryable
                if e.connection_invalidated or 'connection' in str(e).lower():
                    retries += 1
                    last_error = e
                    logger.warning(f"Retryable database error (attempt {retries}/{max_retries}): {str(e)}")
                    if retries < max_retries:
                        # Exponential backoff
                        import time
                        time.sleep(0.5 * (2 ** (retries - 1)))
                        continue
                raise
                
            except SQLAlchemyError as e:
                # Some SQLAlchemy errors might be retryable
                if 'deadlock' in str(e).lower() or 'timeout' in str(e).lower():
                    retries += 1
                    last_error = e
                    logger.warning(f"Retryable SQL error (attempt {retries}/{max_retries}): {str(e)}")
                    if retries < max_retries:
                        import time
                        time.sleep(0.5 * (2 ** (retries - 1)))
                        continue
                raise
        
        # Max retries exceeded
        logger.error(f"Max retries ({max_retries}) exceeded for database operation")
        raise last_error
    
    def dispose_connections(self):
        """Dispose all connections in the pool"""
        engine.dispose()
        logger.info("Database connections disposed")

# Global database manager instance
db_manager = DatabaseManager()

# Convenience function for backward compatibility
def get_db():
    """
    Dependency for FastAPI routes.
    
    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    with db_manager.get_db_session() as session:
        yield session

def create_tables():
    """Create all database tables"""
    # Import models inside function to avoid circular imports
    from .models import Document, Page, ProcessingEvent, Artifact  # noqa
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")

# Export for backward compatibility
__all__ = ['engine', 'SessionLocal', 'Base', 'get_db', 'create_tables', 'db_manager']