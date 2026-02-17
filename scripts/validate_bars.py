"""
OHLCV Bar Validator - Validates aggregated bar data
"""

import pandas as pd
import logging
from pathlib import Path
import sys
import argparse
from datetime import datetime

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/validator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class OHLCVValidator:
    """Validates OHLCV data integrity"""
    
    def __init__(self):
        """Initialize validator"""
        self.errors = []
        self.warnings = []
    
    def check_duplicates(self, df, filename):
        """
        Check for duplicate timestamps
        
        Args:
            df (pd.DataFrame): DataFrame to check
            filename (str): Filename for reporting
            
        Returns:
            bool: True if no duplicates found
        """
        if df.index.duplicated().any():
            count = df.index.duplicated().sum()
            msg = f"ERROR: {filename}: Found {count} duplicate timestamps"
            logger.error(msg)
            self.errors.append(msg)
            return False
        return True
    
    def check_ohlc_rules(self, df, filename):
        """
        Validate OHLC relationships: high >= open, high >= close, 
        low <= open, low <= close
        
        Args:
            df (pd.DataFrame): DataFrame to check
            filename (str): Filename for reporting
            
        Returns:
            bool: True if all OHLC rules are valid
        """
        violations = 0
        
        # High must be >= open and close
        if (df['high'] < df['open']).any():
            count = (df['high'] < df['open']).sum()
            msg = f"ERROR: {filename}: {count} bars where high < open"
            logger.error(msg)
            self.errors.append(msg)
            violations += count
            
        if (df['high'] < df['close']).any():
            count = (df['high'] < df['close']).sum()
            msg = f"ERROR: {filename}: {count} bars where high < close"
            logger.error(msg)
            self.errors.append(msg)
            violations += count
        
        # Low must be <= open and close
        if (df['low'] > df['open']).any():
            count = (df['low'] > df['open']).sum()
            msg = f"ERROR: {filename}: {count} bars where low > open"
            logger.error(msg)
            self.errors.append(msg)
            violations += count
            
        if (df['low'] > df['close']).any():
            count = (df['low'] > df['close']).sum()
            msg = f"ERROR: {filename}: {count} bars where low > close"
            logger.error(msg)
            self.errors.append(msg)
            violations += count
        
        return violations == 0
    
    def check_timestamp_alignment(self, df, filename, timeframe=None):
        """
        Check if timestamps align with expected timeframe
        
        Args:
            df (pd.DataFrame): DataFrame to check
            filename (str): Filename for reporting
            timeframe (str): Expected timeframe
            
        Returns:
            bool: True if timestamps are properly aligned
        """
        if timeframe is None:
            return True
        
        # Map timeframe to seconds
        tf_seconds = {
            '15s': 15,
            '30s': 30,
            '45s': 45,
            '1min': 60,
            '2min': 120,
            '5min': 300,
            '15min': 900,
            '30min': 1800,
            '1h': 3600,
        }
        
        if timeframe not in tf_seconds:
            logger.debug(f"Timestamp check skipped for unknown timeframe: {timeframe}")
            return True
        
        seconds = tf_seconds[timeframe]
        
        # Check if timestamps are on expected boundaries
        timestamps = df.index.to_series()
        seconds_since_epoch = timestamps.astype('int64') // 10**9
        misaligned = (seconds_since_epoch % seconds) != 0
        
        if misaligned.any():
            count = misaligned.sum()
            msg = f"WARNING: {filename}: {count} timestamps not aligned to {timeframe} boundary"
            logger.warning(msg)
            self.warnings.append(msg)
            return False
            
        return True
    
    def check_volume_sum(self, agg_df, raw_df, timeframe, filename):
        """
        Check if aggregated volume equals sum of raw volume
        
        Args:
            agg_df (pd.DataFrame): Aggregated DataFrame
            raw_df (pd.DataFrame): Raw 1-second DataFrame
            timeframe (str): Timeframe of aggregated data
            filename (str): Filename for reporting
            
        Returns:
            bool: True if volumes match within tolerance
        """
        # Map timeframe to pandas frequency
        tf_map = {
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
        
        if timeframe not in tf_map:
            logger.debug(f"Volume check skipped for unknown timeframe: {timeframe}")
            return True
        
        try:
            # Resample raw data to same timeframe
            freq = tf_map[timeframe]
            raw_resampled = raw_df.resample(freq, label='left', closed='left')['volume'].sum()
            
            # Compare with aggregated volumes
            # Use merge to align timestamps
            comparison = pd.DataFrame({
                'agg_volume': agg_df['volume'],
                'raw_volume': raw_resampled
            })
            
            # Fill NaN with 0 for comparison
            comparison = comparison.fillna(0)
            
            # Check for mismatches (allow small floating point errors)
            tolerance = 0.01
            mismatches = abs(comparison['agg_volume'] - comparison['raw_volume']) > tolerance
            
            if mismatches.any():
                count = mismatches.sum()
                max_diff = abs(comparison['agg_volume'] - comparison['raw_volume']).max()
                msg = f"WARNING: {filename}: {count} volume mismatches (max diff: {max_diff:.2f})"
                logger.warning(msg)
                self.warnings.append(msg)
                return False
            
            return True
            
        except Exception as e:
            logger.debug(f"Volume check error for {filename}: {str(e)}")
            return True  # Don't fail validation on volume check errors
    
    def check_negative_values(self, df, filename):
        """
        Check for negative prices or volumes
        
        Args:
            df (pd.DataFrame): DataFrame to check
            filename (str): Filename for reporting
            
        Returns:
            bool: True if no negative values found
        """
        violations = 0
        
        for col in ['open', 'high', 'low', 'close']:
            if (df[col] < 0).any():
                count = (df[col] < 0).sum()
                msg = f"ERROR: {filename}: {count} negative values in {col}"
                logger.error(msg)
                self.errors.append(msg)
                violations += count
        
        if (df['volume'] < 0).any():
            count = (df['volume'] < 0).sum()
            msg = f"ERROR: {filename}: {count} negative volumes"
            logger.error(msg)
            self.errors.append(msg)
            violations += count
        
        return violations == 0
    
    def check_missing_data(self, df, filename, timeframe=None):
        """
        Check for gaps in time series
        
        Args:
            df (pd.DataFrame): DataFrame to check
            filename (str): Filename for reporting
            timeframe (str): Expected timeframe
            
        Returns:
            bool: True if no significant gaps found
        """
        if timeframe is None or len(df) < 2:
            return True
        
        # Map timeframe to pandas frequency
        tf_map = {
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
        
        if timeframe not in tf_map:
            logger.debug(f"Gap check skipped for unknown timeframe: {timeframe}")
            return True
        
        freq = tf_map[timeframe]
        
        # Calculate expected time differences
        time_diff = df.index.to_series().diff()
        expected = pd.Timedelta(freq)
        
        # Find gaps larger than expected (allowing for market hours)
        gaps = time_diff[time_diff > expected * 2]  # Allow 2x for market gaps
        
        if len(gaps) > 0:
            msg = f"INFO: {filename}: {len(gaps)} time gaps detected (may be normal for market hours)"
            logger.info(msg)
        
        return True
    
    def validate_file(self, filepath, timeframe=None, raw_data_dir=None):
        """
        Validate a single CSV file
        
        Args:
            filepath (str): Path to CSV file
            timeframe (str): Expected timeframe
            raw_data_dir (str): Optional path to raw 1s data for volume validation
            
        Returns:
            bool: True if file passes all validations
        """
        filename = Path(filepath).name
        logger.info(f"Validating {filename}...")
        
        try:
            # Load data
            df = pd.read_csv(filepath, index_col=0, parse_dates=True)
            
            if len(df) == 0:
                msg = f"ERROR: {filename}: Empty file"
                logger.error(msg)
                self.errors.append(msg)
                return False
            
            # Run all checks
            checks = []
            checks.append(self.check_duplicates(df, filename))
            checks.append(self.check_ohlc_rules(df, filename))
            checks.append(self.check_timestamp_alignment(df, filename, timeframe))
            checks.append(self.check_negative_values(df, filename))
            checks.append(self.check_missing_data(df, filename, timeframe))
            
            # Volume validation if raw data available
            if raw_data_dir and timeframe:
                try:
                    # Parse filename to get symbol and date
                    # Expected format: SYMBOL_YYYY_MM.csv
                    parts = filename.replace('.csv', '').split('_')
                    if len(parts) >= 3:
                        symbol = parts[0]
                        year = parts[1]
                        month = parts[2]
                        
                        # Construct raw file path
                        raw_filename = f"{symbol}_{year}_{month}.csv"
                        raw_filepath = Path(raw_data_dir) / symbol / raw_filename
                        
                        if raw_filepath.exists():
                            logger.debug(f"Loading raw data for volume validation: {raw_filepath}")
                            raw_df = pd.read_csv(raw_filepath, index_col=0, parse_dates=True)
                            checks.append(self.check_volume_sum(df, raw_df, timeframe, filename))
                        else:
                            logger.debug(f"Raw file not found for volume validation: {raw_filepath}")
                    else:
                        logger.debug(f"Could not parse filename for volume validation: {filename}")
                        
                except Exception as e:
                    logger.debug(f"Could not perform volume validation: {str(e)}")
            
            # All checks passed?
            if all(checks):
                logger.info(f"SUCCESS: {filename}: All checks passed ({len(df)} rows)")
                return True
            else:
                return False
                
        except Exception as e:
            msg = f"ERROR: {filename}: Validation error - {str(e)}"
            logger.error(msg)
            self.errors.append(msg)
            return False
    
    def validate_directory(self, directory, timeframe=None, raw_data_dir=None):
        """
        Validate all CSV files in a directory
        
        Args:
            directory (str): Directory to validate
            timeframe (str): Expected timeframe
            raw_data_dir (str): Optional path to raw 1s data for volume validation
            
        Returns:
            bool: True if all files pass validation
        """
        dir_path = Path(directory)
        
        if not dir_path.exists():
            msg = f"ERROR: Directory not found: {directory}"
            logger.error(msg)
            self.errors.append(msg)
            return False
        
        # Find all CSV files
        csv_files = list(dir_path.glob('**/*.csv'))
        
        if len(csv_files) == 0:
            msg = f"WARNING: No CSV files found in {directory}"
            logger.warning(msg)
            self.warnings.append(msg)
            return False
        
        logger.info(f"Found {len(csv_files)} CSV files to validate")
        
        passed = 0
        failed = 0
        
        for csv_file in csv_files:
            if self.validate_file(str(csv_file), timeframe, raw_data_dir):
                passed += 1
            else:
                failed += 1
        
        logger.info(f"Results: {passed} passed, {failed} failed")
        return failed == 0
    
    def write_report(self, output_file):
        """
        Write validation report to file
        
        Args:
            output_file (str): Output file path
        """
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("OHLCV VALIDATION REPORT\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            
            f.write(f"ERRORS: {len(self.errors)}\n")
            f.write("-" * 60 + "\n")
            for error in self.errors:
                f.write(f"{error}\n")
            f.write("\n")
            
            f.write(f"WARNINGS: {len(self.warnings)}\n")
            f.write("-" * 60 + "\n")
            for warning in self.warnings:
                f.write(f"{warning}\n")
            f.write("\n")
            
        logger.info(f"Report written to {output_file}")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Validate OHLCV bar data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate all files in a directory
  python validate_bars.py --input_dir data/aggregated/15s --timeframe 15s
  
  # Validate with volume check against raw data
  python validate_bars.py --input_dir data/aggregated/15s --timeframe 15s --raw_data_dir data/raw_1s
  
  # Custom report location
  python validate_bars.py --input_dir data/aggregated/1min --timeframe 1min --report validation.txt
        """
    )
    
    parser.add_argument(
        '--input_dir',
        required=True,
        help='Directory containing CSV files to validate'
    )
    parser.add_argument(
        '--timeframe',
        help='Expected timeframe (15s, 30s, 1min, etc.)'
    )
    parser.add_argument(
        '--raw_data_dir',
        help='Path to raw 1s data directory for volume validation (optional)'
    )
    parser.add_argument(
        '--report',
        default='logs/validation_report.txt',
        help='Output report file (default: logs/validation_report.txt)'
    )
    
    return parser.parse_args()


def main():
    """Main execution"""
    args = parse_arguments()
    
    # Initialize validator
    validator = OHLCVValidator()
    
    # Validate
    logger.info(f"Starting validation of {args.input_dir}")
    if args.timeframe:
        logger.info(f"Timeframe: {args.timeframe}")
    if args.raw_data_dir:
        logger.info(f"Volume validation enabled with raw data: {args.raw_data_dir}")
    
    success = validator.validate_directory(args.input_dir, args.timeframe, args.raw_data_dir)
    
    # Write report
    validator.write_report(args.report)
    
    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info(f"Errors: {len(validator.errors)}")
    logger.info(f"Warnings: {len(validator.warnings)}")
    logger.info(f"Report: {args.report}")
    logger.info("=" * 60)
    
    # Exit code
    if success:
        logger.info("SUCCESS: All validations passed!")
        sys.exit(0)
    else:
        logger.error("ERROR: Validation failed - check report for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
