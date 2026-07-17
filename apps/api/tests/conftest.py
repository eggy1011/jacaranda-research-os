from __future__ import annotations

import json
import socket
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest import MonkeyPatch

FIXTURES = Path(__file__).parent / "fixtures" / "market_data"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 7, 16, 8, 30, tzinfo=UTC)


@pytest.fixture
def load_market_fixture() -> Callable[[str], dict[str, object]]:
    def load(name: str) -> dict[str, object]:
        value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("market fixture must be a JSON object")
        return value

    return load


@pytest.fixture(autouse=True)
def block_live_network(monkeypatch: MonkeyPatch) -> Iterator[None]:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    yield
