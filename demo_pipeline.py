#!/usr/bin/env python3
"""
Complete End-to-End Demo of Databento Pipeline

This script demonstrates the entire pipeline:
1. Download 1-second OHLCV data
2. Aggregate to multiple timeframes
3. Validate data integrity (including volume checks)

Usage:
    python demo_pipeline.py --symbol SPY --month 2024-01
    python demo_pipeline.py --symbol ES.v.0 --month 2024-01 --dataset GLBX.MDP3
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/demo.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import our scripts
sys.path.insert(0, str(Path(__file__).parent))
from scripts.fetch_1s_bars import DatabentoDownloader
from scripts.resample_bars import OHLCVAggregator
from scripts.validate_bars import OHLCVValidator


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Complete pipeline demo: download → aggregate → validate',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # SPY for January 2024
  python demo_pipeline.py --symbol SPY --month 2024-01
  
  # ES continuous contract for January 2024
  python demo_pipeline.py --symbol ES.v.0 --month 2024-01 --dataset GLBX.MDP3
  
  # Custom timeframes
  python demo_pipeline.py --symbol SPY --month 2024-01 --timeframes 15s,1min,5min
        """
    )
    
    parser.add_argument('--symbol', required=True, help='Trading symbol (SPY, ES.v.0, etc.)')
    parser.add_argument('--month', required=True, help='Month to process (YYYY-MM)')
    parser.add_argument('--dataset', default='DBEQ.BASIC', help='Databento dataset (default: DBEQ.BASIC)')
    parser.add_argument('--timeframes', default='15s,30s,1min', help='Timeframes to aggregate (default: 15s,30s,1min)')
    parser.add_argument('--force', action='store_true', help='Force re-download')
    
    return parser.parse_args()


def main():
    """Run complete pipeline demo"""
    args = parse_arguments()
    
    # Parse month
    try:
        year, month = map(int, args.month.split('-'))
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year}-{month:02d}-31"
        else:
            # Last day of month
            from calendar import monthrange
            last_day = monthrange(year, month)[1]
            end_date = f"{year}-{month:02d}-{last_day}"
    except ValueError:
        logger.error("Invalid month format. Use YYYY-MM")
        sys.exit(1)
    
    # Load API key
    load_dotenv()
    api_key = os.getenv('DATABENTO_API_KEY')
    if not api_key:
        logger.error("DATABENTO_API_KEY not found. Create .env file with your API key")
        sys.exit(1)
    
    # Print header
    logger.info("=" * 70)
    logger.info("DATABENTO PIPELINE - COMPLETE DEMO")
    logger.info("=" * 70)
    logger.info(f"Symbol: {args.symbol}")
    logger.info(f"Month: {args.month}")
    logger.info(f"Dataset: {args.dataset}")
    logger.info(f"Timeframes: {args.timeframes}")
    logger.info(f"Timezone: UTC (all timestamps)")
    logger.info("=" * 70)
    
    # Directories
    raw_dir = 'data/raw_1s'
    agg_dir = 'data/aggregated'
    
    # STEP 1: Download
    logger.info("\n" + "=" * 70)
    logger.info("STEP 1: DOWNLOADING 1-SECOND DATA")
    logger.info("=" * 70)
    
    downloader = DatabentoDownloader(api_key, dataset=args.dataset)
    download_summary = downloader.download_range(
        symbol=args.symbol,
        start_date=start_date,
        end_date=end_date,
        output_dir=raw_dir,
        force=args.force
    )
    
    if download_summary.get('success', 0) == 0 and download_summary.get('skipped', 0) == 0:
        logger.error("Download failed. Check logs for details.")
        sys.exit(1)
    
    logger.info(f"✓ Downloaded/Skipped: {download_summary.get('success', 0) + download_summary.get('skipped', 0)} files")
    
    # STEP 2: Aggregate
    logger.info("\n" + "=" * 70)
    logger.info("STEP 2: AGGREGATING TO HIGHER TIMEFRAMES")
    logger.info("=" * 70)
    
    aggregator = OHLCVAggregator()
    timeframes = args.timeframes.split(',')
    
    agg_summary = aggregator.process_symbol(
        symbol=args.symbol,
        input_dir=raw_dir,
        output_dir=agg_dir,
        timeframes=timeframes
    )
    
    if agg_summary.get('failed', 0) > 0:
        logger.warning(f"Some aggregations failed. Check logs.")
    
    logger.info(f"✓ Aggregated: {agg_summary.get('success', 0)} files")
    
    # STEP 3: Validate
    logger.info("\n" + "=" * 70)
    logger.info("STEP 3: VALIDATING DATA INTEGRITY")
    logger.info("=" * 70)
    
    all_passed = True
    for timeframe in timeframes:
        logger.info(f"\nValidating {timeframe} bars...")
        
        validator = OHLCVValidator()
        tf_dir = Path(agg_dir) / timeframe
        
        if not tf_dir.exists():
            logger.warning(f"Directory not found: {tf_dir}")
            continue
        
        success = validator.validate_directory(
            directory=str(tf_dir),
            timeframe=timeframe,
            raw_data_dir=raw_dir
        )
        
        if success:
            logger.info(f"✓ {timeframe}: All validations passed")
        else:
            logger.error(f"✗ {timeframe}: Validation failed")
            logger.error(f"  Errors: {len(validator.errors)}")
            logger.error(f"  Warnings: {len(validator.warnings)}")
            all_passed = False
    
    # Final summary
    logger.info("\n" + "=" * 70)
    logger.info("DEMO COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Symbol: {args.symbol}")
    logger.info(f"Month: {args.month}")
    logger.info(f"Download: {download_summary.get('success', 0) + download_summary.get('skipped', 0)} files")
    logger.info(f"Aggregation: {agg_summary.get('success', 0)} files")
    logger.info(f"Validation: {'PASSED' if all_passed else 'FAILED (check logs)'}")
    logger.info("=" * 70)
    
    # Show file locations
    logger.info("\nGenerated Files:")
    logger.info(f"  Raw data: {raw_dir}/{args.symbol}/")
    for tf in timeframes:
        logger.info(f"  {tf} bars: {agg_dir}/{tf}/")
    logger.info(f"  Logs: logs/demo.log")
    
    logger.info("\n✓ Pipeline demo complete!")
    
    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
