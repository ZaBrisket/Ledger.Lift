import os
import psutil
import logging
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, HTTPException

from ..db import db_manager
from ..aws import s3_client
from ..settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Cache for health status
_health_cache = {
    'status': None,
    'timestamp': None,
    'ttl': 30  # seconds
}

def get_system_health() -> Dict[str, Any]:
    """Get system resource utilization"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_info = {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent
        }
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_info = {
            'total': disk.total,
            'free': disk.free,
            'used': disk.used,
            'percent': disk.percent
        }
        
        # Process info
        process = psutil.Process(os.getpid())
        process_info = {
            'pid': process.pid,
            'memory_mb': process.memory_info().rss / 1024 / 1024,
            'cpu_percent': process.cpu_percent(),
            'num_threads': process.num_threads(),
            'connections': len(process.connections())
        }
        
        return {
            'healthy': True,
            'cpu_percent': cpu_percent,
            'memory': memory_info,
            'disk': disk_info,
            'process': process_info
        }
    except Exception as e:
        logger.error(f"Failed to get system health: {str(e)}")
        return {
            'healthy': False,
            'error': str(e)
        }

@router.get("/healthz")
def healthz():
    """Basic health check endpoint"""
    return {"ok": True, "timestamp": datetime.utcnow().isoformat()}

@router.get("/health")
async def health():
    """Comprehensive health check with caching"""
    now = datetime.utcnow()
    
    # Check cache
    if (_health_cache['timestamp'] and 
        (now - _health_cache['timestamp']).total_seconds() < _health_cache['ttl']):
        return _health_cache['status']
    
    # Perform health checks
    health_status = {
        'timestamp': now.isoformat(),
        'services': {},
        'status': 'healthy'
    }
    
    # Database health
    try:
        db_health = db_manager.check_health()
        health_status['services']['database'] = db_health
        if not db_health['healthy']:
            health_status['status'] = 'degraded'
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        health_status['services']['database'] = {
            'healthy': False,
            'error': str(e)
        }
        health_status['status'] = 'unhealthy'
    
    # S3 health
    try:
        s3_health = s3_client.get_health()
        health_status['services']['s3'] = s3_health
        if not s3_health['healthy']:
            health_status['status'] = 'degraded'
    except Exception as e:
        logger.error(f"S3 health check failed: {str(e)}")
        health_status['services']['s3'] = {
            'healthy': False,
            'error': str(e)
        }
        health_status['status'] = 'degraded'
    
    # System health
    system_health = get_system_health()
    health_status['services']['system'] = system_health
    
    # Overall health determination
    if health_status['status'] == 'healthy':
        # Check system resources
        if system_health.get('cpu_percent', 0) > 90:
            health_status['status'] = 'degraded'
            health_status['warnings'] = health_status.get('warnings', [])
            health_status['warnings'].append('High CPU usage')
        
        if system_health.get('memory', {}).get('percent', 0) > 90:
            health_status['status'] = 'degraded'
            health_status['warnings'] = health_status.get('warnings', [])
            health_status['warnings'].append('High memory usage')
        
        if system_health.get('disk', {}).get('percent', 0) > 90:
            health_status['status'] = 'degraded'
            health_status['warnings'] = health_status.get('warnings', [])
            health_status['warnings'].append('High disk usage')
    
    # Cache the result
    _health_cache['status'] = health_status
    _health_cache['timestamp'] = now
    
    # Return appropriate HTTP status
    if health_status['status'] == 'unhealthy':
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status

@router.get("/health/database")
async def health_database():
    """Database-specific health check"""
    try:
        db_health = db_manager.check_health()
        if not db_health['healthy']:
            raise HTTPException(status_code=503, detail=db_health)
        return db_health
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail={'healthy': False, 'error': str(e)}
        )

@router.get("/health/s3")
async def health_s3():
    """S3-specific health check"""
    try:
        s3_health = s3_client.get_health()
        if not s3_health['healthy']:
            raise HTTPException(status_code=503, detail=s3_health)
        return s3_health
    except Exception as e:
        logger.error(f"S3 health check failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail={'healthy': False, 'error': str(e)}
        )

@router.get("/health/system")
async def health_system():
    """System resources health check"""
    system_health = get_system_health()
    if not system_health['healthy']:
        raise HTTPException(status_code=503, detail=system_health)
    return system_health

@router.get("/ready")
async def readiness():
    """Readiness probe for Kubernetes"""
    # Check if all critical services are ready
    try:
        # Quick database check
        db_health = db_manager.check_health()
        if not db_health['healthy']:
            raise HTTPException(
                status_code=503,
                detail={'ready': False, 'reason': 'Database not ready'}
            )
        
        # Quick S3 check
        s3_health = s3_client.get_health()
        if s3_health.get('circuit_breaker', {}).get('state') == 'open':
            raise HTTPException(
                status_code=503,
                detail={'ready': False, 'reason': 'S3 circuit breaker open'}
            )
        
        return {
            'ready': True,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail={'ready': False, 'error': str(e)}
        )

@router.get("/live")
async def liveness():
    """Liveness probe for Kubernetes"""
    # Basic check to see if the service is alive
    return {
        'alive': True,
        'timestamp': datetime.utcnow().isoformat(),
        'uptime': get_uptime()
    }

def get_uptime() -> str:
    """Get service uptime"""
    try:
        process = psutil.Process(os.getpid())
        create_time = datetime.fromtimestamp(process.create_time())
        uptime = datetime.now() - create_time
        
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        return f"{days}d {hours}h {minutes}m {seconds}s"
    except:
        return "unknown"

@router.get("/metrics")
async def metrics():
    """Basic metrics endpoint"""
    try:
        # Collect metrics
        metrics_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'system': get_system_health(),
            'database': db_manager.check_health(),
            's3': s3_client.get_health(),
            'application': {
                'version': settings.app_version if hasattr(settings, 'app_version') else '0.1.0',
                'environment': settings.environment if hasattr(settings, 'environment') else 'production'
            }
        }
        
        return metrics_data
    except Exception as e:
        logger.error(f"Failed to collect metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to collect metrics'}
        )