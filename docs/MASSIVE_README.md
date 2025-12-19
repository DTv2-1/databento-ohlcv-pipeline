# Massive.com OHLCV Pipeline

Fork of the Databento OHLCV pipeline adapted for Massive.com API.

## Overview

This script downloads 1-second OHLCV bars from Massive.com and outputs them in **identical format** to the Databento version, making them compatible with the same aggregation and validation scripts.

## What's Different from Databento Version?

### API Source
- **Databento version**: Uses `databento` Python library
- **Massive version**: Uses `massive` Python library (formerly Polygon.io)

### Data Access
- **Databento**: Requires dataset selection (DBEQ.BASIC, GLBX.MDP3)
- **Massive**: Single API for all US stocks

### Output Format
Both versions produce **identical CSV format**:
```
ts_event,open,high,low,close,volume
2024-01-02 09:30:00+00:00,475.32,475.45,475.28,475.40,15234
2024-01-02 09:30:01+00:00,475.40,475.52,475.38,475.50,8956
...
```

## Setup

### 1. Install Dependencies

```bash
pip install massive pandas python-dotenv
```

### 2. Get API Key

1. Sign up at [https://massive.com/dashboard](https://massive.com/dashboard)
2. Navigate to API Keys section
3. Create a new API key
4. Copy your API key

**Note**: You need at least **Stocks Starter** plan ($29/month) to access 1-second aggregates.

### 3. Configure Environment

Add to your `.env` file:
```bash
MASSIVE_API_KEY=your_api_key_here
```

## Usage

### Download 1-Second Bars

```bash
# Download SPY for last year (2024)
python scripts/fetch_1s_bars_massive.py \
  --symbol SPY \
  --start 2024-01-01 \
  --end 2024-12-31

# Download QQQ for specific month
python scripts/fetch_1s_bars_massive.py \
  --symbol QQQ \
  --start 2024-06-01 \
  --end 2024-06-30
```

### Aggregate to Higher Timeframes

Once you have the 1s data, use the **same aggregation script** as Databento:

```bash
# Aggregate SPY to 15s, 30s, 1min
python scripts/resample_bars.py --symbol SPY --timeframes 15s,30s,1min
```

### Validate Data

Use the **same validation script**:

```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/1min \
  --timeframe 1min \
  --raw_data_dir data/raw_1s
```

## Command Line Options

```
--symbol SYMBOL       Trading symbol (e.g., SPY, QQQ, AAPL)
--start START         Start date (YYYY-MM-DD)
--end END             End date (YYYY-MM-DD)
--output_dir DIR      Output directory (default: data/raw_1s)
--force               Force re-download existing files
```

## Data Coverage

### Massive.com Data Availability

- **Stocks**: 20+ years of historical data (depending on plan)
- **Granularity**: 
  - 1-second bars ✅ (requires Stocks Starter or higher)
  - 1-minute bars ✅ (all plans)
  - Daily bars ✅ (all plans)

### Subscription Tiers

| Plan | 1s Bars | Historical | Price/month |
|------|---------|------------|-------------|
| Basic | ❌ | 2 years | $0 |
| Starter | ✅ | 5 years | $29 |
| Developer | ✅ | 10 years | $79 |
| Advanced | ✅ | 20+ years | $199 |

## Examples

### Download Full Year for SPY and QQQ

```bash
# SPY
python scripts/fetch_1s_bars_massive.py \
  --symbol SPY \
  --start 2024-01-01 \
  --end 2024-12-31

# QQQ
python scripts/fetch_1s_bars_massive.py \
  --symbol QQQ \
  --start 2024-01-01 \
  --end 2024-12-31

# Aggregate both
python scripts/resample_bars.py --symbol SPY --timeframes 15s,30s,1min
python scripts/resample_bars.py --symbol QQQ --timeframes 15s,30s,1min
```

## Output Structure

```
data/
├── raw_1s/                      # 1-second bars from Massive.com
│   ├── SPY/
│   │   ├── SPY_2024_01.csv
│   │   ├── SPY_2024_02.csv
│   │   └── ...
│   └── QQQ/
│       ├── QQQ_2024_01.csv
│       └── ...
└── aggregated/                   # Higher timeframes
    ├── 15s/
    │   ├── SPY_2024_01_15s.csv
    │   └── ...
    ├── 30s/
    │   └── ...
    └── 1min/
        └── ...
```

## Timezone

All timestamps are in **UTC** (same as Databento version).

If you need exchange local time:
```python
import pandas as pd
df = pd.read_csv('SPY_2024_01.csv', index_col='ts_event', parse_dates=True)
df.index = df.index.tz_convert('America/New_York')  # Eastern Time
```

## Troubleshooting

### "MASSIVE_API_KEY not found"
- Check that `.env` file exists in project root
- Verify the key is correctly formatted: `MASSIVE_API_KEY=your_key_here`

### "No data returned"
- Verify your subscription includes 1-second bars
- Check if the symbol is valid (US stocks only)
- Ensure date range is within your plan's historical coverage

### "Rate limit exceeded"
- Massive.com has rate limits per plan
- Add delays between requests if needed
- Consider upgrading your plan

## Comparison with Databento Version

| Feature | Databento | Massive.com |
|---------|-----------|-------------|
| Data source | Databento | Massive.com (ex-Polygon.io) |
| Markets | Stocks, Futures, Options | Stocks, Options, Forex, Crypto, Futures |
| 1s bars | ✅ OHLCV-1s schema | ✅ Second aggregates |
| Output format | CSV with UTC timestamps | **Identical** |
| Continuous contracts | ✅ ES.v.0, NQ.v.0 | ❌ Not applicable (stocks only) |
| Resume capability | ✅ | ✅ |
| Python library | `databento` | `massive` |

## Next Steps

After downloading data from Massive.com, the workflow is **identical** to Databento:

1. ✅ Download 1s bars → `fetch_1s_bars_massive.py`
2. ✅ Aggregate → `resample_bars.py` (same script)
3. ✅ Validate → `validate_bars.py` (same script)

## Support

For Massive.com API issues:
- Docs: https://massive.com/docs
- Support: https://massive.com/contact

For pipeline issues:
- GitHub: https://github.com/1di210299/databento-ohlcv-pipeline
