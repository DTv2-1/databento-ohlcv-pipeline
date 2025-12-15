# Databento Pipeline - Quick Start Guide

This guide will get you up and running in 5 minutes.

## 📋 Prerequisites

- Python 3.9+
- Databento API key

## 🚀 Quick Setup

### 1. Install Dependencies
```bash
cd /Users/1di/DataBento
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set API Key
```bash
# Create .env file
echo "DATABENTO_API_KEY=your-api-key-here" > .env
```

### 3. Test Connection
```bash
python test_connection.py
```

Expected output:
```
🔍 Testing Databento API connection...
✅ Databento client created successfully
✅ Available datasets: X
✅ Ready to proceed with development!
```

## 📥 Download Data

Download ES futures for January 2024:
```bash
python scripts/fetch_1s_bars.py \
  --symbol ES \
  --start 2024-01-01 \
  --end 2024-01-31
```

Files will be saved to: `data/raw_1s/ES/ES_2024_01.csv`

## 🔄 Aggregate Data

Create 15s, 30s, and 1min bars:
```bash
python scripts/resample_bars.py --symbol ES
```

Files will be saved to:
- `data/aggregated/15s/ES_2024_01_15s.csv`
- `data/aggregated/30s/ES_2024_01_30s.csv`
- `data/aggregated/1min/ES_2024_01_1min.csv`

## ✅ Validate Data

Check data integrity:
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s
```

## 🎯 Complete Example

Full workflow for 6 months of ES data:
```bash
# 1. Download
python scripts/fetch_1s_bars.py \
  --symbol ES \
  --start 2024-01-01 \
  --end 2024-06-30

# 2. Aggregate
python scripts/resample_bars.py \
  --symbol ES \
  --timeframes 15s,30s,1min

# 3. Validate (with volume check)
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s \
  --raw_data_dir data/raw_1s
```

## 📚 Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Run `python test_pipeline.py` for comprehensive testing
- Add more symbols: SPY, QQQ, NQ, etc.
- Try custom timeframes: 45s, 5min, etc.

## ⚠️ Common Issues

**"DATABENTO_API_KEY not found"**
```bash
export DATABENTO_API_KEY='your-key'
```

**"No module named 'databento'"**
```bash
pip install -r requirements.txt
```

**Files not downloading**
- Check API key is valid
- Verify symbol is available in dataset
- Check date range is valid

## 📞 Help

For detailed troubleshooting, see [README.md](README.md#troubleshooting)
