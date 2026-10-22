"""Bitget adapter. Three-field authentication. No native OCO. No WS order entry."""

from __future__ import annotations

from typing import Any

from parity.capabilities import Feature, has_native
from parity.emulate.oco import OCOEmulator
from parity.exchanges.base import ExchangeAdapter, ExchangeError
from parity.exchanges.credentials import Credentials
from parity.exchanges.transport import HttpTransport
from parity.schemas import OCOOrder, OCORequest, Order, OrderRequest, OrderStatus, OrderType, Side

_BASE = "https://api.bitget.com"


class BitgetAdapter(ExchangeAdapter):
    """Bitget v2 adapter. OCO is emulated; WS order entry is not available."""

    def __init__(self, creds: Credentials | None, transport: HttpTransport) -> None:
        if creds is not None:
            if not creds.api_key:
                msg = "Bitget requires api_key"
                raise ExchangeError(msg)
            if not creds.passphrase:
                msg = "Bitget requires passphrase (third credential field)"
                raise ExchangeError(msg)
        self._creds = creds
        self._transport = transport
        self._oco = OCOEmulator(self) if not has_native("bitget", Feature.OCO) else None

    @property
    def name(self) -> str:
        return "bitget"

    @property
    def supports_native_oco(self) -> bool:
        return has_native("bitget", Feature.OCO)

    def _auth_headers(self) -> dict[str, str]:
        if self._creds is None:
            return {}
        return {
            "ACCESS-KEY": self._creds.api_key,
            "ACCESS-PASSPHRASE": self._creds.passphrase or "",
        }

    async def place_order(self, req: OrderRequest) -> Order:
        body = {
            "symbol": req.symbol.upper(),
            "side": req.side.value.lower(),
            "orderType": "limit" if req.order_type is OrderType.LIMIT else "market",
            "size": str(req.quantity),
            "force": req.time_in_force.value.lower(),
        }
        if req.price is not None:
            body["price"] = str(req.price)
        import json as _json

        resp = await self._transport.request(
            "POST",
            f"{_BASE}/api/v2/spot/trade/place-order",
            headers=self._auth_headers(),
            body=_json.dumps(body),
        )
        return _parse_order(self.name, resp)

    async def cancel_order(self, symbol: str, order_id: str) -> Order:
        import json as _json

        resp = await self._transport.request(
            "POST",
            f"{_BASE}/api/v2/spot/trade/cancel-order",
            headers=self._auth_headers(),
            body=_json.dumps({"symbol": symbol.upper(), "orderId": order_id}),
        )
        return _parse_order(self.name, resp)

    async def get_order(self, symbol: str, order_id: str) -> Order:
        resp = await self._transport.request(
            "GET",
            f"{_BASE}/api/v2/spot/trade/orderInfo",
            params={"symbol": symbol.upper(), "orderId": order_id},
            headers=self._auth_headers(),
        )
        return _parse_order(self.name, resp)

    async def place_oco(self, req: OCORequest) -> OCOOrder:
        if self._oco is None:
            msg = "Bitget native OCO not implemented"
            raise ExchangeError(msg)
        return await self._oco.place(req)

    async def cancel_oco(self, symbol: str, list_id: str) -> None:
        if self._oco is None:
            msg = "Bitget native OCO not implemented"
            raise ExchangeError(msg)
        await self._oco.cancel(list_id)

    def _emulator(self) -> OCOEmulator | None:
        return self._oco


def _parse_order(exchange: str, raw: dict[str, Any]) -> Order:
    """Translate Bitget's v2 response into our unified Order."""
    from datetime import UTC, datetime
    from decimal import Decimal

    if raw.get("code") not in (None, "00000", 0):
        msg = f"Bitget error {raw.get('code')}: {raw.get('msg')}"
        raise ExchangeError(msg)

    data_raw = raw.get("data")
    data: dict[str, Any] = data_raw if isinstance(data_raw, dict) else raw

    status_map = {
        "new": OrderStatus.NEW,
        "partial_fill": OrderStatus.PARTIALLY_FILLED,
        "full_fill": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELED,
        "live": OrderStatus.NEW,
        "filled": OrderStatus.FILLED,
    }
    type_map = {
        "market": OrderType.MARKET,
        "limit": OrderType.LIMIT,
    }

    return Order(
        exchange=exchange,
        order_id=str(data.get("orderId", "")),
        client_order_id=data.get("clientOid"),
        symbol=str(data.get("symbol", "")),
        side=Side(str(data.get("side", "buy")).upper()),
        order_type=type_map.get(str(data.get("orderType", "limit")), OrderType.LIMIT),
        quantity=Decimal(str(data.get("size", "0"))),
        executed_quantity=Decimal(str(data.get("baseVolume", "0"))),
        price=Decimal(str(data["price"])) if data.get("price") else None,
        status=status_map.get(str(data.get("status", "new")), OrderStatus.NEW),
        created_at=datetime.now(UTC),
    )
