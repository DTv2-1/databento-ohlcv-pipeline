"""
Analyze gaps in 1-second OHLCV data
"""

import pandas as pd
import sys
from pathlib import Path

def analyze_gaps(filepath):
    """Analyze time gaps in 1-second data"""
    print(f"Analyzing: {filepath}")
    print("=" * 60)
    
    # Load data
    df = pd.read_csv(filepath, index_col=0, parse_dates=True)
    print(f"Total rows: {len(df):,}")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    print(f"Duration: {df.index[-1] - df.index[0]}")
    
    # Calculate time differences
    time_diff = df.index.to_series().diff()
    
    # Expected is 1 second
    expected = pd.Timedelta('1s')
    
    # Find gaps
    gaps = time_diff[time_diff > expected]
    
    print(f"\n{'Gap Analysis':^60}")
    print("=" * 60)
    print(f"Total gaps found: {len(gaps):,}")
    
    if len(gaps) > 0:
        print(f"Smallest gap: {gaps.min()}")
        print(f"Largest gap: {gaps.max()}")
        print(f"Average gap: {gaps.mean()}")
        
        # Show first 10 gaps
        print(f"\nFirst 10 gaps:")
        print("-" * 60)
        for idx, gap in gaps.head(10).items():
            print(f"{idx}: {gap} (previous: {idx - gap})")
        
        # Gap size distribution
        print(f"\n{'Gap Size Distribution':^60}")
        print("-" * 60)
        gap_seconds = (gaps.dt.total_seconds()).astype(int)
        print(gap_seconds.value_counts().head(20))
        
        # Calculate missing seconds
        total_expected_seconds = (df.index[-1] - df.index[0]).total_seconds()
        actual_rows = len(df)
        missing_seconds = int(total_expected_seconds - actual_rows)
        
        print(f"\n{'Summary':^60}")
        print("=" * 60)
        print(f"Expected seconds (continuous): {int(total_expected_seconds):,}")
        print(f"Actual rows: {actual_rows:,}")
        print(f"Missing seconds: {missing_seconds:,} ({missing_seconds/total_expected_seconds*100:.1f}%)")
        
    else:
        print("No gaps found - data is continuous!")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_gaps.py <csv_file>")
        print("\nExample:")
        print("  python utils/analyze_gaps.py data/raw_1s/SPY/SPY_2024_01.csv")
        sys.exit(1)
    
    filepath = sys.argv[1]
    if not Path(filepath).exists():
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)
    
    analyze_gaps(filepath)
