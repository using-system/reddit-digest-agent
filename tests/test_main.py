from unittest.mock import patch, MagicMock, AsyncMock
import pytest


@pytest.mark.asyncio
@patch("reddit_digest.main.build_digest_graph")
@patch("reddit_digest.main.get_tracer")
@patch("reddit_digest.main.get_meter")
async def test_run_digest_uses_session_id(mock_meter, mock_tracer, mock_build):
    """run_digest should wrap graph invocation with using_attributes(session_id=...)."""
    from reddit_digest.main import run_digest

    # Setup mocks
    mock_meter_instance = MagicMock()
    mock_meter.return_value = mock_meter_instance
    mock_meter_instance.create_counter.return_value = MagicMock()
    mock_meter_instance.create_histogram.return_value = MagicMock()

    mock_span = MagicMock()
    mock_tracer_instance = MagicMock()
    mock_tracer.return_value = mock_tracer_instance
    mock_tracer_instance.start_as_current_span.return_value.__enter__ = lambda _: (
        mock_span
    )
    mock_tracer_instance.start_as_current_span.return_value.__exit__ = MagicMock(
        return_value=False
    )

    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {"delivered_ids": []}
    mock_build.return_value = mock_graph

    settings = MagicMock()
    settings.reddit_subreddits = ["r/test"]
    settings.digest_cron = "0 8 * * *"
    db_conn = MagicMock()

    with patch("reddit_digest.main.using_attributes") as mock_using:
        mock_using.return_value.__enter__ = MagicMock()
        mock_using.return_value.__exit__ = MagicMock(return_value=False)
        await run_digest(settings, db_conn)

        mock_using.assert_called_once()
        call_kwargs = mock_using.call_args
        session_id = call_kwargs.kwargs.get("session_id") or call_kwargs[1].get(
            "session_id"
        )
        assert session_id is not None
        assert len(session_id) == 36  # UUID v4 format
