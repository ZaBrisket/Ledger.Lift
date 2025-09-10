import os
from opentelemetry import trace
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.requests import RequestsInstrumentor

def setup_telemetry():
    """Initialize OpenTelemetry tracing and metrics for worker"""
    
    # Only setup if OTEL environment variables are present
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        print("OTEL_EXPORTER_OTLP_ENDPOINT not set, skipping telemetry setup")
        return None
    
    # Create resource
    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", "ledger-lift-worker"),
        "service.version": "0.1.0",
    })
    
    # Setup tracing
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer = trace.get_tracer(__name__)
    
    # Add OTLP exporter
    otlp_exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
        insecure=True,  # Set to False for production with TLS
    )
    
    span_processor = BatchSpanProcessor(otlp_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)
    
    # Setup metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            insecure=True,
        ),
        export_interval_millis=10000,  # Export every 10 seconds
    )
    
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )
    metrics.set_meter_provider(meter_provider)
    
    # Create meters
    meter = metrics.get_meter(__name__)
    
    # Create custom metrics
    document_processed_counter = meter.create_counter(
        name="worker_documents_processed_total",
        description="Total number of documents processed",
    )
    
    render_time_histogram = meter.create_histogram(
        name="worker_render_time_ms",
        description="Document rendering time in milliseconds",
    )
    
    extract_time_histogram = meter.create_histogram(
        name="worker_extract_time_ms",
        description="Table extraction time in milliseconds",
    )
    
    ocr_pages_counter = meter.create_counter(
        name="worker_ocr_pages_processed_total",
        description="Total number of pages processed with OCR",
    )
    
    ocr_confidence_histogram = meter.create_histogram(
        name="worker_ocr_mean_confidence",
        description="OCR mean confidence score",
    )
    
    # Instrument requests
    RequestsInstrumentor().instrument()
    
    print("OpenTelemetry instrumentation enabled for worker")
    
    # Store metrics for use in worker functions
    return {
        "tracer": tracer,
        "document_processed_counter": document_processed_counter,
        "render_time_histogram": render_time_histogram,
        "extract_time_histogram": extract_time_histogram,
        "ocr_pages_counter": ocr_pages_counter,
        "ocr_confidence_histogram": ocr_confidence_histogram,
    }

def get_tracer():
    """Get the tracer instance"""
    return trace.get_tracer(__name__)

def get_meter():
    """Get the meter instance"""
    return metrics.get_meter(__name__)