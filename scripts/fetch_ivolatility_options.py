#!/usr/bin/env python3
"""
iVolatility SPY Options Data Pull
==================================
Pulls historical EOD SPY options chain data from iVolatility REST API.

Data includes: price, bid, ask, IV, delta, gamma, vega, theta, rho,
               volume, open interest per contract per trading day.

Architecture:
  1. Get auth token
  2. Fetch full option series (all SPY contracts) for each date range
  3. For each option symbol, pull EOD raw-IV data via single-stock-option-raw-iv
  4. Save to CSV with resume capability

Usage:
  python3 fetch_ivolatility_options.py                    # Run test week
  python3 fetch_ivolatility_options.py --full              # Run full 2-year pull
  python3 fetch_ivolatility_options.py --from 2025-01-01 --to 2025-03-31  # Custom range

Author: DataBento Pipeline
Date: March 2026
"""

import argparse
import csv
import gzip
import io
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL = "https://restapi.ivolatility.com"
USERNAME = os.environ.get("IVOL_USERNAME", "")
PASSWORD = os.environ.get("IVOL_PASSWORD", "")

# Rate limiting (configurable)
REQUEST_DELAY = 0.2          # seconds between API calls
TOKEN_REFRESH_INTERVAL = 1500  # seconds before refreshing token (25 min, token expires in 30)

# Directories
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = REPO_ROOT / "data" / "options" / "ivolatility"
LOG_DIR = REPO_ROOT / "logs"

# Output CSV columns (matches Pete's spec)
CSV_COLUMNS = [
    "date", "underlying_price", "option_symbol", "expiry", "strike",
    "type", "style", "bid", "ask", "close", "volume", "open_interest",
    "iv", "delta", "gamma", "vega", "theta", "rho",
]

# ─── Logging Setup ────────────────────────────────────────────────────────────

LOG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

log_file = LOG_DIR / f"ivolatility_pull_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
error_log = LOG_DIR / f"ivolatility_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("ivolatility")

# Separate error logger
error_handler = logging.FileHandler(error_log)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(error_handler)


# ─── API Client ───────────────────────────────────────────────────────────────

