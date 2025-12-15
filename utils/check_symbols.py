"""
Check available symbols and contracts in Databento
"""

import databento as db
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('DATABENTO_API_KEY')

if not api_key:
    print("ERROR: API key not found")
    exit(1)

client = db.Historical(api_key)

print("=" * 60)
print("DATABENTO SYMBOL CHECKER")
print("=" * 60)
print()

# Check datasets
print("Available datasets:")
datasets = client.metadata.list_datasets()
for ds in datasets[:10]:
    print(f"  - {ds}")
print()

# Information about symbol formats
print("Checking ES futures contracts...")
print()
print("For ES futures, you typically need to specify:")
print("  - Specific contract month: ESH4, ESM4, ESU4, ESZ4 (for 2024)")
print("  - Or use continuous contracts if available")
print()

print("Common ES contract formats:")
print("  - ESH24 (March 2024)")
print("  - ESM24 (June 2024)")  
print("  - ESU24 (September 2024)")
print("  - ESZ24 (December 2024)")
print()

print("For equities, use simple symbols:")
print("  - SPY")
print("  - AAPL")
print("  - MSFT")
print()

print("Try running:")
print("  python scripts/fetch_1s_bars.py --symbol ESH24 --dataset GLBX.MDP3 --start 2024-01-01 --end 2024-03-31")
print("  python scripts/fetch_1s_bars.py --symbol SPY --dataset DBEQ.BASIC --start 2024-01-01 --end 2024-01-31")
