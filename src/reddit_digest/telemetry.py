from __future__ import annotations

import atexit
import logging
import os

from opentelemetry import metrics, trace

logger = logging.getLogger(__name__)

_initialized = False


def setup_telemetry() -> None:
    """Configure OTel providers and auto-instrumentation.

    No-op when OTEL_EXPORTER_OTLP_ENDPOINT is not set.
    """
    global _initialized
    if _initialized:
        return

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.info("OTel export disabled (OTEL_EXPORTER_OTLP_ENDPOINT not set)")
        _initialized = True
        return

    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from importlib.metadata import version

    service_name = os.environ.get("OTEL_SERVICE_NAME", "reddit-digest-agent")
    try:
        service_version = version("reddit-digest-agent")
    except Exception:
        service_version = "unknown"
    resource = Resource.create(
        {"service.name": service_name, "service.version": service_version}
    )

    # Traces
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    # Metrics
    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Auto-instrumentation for OpenAI SDK (used by langchain-openai)
    from opentelemetry.instrumentation.openai import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    # OpenInference instrumentation for LangChain/LangGraph
    # Adds span.kind (CHAIN/LLM/TOOL) attributes for Phoenix
    from openinference.instrumentation.langchain import LangChainInstrumentor

    LangChainInstrumentor().instrument()

    def _shutdown() -> None:
        tracer_provider.shutdown()
        meter_provider.shutdown()

    atexit.register(_shutdown)
    _initialized = True
    logger.info("OTel telemetry configured (endpoint=%s)", endpoint)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    return metrics.get_meter(name)
