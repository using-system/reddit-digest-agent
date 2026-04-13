from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

import opentelemetry.metrics._internal as _metrics_internal
import opentelemetry.trace as _trace_mod
from opentelemetry import metrics, trace


def _reset_otel_providers() -> None:
    """Reset OTel global provider state for test isolation.

    The OTel SDK uses a Once guard that prevents re-setting providers.
    This helper resets those guards so each test starts clean.
    """
    _trace_mod._TRACER_PROVIDER_SET_ONCE._done = False
    _trace_mod._TRACER_PROVIDER = None
    _metrics_internal._METER_PROVIDER_SET_ONCE._done = False
    _metrics_internal._METER_PROVIDER = None


class TestSetupTelemetryDisabled:
    """When OTEL_EXPORTER_OTLP_ENDPOINT is not set, telemetry is a no-op."""

    def test_no_op_when_endpoint_unset(self):
        env = os.environ.copy()
        env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        with patch.dict(os.environ, env, clear=True):
            import reddit_digest.telemetry as tel

            tel._initialized = False
            tel.setup_telemetry()

            tracer = trace.get_tracer("test")
            assert tracer is not None
            # NoOp tracer produces non-recording spans
            with tracer.start_as_current_span("test-span") as span:
                assert not span.is_recording()

    def test_get_tracer_returns_tracer(self):
        from reddit_digest.telemetry import get_tracer

        tracer = get_tracer("test")
        assert tracer is not None

    def test_get_meter_returns_meter(self):
        from reddit_digest.telemetry import get_meter

        meter = get_meter("test")
        assert meter is not None


@pytest.fixture(autouse=True)
def reset_telemetry():
    """Reset telemetry state between tests."""
    import reddit_digest.telemetry as mod

    mod._initialized = False
    yield
    mod._initialized = False


@patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"})
def test_setup_telemetry_instruments_langchain():
    """LangChainInstrumentor.instrument() must be called during setup_telemetry()."""
    import reddit_digest.telemetry as tel

    mock_instance = MagicMock()
    mock_lc_cls = MagicMock(return_value=mock_instance)

    # Patch all the lazy-imported SDK symbols at their canonical paths so that
    # setup_telemetry() does not try to open real network connections.
    patches = [
        patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"),
        patch("opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"),
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
        patch("opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader"),
        patch("opentelemetry.instrumentation.openai.OpenAIInstrumentor"),
        patch("openinference.instrumentation.langchain.LangChainInstrumentor", mock_lc_cls),
    ]

    tel._initialized = False
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
    ):
        tel.setup_telemetry()

    mock_instance.instrument.assert_called_once()


class TestSetupTelemetryEnabled:
    """When OTEL_EXPORTER_OTLP_ENDPOINT is set, providers are configured."""

    def test_tracer_provider_configured(self):
        env = {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
            "OTEL_SERVICE_NAME": "test-service",
        }
        with patch.dict(os.environ, env, clear=False):
            import reddit_digest.telemetry as tel

            # Reset OTel global provider state and the module's init guard
            _reset_otel_providers()
            tel._initialized = False

            tel.setup_telemetry()

            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("test-span") as span:
                assert span.is_recording()

            # Cleanup: shutdown to avoid leaking resources
            provider = trace.get_tracer_provider()
            if hasattr(provider, "shutdown"):
                provider.shutdown()
            meter_provider = metrics.get_meter_provider()
            if hasattr(meter_provider, "shutdown"):
                meter_provider.shutdown()
