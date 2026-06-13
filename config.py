"""Central configuration for the swing trading agent.

Loads environment variables from a local .env file and exposes them as simple
module-level constants. Secrets live in .env (git-ignored) and are never
hardcoded here.
"""

import os

from dotenv import load_dotenv

# Read key=value pairs from .env into the process environment.
load_dotenv()

# --- Data and news APIs ---
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

# --- Interactive Brokers (paper) ---
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "7497"))
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "1"))

# --- Agent behavior ---
# Autonomy gate mode: signal_only | approve | semi_auto | full_auto. Start safe.
AUTONOMY_MODE = os.getenv("AUTONOMY_MODE", "approve")

# Fraction of account equity risked per trade (1% default).
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))
