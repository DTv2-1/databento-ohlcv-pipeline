"""
OHLCV Aggregator - Resample 1-second bars to higher timeframes
Supports 15s, 30s, 1min and custom timeframes
"""

import os
import sys
import argparse
import logging
from pathlib import Path
import pandas as pd
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/aggregator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class OHLCVAggregator:
    """Resamples 1-second OHLCV data to higher timeframes"""
    
    # Map de timeframes legibles a pandas frequency
    TIMEFRAME_MAP = {
        '15s': '15s',
        '30s': '30s',
        '45s': '45s',
        '1min': '1min',
        '2min': '2min',
        '5min': '5min',
        '15min': '15min',
        '30min': '30min',
        '1h': '1h',
    }
    
    def __init__(self):
        """Initialize aggregator"""
        logger.info("OHLCV Aggregator initialized")
    
    def resample_ohlcv(self, df, timeframe):
        """
        Resample OHLCV data to specified timeframe
        
        Args:
            df (pd.DataFrame): Input DataFrame with OHLCV data
            timeframe (str): Target timeframe (e.g., '15s', '30s', '1min')
            
        Returns:
            pd.DataFrame: Resampled OHLCV data
            
        Raises:
            ValueError: If timeframe is not supported
        """
        # Validar que el timeframe esté soportado
        if timeframe not in self.TIMEFRAME_MAP:
            raise ValueError(
                f"Unsupported timeframe: {timeframe}. "
                f"Supported: {', '.join(self.TIMEFRAME_MAP.keys())}"
            )
        
        # Obtener frequency de pandas
        freq = self.TIMEFRAME_MAP[timeframe]
        
        try:
            # Asegurar que el índice sea datetime
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            
            # Definir reglas de agregación OHLCV
            agg_rules = {
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }
            
            # Resample
            resampled = df.resample(freq, label='left', closed='left').agg(agg_rules)
            
            # Count empty periods before dropping
            empty_periods = resampled['open'].isna().sum()
            
            # Eliminar filas con NaN (períodos sin datos)
            resampled = resampled.dropna()
            
            logger.debug(f"Resampled to {timeframe}: {len(df)} → {len(resampled)} rows "
                        f"({empty_periods} empty periods dropped)")
            
            return resampled
            
        except Exception as e:
            logger.error(f"Error resampling to {timeframe}: {str(e)}")
            raise
    
    def process_file(self, input_file, output_dir, timeframes):
        """
        Process a single 1-second CSV file
        
        Args:
            input_file (str): Path to input CSV
            output_dir (str): Output directory
            timeframes (list): List of timeframes to generate
            
        Returns:
            dict: Processing results
        """
        input_path = Path(input_file)
        
        if not input_path.exists():
            logger.error(f"File not found: {input_file}")
            return {'status': 'failed', 'error': 'File not found'}
        
        try:
            # Leer CSV
            logger.info(f"Reading {input_path.name}...")
            df = pd.read_csv(input_file, index_col=0, parse_dates=True)
            
            # Validar columnas OHLCV
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                logger.error(f"Missing columns in {input_path.name}: {missing_cols}")
                return {'status': 'failed', 'error': f'Missing columns: {missing_cols}'}
            
            results = []
            
            # Procesar cada timeframe
            for tf in timeframes:
                try:
                    # Resample
                    resampled = self.resample_ohlcv(df, tf)
                    
                    # Crear nombre de archivo output
                    # Input: ES_2024_01.csv → Output: ES_2024_01_15s.csv
                    base_name = input_path.stem  # ES_2024_01
                    output_filename = f"{base_name}_{tf}.csv"
                    
                    # Crear directorio de output
                    output_path = Path(output_dir) / tf / output_filename
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Guardar
                    resampled.to_csv(output_path, index=True)
                    logger.info(f"SUCCESS: Saved {output_filename} ({len(resampled)} rows)")
                    
                    results.append({
                        'timeframe': tf,
                        'status': 'success',
                        'rows': len(resampled),
                        'file': str(output_path)
                    })
                    
                except Exception as e:
                    logger.error(f"ERROR: Failed to process {tf}: {str(e)}")
                    results.append({
                        'timeframe': tf,
                        'status': 'failed',
                        'error': str(e)
                    })
            
            return {'status': 'success', 'results': results}
            
        except Exception as e:
            logger.error(f"❌ Error processing {input_path.name}: {str(e)}")
            return {'status': 'failed', 'error': str(e)}
    
    def process_symbol(self, symbol, input_dir, output_dir, timeframes):
        """
        Process all files for a symbol
        
        Args:
            symbol (str): Trading symbol
            input_dir (str): Input directory with 1s data
            output_dir (str): Output directory
            timeframes (list): List of timeframes
            
        Returns:
            dict: Summary of processing
        """
        # Encontrar todos los CSVs del símbolo
        symbol_dir = Path(input_dir) / symbol
        
        if not symbol_dir.exists():
            logger.error(f"Symbol directory not found: {symbol_dir}")
            return {'processed': 0, 'failed': 1, 'timeframes_created': 0}
        
        csv_files = sorted(symbol_dir.glob('*.csv'))
        
        if not csv_files:
            logger.warning(f"No CSV files found in {symbol_dir}")
            return {'processed': 0, 'failed': 0, 'timeframes_created': 0}
        
        logger.info(f"Found {len(csv_files)} files to process")
        
        # Counters
        processed = 0
        failed = 0
        timeframes_created = 0
        
        # Procesar cada archivo
        for csv_file in csv_files:
            result = self.process_file(
                input_file=str(csv_file),
                output_dir=output_dir,
                timeframes=timeframes
            )
            
            if result['status'] == 'success':
                processed += 1
                # Contar timeframes exitosos
                for r in result['results']:
                    if r['status'] == 'success':
                        timeframes_created += 1
            else:
                failed += 1
        
        return {
            'processed': processed,
            'failed': failed,
            'timeframes_created': timeframes_created
        }


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Aggregate 1-second OHLCV to higher timeframes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Aggregate ES data to default timeframes (15s, 30s, 1min)
  python scripts/resample_bars.py --symbol ES
  
  # Aggregate to specific timeframes
  python scripts/resample_bars.py --symbol SPY --timeframes 15s,1min,5min
  
  # Custom input/output directories
  python scripts/resample_bars.py --symbol ES --input_dir data/raw_1s --output_dir data/aggregated
  
