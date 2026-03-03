"""Contract tests — verify adapters satisfy ChannelAdapter Protocol."""

from chatpilot.channels.adapter import ChannelAdapter
from chatpilot.channels.line import LineAdapter
from chatpilot.channels.mock import MockAdapter


def test_mock_adapter_satisfies_protocol():
    """MockAdapter should be an instance of ChannelAdapter Protocol."""
    adapter = MockAdapter()
    assert isinstance(adapter, ChannelAdapter)


def test_line_adapter_satisfies_protocol():
    """LineAdapter should be an instance of ChannelAdapter Protocol."""
    adapter = LineAdapter()
    assert isinstance(adapter, ChannelAdapter)


def test_mock_adapter_has_platform():
    adapter = MockAdapter()
    assert adapter.platform == "mock"


def test_line_adapter_has_platform():
    adapter = LineAdapter()
    assert adapter.platform == "line"
