# Options Chain Data — Polygon / Massive API

## Quick Start

The script `databento/scripts/fetch_options_chain.py` downloads full options chain data for any ticker.

**Two modes:**
| Mode | Flag | What you get | When to use |
|------|------|-------------|-------------|
| **Snapshot** | *(default)* | Greeks, IV, open interest, bid/ask, break-even, last trade | Options that are **currently active** (not yet expired) |
| **Expired** | `--expired` | Daily OHLCV bars (open, high, low, close, volume, vwap, # trades) | Options that have **already expired** |

> **Why two modes?** The Polygon API only returns greeks/IV/bid-ask for *live* options via the snapshot endpoint. For expired options, we pull the contract list + historical daily bars instead.

---

## GitBash / Terminal Commands

### 1. Set your API key (one time)

```bash
export MASSIVE_API_KEY="lb61CFk2g4pp9NsKXyEkF4s9fv8OrKIA"
```

Or put it in the `.env` file at the repo root:
```
MASSIVE_API_KEY=lb61CFk2g4pp9NsKXyEkF4s9fv8OrKIA
```

### 2. Download expired options (historical daily bars)

```bash
# SPY — all February 2026 expirations, with daily bars from Jan 15 to Feb 28
python3 databento/scripts/fetch_options_chain.py SPY \
  --exp-from 2026-02-01 --exp-to 2026-02-28 \
  --expired \
  --bars-from 2026-01-15 --bars-to 2026-02-28

# AAPL — January 2026
python3 databento/scripts/fetch_options_chain.py AAPL \
  --exp-from 2026-01-01 --exp-to 2026-01-31 \
  --expired \
  --bars-from 2025-12-15 --bars-to 2026-01-31

# TSLA — only puts, strikes between 200 and 300
python3 databento/scripts/fetch_options_chain.py TSLA \
  --exp-from 2026-02-01 --exp-to 2026-02-28 \
  --expired \
  --type put \
  --strike-min 200 --strike-max 300

# QQQ — single expiration date
python3 databento/scripts/fetch_options_chain.py QQQ \
  --exp-from 2026-02-20 --exp-to 2026-02-20 \
  --expired
```

### 3. Download active options (live snapshot with greeks)

```bash
# SPY — this week's expiration (current greeks, IV, bid/ask)
python3 databento/scripts/fetch_options_chain.py SPY \
  --exp-from 2026-03-20 --exp-to 2026-03-21

# AMZN — next month, calls only
python3 databento/scripts/fetch_options_chain.py AMZN \
  --exp-from 2026-04-01 --exp-to 2026-04-30 \
  --type call

# SPY — all active expirations, narrow strike range
python3 databento/scripts/fetch_options_chain.py SPY \
  --exp-from 2026-03-19 --exp-to 2026-12-31 \
  --strike-min 640 --strike-max 680
```

### 4. Output options

```bash
# Custom output path
python3 databento/scripts/fetch_options_chain.py SPY \
  --exp-from 2026-02-01 --exp-to 2026-02-28 \
  --expired \
  -o /path/to/my_file.csv

# JSON format
python3 databento/scripts/fetch_options_chain.py SPY \
  --exp-from 2026-02-01 --exp-to 2026-02-28 \
  --expired \
  --format json
```

Default output path: `data/options/{TICKER}_options_{mode}_{dates}_{timestamp}.csv`

---

## All Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `TICKER` | yes | First argument. Underlying ticker: SPY, AAPL, QQQ, TSLA, AMZN, etc. |
| `--exp-from` | yes | Start of expiration date range (YYYY-MM-DD) |
| `--exp-to` | yes | End of expiration date range (YYYY-MM-DD) |
| `--expired` | no | Use this for options that have already expired |
| `--type` | no | `call` or `put` — omit for both |
| `--strike-min` | no | Minimum strike price |
| `--strike-max` | no | Maximum strike price |
| `--bars-from` | no | Start date for daily bars (only with `--expired`, default = exp-from) |
| `--bars-to` | no | End date for daily bars (only with `--expired`, default = exp-to) |
| `--api-key` | no | API key (default: reads `MASSIVE_API_KEY` from env or `.env` file) |
| `-o` / `--output` | no | Output file path |
| `--format` | no | `csv` (default) or `json` |

---

## Output Columns

### Snapshot mode (active options)

| Column | Description |
|--------|-------------|
| ticker | Options contract ticker (e.g. `O:SPY260320C00655000`) |
| contract_type | `call` or `put` |
| expiration_date | YYYY-MM-DD |
| strike_price | Strike price |
| exercise_style | `american` or `european` |
| break_even_price | Break-even price of the option |
| implied_volatility | IV |
| open_interest | Current open interest |
| fair_market_value | Fair market value |
| delta, gamma, theta, vega | The Greeks |
| day_open/high/low/close | Today's OHLC |
| day_volume, day_vwap | Today's volume and VWAP |
| bid, bid_size, ask, ask_size, midpoint | Current quote |
| last_trade_price, last_trade_size | Last trade |
| underlying_price | Current price of the underlying |
| change_to_break_even | Distance from underlying to break-even |

### Expired mode (daily bars)

| Column | Description |
|--------|-------------|
| ticker | Options contract ticker |
| contract_type | `call` or `put` |
| expiration_date | Contract expiration date |
| strike_price | Strike price |
| primary_exchange | Primary exchange |
| bar_date | Date of the daily bar |
| open, high, low, close | OHLC for that day |
| volume | Daily volume |
| vwap | Volume-weighted average price |
| num_trades | Number of trades |

---

## Reading the Options Ticker Format

Polygon options tickers follow the OCC format:

```
O:SPY260220C00580000
│ │   │    │ │
│ │   │    │ └─ strike price × 1000 (580.000 = $580)
│ │   │    └─── C = call, P = put
│ │   └──────── expiration: 260220 = 2026-02-20
│ └──────────── underlying ticker
└────────────── "O:" prefix for options
```

---

## Finding Available Tickers

Any US equity or ETF that has listed options will work:

**Popular ETFs:** SPY, QQQ, IWM, DIA, XLF, XLE, GLD, SLV, TLT, HYG, EEM

**Popular stocks:** AAPL, MSFT, AMZN, GOOGL, META, TSLA, NVDA, AMD, NFLX, JPM, BAC

**Index options:** Use the index symbol directly — SPX, NDX, RUT, VIX

To check if a ticker has options data, just run the script with a narrow date range:
```bash
python3 databento/scripts/fetch_options_chain.py NVDA \
  --exp-from 2026-03-20 --exp-to 2026-03-21 \
  --type call --strike-min 100 --strike-max 110
```

---

## Rate Limits

The free Polygon plan allows 5 requests/minute. The script handles this automatically with built-in delays:
- **Contract listing pages:** ~13s between pages
- **Daily bar fetches:** ~0.22s between requests

For a full month of SPY options (~6000+ contracts), expect **~25-30 minutes** total download time.

## Troubleshooting

| Error | Fix |
|-------|-----|
| `no API key` | Set `MASSIVE_API_KEY` env variable or pass `--api-key` |
| `no data returned` | Check date range — snapshot only works for active options, use `--expired` for past dates |
| `HTTP 429` (rate limit) | Wait a minute and retry — the script auto-throttles but the free plan is strict |
| `NOT_AUTHORIZED` | Some endpoints require a paid plan (quotes, trades) — daily bars work on free plan |
