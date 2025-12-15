# Databento OHLCV Pipeline

Professional toolset for downloading and aggregating 1-second OHLCV data from Databento.

## 📋 Table of Contents
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Download 1-Second Data](#download-1-second-data)
  - [Aggregate to Higher Timeframes](#aggregate-to-higher-timeframes)
  - [Validate Data](#validate-data)
- [Directory Structure](#directory-structure)
- [Adding New Timeframes](#adding-new-timeframes)
- [Troubleshooting](#troubleshooting)

---

## 🔧 Requirements

- **Python**: 3.9 or higher
- **Operating System**: macOS, Linux, or Windows
- **Databento Account**: Active account with API access

---

## 📦 Installation

### Step 1: Navigate to Project Directory
```bash
cd databento-pipeline
```

### Step 2: Create Virtual Environment (Recommended)
```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# OR
.\venv\Scripts\activate  # Windows
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Verify Installation
```bash
python test_connection.py
```

---

## ⚙️ Configuration

### Set Databento API Key

**Option 1: Environment Variable (Recommended)**
```bash
export DATABENTO_API_KEY='your-api-key-here'
```

**Option 2: .env File**
```bash
# Create .env file in project root
echo "DATABENTO_API_KEY=your-api-key-here" > .env
```

**Option 3: Direct in Shell**
```bash
# For one-time use
DATABENTO_API_KEY='your-key' python scripts/fetch_1s_bars.py ...
```

---

## 🚀 Usage

### Download 1-Second Data

**Basic Usage:**
```bash
# For US Equities (SPY, AAPL, etc.)
python scripts/fetch_1s_bars.py \
  --symbol SPY \
  --dataset DBEQ.BASIC \
  --start 2024-01-01 \
  --end 2024-12-31

# For CME Futures (ES, NQ, etc.) - use specific contract
python scripts/fetch_1s_bars.py \
  --symbol ESH24 \
  --dataset GLBX.MDP3 \
  --start 2024-01-01 \
  --end 2024-03-31
```

**Parameters:**
- `--symbol`: Trading symbol (e.g., SPY, AAPL for equities; ESH24, NQM24 for futures)
- `--dataset`: Databento dataset (DBEQ.BASIC for equities, GLBX.MDP3 for CME futures)
- `--start`: Start date (YYYY-MM-DD)
- `--end`: End date (YYYY-MM-DD)
- `--output_dir`: Output directory (default: data/raw_1s)
- `--force`: Force re-download existing files (optional)

**Common Datasets:**
- `DBEQ.BASIC` - US Equities (SPY, AAPL, MSFT, etc.)
- `GLBX.MDP3` - CME Futures (ESH24, NQM24, etc.)
- `XNAS.ITCH` - NASDAQ equities
- `OPRA.PILLAR` - US Options

**Examples:**

Download SPY for 2024:
```bash
python scripts/fetch_1s_bars.py \
  --symbol SPY \
  --dataset DBEQ.BASIC \
  --start 2024-01-01 \
  --end 2024-12-31
```

Download multiple months with resume capability:
```bash
# First run - downloads 6 months
python scripts/fetch_1s_bars.py \
  --symbol QQQ \
  --start 2023-01-01 \
  --end 2023-06-30

# Second run - downloads remaining 6 months (skips already downloaded)
python scripts/fetch_1s_bars.py \
  --symbol QQQ \
  --start 2023-01-01 \
  --end 2023-12-31
```

Force re-download (overwrite existing files):
```bash
python scripts/fetch_1s_bars.py \
  --symbol ES \
  --start 2024-01-01 \
  --end 2024-01-31 \
  --force
```

---

### Aggregate to Higher Timeframes

**Basic Usage:**
```bash
python scripts/resample_bars.py \
  --symbol ES \
  --input_dir data/raw_1s \
  --output_dir data/aggregated \
  --timeframes 15s,30s,1min
```

**Parameters:**
- `--symbol`: Trading symbol
- `--input_dir`: Directory with 1-second CSV files (default: data/raw_1s)
- `--output_dir`: Output directory (default: data/aggregated)
- `--timeframes`: Comma-separated timeframes (default: 15s,30s,1min)

**Supported Timeframes:**
- `15s`, `30s`, `45s` - Seconds
- `1min`, `2min`, `5min`, `15min`, `30min` - Minutes
- `1h` - Hours

**Examples:**

Aggregate SPY to default timeframes:
```bash
python scripts/resample_bars.py --symbol SPY
```

Generate only specific timeframes:
```bash
python scripts/resample_bars.py \
  --symbol ES \
  --timeframes 15s,1min,5min
```

Aggregate to 45-second bars:
```bash
python scripts/resample_bars.py \
  --symbol ES \
  --timeframes 45s
```

---

### Validate Data

**Basic Usage:**
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s \
  --report logs/validation_15s.txt
```

**Parameters:**
- `--input_dir`: Directory with CSV files to validate
- `--timeframe`: Timeframe for alignment check (optional)
- `--raw_data_dir`: Path to raw 1s data for volume validation (optional)
- `--report`: Output report file (default: logs/validation_report.txt)

**Validation Checks:**
1. ✅ No duplicate timestamps
2. ✅ OHLC rules (high >= open/close, low <= open/close, high >= low)
3. ✅ No negative values
4. ✅ No missing data (NaN)
5. ✅ Timestamp alignment to timeframe boundaries
6. ✅ Volume sum validation (aggregated volume = sum of raw volumes)

**Examples:**

Validate all 15-second bars:
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s
```

Validate with volume check against raw data:
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s \
  --raw_data_dir data/raw_1s
```

Validate 1-minute bars:
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/1min \
  --timeframe 1min
```

Validate without timeframe alignment check:
```bash
python scripts/validate_bars.py \
  --input_dir data/raw_1s/ES
```

---

## 📁 Directory Structure

```
databento-pipeline/
├── scripts/
│   ├── fetch_1s_bars.py      # Download 1-second data
│   ├── resample_bars.py       # Aggregate to higher timeframes
│   └── validate_bars.py       # Validate data integrity
│
├── data/
│   ├── raw_1s/                # Downloaded 1-second data
│   │   ├── ES/
│   │   │   ├── ES_2024_01.csv
│   │   │   ├── ES_2024_02.csv
│   │   │   └── ...
│   │   ├── SPY/
│   │   └── QQQ/
│   │
│   └── aggregated/            # Aggregated data
│       ├── 15s/
│       │   ├── ES_2024_01_15s.csv
│       │   └── ...
│       ├── 30s/
│       └── 1min/
│
├── logs/                      # Log files
│   ├── downloader.log
│   ├── aggregator.log
│   ├── validator.log
│   └── validation_report.txt
│
├── test_connection.py         # API connection test
├── requirements.txt           # Python dependencies
├── .env                       # API key (create this)
├── .env.example              # API key template
└── README.md                  # This file
```

---

## 🔧 Adding New Timeframes

Want to add a new timeframe like 2 minutes or 1 hour?

### Step 1: Check if Already Supported

The following timeframes are already built-in:
- `15s`, `30s`, `45s`
- `1min`, `2min`, `5min`, `15min`, `30min`
- `1h`

### Step 2: Add Custom Timeframe (if needed)

Edit `scripts/resample_bars.py` at line ~30:

```python
TIMEFRAME_MAP = {
    '15s': '15S',
    '30s': '30S',
    '1min': '1T',
    '45s': '45S',
    '2min': '2T',    # Already included
    '3min': '3T',    # ← Add custom timeframe
    '10min': '10T',  # ← Add custom timeframe
}
```

### Step 3: Run Aggregation

```bash
python scripts/resample_bars.py \
  --symbol ES \
  --timeframes 3min,10min
```

### Step 4: Validate (Optional)

```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/3min \
  --timeframe 3min
```

**That's it!** The new timeframe is now available.

---

## 🔍 Troubleshooting

### Error: "DATABENTO_API_KEY not found"

**Problem:** API key not set in environment.

**Solution:**
```bash
# Check if key is set
echo $DATABENTO_API_KEY

# If empty, set it
export DATABENTO_API_KEY='your-key-here'

# Or use .env file
echo "DATABENTO_API_KEY=your-key" > .env
```

---

### Error: "No module named 'databento'"

**Problem:** Dependencies not installed.

**Solution:**
```bash
# Activate virtual environment first
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

### Warning: "No data returned for month"

**Problem:** Databento has no data for that symbol/date range.

**Possible Causes:**
- Symbol not available for that date
- Wrong dataset selected
- Market was closed (holidays)
- Date is in the future

**Solution:**
- Verify symbol is correct
- Check Databento documentation for data availability
- Try a different date range
- Try a different dataset with `--dataset` parameter

---

### Error: "Permission denied" when writing files

**Problem:** No write permissions for output directory.

**Solution:**
```bash
# Create directories with correct permissions
mkdir -p data/raw_1s data/aggregated logs
chmod 755 data data/raw_1s data/aggregated logs
```

---

### Files are not being skipped (resume not working)

**Problem:** Resume logic not detecting existing files.

**Possible causes:**
- Files in wrong directory
- Filename format mismatch

**Solution:**
```bash
# Check existing files
ls -lh data/raw_1s/ES/

# Expected format: ES_2024_01.csv
# If files are named differently, they won't be detected

# Force re-download if needed
python scripts/fetch_1s_bars.py ... --force
```

---

### Aggregated data looks wrong

**Problem:** OHLCV aggregation producing unexpected results.

**Solution:**
1. Check input data:
```bash
head -20 data/raw_1s/ES/ES_2024_01.csv
```

2. Run validation:
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s
```

3. Check logs:
```bash
cat logs/aggregator.log
cat logs/validation_report.txt
```

---

### Validation errors: "high < low" or similar

**Problem:** Data integrity issues in OHLCV data.

**Possible causes:**
- Corrupted download
- API returned bad data
- Data processing error

**Solution:**
1. Re-download the affected month:
```bash
python scripts/fetch_1s_bars.py \
  --symbol ES \
  --start 2024-01-01 \
  --end 2024-01-31 \
  --force
```

2. Re-aggregate:
```bash
python scripts/resample_bars.py --symbol ES
```

3. Validate again:
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s
```

---

### Common Pandas/Python Issues

**Problem:** "ValueError: time data does not match format"

**Solution:** Ensure timestamp column is in ISO format (YYYY-MM-DD HH:MM:SS)

**Problem:** "Memory error" when processing large files

**Solution:** Process files one at a time or increase system memory

**Problem:** "ImportError: No module named 'pandas'"

**Solution:** Activate virtual environment and install dependencies:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## ⏱️ Expected Runtime Notes

**Download times** (approximate, per symbol per month):
- 1-second data: 30-60 seconds (depending on network and API)
- For 12 months: ~10-15 minutes per symbol
- For 60 months (5 years): ~45-75 minutes per symbol

**Aggregation times** (per month):
- 15s bars: 2-5 seconds
- 30s bars: 2-5 seconds
- 1min bars: 2-5 seconds
- For 12 months: ~1-2 minutes per symbol
- For 60 months: ~5-10 minutes per symbol

**Validation times** (per timeframe):
- ~1-2 seconds per file
- For 12 files: ~15-30 seconds
- For 60 files: ~2-3 minutes

**Total pipeline** (download + aggregate + validate):
- Single symbol, 12 months: ~15-20 minutes
- Single symbol, 60 months: ~60-90 minutes
- Multiple symbols: scale linearly

---

## 🔄 Complete Workflow Example

Here's a complete workflow from download to validation:

```bash
# 1. Test connection first
python test_connection.py

# 2. Download 1-second data for ES (Jan-Dec 2024)
python scripts/fetch_1s_bars.py \
  --symbol ES \
  --start 2024-01-01 \
  --end 2024-12-31

# 3. Aggregate to multiple timeframes
python scripts/resample_bars.py \
  --symbol ES \
  --timeframes 15s,30s,1min,5min

# 4. Validate each timeframe
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s

python scripts/validate_bars.py \
  --input_dir data/aggregated/30s \
  --timeframe 30s

python scripts/validate_bars.py \
  --input_dir data/aggregated/1min \
  --timeframe 1min

# 5. Check validation reports
cat logs/validation_report.txt
```

---

## 📊 File Formats

### Raw 1-Second CSV Format
```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,4500.25,4500.50,4500.00,4500.25,150
2024-01-01 00:00:01,4500.25,4500.75,4500.25,4500.50,200
2024-01-01 00:00:02,4500.50,4500.50,4500.25,4500.25,100
...
```

### Aggregated CSV Format
```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,4500.25,4500.75,4500.00,4500.50,450
2024-01-01 00:00:15,4500.50,4501.00,4500.25,4500.75,600
2024-01-01 00:00:30,4500.75,4501.25,4500.50,4501.00,550
...
```

---

## 📞 Support

For issues or questions:
1. Check logs in `logs/` directory
2. Review this troubleshooting section
3. Run validation to identify data issues
4. Check Databento API documentation: https://docs.databento.com/

---

## 📄 License

This project is provided as-is for internal use.

---

**Version:** 1.0  
**Last Updated:** December 15, 2025  
**Author:** Databento Pipeline Team
