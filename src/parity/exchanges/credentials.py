"""Exchange credentials. Each exchange requires a different field set."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Credentials(BaseModel):
    """API credentials. `passphrase` is required for Bitget only."""

    model_config = ConfigDict(frozen=True)

    api_key: str
    api_secret: str
    passphrase: str | None = None
