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
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

def setup_telemetry():
    """Initialize OpenTelemetry tracing and metrics"""
    
    # Only setup if OTEL environment variables are present
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        print("OTEL_EXPORTER_OTLP_ENDPOINT not set, skipping telemetry setup")
        return
    
    # Create resource
    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", "ledger-lift-api"),
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
    request_counter = meter.create_counter(
        name="api_requests_total",
        description="Total number of API requests",
    )
    
    request_duration = meter.create_histogram(
        name="api_request_duration_ms",
        description="API request duration in milliseconds",
    )
    
    error_counter = meter.create_counter(
        name="api_errors_total",
        description="Total number of API errors",
    )
    
    # Store metrics for use in routes
    return {
        "tracer": tracer,
        "request_counter": request_counter,
        "request_duration": request_duration,
        "error_counter": error_counter,
    }

def instrument_app(app):
    """Instrument FastAPI app with OpenTelemetry"""
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument()
    
    # Instrument requests
    RequestsInstrumentor().instrument()
    
    print("OpenTelemetry instrumentation enabled")

def get_tracer():
    """Get the tracer instance"""
    return trace.get_tracer(__name__)

def get_meter():
    """Get the meter instance"""
    return metrics.get_meter(__name__)