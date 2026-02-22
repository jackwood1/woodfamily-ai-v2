"""OpenTelemetry tracing initialization."""

import os
import sys
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from otel_setup.span_buffer import SpanBufferProcessor, set_span_buffer


def init_tracing(
    service_name: str = "woodfamily-ai",
    otlp_endpoint: Optional[str] = None,
    console: bool = False,
    buffer_spans: bool = False,
    buffer_size: int = 100,
) -> trace.Tracer:
    """Initialize OpenTelemetry tracing. Returns a tracer."""
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))

    if console or os.environ.get("OTEL_CONSOLE_EXPORT", "").lower() in ("1", "true", "yes"):
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    if buffer_spans:
        buffer_proc = SpanBufferProcessor(max_spans=buffer_size)
        provider.add_span_processor(buffer_proc)
        set_span_buffer(buffer_proc)

    trace.set_tracer_provider(provider)

    # Auto-instrument common libraries
    HTTPXClientInstrumentor().instrument()
    SQLite3Instrumentor().instrument()

    # OpenAI instrumentation (requires Python 3.10+)
    if sys.version_info >= (3, 10):
        try:
            from opentelemetry.instrumentation.openai import OpenAIInstrumentor
            OpenAIInstrumentor().instrument()
        except ImportError:
            pass

    return trace.get_tracer(service_name, "1.0.0")
