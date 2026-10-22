"""Binance adapter. Native OCO, native trailing stops, full testnet."""

from __future__ import annotations

from typing import Any

from parity.capabilities import Feature, has_native
from parity.exchanges.base import ExchangeAdapter, ExchangeError
from parity.exchanges.credentials import Credentials
from parity.exchanges.transport import HttpTransport
from parity.schemas import OCOOrder, OCORequest, Order, OrderRequest, OrderStatus, OrderType, Side

_BASE = "https://api.binance.com"


class BinanceAdapter(ExchangeAdapter):
    """Binance spot adapter. OCO uses the exchange's native endpoint."""

    def __init__(self, creds: Credentials | None, transport: HttpTransport) -> None:
        if creds is not None and not creds.api_key:
            msg = "Binance requires api_key"
            raise ExchangeError(msg)
        self._creds = creds
        self._transport = transport

    @property
    def name(self) -> str:
        return "binance"

    @property
    def supports_native_oco(self) -> bool:
        return has_native("binance", Feature.OCO)

    async def place_order(self, req: OrderRequest) -> Order:
        params = {
            "symbol": req.symbol.upper(),
            "side": req.side.value,
            "type": req.order_type.value,
            "quantity": str(req.quantity),
            "timeInForce": req.time_in_force.value,
        }
        if req.price is not None:
            params["price"] = str(req.price)
        if req.client_order_id:
            params["newClientOrderId"] = req.client_order_id
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
            "GET",
            f"{_BASE}/api/v3/order",
            params={"symbol": symbol.upper(), "orderId": order_id},
        )
        return _parse_order(self.name, resp)

    async def place_oco(self, req: OCORequest) -> OCOOrder:
        params = {
            "symbol": req.symbol.upper(),
            "side": req.side.value,
            "quantity": str(req.quantity),
            "price": str(req.price),
            "stopPrice": str(req.stop_price),
            "stopLimitPrice": str(req.stop_limit_price),
            "stopLimitTimeInForce": "GTC",
        }
        resp = await self._transport.request("POST", f"{_BASE}/api/v3/order/oco", params=params)
        # Binance OCO response shape:
        #   {"orderListId": N, "orders": [{...}, {...}], "listOrderStatus": "..."}
        orders = resp.get("orders") or []
        if len(orders) < 2:
            msg = f"unexpected OCO response: {resp}"
            raise ExchangeError(msg)

        limit_order = _parse_order(self.name, orders[0])
        stop_order = _parse_order(self.name, orders[1])

        return OCOOrder(
            exchange=self.name,
            list_id=str(resp.get("orderListId", "")),
            limit_order=limit_order,
            stop_order=stop_order,
            emulated=False,
        )

    async def cancel_oco(self, symbol: str, list_id: str) -> None:
        await self._transport.request(
            "DELETE",
            f"{_BASE}/api/v3/orderList",
            params={"symbol": symbol.upper(), "orderListId": list_id},
        )


def _parse_order(exchange: str, raw: dict[str, Any]) -> Order:
    """Translate Binance's order JSON into our unified Order."""
    from datetime import UTC, datetime
    from decimal import Decimal

    status_map = {
        "NEW": OrderStatus.NEW,
        "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
        "FILLED": OrderStatus.FILLED,
        "CANCELED": OrderStatus.CANCELED,
        "REJECTED": OrderStatus.REJECTED,
        "EXPIRED": OrderStatus.EXPIRED,
    }
    order_type_map = {
        "MARKET": OrderType.MARKET,
        "LIMIT": OrderType.LIMIT,
        "LIMIT_MAKER": OrderType.LIMIT_MAKER,
        "STOP_LOSS": OrderType.STOP_LOSS,
        "STOP_LOSS_LIMIT": OrderType.STOP_LOSS_LIMIT,
        "TAKE_PROFIT": OrderType.TAKE_PROFIT,
        "TAKE_PROFIT_LIMIT": OrderType.TAKE_PROFIT_LIMIT,
    }

    return Order(
        exchange=exchange,
        order_id=str(raw.get("orderId", "")),
        client_order_id=raw.get("clientOrderId"),
        symbol=str(raw.get("symbol", "")),
        side=Side(str(raw.get("side", "BUY"))),
        order_type=order_type_map.get(str(raw.get("type", "LIMIT")), OrderType.LIMIT),
        quantity=Decimal(str(raw.get("origQty", "0"))),
        executed_quantity=Decimal(str(raw.get("executedQty", "0"))),
        price=Decimal(str(raw["price"])) if raw.get("price") else None,
        status=status_map.get(str(raw.get("status", "NEW")), OrderStatus.NEW),
        created_at=datetime.fromtimestamp(int(raw.get("transactTime", 0)) / 1000, tz=UTC)
        if raw.get("transactTime")
        else datetime.now(UTC),
    )
