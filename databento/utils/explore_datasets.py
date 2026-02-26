"""
Explore available datasets and their symbols
"""

import databento as db
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('DATABENTO_API_KEY')
client = db.Historical(api_key)

print("=" * 80)
print("DATABENTO DATASET & SCHEMA EXPLORER")
print("=" * 80)
print()

# List all datasets
datasets = client.metadata.list_datasets()
print(f"Total datasets available: {len(datasets)}")
print()

# Show details for each dataset
for dataset in datasets[:15]:
    print(f"Dataset: {dataset}")
    
    try:
        # Get schemas for this dataset
        schemas = client.metadata.list_schemas(dataset=dataset)
        print(f"  Schemas: {', '.join(schemas)}")
    except Exception as e:
        print(f"  Schemas: Unable to fetch - {str(e)[:50]}")
    
    print()

print("=" * 80)
print("RECOMMENDED DATASETS FOR COMMON INSTRUMENTS")
print("=" * 80)
print()

recommendations = {
    "CME Futures (ES, NQ, etc.)": ["GLBX.MDP3"],
    "US Equities (SPY, AAPL, etc.)": ["XNAS.ITCH", "XNYS.TRADES", "DBEQ.BASIC", "XCHI.TRADES"],
    "Options": ["OPRA.PILLAR"],
}

for instrument, dataset_list in recommendations.items():
    print(f"{instrument}:")
    for ds in dataset_list:
        if ds in datasets:
            print(f"  AVAILABLE: {ds}")
        else:
            print(f"  NOT AVAILABLE: {ds}")
    print()

print("=" * 80)
print("TESTING WITH DBEQ.BASIC (Databento Equities)")
print("=" * 80)
print()

# Try DBEQ.BASIC which should work for most accounts
try_dataset = "DBEQ.BASIC"
if try_dataset in datasets:
    print(f"SUCCESS: {try_dataset} is available!")
    print()
    print("Try this command:")
    print(f"  python scripts/fetch_1s_bars.py \\")
    print(f"    --symbol SPY \\")
    print(f"    --dataset {try_dataset} \\")
    print(f"    --start 2024-01-01 \\")
    print(f"    --end 2024-01-31")
    print()
else:
    print(f"WARNING: {try_dataset} not available")
    print()
    print("Available equity datasets:")
    equity_datasets = [d for d in datasets if any(x in d for x in ['XNAS', 'XNYS', 'DBEQ', 'EQUS'])]
    for ds in equity_datasets:
        print(f"  - {ds}")
