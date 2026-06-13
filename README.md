# Swing Trading Agent

A personal swing trading agent that screens the market top-down (sectors first, then names), generates signals, gates every trade through an adjustable autonomy control, and executes on Interactive Brokers. Built paper-first.

See `PROJECT_PLAN.md` for the full stack, roadmap, and design decisions.

## Prerequisites

- Python 3.11 or higher
- An Interactive Brokers paper trading account
- TWS or IB Gateway installed and running locally, with the API enabled (Global Configuration > API > Settings)
- A free Finnhub API key from https://finnhub.io

## Setup

1. Clone the repo and move into it:
   ```
   git clone <your-repo-url>
   cd trading-agent
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate      # Mac/Linux
   venv\Scripts\activate         # Windows
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up your environment variables:
   ```
   cp .env.example .env
   ```
   Then open `.env` and fill in your real keys. Never commit `.env`.

## Running

Make sure TWS or IB Gateway is running and connected to your paper account before running anything that touches the broker.

```
python main.py
```

## Project structure

```
trading-agent/
  config.py          # settings: autonomy_mode, risk_per_trade, ports, keys from env
  data/              # data fetching (yfinance, finnhub)
  screener/          # sector ranking + stock selection
  signals/           # entry rules + signal generation
  risk/              # position sizing + stop logic
  decision/          # compute_decision + autonomy gate
  execution/         # ib_async wrapper
  backtest/          # backtesting harness
  storage/           # sqlite layer
  logs/
  main.py
```

## Safety

- This runs against an IBKR paper account. Port 7497 is paper, 7496 is live. Stay on paper until a strategy has a real out-of-sample track record.
- Never commit API keys or your `.env` file.

## Status

In development. See the roadmap in `PROJECT_PLAN.md` for current phase.
