"""Run owner-authorized beta collectors with a personal API token."""

from __future__ import annotations

import argparse
import os

from .api import V1Client
from . import market, tracker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("u21", "market"))
    args = parser.parse_args()
    if os.environ.get("BB_V1_EXCEPTION_APPROVED") != "true":
        raise SystemExit("The written collection/publication exception must be verified before beta collectors run.")
    token = os.environ.get("BB_V1_PERSONAL_TOKEN", "")
    if not token:
        raise SystemExit("BB_V1_PERSONAL_TOKEN is required as an environment secret.")
    client = V1Client(token)
    if args.mode == "u21":
        print(f"Wrote {tracker.collect(client)}")
    else:
        changed, archive = market.collect(client)
        print(f"Market {'updated' if changed else 'not yet due'}; {len(archive.get('players', {}))} archived players.")


if __name__ == "__main__":
    main()
