"""Entry point for the swing trading agent.

Phase 0 skeleton: load configuration and print a couple of values to confirm
the .env wiring works. No trading, data, or broker logic yet.
"""

import config


def main() -> None:
    """Print loaded config so we can confirm settings load correctly."""
    print(f"Autonomy mode: {config.AUTONOMY_MODE}")
    print(f"IB port: {config.IB_PORT}")


if __name__ == "__main__":
    main()
