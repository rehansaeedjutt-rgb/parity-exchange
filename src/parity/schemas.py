"""Unified order types. Every exchange adapter translates to and from these."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"

    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class TimeInForce(StrEnum):
    GTC = "GTC"  # good till cancelled
    IOC = "IOC"  # immediate or cancel
    FOK = "FOK"  # fill or kill


class OrderStatus(StrEnum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderRequest(BaseModel):
    """A new order to submit. Adapter translates this to the exchange format."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: Side
    order_type: OrderType
    quantity: Decimal = Field(..., gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    time_in_force: TimeInForce = TimeInForce.GTC
    client_order_id: str | None = None


class Order(BaseModel):
    """An order returned by the exchange."""

    model_config = ConfigDict(frozen=True)

    exchange: str
    order_id: str
    client_order_id: str | None = None
    symbol: str
    side: Side
    order_type: OrderType
    quantity: Decimal
    executed_quantity: Decimal
    price: Decimal | None = None
    status: OrderStatus
    created_at: datetime


class OCORequest(BaseModel):
    """One-Cancels-Other order. When one leg fills, the other cancels.

    Native on Binance. On MEXC and Bitget, this has to be emulated by
    submitting two orders and installing a cancel-on-fill watcher.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: Side
    quantity: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., gt=0, description="Limit price leg")
    stop_price: Decimal = Field(..., gt=0, description="Stop trigger")
    stop_limit_price: Decimal = Field(..., gt=0, description="Stop limit price")


class OCOOrder(BaseModel):
    """Result of an OCO submission. Two order IDs and the group ID."""

    model_config = ConfigDict(frozen=True)

    exchange: str
    list_id: str
    limit_order: Order
    stop_order: Order
    emulated: bool = Field(
        default=False,
        description="True if this was emulated on exchanges without native OCO",
    )
