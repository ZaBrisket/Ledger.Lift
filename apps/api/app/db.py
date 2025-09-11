import logging
import time
import threading
import random
from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any, Callable, TypeVar
from functools import wraps
from sqlalchemy import create_engine, event, pool, text, inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from sqlalchemy.exc import (
    SQLAlchemyError, DisconnectionError, OperationalError, 
    TimeoutError, DatabaseError, InterfaceError, DataError
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool, QueuePool, StaticPool
from .settings import settings

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Retriable database exceptions
RETRIABLE_EXCEPTIONS = (
    DisconnectionError,
    OperationalError,
    TimeoutError,
    InterfaceError,
)

# Error codes that indicate transient failures
RETRIABLE_ERROR_PATTERNS = [
    'connection', 'timeout', 'too many connections',
    'database is locked', 'could not connect',
    'server closed the connection', 'connection reset',
    'broken pipe', 'connection refused'
]


def is_retriable_error(error: Exception) -> bool:
    """Determine if a database error is retriable."""
    if isinstance(error, RETRIABLE_EXCEPTIONS):
        return True
    
    error_msg = str(error).lower()
    return any(pattern in error_msg for pattern in RETRIABLE_ERROR_PATTERNS)


def exponential_backoff_with_jitter(attempt: int, base_delay: float = 0.1, 
                                  max_delay: float = 10.0, jitter: float = 0.1) -> float:
    """Calculate exponential backoff delay with jitter for database retries."""
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter_range = delay * jitter
    actual_delay = delay + random.uniform(-jitter_range, jitter_range)
    return max(0, actual_delay)


def retry_database_operation(
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 10.0,
    jitter: float = 0.1
):
    """Decorator for retrying database operations with exponential backoff."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if not is_retriable_error(e):
                        logger.error(f"Non-retriable database error in {func.__name__}: {e}")
                        raise
                    
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = exponential_backoff_with_jitter(attempt, base_delay, max_delay, jitter)
                        logger.warning(
                            f"Retriable database error in {func.__name__} "
                            f"(attempt {attempt + 1}/{max_attempts}): {e}. "
                            f"Retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {func.__name__}: {e}")
            
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


class DatabaseManager:
    """Enhanced database manager with connection pooling, health monitoring, and retry logic."""
    
    def __init__(self):
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self._health_cache: Dict[str, Any] = {}
        self._health_cache_ttl = 30  # 30 seconds
        self._last_health_check = 0
        self._connection_lock = threading.Lock()
        self._stats = {
            'total_connections': 0,
            'successful_connections': 0,
            'failed_connections': 0,
            'total_queries': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'slow_queries': 0,
            'avg_query_time': 0,
            'last_connection_time': 0
        }
        self._stats_lock = threading.Lock()
        self._slow_query_threshold = getattr(settings, 'db_slow_query_threshold', 5.0)  # 5 seconds
        self._initialize()
    
    @retry_database_operation(max_attempts=3, base_delay=1.0)
    def _initialize(self):
        """Initialize database engine with optimized settings and validation."""
        try:
            # Determine pool class based on database URL
            db_url = settings.database_url.lower()
            if 'sqlite' in db_url and ':memory:' in db_url:
                pool_class = StaticPool
                pool_kwargs = {'connect_args': {'check_same_thread': False}}
            elif 'sqlite' in db_url:
                pool_class = NullPool
                pool_kwargs = {'connect_args': {'check_same_thread': False, 'timeout': 30}}
            else:
                pool_class = QueuePool
                pool_kwargs = {}
            
            # Enhanced engine configuration for production use
            engine_config = {
                'future': True,
                'pool_pre_ping': True,
                'poolclass': pool_class,
                'echo': getattr(settings, 'db_echo_sql', False),
                'echo_pool': getattr(settings, 'db_echo_pool', False),
                'query_cache_size': 1200,
                'connect_args': {
                    'connect_timeout': getattr(settings, 'db_connect_timeout', 30),
                    'application_name': 'ledgerlift-api',
                    'options': '-c statement_timeout=300000'  # 5 minute statement timeout
                }
            }
            
            # Add pool configuration for non-SQLite databases
            if pool_class == QueuePool:
                engine_config.update({
                    'pool_size': getattr(settings, 'db_pool_size', 20),
                    'max_overflow': getattr(settings, 'db_max_overflow', 30),
                    'pool_timeout': getattr(settings, 'db_pool_timeout', 30),
                    'pool_recycle': getattr(settings, 'db_pool_recycle', 3600),  # 1 hour
                    'pool_reset_on_return': 'rollback',
                })
            
            # Merge pool-specific kwargs
            engine_config['connect_args'].update(pool_kwargs.get('connect_args', {}))
            
            # Create engine
            self.engine = create_engine(settings.database_url, **engine_config)
            
            # Setup connection event listeners for monitoring
            event.listen(self.engine, "connect", self._on_connect)
            event.listen(self.engine, "checkout", self._on_checkout)
            event.listen(self.engine, "checkin", self._on_checkin)
            event.listen(self.engine, "engine_connect", self._on_engine_connect)
            
            # Validate connection immediately
            self._validate_connection()
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                autoflush=False,
                expire_on_commit=False,
                future=True,
                class_=Session
            )
            
            logger.info(f"Database manager initialized successfully with {pool_class.__name__}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database manager: {e}")
            raise
    
    def _validate_connection(self):
        """Validate database connection with timeout."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                if result.scalar() != 1:
                    raise DatabaseError("Database validation query failed")
            logger.info("Database connection validated successfully")
        except Exception as e:
            logger.error(f"Database connection validation failed: {e}")
            raise
    
    def _on_connect(self, dbapi_connection, connection_record):
        """Called when a new database connection is created."""
        with self._stats_lock:
            self._stats['total_connections'] += 1
            self._stats['successful_connections'] += 1
            self._stats['last_connection_time'] = time.time()
        
        # Set connection parameters for PostgreSQL
        if hasattr(dbapi_connection, 'set_client_encoding'):
            dbapi_connection.set_client_encoding('UTF8')
        
        logger.debug("New database connection established")
    
    def _on_engine_connect(self, conn, branch):
        """Called when engine connects."""
        if not branch:
            # This is a new connection, not a branch
            logger.debug("Engine connected to database")
    
    def _on_checkout(self, dbapi_connection, connection_record, connection_proxy):
        """Called when a connection is retrieved from the pool."""
        connection_record.info['checkout_time'] = time.time()
        connection_record.info['queries_executed'] = 0
    
    def _on_checkin(self, dbapi_connection, connection_record):
        """Called when a connection is returned to the pool."""
        checkout_time = connection_record.info.get('checkout_time')
        if checkout_time:
            duration = time.time() - checkout_time
            queries_executed = connection_record.info.get('queries_executed', 0)
            
            # Update statistics
            with self._stats_lock:
                if duration > self._slow_query_threshold:
                    self._stats['slow_queries'] += 1
                    logger.warning(
                        f"Slow database session detected: {duration:.2f}s "
                        f"({queries_executed} queries executed)"
                    )
                
                # Update average query time
                if queries_executed > 0:
                    avg_query_time = duration / queries_executed
                    total_queries = self._stats['total_queries']
                    current_avg = self._stats['avg_query_time']
                    self._stats['avg_query_time'] = (
                        (current_avg * total_queries + avg_query_time) / (total_queries + 1)
                    )
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions with automatic cleanup and monitoring.
        Ensures proper session lifecycle management with retry support.
        """
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized")
        
        session = None
        start_time = time.time()
        
        try:
            # Create session with retry
            session = self._create_session_with_retry()
            
            # Track query execution
            @event.listens_for(session, "after_bulk_insert")
            @event.listens_for(session, "after_bulk_update") 
            @event.listens_for(session, "after_bulk_delete")
            def receive_after_bulk_operation(mapper, connection, target):
                if hasattr(connection, 'info'):
                    connection.info['queries_executed'] = connection.info.get('queries_executed', 0) + 1
            
            with self._stats_lock:
                self._stats['total_queries'] += 1
            
            yield session
            
            # Commit with retry for transient failures
            self._commit_with_retry(session)
            
            # Record successful query
            with self._stats_lock:
                self._stats['successful_queries'] += 1
                
        except SQLAlchemyError as e:
            if session:
                session.rollback()
            
            with self._stats_lock:
                self._stats['failed_queries'] += 1
            
            logger.error(f"Database session error: {e}", exc_info=True)
            raise
            
        except Exception as e:
            if session:
                session.rollback()
            
            with self._stats_lock:
                self._stats['failed_queries'] += 1
            
            logger.error(f"Unexpected error in database session: {e}", exc_info=True)
            raise
            
        finally:
            duration = time.time() - start_time
            
            if session:
                session.close()
            
            # Log slow sessions
            if duration > self._slow_query_threshold:
                logger.warning(f"Slow database session: {duration:.2f}s")
    
    @retry_database_operation(max_attempts=3)
    def _create_session_with_retry(self) -> Session:
        """Create a database session with retry logic."""
        return self.SessionLocal()
    
    @retry_database_operation(max_attempts=3)
    def _commit_with_retry(self, session: Session):
        """Commit session with retry logic for transient failures."""
        session.commit()
    
    def get_session_direct(self) -> Session:
        """
        Get a session directly (for dependency injection).
        Caller is responsible for session cleanup.
        """
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized")
        return self.SessionLocal()
    
    @retry_database_operation(max_attempts=2, base_delay=0.5)
    def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check with caching and detailed diagnostics.
        Returns database status, connection pool info, and performance metrics.
        """
        current_time = time.time()
        
        # Return cached result if still valid
        if (current_time - self._last_health_check < self._health_cache_ttl 
            and self._health_cache):
            return self._health_cache
        
        health_info = {
            'timestamp': current_time,
            'checks': {}
        }
        
        try:
            # 1. Test basic connectivity
            start_time = time.time()
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1")).scalar()
                if result != 1:
                    raise DatabaseError("Basic connectivity test failed")
            
            connectivity_time = time.time() - start_time
            health_info['checks']['connectivity'] = {
                'status': 'healthy',
                'response_time_ms': round(connectivity_time * 1000, 2)
            }
            
            # 2. Test session creation
            start_time = time.time()
            with self.get_session() as session:
                # Test a simple query through session
                session.execute(text("SELECT 1"))
            
            session_time = time.time() - start_time
            health_info['checks']['session'] = {
                'status': 'healthy',
                'response_time_ms': round(session_time * 1000, 2)
            }
            
            # 3. Get connection pool statistics
            pool_status = self._get_pool_status()
            health_info['pool_status'] = pool_status
            
            # Check pool health
            pool_health = 'healthy'
            if pool_status.get('utilization', 0) > 0.8:
                pool_health = 'degraded'
                logger.warning(f"Database pool utilization high: {pool_status['utilization']:.1%}")
            
            health_info['checks']['connection_pool'] = {
                'status': pool_health,
                'utilization': pool_status.get('utilization', 0)
            }
            
            # 4. Database statistics
            with self._stats_lock:
                health_info['statistics'] = self._stats.copy()
            
            # Calculate error rate
            total_queries = health_info['statistics']['total_queries']
            failed_queries = health_info['statistics']['failed_queries']
            error_rate = failed_queries / max(1, total_queries)
            
            # Overall health determination
            if error_rate > 0.1:  # >10% error rate
                health_info['status'] = 'degraded'
                health_info['message'] = f"High error rate: {error_rate:.1%}"
            elif pool_health == 'degraded':
                health_info['status'] = 'degraded' 
                health_info['message'] = "Connection pool utilization high"
            else:
                health_info['status'] = 'healthy'
                health_info['message'] = "All checks passed"
            
            # Cache the result
            self._health_cache = health_info
            self._last_health_check = current_time
            
            total_time = sum(
                check.get('response_time_ms', 0) 
                for check in health_info['checks'].values()
            )
            logger.debug(f"Database health check completed in {total_time:.2f}ms")
            
            return health_info
            
        except Exception as e:
            health_info['status'] = 'unhealthy'
            health_info['error'] = str(e)
            health_info['error_type'] = type(e).__name__
            
            logger.error(f"Database health check failed: {e}")
            return health_info
    
    def _get_pool_status(self) -> Dict[str, Any]:
        """Get detailed connection pool status."""
        try:
            if hasattr(self.engine.pool, 'size'):
                pool_size = self.engine.pool.size()
                checked_in = self.engine.pool.checkedin()
                checked_out = self.engine.pool.checkedout() 
                overflow = self.engine.pool.overflow()
                total = self.engine.pool.total()
                
                return {
                    'pool_size': pool_size,
                    'checked_in': checked_in,
                    'checked_out': checked_out,
                    'overflow': overflow,
                    'total': total,
                    'invalid': getattr(self.engine.pool, 'invalid', lambda: 0)(),
                    'utilization': checked_out / max(1, pool_size)
                }
            else:
                # For NullPool or StaticPool
                return {
                    'pool_type': type(self.engine.pool).__name__,
                    'info': 'No pool statistics available'
                }
        except Exception as e:
            logger.warning(f"Failed to get pool status: {e}")
            return {'error': str(e)}
    
    def retry_on_disconnect(self, func, *args, max_retries=3, base_delay=0.5, **kwargs):
        """
        Retry database operations on connection failures with exponential backoff.
        
        Args:
            func: Function to retry
            max_retries: Maximum number of retry attempts
            base_delay: Base delay between retries
            *args, **kwargs: Arguments to pass to func
            
        Returns:
            Result of func
            
        Raises:
            Last exception if all retries fail
        """
        @retry_database_operation(
            max_attempts=max_retries,
            base_delay=base_delay
        )
        def wrapped():
            return func(*args, **kwargs)
        
        return wrapped()
    
    def execute_with_timeout(self, query: str, timeout: int = 30, params: Optional[Dict] = None):
        """
        Execute a query with a specific timeout.
        
        Args:
            query: SQL query to execute
            timeout: Timeout in seconds
            params: Query parameters
            
        Returns:
            Query result
        """
        with self.get_session() as session:
            # Set statement timeout for this query
            session.execute(text(f"SET LOCAL statement_timeout = {timeout * 1000}"))
            
            # Execute the actual query
            result = session.execute(text(query), params or {})
            return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive database statistics."""
        with self._stats_lock:
            stats = self._stats.copy()
        
        # Calculate derived metrics
        total_queries = stats['total_queries']
        if total_queries > 0:
            stats['success_rate'] = stats['successful_queries'] / total_queries
            stats['error_rate'] = stats['failed_queries'] / total_queries
            stats['slow_query_rate'] = stats['slow_queries'] / total_queries
        else:
            stats['success_rate'] = 0
            stats['error_rate'] = 0
            stats['slow_query_rate'] = 0
        
        # Add pool status
        stats['pool_status'] = self._get_pool_status()
        
        return stats
    
    def reset_statistics(self):
        """Reset database statistics."""
        with self._stats_lock:
            self._stats = {
                'total_connections': 0,
                'successful_connections': 0,
                'failed_connections': 0,
                'total_queries': 0,
                'successful_queries': 0,
                'failed_queries': 0,
                'slow_queries': 0,
                'avg_query_time': 0,
                'last_connection_time': 0
            }
        logger.info("Database statistics reset")
    
    def validate_connection(self, timeout: int = 5) -> bool:
        """
        Validate database connection is alive.
        
        Args:
            timeout: Query timeout in seconds
            
        Returns:
            True if connection is valid, False otherwise
        """
        try:
            result = self.execute_with_timeout("SELECT 1", timeout=timeout)
            return result.scalar() == 1
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False
    
    def close(self):
        """Clean shutdown of database connections."""
        if self.engine:
            # Log final statistics
            stats = self.get_statistics()
            logger.info(f"Database manager shutting down. Final stats: {stats}")
            
            # Dispose of connection pool
            self.engine.dispose()
            logger.info("Database connections closed")
    
    def __enter__(self):
        """Support using DatabaseManager as context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up on context manager exit."""
        self.close()

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
        from .models import Document, Page, ProcessingEvent, Artifact  # noqa
        Base.metadata.create_all(bind=db_manager.engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise

def get_db_health() -> Dict[str, Any]:
    """Get database health status."""
    return db_manager.health_check()
