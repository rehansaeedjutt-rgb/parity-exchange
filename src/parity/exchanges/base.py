"""Abstract exchange adapter.

Every concrete adapter implements this interface. The point of the
interface is not to be small — it is to be the *same* for every exchange,
so that a caller writing generic trading logic does not have to branch
on `if exchange == "binance"`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from parity.schemas import OCOOrder, OCORequest, Order, OrderRequest


class ExchangeError(RuntimeError):
    """Raised when an exchange rejects a request or fails to respond."""


class ExchangeAdapter(ABC):
    """Base class for all exchange adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Canonical lowercase name, e.g. 'binance', 'mexc', 'bitget'."""
        raise NotImplementedError

    @property
    @abstractmethod
    def supports_native_oco(self) -> bool:
        """Whether the exchange has native OCO (Binance does, others do not)."""
        raise NotImplementedError

    @abstractmethod
    async def place_order(self, req: OrderRequest) -> Order:
        """Submit a plain order."""
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> Order:
        """Cancel an order and return its final state."""
        raise NotImplementedError

    @abstractmethod
    async def get_order(self, symbol: str, order_id: str) -> Order:
        """Fetch current state of an order."""
        raise NotImplementedError

    @abstractmethod
    async def place_oco(self, req: OCORequest) -> OCOOrder:
        """Submit an OCO.

        If the exchange does not have native OCO, the adapter's
        implementation is responsible for invoking the emulation layer.
        """
        raise NotImplementedError

    @abstractmethod
    async def cancel_oco(self, symbol: str, list_id: str) -> None:
        """Cancel an OCO by its list id."""
        raise NotImplementedError
