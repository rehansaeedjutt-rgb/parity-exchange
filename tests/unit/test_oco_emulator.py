"""Tests for the OCO emulator. Uses a fake adapter, no network."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from parity.emulate.oco import OCOEmulator
from parity.exchanges.base import ExchangeAdapter
from parity.schemas import (
    OCORequest,
    Order,
    OrderRequest,
    OrderStatus,
    OrderType,
    Side,
)


class FakeAdapter(ExchangeAdapter):
    """Adapter that keeps state in memory. Used to drive the emulator."""

    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self.cancellations: list[str] = []
        self._next_id = 1

    @property
    def name(self) -> str:
        return "fake"

    @property
    def supports_native_oco(self) -> bool:
        return False

    async def place_order(self, req: OrderRequest) -> Order:
        oid = str(self._next_id)
        self._next_id += 1
        order = Order(
            exchange=self.name,
            order_id=oid,
            client_order_id=req.client_order_id,
            symbol=req.symbol,
            side=req.side,
            order_type=req.order_type,
            quantity=req.quantity,
            executed_quantity=Decimal(0),
            price=req.price,
            status=OrderStatus.NEW,
            created_at=datetime.now(UTC),
        )
        self.orders[oid] = order
        return order

    async def cancel_order(self, symbol: str, order_id: str) -> Order:
        self.cancellations.append(order_id)
        o = self.orders[order_id]
        updated = o.model_copy(update={"status": OrderStatus.CANCELED})
        self.orders[order_id] = updated
        return updated

    async def get_order(self, symbol: str, order_id: str) -> Order:
        return self.orders[order_id]

    async def place_oco(self, req: OCORequest):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def cancel_oco(self, symbol: str, list_id: str) -> None:
        raise NotImplementedError

    def fill(self, order_id: str) -> None:
        """Test helper: mark an order as filled."""
        o = self.orders[order_id]
        self.orders[order_id] = o.model_copy(
            update={"status": OrderStatus.FILLED, "executed_quantity": o.quantity}
        )


def _oco_request() -> OCORequest:
    return OCORequest(
        symbol="BTCUSDT",
        side=Side.SELL,
        quantity=Decimal("1"),
        price=Decimal("50000"),
        stop_price=Decimal("48000"),
        stop_limit_price=Decimal("47900"),
    )


@pytest.mark.asyncio
async def test_place_creates_both_legs() -> None:
    adapter = FakeAdapter()
    emu = OCOEmulator(adapter)
    result = await emu.place(_oco_request())

    assert result.emulated is True
    assert result.limit_order.order_type is OrderType.LIMIT
    assert result.stop_order.order_type is OrderType.STOP_LOSS_LIMIT
    assert result.list_id.startswith("oco-")
    assert len(adapter.orders) == 2


@pytest.mark.asyncio
async def test_reconcile_cancels_stop_after_limit_fill() -> None:
    adapter = FakeAdapter()
    emu = OCOEmulator(adapter)
    result = await emu.place(_oco_request())

    adapter.fill(result.limit_order.order_id)

    group = await emu.reconcile(result.list_id)
    assert group is None  # group closed, both legs resolved
    assert result.stop_order.order_id in adapter.cancellations


@pytest.mark.asyncio
async def test_reconcile_cancels_limit_after_stop_fill() -> None:
    adapter = FakeAdapter()
    emu = OCOEmulator(adapter)
    result = await emu.place(_oco_request())

    adapter.fill(result.stop_order.order_id)

    group = await emu.reconcile(result.list_id)
    assert group is None
    assert result.limit_order.order_id in adapter.cancellations


@pytest.mark.asyncio
async def test_reconcile_keeps_group_open_when_nothing_fills() -> None:
    adapter = FakeAdapter()
    emu = OCOEmulator(adapter)
    result = await emu.place(_oco_request())

    group = await emu.reconcile(result.list_id)
    assert group is not None
    assert group.list_id == result.list_id
    assert adapter.cancellations == []


@pytest.mark.asyncio
async def test_cancel_cancels_both_legs() -> None:
    adapter = FakeAdapter()
    emu = OCOEmulator(adapter)
    result = await emu.place(_oco_request())

    await emu.cancel(result.list_id)
    assert result.limit_order.order_id in adapter.cancellations
    assert result.stop_order.order_id in adapter.cancellations
    assert emu.open_groups() == []


@pytest.mark.asyncio
async def test_cancel_unknown_raises() -> None:
    adapter = FakeAdapter()
    emu = OCOEmulator(adapter)
    with pytest.raises(KeyError):
        await emu.cancel("oco-does-not-exist")
