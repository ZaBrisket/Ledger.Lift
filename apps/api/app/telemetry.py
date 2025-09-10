import os
import logging
from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

def init_telemetry():
    """Initialize OpenTelemetry tracing and metrics."""
    
    # Check if OTEL is configured
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    service_name = os.getenv("OTEL_SERVICE_NAME", "ledger-lift-api")
    
    if not otlp_endpoint:
        logger.info("OpenTelemetry not configured (OTEL_EXPORTER_OTLP_ENDPOINT not set)")
        return
    
    # Create resource
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "0.1.0"
    })
    
    # Configure tracing
    trace_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(trace_provider)
    
    # Add OTLP span exporter
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    span_processor = BatchSpanProcessor(otlp_exporter)
    trace_provider.add_span_processor(span_processor)
    
    # Configure metrics
    try:
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otlp_endpoint),
            export_interval_millis=60000  # Export every 60 seconds
        )
        metric_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(metric_provider)
    except Exception as e:
        logger.warning(f"Failed to configure metrics: {e}")
    
    logger.info(f"OpenTelemetry initialized for {service_name} -> {otlp_endpoint}")


def instrument_app(app):
    """Instrument FastAPI app with OpenTelemetry."""
    try:
        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)
        
        # Instrument SQLAlchemy
        SQLAlchemyInstrumentor().instrument()
        
        logger.info("FastAPI and SQLAlchemy instrumented with OpenTelemetry")
    except Exception as e:
        logger.error(f"Failed to instrument app: {e}")


def get_tracer(name: str = "ledger-lift-api"):
    """Get a tracer instance."""
    return trace.get_tracer(name)


def get_meter(name: str = "ledger-lift-api"):
    """Get a meter instance."""
    return metrics.get_meter(name)


# Create global meter for custom metrics
meter = get_meter()

# Custom metrics
adapter_s3_counter = meter.create_counter(
    "adapter_s3_used_total",
    description="Number of times S3 adapter was used",
    unit="1"
)

api_request_duration = meter.create_histogram(
    "api_request_latency_ms",
    description="API request duration in milliseconds",
    unit="ms"
)

artifacts_emitted_counter = meter.create_counter(
    "artifacts_emitted_total",
    description="Total number of artifacts created",
    unit="1"
)

artifact_patch_counter = meter.create_counter(
    "artifact_patch_total", 
    description="Total number of artifact patches",
    unit="1"
)

xlsx_sheets_counter = meter.create_counter(
    "xlsx_sheets_total",
    description="Total number of Excel sheets generated",
    unit="1"
)

rate_limit_hits_counter = meter.create_counter(
    "rate_limit_hits_total",
    description="Total number of rate limit hits",
    unit="1"
)

purge_objects_counter = meter.create_counter(
    "purge_objects_total",
    description="Total number of objects purged",
    unit="1"
)