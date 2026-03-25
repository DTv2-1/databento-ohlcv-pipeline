#!/usr/bin/env python3
"""
fetch_options_chain.py
======================
Downloads SPY (or any ticker) options chain data from the Polygon / Massive API.

For ACTIVE (non-expired) options  → uses the snapshot endpoint which includes
greeks, IV, open interest, bid/ask, break-even, last trade, etc.

For EXPIRED options → uses the contracts reference + daily OHLCV aggregates,
since the snapshot endpoint only returns data for live contracts.

Usage examples:
  # Active options expiring this week (snapshot with full greeks):
  python3 fetch_options_chain.py SPY --exp-from 2026-03-20 --exp-to 2026-03-27

  # Expired Feb 2026 full chain (daily bars):
  python3 fetch_options_chain.py SPY --exp-from 2026-02-01 --exp-to 2026-02-28 --expired

  # Only puts, strike range 550-600:
  python3 fetch_options_chain.py SPY --exp-from 2026-02-01 --exp-to 2026-02-28 --expired --type put --strike-min 550 --strike-max 600

  # Fetch daily bars for the full month of the contract life:
  python3 fetch_options_chain.py SPY --exp-from 2026-02-01 --exp-to 2026-02-28 --expired --bars-from 2026-01-01 --bars-to 2026-02-28

Environment:
  MASSIVE_API_KEY  — your Polygon / Massive API key (or pass --api-key)
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, date

# ─── config ──────────────────────────────────────────────────────────────
API_BASE = "https://api.polygon.io"
CONTRACTS_LIMIT = 1000          # max per page
SNAPSHOT_LIMIT = 250            # max per page
RATE_LIMIT_SLEEP = 13           # seconds between pages (free plan = 5 req/min)
BAR_SLEEP = 0.22                # sleep between individual bar requests


MAX_RETRIES = 5


# ─── helpers ─────────────────────────────────────────────────────────────
def api_get(url, api_key, retries=MAX_RETRIES):
    """GET request with API key + retry with exponential backoff."""
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}apiKey={api_key}"
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "OptionsChainFetcher/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            if e.code == 429:  # rate limited
                wait = min(2 ** attempt * 5, 120)
                print(f"  ⏳ rate limited, waiting {wait}s (attempt {attempt}/{retries})")
                time.sleep(wait)
                continue
            print(f"  HTTP {e.code}: {body[:200]}", file=sys.stderr)
            return None
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            wait = min(2 ** attempt * 2, 60)
            print(f"  ⚠ {type(e).__name__}: {e} — retry {attempt}/{retries} in {wait}s")
            time.sleep(wait)
    print(f"  ✗ failed after {retries} attempts", file=sys.stderr)
    return None


def paginate_all(base_url, api_key, results_key="results", sleep=RATE_LIMIT_SLEEP):
    """Fetch all pages from a paginated Polygon endpoint."""
    all_results = []
    url = base_url
    page = 0
    while url:
        page += 1
        data = api_get(url, api_key)
        if data is None:
            break
        results = data.get(results_key, [])
        all_results.extend(results)
        print(f"  page {page}: +{len(results)} rows  (total {len(all_results)})")
        url = data.get("next_url")
        if url:
            time.sleep(sleep)
    return all_results


# ─── 1) SNAPSHOT — active options ────────────────────────────────────────
SNAPSHOT_HEADERS = [
    "ticker", "contract_type", "expiration_date", "strike_price",
    "exercise_style", "shares_per_contract",
    "break_even_price", "implied_volatility", "open_interest", "fair_market_value",
    "delta", "gamma", "theta", "vega",
    "day_open", "day_high", "day_low", "day_close", "day_volume", "day_vwap",
    "day_change", "day_change_pct", "day_prev_close",
    "bid", "bid_size", "ask", "ask_size", "midpoint",
    "last_trade_price", "last_trade_size", "last_trade_timestamp",
    "underlying_ticker", "underlying_price", "change_to_break_even",
]


def flatten_snapshot(snap):
    """Flatten an OptionContractSnapshot dict into a flat row dict."""
    details = snap.get("details") or {}
    greeks = snap.get("greeks") or {}
    day = snap.get("day") or {}
    quote = snap.get("last_quote") or {}
    trade = snap.get("last_trade") or {}
    underlying = snap.get("underlying_asset") or {}

    return {
        "ticker": details.get("ticker", ""),
        "contract_type": details.get("contract_type", ""),
        "expiration_date": details.get("expiration_date", ""),
        "strike_price": details.get("strike_price", ""),
        "exercise_style": details.get("exercise_style", ""),
        "shares_per_contract": details.get("shares_per_contract", ""),
        "break_even_price": snap.get("break_even_price", ""),
        "implied_volatility": snap.get("implied_volatility", ""),
        "open_interest": snap.get("open_interest", ""),
        "fair_market_value": snap.get("fair_market_value", ""),
        "delta": greeks.get("delta", ""),
        "gamma": greeks.get("gamma", ""),
        "theta": greeks.get("theta", ""),
        "vega": greeks.get("vega", ""),
        "day_open": day.get("open", ""),
        "day_high": day.get("high", ""),
        "day_low": day.get("low", ""),
        "day_close": day.get("close", ""),
        "day_volume": day.get("volume", ""),
        "day_vwap": day.get("vwap", ""),
        "day_change": day.get("change", ""),
        "day_change_pct": day.get("change_percent", ""),
        "day_prev_close": day.get("previous_close", ""),
        "bid": quote.get("bid", ""),
        "bid_size": quote.get("bid_size", ""),
        "ask": quote.get("ask", ""),
        "ask_size": quote.get("ask_size", ""),
        "midpoint": quote.get("midpoint", ""),
        "last_trade_price": trade.get("price", ""),
        "last_trade_size": trade.get("size", ""),
        "last_trade_timestamp": trade.get("sip_timestamp", ""),
        "underlying_ticker": underlying.get("ticker", ""),
        "underlying_price": underlying.get("price", ""),
        "change_to_break_even": underlying.get("change_to_break_even", ""),
    }


def fetch_snapshot_chain(ticker, exp_from, exp_to, api_key,
                         contract_type=None, strike_min=None, strike_max=None):
    """Fetch active options chain via snapshot endpoint."""
    # Polygon snapshot uses dot-notation params: strike_price.gte, expiration_date.gte
    parts = [
        f"expiration_date.gte={exp_from}",
        f"expiration_date.lte={exp_to}",
        f"limit={SNAPSHOT_LIMIT}",
    ]
    if contract_type:
        parts.append(f"contract_type={contract_type}")
    if strike_min is not None:
        parts.append(f"strike_price.gte={strike_min}")
    if strike_max is not None:
        parts.append(f"strike_price.lte={strike_max}")

    qs = "&".join(parts)
    url = f"{API_BASE}/v3/snapshot/options/{ticker}?{qs}"

    print(f"\n[snapshot] fetching active options chain for {ticker} ...")
    raw = paginate_all(url, api_key, sleep=RATE_LIMIT_SLEEP)
    rows = [flatten_snapshot(s) for s in raw]
    print(f"[snapshot] {len(rows)} contracts fetched")
    return rows, SNAPSHOT_HEADERS


# ─── 2) EXPIRED — contracts list + daily bars ────────────────────────────
EXPIRED_HEADERS = [
    "ticker", "contract_type", "expiration_date", "strike_price",
    "exercise_style", "shares_per_contract", "primary_exchange",
    "bar_date", "open", "high", "low", "close", "volume", "vwap", "num_trades",
]


def fetch_expired_chain(ticker, exp_from, exp_to, api_key,
                        contract_type=None, strike_min=None, strike_max=None,
                        bars_from=None, bars_to=None,
                        skip=0, output_path=None):
    """
    Fetch expired options chain:
    1. list all contracts via /v3/reference/options/contracts
    2. for each contract, fetch daily OHLCV via /v2/aggs/ticker/.../range/1/day/...
    """
    # ── step 1: list all contracts ──
    params = {
        "underlying_ticker": ticker,
        "expiration_date.gte": exp_from,
        "expiration_date.lte": exp_to,
        "expired": "true",
        "limit": CONTRACTS_LIMIT,
        "sort": "ticker",
        "order": "asc",
    }
    if contract_type:
        params["contract_type"] = contract_type
    if strike_min is not None:
        params["strike_price.gte"] = strike_min
    if strike_max is not None:
        params["strike_price.lte"] = strike_max

    qs = urllib.parse.urlencode(params)
    url = f"{API_BASE}/v3/reference/options/contracts?{qs}"

    print(f"\n[expired] listing contracts for {ticker} ({exp_from} to {exp_to}) ...")
    contracts = paginate_all(url, api_key, sleep=RATE_LIMIT_SLEEP)
    print(f"[expired] {len(contracts)} contracts found")

    if not contracts:
        return [], EXPIRED_HEADERS

    # ── step 2: fetch daily bars for each contract ──
    b_from = bars_from or exp_from
    b_to = bars_to or exp_to
    all_rows = []
    total = len(contracts)

    # If an output_path is given, write incrementally (append mode)
    csv_writer = None
    csv_file = None
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        append_mode = skip > 0 and os.path.exists(output_path)
        csv_file = open(output_path, "a" if append_mode else "w", newline="")
        csv_writer = csv.DictWriter(csv_file, fieldnames=EXPIRED_HEADERS)
        if not append_mode:
            csv_writer.writeheader()

    print(f"[expired] fetching daily bars for {total} contracts ({b_from} to {b_to}) ...")
    if skip > 0:
        print(f"[expired] resuming — skipping first {skip} contracts")

    row_count = 0
    for i, contract in enumerate(contracts, 1):
        if i <= skip:
            continue

        opt_ticker = contract["ticker"]
        ctype = contract.get("contract_type", "")
        exp = contract.get("expiration_date", "")
        strike = contract.get("strike_price", "")
        exercise = contract.get("exercise_style", "")
        shares = contract.get("shares_per_contract", "")
        exchange = contract.get("primary_exchange", "")

        agg_url = (
            f"{API_BASE}/v2/aggs/ticker/{opt_ticker}/range/1/day/{b_from}/{b_to}"
            f"?adjusted=true&sort=asc&limit=50000"
        )
        data = api_get(agg_url, api_key)

        bars = (data or {}).get("results", [])
        if bars:
            for bar in bars:
                ts = bar.get("t", 0)
                bar_date = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
                row = {
                    "ticker": opt_ticker,
                    "contract_type": ctype,
                    "expiration_date": exp,
                    "strike_price": strike,
                    "exercise_style": exercise,
                    "shares_per_contract": shares,
                    "primary_exchange": exchange,
                    "bar_date": bar_date,
                    "open": bar.get("o", ""),
                    "high": bar.get("h", ""),
                    "low": bar.get("l", ""),
                    "close": bar.get("c", ""),
                    "volume": bar.get("v", ""),
                    "vwap": bar.get("vw", ""),
                    "num_trades": bar.get("n", ""),
                }
                if csv_writer:
                    csv_writer.writerow(row)
                all_rows.append(row)
                row_count += 1

        if i % 50 == 0 or i == total:
            print(f"  [{i}/{total}] {opt_ticker}  bars={len(bars)}  rows_total={row_count}")
            if csv_file:
                csv_file.flush()

        time.sleep(BAR_SLEEP)

    if csv_file:
        csv_file.close()

    print(f"[expired] {row_count} total bar rows")
    return all_rows, EXPIRED_HEADERS


# ─── write output ────────────────────────────────────────────────────────
def write_csv(rows, headers, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)
    print(f"\n✓ saved {len(rows)} rows → {path}")


def write_json(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"✓ saved {len(rows)} rows → {path}")


# ─── main ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Download options chain data from Polygon / Massive API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("ticker", help="Underlying ticker (e.g. SPY, AAPL, QQQ)")
    parser.add_argument("--exp-from", required=True, help="Expiration date range start (YYYY-MM-DD)")
    parser.add_argument("--exp-to", required=True, help="Expiration date range end (YYYY-MM-DD)")
    parser.add_argument("--expired", action="store_true",
                        help="Fetch EXPIRED options (uses contracts + daily bars instead of snapshot)")
    parser.add_argument("--type", choices=["call", "put"], default=None,
                        help="Filter by contract type")
    parser.add_argument("--strike-min", type=float, default=None, help="Min strike price")
    parser.add_argument("--strike-max", type=float, default=None, help="Max strike price")
    parser.add_argument("--bars-from", default=None,
                        help="Start date for daily bars (default = exp-from). Only for --expired.")
    parser.add_argument("--bars-to", default=None,
                        help="End date for daily bars (default = exp-to). Only for --expired.")
    parser.add_argument("--skip", type=int, default=0,
                        help="Resume: skip first N contracts (use with --expired to resume interrupted downloads)")
    parser.add_argument("--api-key", default=None,
                        help="API key (default: env MASSIVE_API_KEY)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file path (default: auto-generated)")
    parser.add_argument("--format", choices=["csv", "json"], default="csv",
                        help="Output format (default: csv)")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        # try reading from .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("MASSIVE_API_KEY="):
                        api_key = line.strip().split("=", 1)[1]
                        break
    if not api_key:
        print("error: no API key. set MASSIVE_API_KEY env var, pass --api-key, or add to .env",
              file=sys.stderr)
        sys.exit(1)

    # default output path
    if not args.output:
        mode = "expired" if args.expired else "snapshot"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{args.ticker}_options_{mode}_{args.exp_from}_to_{args.exp_to}_{ts}"
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                               "data", "options")
        args.output = os.path.join(out_dir, f"{fname}.{args.format}")

    print(f"═══════════════════════════════════════════════════")
    print(f"  Options Chain Downloader")
    print(f"  Ticker:      {args.ticker}")
    print(f"  Expiration:  {args.exp_from} → {args.exp_to}")
    print(f"  Mode:        {'EXPIRED (contracts + daily bars)' if args.expired else 'ACTIVE (snapshot)'}")
    if args.type:
        print(f"  Type filter: {args.type}")
    if args.strike_min or args.strike_max:
        print(f"  Strike:      {args.strike_min or '...'} – {args.strike_max or '...'}")
    if args.expired and (args.bars_from or args.bars_to):
        print(f"  Bars range:  {args.bars_from or args.exp_from} → {args.bars_to or args.exp_to}")
    print(f"  Output:      {args.output}")
    print(f"═══════════════════════════════════════════════════")

    if args.expired:
        rows, headers = fetch_expired_chain(
            args.ticker, args.exp_from, args.exp_to, api_key,
            contract_type=args.type,
            strike_min=args.strike_min,
            strike_max=args.strike_max,
            bars_from=args.bars_from,
            bars_to=args.bars_to,
            skip=args.skip,
            output_path=args.output if args.format == "csv" else None,
        )
    else:
        rows, headers = fetch_snapshot_chain(
            args.ticker, args.exp_from, args.exp_to, api_key,
            contract_type=args.type,
            strike_min=args.strike_min,
            strike_max=args.strike_max,
        )

    if not rows:
        print("\n⚠ no data returned. check your date range and ticker.", file=sys.stderr)
        sys.exit(1)

    # For expired+csv, data was already written incrementally
    if args.expired and args.format == "csv":
        print(f"\n✓ saved {len(rows)} rows → {args.output}")
    elif args.format == "csv":
        write_csv(rows, headers, args.output)
    else:
        write_json(rows, args.output)

    print("\ndone ✓")


if __name__ == "__main__":
    main()
