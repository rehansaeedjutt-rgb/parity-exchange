"""Tests for Bitget's three-field credential requirement."""

import pytest

from parity.exchanges.base import ExchangeError
from parity.exchanges.bitget import BitgetAdapter
from parity.exchanges.credentials import Credentials
from parity.exchanges.transport import AiohttpTransport


def test_bitget_requires_passphrase() -> None:
    transport = AiohttpTransport()
    with pytest.raises(ExchangeError, match="passphrase"):
        BitgetAdapter(
            Credentials(api_key="k", api_secret="s", passphrase=None),
            transport,
        )


def test_bitget_accepts_three_fields() -> None:
    transport = AiohttpTransport()
    adapter = BitgetAdapter(
        Credentials(api_key="k", api_secret="s", passphrase="p"),
        transport,
    )
    headers = adapter._auth_headers()
    assert headers["ACCESS-KEY"] == "k"
    assert headers["ACCESS-PASSPHRASE"] == "p"


def test_bitget_allows_no_creds_for_public_calls() -> None:
    transport = AiohttpTransport()
    adapter = BitgetAdapter(None, transport)
    assert adapter._auth_headers() == {}
