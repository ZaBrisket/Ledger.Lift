import logging
import time
from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any
from sqlalchemy import create_engine, event, pool, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError
from sqlalchemy.engine import Engine
from .settings import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Enhanced database manager with connection pooling, health monitoring, and retry logic."""
    
    def __init__(self):
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self._health_cache: Dict[str, Any] = {}
        self._health_cache_ttl = 30  # 30 seconds
        self._last_health_check = 0
        self._initialize()
    
    def _initialize(self):
        """Initialize database engine with optimized settings."""
        try:
            # Enhanced engine configuration for production use
            engine_config = {
                'future': True,
                'pool_pre_ping': True,
                'pool_size': getattr(settings, 'db_pool_size', 20),
                'max_overflow': getattr(settings, 'db_max_overflow', 30),
                'pool_timeout': getattr(settings, 'db_pool_timeout', 30),
                'pool_recycle': 3600,  # Recycle connections every hour
                'pool_reset_on_return': 'rollback',
                'echo': False,  # Set to True for SQL debugging
                'connect_args': {
                    'connect_timeout': 30,
                    'application_name': 'ledgerlift-api'
                }
            }
            
            self.engine = create_engine(settings.database_url, **engine_config)
            
            # Setup connection event listeners for monitoring
            event.listen(self.engine, "connect", self._on_connect)
            event.listen(self.engine, "checkout", self._on_checkout)
            event.listen(self.engine, "checkin", self._on_checkin)
            
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                autoflush=False,
                expire_on_commit=False,
                future=True
            )
            
            logger.info("Database manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database manager: {e}")
            raise
    
    def _on_connect(self, dbapi_connection, connection_record):
        """Called when a new database connection is created."""
        logger.debug("New database connection established")
    
    def _on_checkout(self, dbapi_connection, connection_record, connection_proxy):
        """Called when a connection is retrieved from the pool."""
        connection_record.info['checkout_time'] = time.time()
    
    def _on_checkin(self, dbapi_connection, connection_record):
        """Called when a connection is returned to the pool."""
        checkout_time = connection_record.info.get('checkout_time')
        if checkout_time:
            duration = time.time() - checkout_time
            if duration > 10:  # Log slow database operations
                logger.warning(f"Slow database operation detected: {duration:.2f}s")
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions with automatic cleanup.
        Ensures proper session lifecycle management.
        """
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized")
        
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error in database session: {e}")
            raise
        finally:
            session.close()
    
    def get_session_direct(self) -> Session:
        """
        Get a session directly (for dependency injection).
        Caller is responsible for session cleanup.
        """
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized")
        return self.SessionLocal()
    
    def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check with caching.
        Returns database status, connection pool info, and performance metrics.
        """
        current_time = time.time()
        
        # Return cached result if still valid
        if (current_time - self._last_health_check < self._health_cache_ttl 
            and self._health_cache):
            return self._health_cache
        
        try:
            start_time = time.time()
            
            # Test basic connectivity
            with self.get_session() as session:
                result = session.execute(text("SELECT 1")).scalar()
                if result != 1:
                    raise Exception("Basic query failed")
            
            query_time = time.time() - start_time
            
            # Get connection pool statistics
            pool_status = {
                'pool_size': self.engine.pool.size(),
                'checked_in': self.engine.pool.checkedin(),
                'checked_out': self.engine.pool.checkedout(),
                'overflow': self.engine.pool.overflow(),
                'invalid': self.engine.pool.invalid()
            }
            
            health_info = {
                'status': 'healthy',
                'query_time_ms': round(query_time * 1000, 2),
                'pool_status': pool_status,
                'timestamp': current_time
            }
            
            # Cache the result
            self._health_cache = health_info
            self._last_health_check = current_time
            
            logger.debug(f"Database health check completed in {query_time:.3f}s")
            return health_info
            
        except Exception as e:
            error_info = {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': current_time
            }
            logger.error(f"Database health check failed: {e}")
            return error_info
    
    def retry_on_disconnect(self, func, *args, max_retries=3, **kwargs):
        """
        Retry database operations on connection failures.
        Useful for handling transient network issues.
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except DisconnectionError as e:
                last_exception = e
                logger.warning(f"Database disconnection on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                break
            except Exception as e:
                # Don't retry on non-connection errors
                logger.error(f"Database operation failed: {e}")
                raise
        
        logger.error(f"Database operation failed after {max_retries} attempts")
        raise last_exception
    
    def close(self):
        """Clean shutdown of database connections."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connections closed")

# Global database manager instance
db_manager = DatabaseManager()

class Base(DeclarativeBase):
    pass

# Legacy compatibility - these will be replaced gradually
engine = db_manager.engine
SessionLocal = db_manager.SessionLocal

def get_db_session() -> Generator[Session, None, None]:
    """Dependency for FastAPI route handlers."""
    session = db_manager.get_session_direct()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def create_tables():
    """Create database tables if they don't exist."""
    try:
        # Import models inside function to avoid circular imports
        from .models import (
            Document,
            Page,
            ProcessingEvent,
            Artifact,
            AuditEvent,
            CostRecord,
            JobSchedule,
        )  # noqa: F401
        Base.metadata.create_all(bind=db_manager.engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise

def get_db_health() -> Dict[str, Any]:
    """Get database health status."""
    return db_manager.health_check()
