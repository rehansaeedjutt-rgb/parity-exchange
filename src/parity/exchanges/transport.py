"""HTTP transport abstraction.

Adapters do not talk to aiohttp directly. They call `HttpTransport.request`,
which returns a decoded JSON dict. Tests provide a mock transport that
returns canned responses without touching the network.
"""

from __future__ import annotations

from typing import Any, Protocol

import aiohttp


class TransportError(RuntimeError):
    """Raised when the transport layer fails (network, timeout, bad JSON)."""


class HttpTransport(Protocol):
    """Interface every transport must implement."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        body: str | None = None,
    ) -> dict[str, Any]: ...

    async def close(self) -> None: ...


class AiohttpTransport:
    """Real HTTP transport using aiohttp. Used in production paths."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        body: str | None = None,
    ) -> dict[str, Any]:
        session = await self._ensure_session()
        try:
            async with session.request(
                method, url, params=params, headers=headers, data=body
            ) as resp:
                if resp.status >= 500:
                    msg = f"HTTP {resp.status} from {url}"
                    raise TransportError(msg)
                data = await resp.json()
                if not isinstance(data, dict):
                    msg = f"non-dict response from {url}"
                    raise TransportError(msg)
                return data
        except aiohttp.ClientError as exc:
            msg = f"transport error on {url}: {exc}"
            raise TransportError(msg) from exc

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
