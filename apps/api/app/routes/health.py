import logging
import time
import psutil
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from ..db import get_db_health
from ..aws import get_s3_health, get_s3_stats
from ..services import DocumentService

logger = logging.getLogger(__name__)
router = APIRouter()

def get_system_health() -> Dict[str, Any]:
    """Get system resource utilization."""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_info = {
            'total': memory.total,
            'available': memory.available,
            'percent': memory.percent,
            'used': memory.used
        }
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_info = {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': (disk.used / disk.total) * 100
        }
        
        # Network stats (if available)
        try:
            network = psutil.net_io_counters()
            network_info = {
                'bytes_sent': network.bytes_sent,
                'bytes_recv': network.bytes_recv,
                'packets_sent': network.packets_sent,
                'packets_recv': network.packets_recv
            }
        except:
            network_info = None
        
        return {
            'status': 'healthy',
            'cpu_percent': cpu_percent,
            'memory': memory_info,
            'disk': disk_info,
            'network': network_info,
            'timestamp': time.time()
        }
        
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        }

@router.get("/healthz")
def healthz():
    """Basic health check endpoint."""
    return {"ok": True, "timestamp": time.time()}

@router.get("/health")
def health():
    """Comprehensive health check with all system components."""
    start_time = time.time()
    
    try:
        # Check all components
        db_health = get_db_health()
        s3_health = get_s3_health()
        system_health = get_system_health()
        
        # Get document statistics
        doc_stats_result = DocumentService.get_document_stats()
        doc_stats = doc_stats_result.data if doc_stats_result.success else None
        
        # Determine overall health status
        overall_status = 'healthy'
        issues = []
        
        if db_health.get('status') != 'healthy':
            overall_status = 'degraded'
            issues.append('database')
        
        if s3_health.get('status') != 'healthy':
            overall_status = 'degraded'
            issues.append('s3')
        
        if system_health.get('status') != 'healthy':
            overall_status = 'degraded'
            issues.append('system')
        
        # Check resource thresholds
        if system_health.get('cpu_percent', 0) > 90:
            overall_status = 'degraded'
            issues.append('high_cpu')
        
        if system_health.get('memory', {}).get('percent', 0) > 90:
            overall_status = 'degraded'
            issues.append('high_memory')
        
        if system_health.get('disk', {}).get('percent', 0) > 90:
            overall_status = 'degraded'
            issues.append('high_disk')
        
        # If any critical component is down, mark as unhealthy
        if any(comp.get('status') == 'unhealthy' for comp in [db_health, s3_health]):
            overall_status = 'unhealthy'
        
        response_time = time.time() - start_time
        
        health_response = {
            'status': overall_status,
            'timestamp': time.time(),
            'response_time_ms': round(response_time * 1000, 2),
            'issues': issues,
            'components': {
                'database': db_health,
                's3': s3_health,
                'system': system_health
            }
        }
        
        # Add document stats if available
        if doc_stats:
            health_response['document_stats'] = doc_stats
        
        # Add S3 statistics
        try:
            s3_stats = get_s3_stats()
            health_response['s3_stats'] = s3_stats
        except Exception as e:
            logger.warning(f"Failed to get S3 stats: {e}")
        
        logger.debug(f"Health check completed in {response_time:.3f}s - Status: {overall_status}")
        
        return health_response
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time(),
            'response_time_ms': round((time.time() - start_time) * 1000, 2)
        }

@router.get("/health/database")
def health_database():
    """Database-specific health check."""
    return get_db_health()

@router.get("/health/s3")
def health_s3():
    """S3-specific health check."""
    return get_s3_health()

@router.get("/health/system")
def health_system():
    """System resource health check."""
    return get_system_health()

@router.get("/readiness")
def readiness():
    """Kubernetes readiness probe - checks if app can serve traffic."""
    try:
        # Quick checks for critical dependencies
        db_health = get_db_health()
        s3_health = get_s3_health()
        
        if (db_health.get('status') == 'healthy' and 
            s3_health.get('status') == 'healthy'):
            return {
                'ready': True,
                'timestamp': time.time()
            }
        else:
            raise HTTPException(
                status_code=503,
                detail={
                    'ready': False,
                    'database_status': db_health.get('status'),
                    's3_status': s3_health.get('status'),
                    'timestamp': time.time()
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                'ready': False,
                'error': str(e),
                'timestamp': time.time()
            }
        )

@router.get("/liveness")
def liveness():
    """Kubernetes liveness probe - checks if app is alive."""
    try:
        # Very basic check - if we can respond, we're alive
        return {
            'alive': True,
            'timestamp': time.time(),
            'uptime': time.time()  # This would be better with actual start time
        }
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                'alive': False,
                'error': str(e),
                'timestamp': time.time()
            }
        )