class IVolatilityClient:
    """REST API client for iVolatility."""

    def __init__(self, username: str, password: str, delay: float = REQUEST_DELAY):
        self.username = username
        self.password = password
        self.delay = delay
        self.token = None
        self.token_ts = 0
        self.request_count = 0

    def _get_token(self) -> str:
        """Get or refresh auth token."""
        now = time.time()
        if self.token and (now - self.token_ts) < TOKEN_REFRESH_INTERVAL:
            return self.token

        url = f"{BASE_URL}/token/get?" + urllib.parse.urlencode({
            "username": self.username,
            "password": self.password,
        })
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            self.token = resp.read().decode().strip()
            self.token_ts = now
            logger.info("Token refreshed successfully")
        return self.token

    def _api_get(self, path: str, params: dict, retries: int = 3) -> dict | None:
        """Make GET request with retries and rate limiting."""
        params["token"] = self._get_token()
        url = f"{BASE_URL}{path}?" + urllib.parse.urlencode(params)

        for attempt in range(retries):
            try:
                time.sleep(self.delay)
                self.request_count += 1
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                body = e.read().decode() if hasattr(e, "read") else ""
                if e.code == 403 and "expired" in body.lower():
                    # Token expired — refresh and retry
                    logger.warning("Token expired, refreshing...")
                    self.token_ts = 0
                    params["token"] = self._get_token()
                    url = f"{BASE_URL}{path}?" + urllib.parse.urlencode(params)
                    continue
                if e.code == 403:
                    logger.error(f"403 Forbidden: {body}")
                    return None
                if e.code == 429:  # Rate limited
                    wait = (attempt + 1) * 10
                    logger.warning(f"Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                logger.error(f"HTTP {e.code} on {path}: {body}")
                if attempt < retries - 1:
                    time.sleep(5)
                    continue
                return None
            except Exception as e:
                logger.error(f"Error on {path}: {e}")
                if attempt < retries - 1:
                    time.sleep(5)
                    # Force token refresh on next attempt
                    self.token_ts = 0
                    continue
                return None
        return None

    def _api_get_raw(self, url: str) -> bytes | None:
        """Download raw bytes from a URL."""
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    def get_option_series(self, symbol: str = "SPY") -> list[dict]:
        """Get all option contracts for a symbol (current trading day)."""
        logger.info(f"Fetching option series for {symbol}...")
        result = self._api_get("/equities/option-series", {"symbol": symbol})
        if not result:
            return []

        status = result.get("status", {})
        records = status.get("recordsFound", 0)
        dl_url = status.get("urlForDetails")

        if dl_url:
            # Large result — need to download CSV
            logger.info(f"Option series has {records} records, downloading...")
            info = self._api_get_raw(dl_url)
            if not info:
                return []
            info_data = json.loads(info.decode())
            if isinstance(info_data, list) and info_data:
                for item in info_data:
                    if "data" in item:
                        for file_info in item["data"]:
                            csv_url = file_info.get("urlForDownload")
                            if csv_url:
                                compressed = self._api_get_raw(csv_url)
                                if compressed:
                                    csv_text = gzip.decompress(compressed).decode()
                                    return self._parse_option_series_csv(csv_text)
        elif result.get("data"):
            return result["data"]

        return []

    def _parse_option_series_csv(self, csv_text: str) -> list[dict]:
        """Parse option series CSV into list of dicts."""
        lines = csv_text.strip().split("\n")
        if not lines:
            return []
        header = [h.strip() for h in lines[0].split(",")]
        records = []
        for line in lines[1:]:
            values = [v.strip() for v in line.split(",")]
            if len(values) >= len(header):
                records.append(dict(zip(header, values)))
        return records

    def get_single_option_rawiv(
        self, option_symbol: str, date_from: str, date_to: str
    ) -> list[dict]:
        """Get EOD data with greeks for a single option contract."""
        result = self._api_get(
            "/equities/eod/single-stock-option-raw-iv",
            {"symbol": option_symbol, "from": date_from, "to": date_to},
        )
        if result and result.get("data"):
            return result["data"]
        return []

    def get_stock_price(self, symbol: str, date: str) -> float | None:
        """Get underlying stock price for a date."""
        result = self._api_get(
            "/equities/eod/stock-prices",
            {"symbol": symbol, "date": date},
        )
        if result and result.get("data"):
            return result["data"][0].get("close")
        return None


# ─── Data Pipeline ────────────────────────────────────────────────────────────

def generate_trading_weeks(date_from: str, date_to: str) -> list[tuple[str, str]]:
    """Generate Monday-Friday week blocks."""
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")

    # Align to Monday
    if start.weekday() != 0:
        start = start - timedelta(days=start.weekday())

    weeks = []
    current = start
    while current <= end:
        week_end = current + timedelta(days=4)  # Friday
        if week_end > end:
            week_end = end
        weeks.append((current.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d")))
        current += timedelta(days=7)

    return weeks


def get_output_file(date_from: str, date_to: str) -> Path:
    """Get output CSV path for a date range."""
    return OUTPUT_DIR / f"SPY_options_{date_from}_to_{date_to}.csv"


def file_already_complete(filepath: Path) -> bool:
    """Check if output file exists and has data (for resume)."""
    if not filepath.exists():
        return False
    try:
        with open(filepath) as f:
            reader = csv.reader(f)
            header = next(reader, None)
            first_row = next(reader, None)
            return first_row is not None
    except Exception:
        return False


def flatten_record(rec: dict) -> dict:
    """Flatten iVolatility API record to our CSV schema."""
    return {
        "date": rec.get("date", ""),
        "underlying_price": rec.get("Adjusted close", rec.get("Unadjusted close", "")),
        "option_symbol": rec.get("option symbol", ""),
        "expiry": rec.get("expiration", ""),
        "strike": rec.get("strike", ""),
        "type": rec.get("Call/Put", ""),
        "style": rec.get("style", ""),
        "bid": rec.get("bid", ""),
        "ask": rec.get("ask", ""),
        "close": rec.get("price", ""),
        "volume": rec.get("volume", ""),
        "open_interest": rec.get("open interest", ""),
        "iv": rec.get("iv", ""),
        "delta": rec.get("delta", ""),
        "gamma": rec.get("gamma", ""),
        "vega": rec.get("vega", ""),
        "theta": rec.get("theta", ""),
        "rho": rec.get("rho", ""),
    }


def get_checkpoint_file(date_from: str, date_to: str) -> Path:
    """Checkpoint file to track progress within a week."""
    return OUTPUT_DIR / f".checkpoint_{date_from}_to_{date_to}.json"


def save_checkpoint(date_from: str, date_to: str, last_index: int, rows_saved: int, errors: int):
    """Save progress checkpoint so we can resume mid-week."""
    ckpt = get_checkpoint_file(date_from, date_to)
    with open(ckpt, "w") as f:
        json.dump({"last_index": last_index, "rows_saved": rows_saved, "errors": errors}, f)


def load_checkpoint(date_from: str, date_to: str) -> dict | None:
    """Load checkpoint if it exists."""
    ckpt = get_checkpoint_file(date_from, date_to)
    if not ckpt.exists():
        return None
    try:
        with open(ckpt) as f:
            return json.load(f)
    except Exception:
        return None


def clear_checkpoint(date_from: str, date_to: str):
    """Remove checkpoint file after week is fully done."""
    ckpt = get_checkpoint_file(date_from, date_to)
    if ckpt.exists():
        ckpt.unlink()


def pull_week(
    client: IVolatilityClient,
    option_symbols: list[str],
    date_from: str,
    date_to: str,
    progress_current: int = 0,
    progress_total: int = 0,
) -> tuple[int, int]:
    """Pull one week of data for all option symbols.

    Writes rows incrementally to CSV so progress is never lost.
    If interrupted, resumes from the last checkpoint.

    Returns (rows_saved, errors).
    """
    output_file = get_output_file(date_from, date_to)
    ckpt = load_checkpoint(date_from, date_to)

    # If file is complete AND no checkpoint (meaning it finished cleanly), skip
    if file_already_complete(output_file) and ckpt is None:
        logger.info(f"⏭  Skipping {date_from} to {date_to} — already complete")
        with open(output_file) as f:
            rows = sum(1 for _ in f) - 1
        return rows, 0

    # Determine start index
    start_index = 0
    rows_saved = 0
    errors = 0
    file_mode = "w"  # default: start fresh

    if ckpt is not None:
        start_index = ckpt["last_index"] + 1
        rows_saved = ckpt["rows_saved"]
        errors = ckpt["errors"]
        file_mode = "a"  # append to existing partial file
        logger.info(
            f"🔄 Resuming {date_from} to {date_to} from contract {start_index}/{len(option_symbols)} "
            f"({rows_saved} rows already saved)"
        )

    if start_index >= len(option_symbols):
        logger.info(f"⏭  All contracts already processed for {date_from} to {date_to}")
        clear_checkpoint(date_from, date_to)
        return rows_saved, errors

    logger.info(f"📦 Pulling {date_from} to {date_to} — {len(option_symbols) - start_index} contracts remaining")

    # Open file for writing/appending
    with open(output_file, file_mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if file_mode == "w":
            writer.writeheader()

        for i in range(start_index, len(option_symbols)):
            opt_sym = option_symbols[i]

            if (i + 1) % 500 == 0 or i == start_index:
                logger.info(
                    f"  [{i+1}/{len(option_symbols)}] {rows_saved} rows, {errors} errors "
                    f"[Week {progress_current}/{progress_total}]"
                )
            elif (i + 1) % 50 == 0:
                print(f"  ... {i+1}/{len(option_symbols)} ({rows_saved} rows)", end="\r")

            try:
                records = client.get_single_option_rawiv(opt_sym, date_from, date_to)
                for rec in records:
                    writer.writerow(flatten_record(rec))
                    rows_saved += 1
                f.flush()  # flush to disk after each contract
            except Exception as e:
                errors += 1
                logger.error(f"  Error on {opt_sym.strip()}: {e}")

            # Save checkpoint every 100 contracts
            if (i + 1) % 100 == 0:
                save_checkpoint(date_from, date_to, i, rows_saved, errors)

    # Week done — save final state and clear checkpoint
    clear_checkpoint(date_from, date_to)

    if rows_saved > 0:
        logger.info(f"✅ Saved {rows_saved} rows to {output_file.name}")
    else:
        logger.warning(f"⚠️  No data returned for {date_from} to {date_to}")

    return rows_saved, errors


def get_option_symbols_for_period(
    client: IVolatilityClient,
    date_from: str,
    date_to: str,
) -> list[str]:
    """Get option symbols that were active during a date range.

    Uses the option-series endpoint which returns current contracts.
    Returns full chain — all strikes, all expiries (per Pete's spec).
    Only filters out contracts that expired before the pull range.
    """
    # Fetch option series
    series = client.get_option_series("SPY")
    if not series:
        logger.error("Could not fetch option series")
        return []

    # Filter: only keep contracts with expiration >= date_from
    symbols = []
    skipped_exp = 0

    for rec in series:
        opt_sym = rec.get("OptionSymbol", rec.get("optionSymbol", ""))
        exp_date = rec.get("expirationDate", rec.get("expDate", ""))

        if not opt_sym or not exp_date:
            continue

        if exp_date < date_from:
            skipped_exp += 1
            continue

        symbols.append(opt_sym)

    logger.info(
        f"Found {len(symbols)} option symbols "
        f"(skipped {skipped_exp} already-expired contracts)"
    )
    return symbols


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="iVolatility SPY Options Data Pull")
    parser.add_argument("--full", action="store_true", help="Full 2-year pull (Mar 2024 — Feb 2026)")
    parser.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="Delay between requests (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--username", default=USERNAME, help="iVolatility username (or set IVOL_USERNAME env var)")
    parser.add_argument("--password", default=PASSWORD, help="iVolatility password (or set IVOL_PASSWORD env var)")
    args = parser.parse_args()

    # Validate credentials
    username = args.username
    password = args.password
    if not username or not password:
        print("ERROR: Credentials required. Use --username/--password or set IVOL_USERNAME/IVOL_PASSWORD env vars.")
        sys.exit(1)

    # Determine date range
    if args.full:
        date_from = "2024-03-01"
        date_to = "2026-02-28"
    elif args.date_from and args.date_to:
        date_from = args.date_from
        date_to = args.date_to
    else:
        # Default: test week
        date_from = "2026-03-09"
        date_to = "2026-03-13"

    logger.info("=" * 70)
    logger.info("iVolatility SPY Options Data Pull")
    logger.info(f"  Date range: {date_from} to {date_to}")
    logger.info(f"  Delay: {args.delay}s between requests")
    logger.info(f"  Output: {OUTPUT_DIR}")
    logger.info(f"  Log: {log_file}")
    logger.info("=" * 70)

    # Initialize client
    client = IVolatilityClient(username, password, delay=args.delay)

    # Step 1: Get option symbols
    logger.info("Step 1: Fetching option series...")
    option_symbols = get_option_symbols_for_period(client, date_from, date_to)
    if not option_symbols:
        logger.error("No option symbols found. Exiting.")
        sys.exit(1)

    # Step 2: Generate week blocks
    weeks = generate_trading_weeks(date_from, date_to)
    logger.info(f"Step 2: {len(weeks)} weeks to pull")

    if args.dry_run:
        logger.info("DRY RUN — would pull:")
        for i, (wf, wt) in enumerate(weeks):
            logger.info(f"  Week {i+1}: {wf} to {wt}")
        logger.info(f"  {len(option_symbols)} contracts × {len(weeks)} weeks")
        logger.info(f"  ≈ {len(option_symbols) * len(weeks)} API calls")
        est_time = len(option_symbols) * len(weeks) * args.delay / 60
        logger.info(f"  Estimated time: {est_time:.0f} minutes")
        return

    # Step 3: Pull each week
    total_rows = 0
    total_errors = 0
    start_time = time.time()

    for i, (week_from, week_to) in enumerate(weeks, 1):
        logger.info(f"\n{'─'*50}")
        logger.info(f"Week {i}/{len(weeks)}: {week_from} to {week_to}")

        rows, errors = pull_week(
            client, option_symbols, week_from, week_to,
            progress_current=i, progress_total=len(weeks),
        )
        total_rows += rows
        total_errors += errors

        elapsed = time.time() - start_time
        rate = total_rows / elapsed if elapsed > 0 else 0
        logger.info(
            f"Running total: {total_rows} rows, {total_errors} errors, "
            f"{elapsed/60:.1f} min elapsed, {rate:.0f} rows/sec"
        )

    # Summary
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 70)
    logger.info("PULL COMPLETE")
    logger.info(f"  Total rows: {total_rows}")
    logger.info(f"  Total errors: {total_errors}")
    logger.info(f"  API requests: {client.request_count}")
    logger.info(f"  Time: {elapsed/60:.1f} minutes")
    logger.info(f"  Output: {OUTPUT_DIR}")
    logger.info("=" * 70)

    # List output files
    csv_files = sorted(OUTPUT_DIR.glob("SPY_options_*.csv"))
    for f in csv_files:
        size_kb = f.stat().st_size / 1024
        logger.info(f"  📄 {f.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
