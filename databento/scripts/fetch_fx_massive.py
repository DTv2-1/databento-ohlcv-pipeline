"""
Massive.com FX Spot Downloader
Downloads 1-second OHLCV for forex pairs (EURUSD, AUDJPY, etc.)
then resamples to 5s for delivery.
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from massive import RESTClient
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/fetch_fx_massive.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Timeframes map for resampling
TIMEFRAME_MAP = {'5s': '5s', '15s': '15s', '30s': '30s', '1min': '1min'}

# Symbol formats to try on Massive
FX_SYMBOL_CANDIDATES = {
    'EURUSD': ['C:EURUSD', 'EURUSD', 'EUR/USD'],
    'AUDJPY': ['C:AUDJPY', 'AUDJPY', 'AUD/JPY'],
}


def detect_symbol(client, pair, test_date='2025-02-03'):
    """Try different symbol formats using get_aggs (works for FX)."""
    candidates = FX_SYMBOL_CANDIDATES.get(pair, [pair])
    for sym in candidates:
        try:
            result = client.get_aggs(sym, 1, 'second', test_date, test_date, limit=3)
            if result and len(result) > 0:
                logger.info(f"Symbol resolved: '{pair}' → '{sym}' ({len(result)} test bars)")
                return sym
            else:
                logger.warning(f"  '{sym}': 0 bars returned")
        except Exception as e:
            logger.warning(f"  '{sym}': error — {e}")
    return None


def download_month(client, symbol, massive_sym, year, month, output_dir, force=False):
    filename = f"{symbol}_{year}_{month:02d}.csv"
    filepath = Path(output_dir) / symbol / filename

    if filepath.exists() and not force:
        logger.info(f"SKIP: {filename} already exists")
        return {'status': 'skipped', 'file': str(filepath)}

    filepath.parent.mkdir(parents=True, exist_ok=True)

    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = datetime(year, month + 1, 1) - timedelta(days=1)

    start_str = start.strftime('%Y-%m-%d')
    end_str = end.strftime('%Y-%m-%d')

    logger.info(f"Downloading {symbol} ({massive_sym}) {year}-{month:02d}  [{start_str} → {end_str}]")

    try:
        # FX trades 24/5 — a month can have ~2.5M seconds
        # get_aggs returns max 50000 per call, so we iterate day by day
        aggs = []
        current_day = start
        while current_day <= end:
            day_str = current_day.strftime('%Y-%m-%d')
            try:
                batch = client.get_aggs(
                    massive_sym, 1, 'second',
                    day_str, day_str,
                    limit=50000,
                    sort='asc',
                )
                if batch:
                    aggs.extend(batch)
                    logger.info(f"  {day_str}: {len(batch):,} bars | running total: {len(aggs):,}")
                else:
                    logger.info(f"  {day_str}: 0 bars (weekend/holiday)")
            except Exception as day_err:
                logger.warning(f"  {day_str}: error — {day_err}")
            current_day += timedelta(days=1)

        if not aggs:
            logger.warning(f"  WARNING: No data returned for {filename}")
            return {'status': 'failed', 'error': 'No data', 'file': str(filepath)}

        rows = []
        for agg in aggs:
            ts = pd.to_datetime(agg.timestamp, unit='ms', utc=True)
            rows.append({
                'ts_event': ts,
                'open': agg.open,
                'high': agg.high,
                'low': agg.low,
                'close': agg.close,
                'volume': agg.volume
            })

        df = pd.DataFrame(rows).set_index('ts_event').sort_index()
        df.to_csv(filepath, index=True)
        logger.info(f"  SUCCESS: {filename} — {len(df):,} rows saved")
        return {'status': 'success', 'file': str(filepath), 'rows': len(df)}

    except Exception as e:
        logger.error(f"  ERROR: {filename} — {e}")
        return {'status': 'failed', 'error': str(e), 'file': str(filepath)}


def resample_to_5s(symbol, raw_dir, out_dir):
    """Resample all 1s CSVs for a symbol to 5s."""
    symbol_dir = Path(raw_dir) / symbol
    csv_files = sorted(symbol_dir.glob('*.csv'))
    logger.info(f"Resampling {len(csv_files)} files for {symbol} → 5s")

    for f in csv_files:
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        resampled = df.resample('5s', label='left', closed='left').agg({
            'open': 'first', 'high': 'max', 'low': 'min',
            'close': 'last', 'volume': 'sum'
        }).dropna()

        out_path = Path(out_dir) / '5s' / f"{f.stem}_5s.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        resampled.to_csv(out_path)
        logger.info(f"  {f.name} → {out_path.name} ({len(resampled):,} rows)")


def main():
    parser = argparse.ArgumentParser(description='Download FX spot data from Massive.com and resample to 5s')
    parser.add_argument('--symbols', default='EURUSD,AUDJPY', help='Comma-separated FX pairs (default: EURUSD,AUDJPY)')
    parser.add_argument('--start', default='2025-02-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', default='2026-01-31', help='End date YYYY-MM-DD')
    parser.add_argument('--raw_dir', default='data/raw_1s', help='Directory for 1s CSVs')
    parser.add_argument('--agg_dir', default='data/aggregated', help='Directory for resampled CSVs')
    parser.add_argument('--delivery_dir', default='delivery/pete_5s_Feb2025_Jan2026', help='Delivery folder')
    parser.add_argument('--force', action='store_true', help='Re-download existing files')
    parser.add_argument('--skip_resample', action='store_true', help='Skip resampling step')
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv('MASSIVE_API_KEY')
    if not api_key:
        logger.error("MASSIVE_API_KEY not found in .env")
        sys.exit(1)

    client = RESTClient(api_key)
    symbols = [s.strip() for s in args.symbols.split(',')]

    start = datetime.strptime(args.start, '%Y-%m-%d')
    end = datetime.strptime(args.end, '%Y-%m-%d')

    for symbol in symbols:
        logger.info("=" * 60)
        logger.info(f"SYMBOL: {symbol}")
        logger.info("=" * 60)

        # Detect working symbol format
        massive_sym = detect_symbol(client, symbol)
        if not massive_sym:
            logger.error(f"Could not resolve '{symbol}' on Massive.com — skipping")
            continue

        # Download month by month
        summary = {'success': 0, 'skipped': 0, 'failed': 0}
        current = start
        while current <= end:
            result = download_month(client, symbol, massive_sym, current.year, current.month, args.raw_dir, args.force)
            summary[result['status']] += 1
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)

        logger.info(f"Download summary for {symbol}: {summary}")

        # Resample to 5s
        if not args.skip_resample:
            resample_to_5s(symbol, args.raw_dir, args.agg_dir)

        # Copy to delivery
        delivery_dir = Path(args.delivery_dir) / symbol
        delivery_dir.mkdir(parents=True, exist_ok=True)
        agg_5s_dir = Path(args.agg_dir) / '5s'
        copied = 0
        for f in sorted(agg_5s_dir.glob(f"{symbol}_*_5s.csv")):
            dest = delivery_dir / f.name
            dest.write_bytes(f.read_bytes())
            copied += 1
        logger.info(f"Copied {copied} files to {delivery_dir}")

    logger.info("=" * 60)
    logger.info("ALL DONE")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
