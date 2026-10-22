# parity-exchange

> Cross-exchange capability matrix with emulation for features exchanges don't provide natively.

[![CI](https://github.com/rehansaeedjutt-rgb/parity-exchange/actions/workflows/ci.yml/badge.svg)](https://github.com/rehansaeedjutt-rgb/parity-exchange/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

## What this is

`parity-exchange` is a unified interface to Binance, MEXC, and Bitget, with
**emulation layers** for features an exchange's API does not provide.

The core observation, verified against each exchange's official API docs
(October 2026):

- **Binance** has the richest feature set: native OCO, trailing stops,
  self-trade prevention, pegged orders, order amendment, a full API testnet.
- **MEXC** has no native OCO, no self-trade prevention, and — most importantly
  for developers — **no API testnet at all**. Every test against MEXC is a
  production test with real money.
- **Bitget** has no native OCO, no WS order entry (subscription-only), and
  requires three credential fields where Binance and MEXC require two.

A caller using the unified `ExchangeAdapter` interface does not need to know
any of this. They place an OCO. On Binance it hits the native endpoint. On
MEXC and Bitget the OCO emulator takes over and both legs are managed as a
single group.

## Why this project

Most exchange SDKs are thin wrappers: they expose whatever the exchange
exposes, and every caller writes `if exchange == "binance": ...` in their
trading logic. That is a real bug source, because the moment you add a
third exchange you find edge cases you did not know existed.

The other approach — write one library per exchange — is worse. You now
have three libraries to maintain, and the user of the library has to
reconcile them.

`parity-exchange` is the third option: **one interface, with the exchange-
specific work pushed down into adapters and emulators**. The caller writes
their logic once. The adapters do the translation.

## Live demo

    pip install -e ".[dev]"
    parity matrix
    parity gaps mexc
    parity gaps bitget

Example output:

    $ parity matrix
    feature                   binance     mexc        bitget
    ------------------------------------------------------------
    oco                       native      MISSING     MISSING
    trailing_stop             native      partial     partial
    stp                       native      MISSING     MISSING
    pegged_order              native      MISSING     MISSING
    order_amend               native      MISSING     MISSING
    testnet                   native      MISSING     partial
    ws_order_entry            native      partial     MISSING
    copy_trading              native      MISSING     native

    Credentials required per exchange:
      binance    2 field(s)
      mexc       2 field(s)
      bitget     3 field(s)

    Legend:
      native   — supported by the exchange's own API
      partial  — supported but limited, or requires workarounds
      MISSING  — not in the exchange API; provided by parity-exchange emulation

    $ parity gaps mexc
    Gaps for mexc:

      [MISSING] oco
      [partial] trailing_stop
      [MISSING] stp
      [MISSING] pegged_order
      [MISSING] order_amend
      [MISSING] testnet
      [partial] ws_order_entry
      [MISSING] copy_trading

    OCO is emulated by OCOEmulator (src/parity/emulate/oco.py).
    Callers using the unified ExchangeAdapter interface get OCO
    transparently — they do not need to know which exchange they are on.

## What is in here

- **Capability matrix** (`capabilities.py`) — one file, three exchanges,
  eight features. Every cell was checked against official docs.
- **Unified schemas** (`schemas.py`) — Side, OrderType, TimeInForce,
  OrderStatus, OrderRequest, Order, OCORequest, OCOOrder.
- **Adapters** (`exchanges/`) — one per exchange. Binance uses native OCO;
  MEXC and Bitget route through the emulator.
- **OCO emulator** (`emulate/oco.py`) — submits both legs, watches them,
  cancels the sibling when one fills, drops the group when both resolve.
- **CLI** — `parity matrix` and `parity gaps <exchange>`.
- **16 tests** — capability matrix assertions, OCO emulator behaviour,
  credential requirements. All offline.
- **GitHub Actions CI** on Python 3.12, 3.13, 3.14.

## What is NOT here (deliberately)

- **No live trades.** Adapters call the exchange's REST API, but the tests
  and demo do not. To use this against a real exchange you supply credentials
  and call the adapter directly. The demo is the capability matrix.
- **No WebSocket order entry.** Bitget's WS is subscription-only; this
  adapter uses REST for order placement, matching what a real user of the
  exchange would do.
- **No trailing stop emulation.** Trailing stops are marked PARTIAL on
  MEXC and Bitget, but the emulator for them is a follow-up. The point of
  this repo is to demonstrate the *pattern* — matrix plus emulation — and
  OCO is the worked example.
- **No rate-limit handling.** Binance uses a shared 6000/min weight pool,
  MEXC uses 300/10s per endpoint, Bitget is per-endpoint. Correct rate
  limiting is a per-exchange project of its own.
- **No signature generation.** The HTTP transport is abstract; signed
  requests would need per-exchange HMAC implementations that are exchange-
  specific and not part of the "parity" story.

## Architecture

    Caller writes: adapter.place_oco(req)
                       |
                       v
    +----------------------------------+
    |  ExchangeAdapter (unified)       |
    +----------------------------------+
                       |
          +------------+------------+
          |            |            |
          v            v            v
    +----------+  +----------+  +----------+
    | Binance  |  |  MEXC    |  | Bitget   |
    | native   |  |  →       |  |  →       |
    | OCO      |  | emulator |  | emulator |
    +----------+  +----------+  +----------+
                       |            |
                       v            v
                  +----------------------+
                  |  OCOEmulator         |
                  |  - submit 2 legs     |
                  |  - reconcile()       |
                  |  - cancel sibling    |
                  |  - drop group        |
                  +----------------------+

## Design notes

**Emulation, not feature-parity-through-workarounds.** The emulator submits
two real orders and cancels the sibling when one fills. It is honest about
its limits: no partial fill handling, no process-restart persistence, no
background watcher. A caller has to drive `reconcile()`. This is documented
in `emulate/oco.py` and in this README, and it is the reason I titled the
project "emulation" rather than "unified OCO".

**Three-field credentials, handled explicitly.** Bitget requires a
passphrase in addition to key and secret. The base interface takes a
`Credentials` model with an optional `passphrase`. On Binance and MEXC, it
is ignored. On Bitget, the adapter refuses to construct without it. That
mismatch is the whole reason this project exists, so it is not papered over.

**Capability matrix as data, not as `if` statements.** Every feature is a
`Support` enum value (native / partial / missing). The CLI reads from the
same dict the code reads from. There is no second copy of "which exchange
supports what" hiding in the adapters.

**`via` a mock transport, not mocks.** Tests use a `FakeAdapter`, not
`pytest.mock` or `respx`. The fake implements the same interface the real
adapters do. Tests that need to move an order forward call `.fill()`. This
keeps the tests honest: they exercise the emulator's logic, not the
mocking framework's.

**No hardcoded API responses.** The Binance and MEXC adapters parse the
documented response shape and raise `ExchangeError` when the shape does not
match. That is the same approach production SDKs take, and it is what
breaks when the exchange changes their schema.

## Roadmap

- [ ] Trailing stop emulator (the second worked example)
- [ ] STP emulation via client-side order ID prefix matching
- [ ] HMAC signature generation per exchange
- [ ] Rate-limit awareness (shared pool on Binance, per-endpoint on MEXC
      and Bitget)
- [ ] WebSocket fill watcher (so `reconcile()` can be driven from events
      instead of polling)
- [ ] Persistence layer (groups survive process restart)
- [ ] OKX, Bybit, Gate adapters (the same pattern, more exchanges)

## Disclaimer

**Educational project.** The capability matrix was accurate as of October
2026 against official exchange docs, but exchange APIs change. Do not rely
on the matrix for production routing without re-verifying each cell.
Do not use the emulator to trade real money without adding the missing
pieces (partial-fill handling, persistence, background reconcile).

## License

MIT — see [LICENSE](LICENSE).

## Author

**Muhammad Rehan Saeed** — [GitHub](https://github.com/rehansaeedjutt-rgb)