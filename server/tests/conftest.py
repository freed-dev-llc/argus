"""Shared test fixtures."""

from __future__ import annotations

import pytest

from argus.config import get_settings


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset cached settings and the lazy NetBox client between tests."""
    from argus.tools import read_tools

    get_settings.cache_clear()
    read_tools._client = None
    yield
    get_settings.cache_clear()
    read_tools._client = None
