#!/usr/bin/env python3
"""
Bulk aggregation script for GC.v.0 - Process all 24 months at once
"""
import subprocess
import sys
from pathlib import Path
import time

def main():
    print("=" * 80)
    print("BULK AGGREGATION: GC.v.0 - 24 Months")
    print("=" * 80)
    
    # Find all GC CSV files
    raw_dir = Path("data/raw_1s/GC.v.0")
    csv_files = sorted(raw_dir.glob("GC.v.0_*.csv"))
    
    print(f"\nFound {len(csv_files)} CSV files to process")
    print(f"Files: {csv_files[0].name} to {csv_files[-1].name}")
    
    # Process each timeframe
    timeframes = ['15s', '30s', '1min']
    
    total_start = time.time()
    
    for tf in timeframes:
        print(f"\n{'='*80}")
        print(f"Processing timeframe: {tf}")
        print(f"{'='*80}")
        
        tf_start = time.time()
        success_count = 0
        error_count = 0
        
        for csv_file in csv_files:
            print(f"\nProcessing: {csv_file.name} -> {tf}")
            
            cmd = [
                sys.executable,
                "scripts/resample_bars.py",
                str(csv_file),
                tf
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )
                print(f"✓ Success: {csv_file.name}")
                success_count += 1
                
                # Print key stats from output
                for line in result.stdout.split('\n'):
                    if 'rows' in line.lower() or 'aggregated' in line.lower():
                        print(f"  {line.strip()}")
                        
            except subprocess.CalledProcessError as e:
                print(f"✗ ERROR: {csv_file.name}")
                print(f"  {e.stderr}")
                error_count += 1
        
        tf_elapsed = time.time() - tf_start
        print(f"\n{tf} Summary:")
        print(f"  Success: {success_count}/{len(csv_files)}")
        print(f"  Errors: {error_count}")
        print(f"  Time: {tf_elapsed:.1f}s")
    
    total_elapsed = time.time() - total_start
    
    print(f"\n{'='*80}")
    print(f"BULK AGGREGATION COMPLETE")
    print(f"{'='*80}")
    print(f"Total files processed: {len(csv_files)}")
    print(f"Timeframes: {', '.join(timeframes)}")
    print(f"Total time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} minutes)")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
