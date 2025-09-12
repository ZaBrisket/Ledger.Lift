"""
Prometheus metrics for Ledger Lift API.
"""
import time
from typing import Dict, Any
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Request metrics
REQUEST_COUNT = Counter(
    'ledger_lift_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'ledger_lift_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

# Document processing metrics
DOCUMENT_UPLOADS = Counter(
    'ledger_lift_document_uploads_total',
    'Total number of document uploads',
    ['status']
)

DOCUMENT_PROCESSING_DURATION = Histogram(
    'ledger_lift_document_processing_seconds',
    'Document processing duration in seconds',
    ['status']
)

DOCUMENT_PROCESSING_QUEUE_SIZE = Gauge(
    'ledger_lift_processing_queue_size',
    'Number of documents in processing queue'
)

# Table extraction metrics
TABLE_EXTRACTIONS = Counter(
    'ledger_lift_table_extractions_total',
    'Total number of table extractions',
    ['engine', 'status']
)

TABLE_EXTRACTION_DURATION = Histogram(
    'ledger_lift_table_extraction_seconds',
    'Table extraction duration in seconds',
    ['engine']
)

TABLES_EXTRACTED = Counter(
    'ledger_lift_tables_extracted_total',
    'Total number of tables extracted',
    ['engine']
)

# Excel export metrics
EXCEL_EXPORTS = Counter(
    'ledger_lift_excel_exports_total',
    'Total number of Excel exports',
    ['status']
)

EXCEL_EXPORT_DURATION = Histogram(
    'ledger_lift_excel_export_seconds',
    'Excel export duration in seconds'
)

# Database metrics
DATABASE_QUERIES = Counter(
    'ledger_lift_database_queries_total',
    'Total number of database queries',
    ['operation', 'table']
)

DATABASE_QUERY_DURATION = Histogram(
    'ledger_lift_database_query_seconds',
    'Database query duration in seconds',
    ['operation', 'table']
)

# S3 metrics
S3_OPERATIONS = Counter(
    'ledger_lift_s3_operations_total',
    'Total number of S3 operations',
    ['operation', 'status']
)

S3_OPERATION_DURATION = Histogram(
    'ledger_lift_s3_operation_seconds',
    'S3 operation duration in seconds',
    ['operation']
)

# System metrics
ACTIVE_DOCUMENTS = Gauge(
    'ledger_lift_active_documents',
    'Number of active documents by status',
    ['status']
)

SYSTEM_INFO = Info(
    'ledger_lift_system_info',
    'System information'
)

# Error metrics
ERRORS = Counter(
    'ledger_lift_errors_total',
    'Total number of errors',
    ['error_type', 'component']
)

class MetricsCollector:
    """Collects and manages application metrics."""
    
    def __init__(self):
        self.start_time = time.time()
        self._setup_system_info()
    
    def _setup_system_info(self):
        """Set up system information."""
        import platform
        import sys
        
        SYSTEM_INFO.info({
            'version': '0.1.0',
            'python_version': sys.version,
            'platform': platform.platform(),
            'architecture': platform.architecture()[0]
        })
    
    def record_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request metrics."""
        REQUEST_COUNT.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()
        
        REQUEST_DURATION.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
    
    def record_document_upload(self, status: str):
        """Record document upload metric."""
        DOCUMENT_UPLOADS.labels(status=status).inc()
    
    def record_document_processing(self, status: str, duration: float):
        """Record document processing metrics."""
        DOCUMENT_PROCESSING_DURATION.labels(status=status).observe(duration)
    
    def record_table_extraction(self, engine: str, status: str, duration: float, tables_count: int = 0):
        """Record table extraction metrics."""
        TABLE_EXTRACTIONS.labels(engine=engine, status=status).inc()
        TABLE_EXTRACTION_DURATION.labels(engine=engine).observe(duration)
        
        if tables_count > 0:
            TABLES_EXTRACTED.labels(engine=engine).inc(tables_count)
    
    def record_excel_export(self, status: str, duration: float):
        """Record Excel export metrics."""
        EXCEL_EXPORTS.labels(status=status).inc()
        EXCEL_EXPORT_DURATION.observe(duration)
    
    def record_database_query(self, operation: str, table: str, duration: float):
        """Record database query metrics."""
        DATABASE_QUERIES.labels(operation=operation, table=table).inc()
        DATABASE_QUERY_DURATION.labels(operation=operation, table=table).observe(duration)
    
    def record_s3_operation(self, operation: str, status: str, duration: float):
        """Record S3 operation metrics."""
        S3_OPERATIONS.labels(operation=operation, status=status).inc()
        S3_OPERATION_DURATION.labels(operation=operation).observe(duration)
    
    def record_error(self, error_type: str, component: str):
        """Record error metric."""
        ERRORS.labels(error_type=error_type, component=component).inc()
    
    def update_active_documents(self, status_counts: Dict[str, int]):
        """Update active documents gauge."""
        for status, count in status_counts.items():
            ACTIVE_DOCUMENTS.labels(status=status).set(count)
    
    def update_processing_queue_size(self, size: int):
        """Update processing queue size gauge."""
        DOCUMENT_PROCESSING_QUEUE_SIZE.set(size)
    
    def get_metrics(self) -> str:
        """Get all metrics in Prometheus format."""
        return generate_latest()
    
    def get_metrics_response(self) -> Response:
        """Get metrics as FastAPI response."""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )

# Global metrics collector instance
metrics_collector = MetricsCollector()

def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return metrics_collector