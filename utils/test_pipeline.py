"""
Complete Pipeline Test Suite
Tests download, aggregation, and validation
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run shell command and return status"""
    print("\n" + "=" * 60)
    print(f"TEST: {description}")
    print("=" * 60)
    print(f"Command: {cmd}")
    print()
    
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode == 0:
        print(f"SUCCESS: {description}")
        return True
    else:
        print(f"ERROR: {description} - FAILED")
        return False


def check_files_exist(pattern, description):
    """Check if files matching pattern exist"""
    files = list(Path('.').glob(pattern))
    if files:
        print(f"SUCCESS: {description}: Found {len(files)} files")
        return True
    else:
        print(f"ERROR: {description}: No files found")
        return False


def test_pipeline():
    """Complete pipeline test"""
    
    print("=" * 60)
    print("DATABENTO PIPELINE - COMPREHENSIVE TEST SUITE")
    print("=" * 60)
    print()
    print("NOTE: This test requires a valid DATABENTO_API_KEY")
    print("NOTE: Test will download ~2 months of SPY data")
    print()
    
    # Check if API key is set
    api_key = os.getenv('DATABENTO_API_KEY')
    if not api_key:
        print("ERROR: DATABENTO_API_KEY not found in environment")
        print("Please set it with: export DATABENTO_API_KEY='your-key'")
        return False
    
    print(f"API key found: {api_key[:10]}...")
    
    results = []
    
    # Test 0: Connection test
    results.append(run_command(
        "python utils/test_connection.py",
        "API Connection"
    ))
    
    if not results[-1]:
        print("\nERROR: Connection test failed. Cannot proceed.")
        return False
    
    # Test 1: Download 2 months
    results.append(run_command(
        """python scripts/fetch_1s_bars.py \
            --symbol SPY \
            --dataset DBEQ.BASIC \
            --start 2024-01-01 \
            --end 2024-02-29 \
            --output_dir data/raw_1s""",
        "Download 1-second data (2 months)"
    ))
    
    # Check downloaded files
    results.append(check_files_exist(
        "data/raw_1s/SPY/*.csv",
        "Verify downloaded files"
    ))
    
    # Test 2: Resume capability (should skip existing)
    results.append(run_command(
        """python scripts/fetch_1s_bars.py \
            --symbol SPY \
            --dataset DBEQ.BASIC \
            --start 2024-01-01 \
            --end 2024-02-29 \
            --output_dir data/raw_1s""",
        "Resume capability (should skip existing)"
    ))
    
    # Test 3: Aggregate to timeframes
    results.append(run_command(
        """python scripts/resample_bars.py \
            --symbol SPY \
            --input_dir data/raw_1s \
            --output_dir data/aggregated \
            --timeframes 15s,30s,1min""",
        "Aggregate to higher timeframes"
    ))
    
    # Check aggregated files
    for tf in ['15s', '30s', '1min']:
        results.append(check_files_exist(
            f"data/aggregated/{tf}/*.csv",
            f"Verify {tf} files"
        ))
    
    # Test 4: Validate each timeframe
    for tf in ['15s', '30s', '1min']:
        results.append(run_command(
            f"""python scripts/validate_bars.py \
                --input_dir data/aggregated/{tf} \
                --timeframe {tf} \
                --report logs/validation_{tf}.txt""",
            f"Validate {tf} data"
        ))
    
    # Test 5: Force re-download
    results.append(run_command(
        """python scripts/fetch_1s_bars.py \
            --symbol SPY \
            --dataset DBEQ.BASIC \
            --start 2024-01-01 \
            --end 2024-01-31 \
            --output_dir data/raw_1s \
            --force""",
        "Force re-download (overwrite)"
    ))
    
    # Test 6: Custom timeframe aggregation
    results.append(run_command(
        """python scripts/resample_bars.py \
            --symbol SPY \
            --timeframes 45s,5min""",
        "Custom timeframes (45s, 5min)"
    ))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success rate: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\nSUCCESS: ALL TESTS PASSED!")
        print("\nPipeline is ready for production use!")
        return True
    else:
        print("\nERROR: SOME TESTS FAILED")
        print("\nCheck logs for details:")
        print("  - logs/downloader.log")
        print("  - logs/aggregator.log")
        print("  - logs/validator.log")
        return False


if __name__ == "__main__":
    try:
        success = test_pipeline()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nWARNING: Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: Test suite error: {str(e)}")
        sys.exit(1)
