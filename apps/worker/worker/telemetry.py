import os
import logging
from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

def init_worker_telemetry():
    """Initialize OpenTelemetry for worker."""
    
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    service_name = os.getenv("OTEL_SERVICE_NAME", "ledger-lift-worker")
    
    if not otlp_endpoint:
        logger.info("OpenTelemetry not configured for worker")
        return
    
    # Create resource
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "0.1.0"
    })
    
    # Configure tracing
    trace_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(trace_provider)
    
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    span_processor = BatchSpanProcessor(otlp_exporter)
    trace_provider.add_span_processor(span_processor)
    
    # Configure metrics
    try:
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otlp_endpoint),
            export_interval_millis=60000
        )
        metric_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(metric_provider)
    except Exception as e:
        logger.warning(f"Failed to configure worker metrics: {e}")
    
    logger.info(f"Worker OpenTelemetry initialized -> {otlp_endpoint}")


def get_tracer(name: str = "ledger-lift-worker"):
    """Get worker tracer."""
    return trace.get_tracer(name)


def get_meter(name: str = "ledger-lift-worker"):
    """Get worker meter."""
    return metrics.get_meter(name)


# Initialize telemetry
init_worker_telemetry()

# Create global meter for custom metrics
meter = get_meter()

# Worker-specific metrics
render_pages_counter = meter.create_counter(
    "render_pages_processed_total",
    description="Total pages rendered",
    unit="1"
)

render_time_histogram = meter.create_histogram(
    "render_time_ms",
    description="Time taken to render pages in milliseconds",
    unit="ms"
)

ocr_pages_counter = meter.create_counter(
    "ocr_pages_processed_total",
    description="Total pages processed with OCR",
    unit="1"
)

ocr_confidence_histogram = meter.create_histogram(
    "ocr_mean_confidence",
    description="OCR confidence scores",
    unit="1"
)

consensus_candidates_counter = meter.create_counter(
    "consensus_candidates_total",
    description="Total consensus candidates evaluated",
    unit="1"
)

consensus_engine_counter = meter.create_counter(
    "consensus_selected_engine_total",
    description="Engines selected by consensus",
    unit="1"
)