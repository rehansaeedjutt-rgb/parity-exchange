"""Tests for the capability matrix."""

from parity.capabilities import CAPABILITIES, Feature, Support, gaps, has_native, needs_emulation


def test_all_exchanges_present() -> None:
    assert set(CAPABILITIES.keys()) == {"binance", "mexc", "bitget"}


def test_binance_has_native_oco() -> None:
    assert has_native("binance", Feature.OCO) is True
    assert needs_emulation("binance", Feature.OCO) is False


def test_mexc_lacks_native_oco() -> None:
    assert has_native("mexc", Feature.OCO) is False
    assert needs_emulation("mexc", Feature.OCO) is True


def test_bitget_lacks_native_oco() -> None:
    assert has_native("bitget", Feature.OCO) is False
    assert needs_emulation("bitget", Feature.OCO) is True


def test_mexc_no_testnet() -> None:
    """MEXC does not expose a public API testnet. This is the reason it
    shows up as MISSING; developers are forced to test in production."""
    assert CAPABILITIES["mexc"][Feature.TESTNET] is Support.MISSING


def test_bitget_no_ws_order_entry() -> None:
    """Bitget's WS is subscription-only; orders must go through REST."""
    assert CAPABILITIES["bitget"][Feature.WS_ORDER_ENTRY] is Support.MISSING


def test_gaps_lists_partial_and_missing() -> None:
    mexc_gaps = gaps("mexc")
    assert Feature.OCO in mexc_gaps
    assert Feature.TESTNET in mexc_gaps
    # MEXC has native STP? No, they don't. So it should be in the gaps list.
    assert Feature.SELF_TRADE_PREVENTION in mexc_gaps