Supported timeframes: 15s, 30s, 45s, 1min, 2min, 5min, 15min, 30min, 1h
        """
    )
    
    parser.add_argument(
        '--symbol',
        type=str,
        required=True,
        help='Trading symbol'
    )
    
    parser.add_argument(
        '--input_dir',
        type=str,
        default='data/raw_1s',
        help='Input directory with 1s data (default: data/raw_1s)'
    )
    
    parser.add_argument(
        '--output_dir',
        type=str,
        default='data/aggregated',
        help='Output directory (default: data/aggregated)'
    )
    
    parser.add_argument(
        '--timeframes',
        type=str,
        default='15s,30s,1min',
        help='Comma-separated timeframes (default: 15s,30s,1min)'
    )
    
    return parser.parse_args()


def main():
    """Main execution"""
    args = parse_arguments()
    
    # Parse timeframes
    timeframes = [tf.strip() for tf in args.timeframes.split(',')]
    
    # Validate timeframes
    aggregator = OHLCVAggregator()
    invalid_tf = [tf for tf in timeframes if tf not in aggregator.TIMEFRAME_MAP]
    if invalid_tf:
        logger.error(f"Invalid timeframes: {invalid_tf}")
        logger.error(f"Supported: {', '.join(aggregator.TIMEFRAME_MAP.keys())}")
        sys.exit(1)
    
    # Process symbol
    logger.info("=" * 60)
    logger.info(f"Processing {args.symbol} for timeframes: {timeframes}")
    logger.info(f"Input: {args.input_dir}")
    logger.info(f"Output: {args.output_dir}")
    logger.info("=" * 60)
    
    summary = aggregator.process_symbol(
        symbol=args.symbol,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        timeframes=timeframes
    )
    
    # Print summary
    logger.info("=" * 60)
    logger.info("AGGREGATION SUMMARY")
    logger.info(f"Files processed: {summary.get('processed', 0)}")
    logger.info(f"Timeframes generated: {summary.get('timeframes_created', 0)}")
    logger.info(f"Failed: {summary.get('failed', 0)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
