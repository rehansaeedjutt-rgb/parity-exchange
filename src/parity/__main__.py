"""CLI entry point. Prints the capability matrix and the emulation plan."""

from __future__ import annotations

import argparse
import sys

from parity import __version__
from parity.capabilities import CAPABILITIES, CREDENTIALS, Feature, Support, gaps


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parity",
        description="Cross-exchange capability matrix with emulation for missing features.",
    )
    parser.add_argument("--version", action="version", version=f"parity {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    matrix = sub.add_parser("matrix", help="Print the full capability matrix.")
    matrix.add_argument(
        "--feature",
        type=str,
        default=None,
        help="Only show one feature (oco, trailing_stop, stp, testnet, ...)",
    )

    gaps_cmd = sub.add_parser("gaps", help="Print which features each exchange is missing.")
    gaps_cmd.add_argument("exchange", type=str, choices=["binance", "mexc", "bitget"])

    return parser


def _run_matrix(feature: str | None) -> int:
    exchanges = list(CAPABILITIES.keys())
    all_features = list(Feature)

    if feature:
        try:
            all_features = [Feature(feature)]
        except ValueError:
            print(f"Unknown feature: {feature}", file=sys.stderr)
            print(f"Valid features: {', '.join(f.value for f in Feature)}", file=sys.stderr)
            return 2

    # Header
    header = f"{'feature':<26}" + "".join(f"{ex:<12}" for ex in exchanges)
    print(header)
    print("-" * len(header))

    for f in all_features:
        row = f"{f.value:<26}"
        for ex in exchanges:
            support = CAPABILITIES[ex].get(f, Support.MISSING)
            marker = {
                Support.NATIVE: "native",
                Support.PARTIAL: "partial",
                Support.MISSING: "MISSING",
            }[support]
            row += f"{marker:<12}"
        print(row)

    print()
    print("Credentials required per exchange:")
    for ex, cred in CREDENTIALS.items():
        print(f"  {ex:<10} {cred.value} field(s)")

    print()
    print("Legend:")
    print("  native   — supported by the exchange's own API")
    print("  partial  — supported but limited, or requires workarounds")
    print("  MISSING  — not in the exchange API; provided by parity-exchange emulation")
    return 0


def _run_gaps(exchange: str) -> int:
    print(f"Gaps for {exchange}:")
    print()
    missing = gaps(exchange)
    if not missing:
        print(f"  {exchange} has every feature in the matrix.")
        return 0
    for f in missing:
        support = CAPABILITIES[exchange].get(f, Support.MISSING)
        tag = "MISSING" if support is Support.MISSING else "partial"
        print(f"  [{tag}] {f.value}")
    print()
    if exchange in ("mexc", "bitget"):
        print("OCO is emulated by OCOEmulator (src/parity/emulate/oco.py).")
        print("Callers using the unified ExchangeAdapter interface get OCO")
        print("transparently — they do not need to know which exchange they are on.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "matrix":
        return _run_matrix(args.feature)
    if args.command == "gaps":
        return _run_gaps(args.exchange)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
