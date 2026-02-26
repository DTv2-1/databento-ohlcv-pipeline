"""
Databento 1-Second OHLCV Downloader
Downloads monthly OHLCV data from Databento API with resume capability

Supports:
- Individual contracts: ESH24, NQM24, etc.
- Continuous contracts: ES.v.0, NQ.v.0, GC.v.0 (front month, auto-rolls)
- Equities: SPY, QQQ, AAPL, etc.

Timezone: All timestamps are in UTC
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import databento as db
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/downloader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DatabentoDownloader:
    """Handles downloading 1-second OHLCV data from Databento"""
    
    def __init__(self, api_key, dataset='GLBX.MDP3'):
        """
        Initialize Databento client
        
        Args:
            api_key (str): Databento API key
            dataset (str): Dataset to use (default: GLBX.MDP3)
        """
        self.client = db.Historical(api_key)
        self.dataset = dataset
        logger.info(f"Databento client initialized with dataset: {dataset}")
    
    def download_month(self, symbol, year, month, output_dir, force=False):
        """
        Download 1-second OHLCV data for a specific month
        
        This function:
        1. Checks if the file already exists (resume-safe)
        2. Calls Databento API for the specified month
        3. Converts response to DataFrame
        4. Saves as CSV
        
        Args:
            symbol (str): Trading symbol (e.g., 'ES', 'SPY')
            year (int): Year (e.g., 2024)
            month (int): Month (1-12)
            output_dir (str): Output directory path
            force (bool): Force re-download if file exists
            
        Returns:
            dict: Result with status, file path, and row count
            
        Example:
            >>> downloader.download_month('ES', 2024, 1, 'data/raw_1s')
            {'status': 'success', 'file': 'data/raw_1s/ES/ES_2024_01.csv', 'rows': 50000}
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
            
            logger.info(f"Downloading {symbol} for {year}-{month:02d}...")
            logger.info(f"Date range: {start.date()} to {end.date()}")
            
            # Detect continuous contracts (e.g., ES.v.0, NQ.v.0)
            stype_in = 'continuous' if '.v.' in symbol else 'raw_symbol'
            if stype_in == 'continuous':
                logger.info(f"Detected continuous contract: {symbol}")
            
            # Hacer request a Databento
            data = self.client.timeseries.get_range(
                dataset=self.dataset,
                symbols=[symbol],
                schema='ohlcv-1s',
                start=start.isoformat(),
                end=end.isoformat(),
                stype_in=stype_in,
            )
            
            # Convertir a DataFrame
            df = data.to_df()
            
            if df.empty:
                logger.warning(f"WARNING: No data returned for {filename}")
                return {'status': 'failed', 'error': 'No data', 'file': str(filepath)}
            
            # Guardar CSV
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
        description='Download 1-second OHLCV data from Databento',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download ES for January 2024
  python scripts/fetch_1s_bars.py --symbol ES --start 2024-01-01 --end 2024-01-31
  
  # Download full year with custom output
  python scripts/fetch_1s_bars.py --symbol SPY --start 2024-01-01 --end 2024-12-31 --output_dir data/raw_1s
  
  # Force re-download existing files
  python scripts/fetch_1s_bars.py --symbol ES --start 2024-01-01 --end 2024-01-31 --force
        """
    )
    
    parser.add_argument(
        '--symbol',
        type=str,
        required=True,
        help='Trading symbol (e.g., ES, SPY, QQQ)'
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
        '--dataset',
        type=str,
        default='GLBX.MDP3',
        help='Databento dataset (default: GLBX.MDP3)'
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
    api_key = os.getenv('DATABENTO_API_KEY')
    
    if not api_key:
        logger.error("DATABENTO_API_KEY not found in environment")
        logger.error("Please create a .env file with: DATABENTO_API_KEY=your-api-key")
        sys.exit(1)
    
    # Initialize downloader
    downloader = DatabentoDownloader(api_key, dataset=args.dataset)
    
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
