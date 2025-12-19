#!/usr/bin/env python3
"""
Demo script for Massive.com pipeline
Shows how to download and aggregate SPY and QQQ data
"""
import subprocess
import sys
from datetime import datetime, timedelta

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n{'='*80}")
    print(f"{description}")
    print(f"{'='*80}")
    print(f"Command: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    if result.returncode != 0:
        print(f"\n❌ Error: Command failed with code {result.returncode}")
        return False
    
    print(f"\n✅ Success!")
    return True

def main():
    print("="*80)
    print("MASSIVE.COM PIPELINE DEMO")
    print("="*80)
    print()
    print("This demo will:")
    print("  1. Download SPY 1s bars for last year (2024)")
    print("  2. Download QQQ 1s bars for last year (2024)")
    print("  3. Aggregate both to 15s, 30s, 1min")
    print("  4. Validate the aggregated data")
    print()
    input("Press Enter to start...")
    
    # Calculate date range (last year = 2024)
    start_date = "2024-01-01"
    end_date = "2024-12-31"
    
    # Step 1: Download SPY
    if not run_command(
        [
            sys.executable,
            "scripts/fetch_1s_bars_massive.py",
            "--symbol", "SPY",
            "--start", start_date,
            "--end", end_date
        ],
        "Step 1/4: Downloading SPY 1s bars"
    ):
        sys.exit(1)
    
    # Step 2: Download QQQ
    if not run_command(
        [
            sys.executable,
            "scripts/fetch_1s_bars_massive.py",
            "--symbol", "QQQ",
            "--start", start_date,
            "--end", end_date
        ],
        "Step 2/4: Downloading QQQ 1s bars"
    ):
        sys.exit(1)
    
    # Step 3: Aggregate SPY
    if not run_command(
        [
            sys.executable,
            "scripts/resample_bars.py",
            "--symbol", "SPY",
            "--timeframes", "15s,30s,1min"
        ],
        "Step 3/4: Aggregating SPY to higher timeframes"
    ):
        sys.exit(1)
    
    # Step 4: Aggregate QQQ
    if not run_command(
        [
            sys.executable,
            "scripts/resample_bars.py",
            "--symbol", "QQQ",
            "--timeframes", "15s,30s,1min"
        ],
        "Step 4/4: Aggregating QQQ to higher timeframes"
    ):
        sys.exit(1)
    
    print("\n" + "="*80)
    print("DEMO COMPLETE!")
    print("="*80)
    print()
    print("Data has been downloaded and aggregated:")
    print("  📁 Raw 1s data: data/raw_1s/SPY/ and data/raw_1s/QQQ/")
    print("  📁 Aggregated:  data/aggregated/{15s,30s,1min}/")
    print()
    print("Next steps:")
    print("  - Run validation: python scripts/validate_bars.py --input_dir data/aggregated/1min --timeframe 1min")
    print("  - Compare native vs aggregated (optional)")
    print()

if __name__ == "__main__":
    main()
