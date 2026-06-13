"""Smoke test for the IBKR paper-trading connection.

Connects to TWS/IB Gateway, prints the account summary, and disconnects.
It places NO orders.

Run from the repository root with TWS or IB Gateway open and the API enabled:

    python scripts/test_connection.py
"""

import logging
import sys
from pathlib import Path

# Allow running this file directly from the repo root: make the project root
# importable so ``config`` and ``execution`` resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from execution.broker import IBBroker  # noqa: E402


def configure_logging() -> None:
    """Readable, timestamped logs; quiet ib_async's chatty internal logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("ib_async").setLevel(logging.WARNING)


def print_account_summary(summary: dict[str, float]) -> None:
    """Print the account summary in a readable, aligned format."""
    labels = {
        "net_liquidation": "Net liquidation",
        "available_funds": "Available funds",
        "buying_power": "Buying power",
    }
    print("\n=== IBKR paper account summary ===")
    for key, label in labels.items():
        value = summary.get(key)
        if value is None:
            print(f"  {label:<16}: (not reported)")
        else:
            print(f"  {label:<16}: ${value:,.2f}")
    print("==================================\n")


def main() -> int:
    """Connect, print the account summary, disconnect, and exit. No orders."""
    configure_logging()
    log = logging.getLogger("test_connection")

    log.info("Target: %s:%s (client id %s)", config.IB_HOST, config.IB_PORT, config.IB_CLIENT_ID)
    broker = IBBroker()

    try:
        broker.connect()
        summary = broker.get_account_summary()
        print_account_summary(summary)
    except Exception as error:  # noqa: BLE001 - report any failure clearly
        log.error("Connection test failed: %s", error)
        return 1
    finally:
        broker.disconnect()

    log.info("Connection test complete. No orders were placed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
