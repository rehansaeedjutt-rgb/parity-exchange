"""MEXC adapter. No native OCO, no API testnet.

OCO is provided by wrapping place_oco() through an OCOEmulator. This is
the entire point of the project: a caller using the generic interface
does not need to know that MEXC lacks native OCO.
"""

from __future__ import annotations

from typing import Any

from parity.capabilities import Feature, has_native
from parity.emulate.oco import OCOEmulator
from parity.exchanges.base import ExchangeAdapter, ExchangeError
from parity.exchanges.credentials import Credentials
from parity.exchanges.transport import HttpTransport
from parity.schemas import OCOOrder, OCORequest, Order, OrderRequest, OrderStatus, OrderType, Side

_BASE = "https://api.mexc.com"


class MexcAdapter(ExchangeAdapter):
    """MEXC spot adapter. OCO goes through the emulator."""

    def __init__(self, creds: Credentials | None, transport: HttpTransport) -> None:
        if creds is not None and not creds.api_key:
            msg = "MEXC requires api_key"
            raise ExchangeError(msg)
        self._creds = creds
        self._transport = transport
        self._oco = OCOEmulator(self) if not has_native("mexc", Feature.OCO) else None

    @property
    def name(self) -> str:
        return "mexc"

    @property
    def supports_native_oco(self) -> bool:
        return has_native("mexc", Feature.OCO)

    async def place_order(self, req: OrderRequest) -> Order:
        params = {
            "symbol": req.symbol.upper(),
            "side": req.side.value,
            "type": req.order_type.value,
            "quantity": str(req.quantity),
        }
        if req.price is not None:
            params["price"] = str(req.price)
        if req.order_type is OrderType.LIMIT:
            params["timeInForce"] = req.time_in_force.value
        resp = await self._transport.request("POST", f"{_BASE}/api/v3/order", params=params)
        return _parse_order(self.name, resp)

    async def cancel_order(self, symbol: str, order_id: str) -> Order:
        resp = await self._transport.request(
            "DELETE",
            f"{_BASE}/api/v3/order",
            params={"symbol": symbol.upper(), "orderId": order_id},
        )
        return _parse_order(self.name, resp)

    async def get_order(self, symbol: str, order_id: str) -> Order:
        resp = await self._transport.request(
            "GET", f"{_BASE}/api/v3/order", params={"symbol": symbol.upper(), "orderId": order_id}
        )
        return _parse_order(self.name, resp)

    async def place_oco(self, req: OCORequest) -> OCOOrder:
        if self._oco is None:
            # If MEXC ever ships native OCO, we switch to the native path.
            msg = "MEXC native OCO not implemented (capability flag says native; update adapter)"
            raise ExchangeError(msg)
        return await self._oco.place(req)

    async def cancel_oco(self, symbol: str, list_id: str) -> None:
        if self._oco is None:
            msg = "MEXC native OCO not implemented"
            raise ExchangeError(msg)
        await self._oco.cancel(list_id)

    def _emulator(self) -> OCOEmulator | None:
        """Test accessor. The emulator owns the reconcile loop."""
        return self._oco


def _parse_order(exchange: str, raw: dict[str, Any]) -> Order:
    """Translate MEXC's order JSON into our unified Order.

    MEXC's response shape is close to Binance's (they intentionally
    copied it). The differences: no transactTime, and 'NEW' status is
    spelled 'NEW' too, but if a request fails it comes back with an
    error code instead of a partially-populated order.
    """
    from datetime import UTC, datetime
    from decimal import Decimal

    if "code" in raw and raw.get("code") not in (0, 200, "200"):
        msg = f"MEXC error {raw.get('code')}: {raw.get('msg')}"
        raise ExchangeError(msg)

    status_map = {
        "NEW": OrderStatus.NEW,
        "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
        "FILLED": OrderStatus.FILLED,
        "CANCELED": OrderStatus.CANCELED,
        "REJECTED": OrderStatus.REJECTED,
        "EXPIRED": OrderStatus.EXPIRED,
    }
    type_map = {
        "MARKET": OrderType.MARKET,
        "LIMIT": OrderType.LIMIT,
        "LIMIT_MAKER": OrderType.LIMIT_MAKER,
    }

    return Order(
        exchange=exchange,
        order_id=str(raw.get("orderId", "")),
        client_order_id=raw.get("clientOrderId"),
        symbol=str(raw.get("symbol", "")),
        side=Side(str(raw.get("side", "BUY"))),
        order_type=type_map.get(str(raw.get("type", "LIMIT")), OrderType.LIMIT),
        quantity=Decimal(str(raw.get("origQty", "0"))),
        executed_quantity=Decimal(str(raw.get("executedQty", "0"))),
        price=Decimal(str(raw["price"])) if raw.get("price") else None,
        status=status_map.get(str(raw.get("status", "NEW")), OrderStatus.NEW),
        created_at=datetime.now(UTC),
    )
