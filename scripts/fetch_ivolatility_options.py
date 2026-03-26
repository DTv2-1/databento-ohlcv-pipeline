#!/usr/bin/env python3
"""
iVolatility Options Data Pull
================================
Pulls historical EOD options chain data from iVolatility REST API.
Supports any equity symbol (SPY, AAPL, QQQ, TSLA, etc.).

Data includes: price, bid, ask, IV, delta, gamma, vega, theta, rho,
               volume, open interest per contract per trading day.

Architecture:
  1. Get auth token
  2. Fetch full option series (all contracts for the symbol) for each date range
  3. For each option symbol, pull EOD raw-IV data via single-stock-option-raw-iv
  4. Save to CSV with resume capability

Usage:
  python3 fetch_ivolatility_options.py                                     # Test week (SPY)
  python3 fetch_ivolatility_options.py --full --monthly                     # Full 2yr, 1 CSV/month
  python3 fetch_ivolatility_options.py --symbol AAPL --from 2024-03-01 --to 2024-12-31 --monthly
  python3 fetch_ivolatility_options.py --from 2024-03-01 --to 2024-03-31    # Single month

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
APIKEY = os.environ.get("IVOL_APIKEY", os.environ.get("API_KEY", ""))

# Rate limiting (configurable)
REQUEST_DELAY = 1.5          # seconds between API calls (free trial needs ~1.5s+)
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

    def __init__(self, username: str = "", password: str = "", delay: float = REQUEST_DELAY, apikey: str = ""):
        self.username = username
        self.password = password
        self.apikey = apikey
        self.delay = delay
        self.token = None
        self.token_ts = 0
        self.request_count = 0

    def _get_token(self) -> str:
        """Get or refresh auth token.

        If apikey is provided (cloud workspace), use it directly as token.
        Otherwise, authenticate with username/password.
        """
        # Cloud workspace: API key IS the token
        if self.apikey:
            if not self.token:
                self.token = self.apikey
                self.token_ts = time.time()
                logger.info("Using API key as token (cloud workspace mode)")
            return self.token

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

    def _api_get(self, path: str, params: dict, retries: int = 5) -> dict | None:
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
                    wait = (attempt + 1) * 15
                    # Auto-increase delay to avoid future rate limits
                    if self.delay < 3.0:
                        self.delay = min(self.delay + 0.5, 3.0)
                        logger.warning(f"Rate limited, waiting {wait}s... (increased delay to {self.delay}s)")
                    else:
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

    def get_option_series_on_date(self, symbol: str = "SPY", date: str = "",
                                  exp_from: str = "", exp_to: str = "") -> list[dict]:
        """Get option contracts for a symbol on a specific date.

        Uses /equities/eod/option-series-on-date which returns data directly
        (no async file generation). This is the correct endpoint for historical data.
        """
        logger.info(f"Fetching option series for {symbol} on date {date}...")
        params = {"symbol": symbol}
        if date:
            params["date"] = date
        if exp_from:
            params["expFrom"] = exp_from
        if exp_to:
            params["expTo"] = exp_to

        result = self._api_get("/equities/eod/option-series-on-date", params)
        if not result:
            return []

        # Direct data response
        if result.get("data"):
            records = result["data"]
            logger.info(f"  Got {len(records)} option contracts directly")
            return records

        # Fallback: check status/urlForDetails pattern
        status = result.get("status", {})
        records_count = status.get("recordsFound", 0)
        dl_url = status.get("urlForDetails")

        if dl_url:
            logger.info(f"  {records_count} records, polling for file...")
            return self._poll_and_download(dl_url)

        logger.error(f"  Unexpected response format: {str(result)[:500]}")
        return []

    def _poll_and_download(self, dl_url: str, max_polls: int = 30, poll_interval: int = 10) -> list[dict]:
        """Poll a detail URL until the async file is ready, then download and parse."""
        for poll in range(max_polls):
            info = self._api_get_raw(dl_url)
            if not info:
                logger.error("Failed to download detail URL")
                return []
            info_text = info.decode()

            try:
                info_data = json.loads(info_text)
            except json.JSONDecodeError:
                if "," in info_text and "\n" in info_text:
                    return self._parse_option_series_csv(info_text)
                logger.error("Response is neither JSON nor CSV")
                return []

            # Extract status
            meta_status = None
            file_info_list = []
            if isinstance(info_data, list) and info_data:
                item = info_data[0]
                if isinstance(item, dict):
                    meta_status = item.get("meta", {}).get("status", "")
                    file_info_list = item.get("data", [])
            elif isinstance(info_data, dict):
                meta_status = info_data.get("meta", {}).get("status", "")
                file_info_list = info_data.get("data", [])

            logger.info(f"  Poll {poll + 1}/{max_polls}: status={meta_status}")

            if meta_status and meta_status.upper() == "PENDING":
                logger.info(f"  File still being generated, waiting {poll_interval}s...")
                time.sleep(poll_interval)
                continue

            # Try to download
            for fi in file_info_list:
                csv_url = fi.get("urlForDownload")
                file_name = fi.get("fileName", "")
                file_size = fi.get("fileSize", 0)
                if csv_url and file_size > 0:
                    logger.info(f"  Downloading: {csv_url}")
                    compressed = self._api_get_raw(csv_url)
                    if compressed:
                        try:
                            csv_text = gzip.decompress(compressed).decode()
                        except Exception:
                            csv_text = compressed.decode()
                        return self._parse_option_series_csv(csv_text)
                elif file_name:
                    constructed_url = f"{BASE_URL}/data/download/{file_name}?token={self._get_token()}"
                    logger.info(f"  Trying constructed URL: {constructed_url}")
                    compressed = self._api_get_raw(constructed_url)
                    if compressed:
                        try:
                            csv_text = gzip.decompress(compressed).decode()
                        except Exception:
                            csv_text = compressed.decode()
                        return self._parse_option_series_csv(csv_text)

            # Maybe data is inline
            if isinstance(info_data, dict) and "data" in info_data:
                if isinstance(info_data["data"], list) and info_data["data"]:
                    if isinstance(info_data["data"][0], dict):
                        return info_data["data"]

            logger.error(f"  File not ready. Response: {info_text[:500]}")
            return []

        logger.error(f"  Timed out after {max_polls * poll_interval}s")
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


def generate_monthly_blocks(date_from: str, date_to: str) -> list[tuple[str, str]]:
    """Generate month-sized blocks (1st to last day of month).

    Each block produces one CSV file. Blocks auto-clip to date_from/date_to.
    """
    from calendar import monthrange
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")

    blocks = []
    current = start.replace(day=1)  # start at 1st of month
    while current <= end:
        month_start = max(current, start)
        _, last_day = monthrange(current.year, current.month)
        month_end = min(current.replace(day=last_day), end)
        blocks.append((month_start.strftime("%Y-%m-%d"), month_end.strftime("%Y-%m-%d")))
        # advance to 1st of next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)

    return blocks


def get_output_file(date_from: str, date_to: str, symbol: str = "SPY") -> Path:
    """Get output CSV path for a date range."""
    return OUTPUT_DIR / f"{symbol}_options_{date_from}_to_{date_to}.csv"


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
    symbol: str = "SPY",
) -> tuple[int, int]:
    """Pull one week of data for all option symbols.

    Writes rows incrementally to CSV so progress is never lost.
    If interrupted, resumes from the last checkpoint.

    Returns (rows_saved, errors).
    """
    output_file = get_output_file(date_from, date_to, symbol=symbol)
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
    symbol: str = "SPY",
) -> list[str]:
    """Get option symbols that were active during a date range.

    Uses /equities/eod/option-series-on-date which returns contracts that existed
    on a specific trading day. We query using the first date of the range.
    Returns full chain — all strikes, all expiries (per Pete's spec).
    Only filters out contracts that expired before the pull range.
    """
    # Use option-series-on-date with the first date of the range
    series = client.get_option_series_on_date(symbol, date=date_from)
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
    parser = argparse.ArgumentParser(description="iVolatility Options Data Pull")
    parser.add_argument("--symbol", default="SPY", help="Underlying symbol (default: SPY). Examples: SPY, AAPL, QQQ, TSLA")
    parser.add_argument("--full", action="store_true", help="Full 2-year pull (Mar 2024 — Feb 2026)")
    parser.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="Delay between requests (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--monthly", action="store_true", help="Split into monthly CSVs (1 file per month, auto-continues)")
    parser.add_argument("--username", default=USERNAME, help="iVolatility username (or set IVOL_USERNAME env var)")
    parser.add_argument("--password", default=PASSWORD, help="iVolatility password (or set IVOL_PASSWORD env var)")
    parser.add_argument("--apikey", default=APIKEY, help="iVolatility API key (cloud workspace; or set IVOL_APIKEY env var)")
    args = parser.parse_args()

    # Validate credentials
    # If user explicitly passed --username and --password, prefer those over any env API key
    # (the cloud workspace may have an API_KEY env var that is NOT for the iVolatility REST API)
    username = args.username
    password = args.password
    apikey = args.apikey
    if username and password:
        apikey = ""  # force username/password auth when both are provided
    if not apikey and (not username or not password):
        print("ERROR: Credentials required.")
        print("  Option A (cloud): --apikey YOUR_KEY  or set IVOL_APIKEY env var")
        print("  Option B (local): --username USER --password PASS  or set IVOL_USERNAME/IVOL_PASSWORD env vars")
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

    symbol = args.symbol.upper()

    logger.info("=" * 70)
    logger.info(f"iVolatility {symbol} Options Data Pull")
    logger.info(f"  Symbol: {symbol}")
    logger.info(f"  Date range: {date_from} to {date_to}")
    logger.info(f"  Delay: {args.delay}s between requests")
    logger.info(f"  Output: {OUTPUT_DIR}")
    logger.info(f"  Log: {log_file}")
    logger.info("=" * 70)

    # Initialize client
    client = IVolatilityClient(username=username, password=password, delay=args.delay, apikey=apikey)

    # Step 1: Get option symbols
    logger.info("Step 1: Fetching option series...")
    option_symbols = get_option_symbols_for_period(client, date_from, date_to, symbol=symbol)
    if not option_symbols:
        logger.error("No option symbols found. Exiting.")
        sys.exit(1)

    # Step 2: Generate time blocks
    if args.monthly:
        months = generate_monthly_blocks(date_from, date_to)
        logger.info(f"Step 2: {len(months)} monthly blocks to pull (1 CSV per month)")
    else:
        months = None

    weeks = generate_trading_weeks(date_from, date_to)
    if not args.monthly:
        logger.info(f"Step 2: {len(weeks)} weeks to pull")

    if args.dry_run:
        if args.monthly:
            logger.info("DRY RUN — monthly mode, would pull:")
            for i, (mf, mt) in enumerate(months):
                m_weeks = generate_trading_weeks(mf, mt)
                logger.info(f"  Month {i+1}: {mf} to {mt} ({len(m_weeks)} weeks)")
            total_weeks = sum(len(generate_trading_weeks(mf, mt)) for mf, mt in months)
            logger.info(f"  {len(option_symbols)} contracts × {total_weeks} weeks")
            logger.info(f"  ≈ {len(option_symbols) * total_weeks} API calls")
            est_time = len(option_symbols) * total_weeks * args.delay / 60
            logger.info(f"  Estimated time: {est_time:.0f} minutes ({est_time/60:.1f} hours)")
        else:
            logger.info("DRY RUN — would pull:")
            for i, (wf, wt) in enumerate(weeks):
                logger.info(f"  Week {i+1}: {wf} to {wt}")
            logger.info(f"  {len(option_symbols)} contracts × {len(weeks)} weeks")
            logger.info(f"  ≈ {len(option_symbols) * len(weeks)} API calls")
            est_time = len(option_symbols) * len(weeks) * args.delay / 60
            logger.info(f"  Estimated time: {est_time:.0f} minutes")
        return

    # Step 3: Pull data
    total_rows = 0
    total_errors = 0
    start_time = time.time()

    if args.monthly:
        # ── Monthly mode: pull each month, all weeks merged into 1 CSV per month ──
        for m_idx, (month_from, month_to) in enumerate(months, 1):
            month_label = month_from[:7]  # e.g. "2024-03"
            month_file = OUTPUT_DIR / f"{symbol}_options_{month_label}.csv"

            logger.info(f"\n{'═'*60}")
            logger.info(f"MONTH {m_idx}/{len(months)}: {month_label} ({month_from} to {month_to})")
            logger.info(f"  Output: {month_file.name}")
            logger.info(f"{'═'*60}")

            # Check if month is already complete
            month_ckpt = OUTPUT_DIR / f".checkpoint_month_{month_label}.json"
            if month_file.exists() and not month_ckpt.exists():
                with open(month_file) as mf:
                    existing_rows = sum(1 for _ in mf) - 1
                if existing_rows > 0:
                    logger.info(f"⏭  Skipping {month_label} — already complete ({existing_rows} rows)")
                    total_rows += existing_rows
                    continue

            m_weeks = generate_trading_weeks(month_from, month_to)
            month_rows = 0
            month_errors = 0

            # Load month checkpoint (tracks which week we're on)
            month_start_week = 0
            if month_ckpt.exists():
                try:
                    with open(month_ckpt) as mc:
                        mck = json.load(mc)
                    month_start_week = mck.get("completed_weeks", 0)
                    month_rows = mck.get("rows", 0)
                    month_errors = mck.get("errors", 0)
                    logger.info(f"🔄 Resuming month {month_label} from week {month_start_week + 1}")
                except Exception:
                    pass

            # Open month CSV (append if resuming, write if fresh)
            file_mode = "a" if month_start_week > 0 and month_file.exists() else "w"
            with open(month_file, file_mode, newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                if file_mode == "w":
                    writer.writeheader()

                for w_idx in range(month_start_week, len(m_weeks)):
                    week_from, week_to = m_weeks[w_idx]
                    logger.info(f"\n{'─'*50}")
                    logger.info(f"  Week {w_idx + 1}/{len(m_weeks)}: {week_from} to {week_to}")

                    # Pull week data directly into the month CSV
                    week_rows = 0
                    week_errors = 0
                    for i, opt_sym in enumerate(option_symbols):
                        if (i + 1) % 500 == 0 or i == 0:
                            logger.info(
                                f"    [{i+1}/{len(option_symbols)}] {month_rows + week_rows} rows "
                                f"[Week {w_idx+1}/{len(m_weeks)}]"
                            )
                        elif (i + 1) % 50 == 0:
                            print(f"    ... {i+1}/{len(option_symbols)} ({month_rows + week_rows} rows)", end="\r")

                        try:
                            records = client.get_single_option_rawiv(opt_sym, week_from, week_to)
                            for rec in records:
                                writer.writerow(flatten_record(rec))
                                week_rows += 1
                            f.flush()
                        except Exception as e:
                            week_errors += 1
                            logger.error(f"    Error on {opt_sym.strip()}: {e}")

                    month_rows += week_rows
                    month_errors += week_errors

                    # Save month checkpoint after each week
                    with open(month_ckpt, "w") as mc:
                        json.dump({"completed_weeks": w_idx + 1, "rows": month_rows, "errors": month_errors}, mc)
                    logger.info(f"  ✓ Week done: +{week_rows} rows (month total: {month_rows})")

            # Month done — clean up checkpoint
            if month_ckpt.exists():
                month_ckpt.unlink()
            total_rows += month_rows
            total_errors += month_errors

            elapsed = time.time() - start_time
            size_kb = month_file.stat().st_size / 1024
            logger.info(f"\n✅ Month {month_label} complete: {month_rows} rows, {month_errors} errors ({size_kb:.0f} KB)")
            logger.info(f"   Overall progress: {total_rows} rows, {elapsed/60:.1f} min elapsed")
            logger.info(f"   Months remaining: {len(months) - m_idx}")
    else:
        # ── Original weekly mode ──
        for i, (week_from, week_to) in enumerate(weeks, 1):
            logger.info(f"\n{'─'*50}")
            logger.info(f"Week {i}/{len(weeks)}: {week_from} to {week_to}")

            rows, errors = pull_week(
                client, option_symbols, week_from, week_to,
                progress_current=i, progress_total=len(weeks),
                symbol=symbol,
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
    csv_files = sorted(OUTPUT_DIR.glob(f"{symbol}_options_*.csv"))
    for f in csv_files:
        size_kb = f.stat().st_size / 1024
        logger.info(f"  📄 {f.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
