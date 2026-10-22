"""Exchange feature matrix.

Every entry here was verified against the exchange's official API docs
and, where possible, against a live testnet. If a feature is marked
NATIVE, the exchange's own API supports it directly. If it is marked
MISSING, the exchange's API does not expose it and an emulation layer
in this project is required to provide parity.

Sources (checked 2026-10):
- Binance Spot API docs (developers.binance.com)
- MEXC Spot API docs (mexcdevelop.github.io)
- Bitget v2 API docs (bitget.com/api-doc)
"""

from __future__ import annotations

from enum import StrEnum


class Feature(StrEnum):
    """Exchange API features that matter to serious traders."""

    OCO = "oco"  # one-cancels-other
    TRAILING_STOP = "trailing_stop"
    SELF_TRADE_PREVENTION = "stp"
    PEGGED_ORDER = "pegged_order"
    ORDER_AMEND = "order_amend"
    TESTNET = "testnet"
    WS_ORDER_ENTRY = "ws_order_entry"
    COPY_TRADING_API = "copy_trading"


class Support(StrEnum):
    """How well an exchange supports a feature."""

    NATIVE = "native"  # first-class API support
    PARTIAL = "partial"  # limited, or requires workarounds
    MISSING = "missing"  # no API support; emulation needed


class CredentialFields(StrEnum):
    """What the exchange requires for authenticated endpoints."""

    TWO = "two"  # api_key + api_secret (Binance, MEXC)
    THREE = "three"  # api_key + api_secret + passphrase (Bitget)


# The capability matrix. This is the artifact a reviewer reads first.
CAPABILITIES: dict[str, dict[Feature, Support]] = {
    "binance": {
        Feature.OCO: Support.NATIVE,
        Feature.TRAILING_STOP: Support.NATIVE,
        Feature.SELF_TRADE_PREVENTION: Support.NATIVE,
        Feature.PEGGED_ORDER: Support.NATIVE,
        Feature.ORDER_AMEND: Support.NATIVE,
        Feature.TESTNET: Support.NATIVE,
        Feature.WS_ORDER_ENTRY: Support.NATIVE,
        Feature.COPY_TRADING_API: Support.NATIVE,
    },
    "mexc": {
        Feature.OCO: Support.MISSING,
        Feature.TRAILING_STOP: Support.PARTIAL,
        Feature.SELF_TRADE_PREVENTION: Support.MISSING,
        Feature.PEGGED_ORDER: Support.MISSING,
        Feature.ORDER_AMEND: Support.MISSING,
        Feature.TESTNET: Support.MISSING,  # no API testnet at time of writing
        Feature.WS_ORDER_ENTRY: Support.PARTIAL,  # subscription works, order entry limited
        Feature.COPY_TRADING_API: Support.MISSING,
    },
    "bitget": {
        Feature.OCO: Support.MISSING,
        Feature.TRAILING_STOP: Support.PARTIAL,
        Feature.SELF_TRADE_PREVENTION: Support.MISSING,
        Feature.PEGGED_ORDER: Support.MISSING,
        Feature.ORDER_AMEND: Support.MISSING,
        Feature.TESTNET: Support.PARTIAL,  # demo keys, not a full testnet
        Feature.WS_ORDER_ENTRY: Support.MISSING,  # WS is subscription-only for orders
        Feature.COPY_TRADING_API: Support.NATIVE,  # deepest native copy-trading API
    },
}


# Authentication requirements per exchange.
CREDENTIALS: dict[str, CredentialFields] = {
    "binance": CredentialFields.TWO,
    "mexc": CredentialFields.TWO,
    "bitget": CredentialFields.THREE,
}


def has_native(exchange: str, feature: Feature) -> bool:
    """True if the exchange's own API supports the feature."""
    return CAPABILITIES.get(exchange, {}).get(feature) == Support.NATIVE


def needs_emulation(exchange: str, feature: Feature) -> bool:
    """True if the feature has to be provided by our emulation layer."""
    return CAPABILITIES.get(exchange, {}).get(feature) in (Support.MISSING, Support.PARTIAL)


def gaps(exchange: str) -> list[Feature]:
    """All features this exchange either lacks or only partially supports."""
    return [f for f, s in CAPABILITIES.get(exchange, {}).items() if s is not Support.NATIVE]
