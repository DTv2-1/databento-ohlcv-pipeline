#!/usr/bin/env python3
"""
Download native 1-minute bars from Databento and compare with aggregated 1-minute bars
"""

import os
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import databento as db
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/comparison.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def download_native_1min(symbol, year, month, dataset, output_dir):
    """Download native 1-minute bars from Databento"""
    
    # Load API key
    load_dotenv()
    api_key = os.getenv('DATABENTO_API_KEY')
    if not api_key:
        logger.error("DATABENTO_API_KEY not found")
        sys.exit(1)
    
    client = db.Historical(api_key)
    
    # Create filename
    filename = f"{symbol}_{year}_{month:02d}_native_1min.csv"
    filepath = Path(output_dir) / filename
    
    # Calculate dates
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year, 12, 31, 23, 59, 59)
    else:
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        end = datetime(year, month, last_day, 23, 59, 59)
    
    logger.info(f"Downloading native 1min bars for {symbol} {year}-{month:02d}")
    logger.info(f"Date range: {start} to {end}")
    
    # Detect continuous contracts
    stype_in = 'continuous' if '.v.' in symbol else 'raw_symbol'
    if stype_in == 'continuous':
        logger.info(f"Using continuous contract: {symbol}")
    
    # Download using ohlcv-1m schema
    data = client.timeseries.get_range(
        dataset=dataset,
        symbols=[symbol],
        schema='ohlcv-1m',
        start=start.isoformat(),
        end=end.isoformat(),
        stype_in=stype_in,
    )
    
    # Convert to DataFrame
    df = data.to_df()
    
    if df.empty:
        logger.error(f"No data returned for {symbol}")
        return None
    
    # Save
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=True)
    logger.info(f"Saved {filename} with {len(df)} rows")
    
    return filepath


def compare_bars(native_file, aggregated_file):
    """Compare native and aggregated 1-minute bars"""
    
    logger.info(f"\nComparing:")
    logger.info(f"  Native: {native_file}")
    logger.info(f"  Aggregated: {aggregated_file}")
    
    # Load both files
    native = pd.read_csv(native_file, index_col=0, parse_dates=True)
    aggregated = pd.read_csv(aggregated_file, index_col=0, parse_dates=True)
    
    logger.info(f"\nData loaded:")
    logger.info(f"  Native rows: {len(native):,}")
    logger.info(f"  Aggregated rows: {len(aggregated):,}")
    
    # Time ranges
    logger.info(f"\nNative time range:")
    logger.info(f"  First: {native.index[0]}")
    logger.info(f"  Last: {native.index[-1]}")
    
    logger.info(f"\nAggregated time range:")
    logger.info(f"  First: {aggregated.index[0]}")
    logger.info(f"  Last: {aggregated.index[-1]}")
    
    # Merge on timestamp
    comparison = native.join(aggregated, lsuffix='_native', rsuffix='_agg', how='outer')
    
    # Find timestamps that exist in both
    both = comparison.dropna()
    logger.info(f"\nTimestamps in both: {len(both):,}")
    
    # Find differences
    only_native = comparison[comparison['open_agg'].isna()]
    only_agg = comparison[comparison['open_native'].isna()]
    
    logger.info(f"Only in native: {len(only_native):,}")
    logger.info(f"Only in aggregated: {len(only_agg):,}")
    
    if len(both) == 0:
        logger.error("ERROR: No matching timestamps found!")
        return False
    
    # Compare OHLCV values for matching timestamps
    logger.info(f"\n{'='*60}")
    logger.info("COMPARING OHLCV VALUES")
    logger.info(f"{'='*60}")
    
    tolerance = 0.01  # Allow small floating point differences
    
    fields = ['open', 'high', 'low', 'close', 'volume']
    all_match = True
    
    for field in fields:
        native_col = f'{field}_native'
        agg_col = f'{field}_agg'
        
        if field == 'volume':
            # Volume should match exactly
            diff = (both[native_col] - both[agg_col]).abs()
            mismatches = diff > 0
        else:
            # Prices can have small floating point differences
            diff = (both[native_col] - both[agg_col]).abs()
            mismatches = diff > tolerance
        
        mismatch_count = mismatches.sum()
        
        if mismatch_count > 0:
            max_diff = diff.max()
            avg_diff = diff.mean()
            logger.warning(f"\n{field.upper()}: {mismatch_count:,} mismatches")
            logger.warning(f"  Max difference: {max_diff:.6f}")
            logger.warning(f"  Avg difference: {avg_diff:.6f}")
            
            # Show first few mismatches
            mismatch_samples = both[mismatches].head(5)
            logger.warning(f"  First {len(mismatch_samples)} mismatches:")
            for idx, row in mismatch_samples.iterrows():
                logger.warning(f"    {idx}: native={row[native_col]:.4f} agg={row[agg_col]:.4f} diff={abs(row[native_col]-row[agg_col]):.6f}")
            
            all_match = False
        else:
            logger.info(f"{field.upper()}: ✓ All values match (tolerance={tolerance})")
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("COMPARISON SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Time range compared: {both.index[0]} to {both.index[-1]}")
    logger.info(f"Bars compared: {len(both):,}")
    logger.info(f"Result: {'✓ PASS - All values match' if all_match else '✗ FAIL - Differences found'}")
    logger.info(f"{'='*60}\n")
    
    return all_match


def main():
    """Main comparison workflow"""
    
    logger.info("="*60)
    logger.info("NATIVE vs AGGREGATED 1MIN COMPARISON")
    logger.info("="*60)
    
    symbol = "ES.v.0"
    dataset = "GLBX.MDP3"
    months = [(2024, 1), (2024, 3)]
    
    native_dir = "data/native_1min"
    agg_dir = "data/aggregated/1min"
    
    all_passed = True
    
    for year, month in months:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing {symbol} {year}-{month:02d}")
        logger.info(f"{'='*60}")
        
        # Download native 1min
        native_file = download_native_1min(symbol, year, month, dataset, native_dir)
        if not native_file:
            logger.error(f"Failed to download native data for {year}-{month:02d}")
            all_passed = False
            continue
        
        # Find aggregated file
        agg_file = Path(agg_dir) / f"{symbol}_{year}_{month:02d}_1min.csv"
        if not agg_file.exists():
            logger.error(f"Aggregated file not found: {agg_file}")
            all_passed = False
            continue
        
        # Compare
        result = compare_bars(native_file, agg_file)
        if not result:
            all_passed = False
    
    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info("FINAL RESULT")
    logger.info(f"{'='*60}")
    logger.info(f"{'✓ ALL COMPARISONS PASSED' if all_passed else '✗ SOME COMPARISONS FAILED'}")
    logger.info(f"{'='*60}")
    
    logger.info(f"\nNative 1min files saved in: {native_dir}/")
    logger.info(f"Comparison log: logs/comparison.log")
    
    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
