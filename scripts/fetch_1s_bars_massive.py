"""
Massive.com 1-Second OHLCV Downloader
Downloads monthly OHLCV data from Massive.com API with resume capability

Supports:
- Equities: SPY, QQQ, AAPL, etc.

Output format: Identical to Databento version
- CSV with columns: ts_event, open, high, low, close, volume
- Timezone: All timestamps are in UTC
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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/downloader_massive.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MassiveDownloader:
    """Handles downloading 1-second OHLCV data from Massive.com"""
    
    def __init__(self, api_key):
        """
        Initialize Massive.com client
        
        Args:
            api_key (str): Massive.com API key
        """
        self.client = RESTClient(api_key)
        logger.info("Massive.com client initialized")
    
    def download_month(self, symbol, year, month, output_dir, force=False):
        """
        Download 1-second OHLCV data for a specific month
        
        This function:
        1. Checks if the file already exists (resume-safe)
        2. Calls Massive.com API for the specified month
        3. Converts response to DataFrame matching Databento format
        4. Saves as CSV
        
        Args:
            symbol (str): Trading symbol (e.g., 'SPY', 'QQQ')
            year (int): Year (e.g., 2024)
            month (int): Month (1-12)
            output_dir (str): Output directory path
            force (bool): Force re-download if file exists
            
        Returns:
            dict: Result with status, file path, and row count
        """
        # Crear nombre de archivo
        filename = f"{symbol}_{year}_{month:02d}.csv"
        filepath = Path(output_dir) / symbol / filename
        
        # Check si ya existe
        if filepath.exists() and not force:
            logger.info(f"SKIP: {filename} (already exists)")
            return {'status': 'skipped', 'file': str(filepath)}
        
        # Crear directorio si no existe
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Calcular fechas del mes
            start = datetime(year, month, 1)
            if month == 12:
                end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
            else:
                end = datetime(year, month + 1, 1) - timedelta(seconds=1)
            
            start_str = start.strftime('%Y-%m-%d')
            end_str = end.strftime('%Y-%m-%d')
            
            logger.info(f"Downloading {symbol} for {year}-{month:02d}...")
            logger.info(f"Date range: {start_str} to {end_str}")
            
            # Llamar API de Massive.com para agregados de 1 segundo
            # timespan: "second", multiplier: 1 = 1-second bars
            aggs = []
            for agg in self.client.list_aggs(
                symbol,
                1,  # multiplier
                "second",  # timespan
                start_str,
                end_str,
                limit=50000
            ):
                aggs.append(agg)
            
            if not aggs:
                logger.warning(f"WARNING: No data returned for {filename}")
                return {'status': 'failed', 'error': 'No data', 'file': str(filepath)}
            
            # Convertir a DataFrame con formato Databento
            rows = []
            for agg in aggs:
                # Massive.com devuelve timestamp en milisegundos
                # Convertir a datetime UTC
                ts = pd.to_datetime(agg.timestamp, unit='ms', utc=True)
                
                rows.append({
                    'ts_event': ts,
                    'open': agg.open,
                    'high': agg.high,
                    'low': agg.low,
                    'close': agg.close,
                    'volume': agg.volume
                })
            
            df = pd.DataFrame(rows)
            df = df.set_index('ts_event')
            df = df.sort_index()
            
            # Guardar CSV (formato idéntico a Databento)
            df.to_csv(filepath, index=True)
            logger.info(f"SUCCESS: Saved {filename} ({len(df)} rows)")
            
            return {'status': 'success', 'file': str(filepath), 'rows': len(df)}
            
        except Exception as e:
            logger.error(f"ERROR: Failed to download {filename}: {str(e)}")
            return {'status': 'failed', 'error': str(e), 'file': str(filepath)}
    
    def download_range(self, symbol, start_date, end_date, output_dir, force=False):
        """
        Download data for a date range (iterates month by month)
        
        Args:
            symbol (str): Trading symbol
            start_date (str): Start date (YYYY-MM-DD)
            end_date (str): End date (YYYY-MM-DD)
            output_dir (str): Output directory path
            force (bool): Force re-download existing files
            
        Returns:
            dict: Summary of downloads (success/failed/skipped)
        """
        # Parse dates
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Initialize counters
        summary = {'success': 0, 'skipped': 0, 'failed': 0}
        
        # Iterate month by month
        current = start
        while current <= end:
            result = self.download_month(
                symbol=symbol,
                year=current.year,
                month=current.month,
                output_dir=output_dir,
                force=force
            )
            
            # Update counters
            summary[result['status']] += 1
            
            # Move to next month
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)
        
        return summary


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Download 1-second OHLCV data from Massive.com',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download SPY for January 2024
  python scripts/fetch_1s_bars_massive.py --symbol SPY --start 2024-01-01 --end 2024-01-31
  
  # Download full year for QQQ
  python scripts/fetch_1s_bars_massive.py --symbol QQQ --start 2024-01-01 --end 2024-12-31
  
  # Force re-download existing files
  python scripts/fetch_1s_bars_massive.py --symbol SPY --start 2024-01-01 --end 2024-01-31 --force
        """
    )
    
    parser.add_argument(
        '--symbol',
        type=str,
        required=True,
        help='Trading symbol (e.g., SPY, QQQ, AAPL)'
    )
    
    parser.add_argument(
        '--start',
        type=str,
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--end',
        type=str,
        required=True,
        help='End date (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--output_dir',
        type=str,
        default='data/raw_1s',
        help='Output directory (default: data/raw_1s)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-download existing files'
    )
    
    return parser.parse_args()


def main():
    """Main execution function"""
    # Parse arguments
    args = parse_arguments()
    
    # Load API key
    load_dotenv()
    api_key = os.getenv('MASSIVE_API_KEY')
    
    if not api_key:
        logger.error("MASSIVE_API_KEY not found in environment")
        logger.error("Please add to .env file: MASSIVE_API_KEY=your-api-key")
        sys.exit(1)
    
    # Initialize downloader
    downloader = MassiveDownloader(api_key)
    
    # Download data
    logger.info("=" * 60)
    logger.info(f"Starting download: {args.symbol} from {args.start} to {args.end}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Force re-download: {args.force}")
    logger.info("=" * 60)
    
    summary = downloader.download_range(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        output_dir=args.output_dir,
        force=args.force
    )
    
    # Print summary
    logger.info("=" * 60)
    logger.info("DOWNLOAD SUMMARY")
    logger.info(f"Successfully downloaded: {summary.get('success', 0)}")
    logger.info(f"Skipped (already exists): {summary.get('skipped', 0)}")
    logger.info(f"Failed: {summary.get('failed', 0)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
