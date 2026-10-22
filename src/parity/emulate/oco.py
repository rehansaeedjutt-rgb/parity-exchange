"""OCO emulation for exchanges that lack native support.

How emulation works:
  1. Submit a limit order (the take-profit leg).
  2. Submit a stop-limit order (the stop-loss leg).
  3. Store the pair in memory with a generated list_id.
  4. On each `reconcile()` call, check both orders. If one has FILLED,
     cancel the sibling. If both are CANCELED/EXPIRED, drop the group.

What this does NOT do:
  - Run a background watcher. The caller drives reconcile(). A production
    system would loop reconcile() on a timer or use WebSocket fill events.
  - Survive a process restart. The groups map is in-memory. A real
    emulator would persist to the store (same JSON or Postgres pattern
    as streamvault).
  - Handle partial fills. If the limit leg partially fills and then the
    stop leg triggers, the position is inconsistent. This is why some
    exchanges refuse to support OCO: it is hard to do correctly across
    restarts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog

from parity.exchanges.base import ExchangeAdapter
from parity.schemas import (
    OCOOrder,
    OCORequest,
    Order,
    OrderRequest,
    OrderStatus,
    OrderType,
    TimeInForce,
)

logger = structlog.get_logger(__name__)


@dataclass
class _OCOGroup:
    """One emulated OCO. Holds both orders and their current state."""

    list_id: str
    limit_order: Order
    stop_order: Order
    request: OCORequest
    notes: list[str] = field(default_factory=list)


class OCOEmulator:
    """Emulates OCO on exchanges without native support."""

    def __init__(self, adapter: ExchangeAdapter) -> None:
        self._adapter = adapter
        self._groups: dict[str, _OCOGroup] = {}

    async def place(self, req: OCORequest) -> OCOOrder:
        """Submit both legs and remember the group."""
        # Leg 1: limit take-profit.
        limit_req = OrderRequest(
            symbol=req.symbol,
            side=req.side,
            order_type=OrderType.LIMIT,
            quantity=req.quantity,
            price=req.price,
            time_in_force=TimeInForce.GTC,
            client_order_id=f"oco-{uuid.uuid4().hex[:8]}-limit",
        )
        limit_order = await self._adapter.place_order(limit_req)

        # Leg 2: stop-limit stop-loss. Same side, opposite of the take-profit.
        # If the take-profit is a SELL (closing a long), the stop is also a
        # SELL at a lower price. If the take-profit is a BUY (closing a short),
        # the stop is also a BUY at a higher price.
        stop_req = OrderRequest(
            symbol=req.symbol,
            side=req.side,
            order_type=OrderType.STOP_LOSS_LIMIT,
            quantity=req.quantity,
            price=req.stop_limit_price,
            time_in_force=TimeInForce.GTC,
            client_order_id=f"oco-{uuid.uuid4().hex[:8]}-stop",
        )
        stop_order = await self._adapter.place_order(stop_req)

        list_id = f"oco-{uuid.uuid4().hex[:12]}"
        self._groups[list_id] = _OCOGroup(
            list_id=list_id,
            limit_order=limit_order,
            stop_order=stop_order,
            request=req,
        )
        logger.info(
            "oco.placed",
            exchange=self._adapter.name,
            list_id=list_id,
            limit_order_id=limit_order.order_id,
            stop_order_id=stop_order.order_id,
            emulated=True,
        )

        return OCOOrder(
            exchange=self._adapter.name,
            list_id=list_id,
            limit_order=limit_order,
            stop_order=stop_order,
            emulated=True,
        )

    async def reconcile(self, list_id: str) -> _OCOGroup | None:
        """Check an OCO group and cancel the sibling leg if one filled.

        Returns the updated group, or None if it is fully closed.
        Caller drives this on a timer.
        """
        group = self._groups.get(list_id)
        if group is None:
            return None

        limit_now = await self._adapter.get_order(group.request.symbol, group.limit_order.order_id)
        stop_now = await self._adapter.get_order(group.request.symbol, group.stop_order.order_id)

        group.limit_order = limit_now
        group.stop_order = stop_now

        # If one leg filled, cancel the other.
        if limit_now.status is OrderStatus.FILLED and stop_now.status in (
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED,
        ):
            try:
                canceled = await self._adapter.cancel_order(group.request.symbol, stop_now.order_id)
                group.stop_order = canceled
                group.notes.append("stop leg cancelled after limit fill")
            except Exception as exc:
                group.notes.append(f"failed to cancel stop leg: {exc}")
        elif stop_now.status is OrderStatus.FILLED and limit_now.status in (
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED,
        ):
            try:
                canceled = await self._adapter.cancel_order(
                    group.request.symbol, limit_now.order_id
                )
                group.limit_order = canceled
                group.notes.append("limit leg cancelled after stop fill")
            except Exception as exc:
                group.notes.append(f"failed to cancel limit leg: {exc}")

        # If both legs are closed (filled or canceled), drop the group.
        closed_states = {
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }
        if group.limit_order.status in closed_states and group.stop_order.status in closed_states:
            del self._groups[list_id]
            logger.info("oco.closed", exchange=self._adapter.name, list_id=list_id)
            # Both legs resolved — the group is done. Return None per the
            # docstring contract so callers can drop their reference.
            return None

        return group

    async def cancel(self, list_id: str) -> None:
        """Cancel both legs of an OCO group."""
        group = self._groups.get(list_id)
        if group is None:
            msg = f"OCO {list_id} not found"
            raise KeyError(msg)

        for leg in (group.limit_order, group.stop_order):
            if leg.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED):
                try:
                    await self._adapter.cancel_order(group.request.symbol, leg.order_id)
                except Exception as exc:
                    logger.warning(
                        "oco.cancel_failed",
                        list_id=list_id,
                        order_id=leg.order_id,
                        error=str(exc),
                    )

        del self._groups[list_id]
        logger.info("oco.cancelled", exchange=self._adapter.name, list_id=list_id)

    def open_groups(self) -> list[str]:
        """List IDs of currently-open OCO groups."""
        return list(self._groups.keys())
