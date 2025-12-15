# Databento Pipeline - Project Structure

```
DataBento/
│
├── README.md                       # Main documentation
├── requirements.txt                # Python dependencies
├── .env.example                    # API key template
├── .gitignore                      # Git ignore rules
│
├── scripts/                        # Core pipeline scripts
│   ├── fetch_1s_bars.py           # Download 1-second OHLCV data
│   ├── resample_bars.py           # Aggregate to higher timeframes
│   └── validate_bars.py           # Validate data integrity
│
├── utils/                          # Utility scripts
│   ├── test_connection.py         # Test Databento API connection
│   ├── test_pipeline.py           # Complete pipeline test suite
│   ├── check_symbols.py           # Symbol availability checker
│   ├── explore_datasets.py        # Dataset explorer
│   └── package_for_delivery.sh    # Package for delivery
│
├── docs/                           # Documentation
│   ├── QUICKSTART.md              # 5-minute setup guide
│   ├── DELIVERY.md                # Delivery instructions
│   ├── DATASET_NOTES.md           # Dataset usage notes
│   ├── PROJECT_OVERVIEW.md        # Technical overview
│   └── mvp.md                     # Original specification
│
├── data/                           # Data storage
│   ├── raw_1s/                    # Downloaded 1-second data
│   │   └── {SYMBOL}/              # Organized by symbol
│   │       └── {SYMBOL}_{YYYY}_{MM}.csv
│   │
│   └── aggregated/                # Aggregated data
│       ├── 15s/                   # 15-second bars
│       ├── 30s/                   # 30-second bars
│       ├── 1min/                  # 1-minute bars
│       └── {timeframe}/           # Other timeframes
│
├── logs/                           # Log files
│   ├── downloader.log             # Download logs
│   ├── aggregator.log             # Aggregation logs
│   ├── validator.log              # Validation logs
│   └── validation_report.txt     # Latest validation report
│
└── tests/                          # Test directory (placeholder)
```

## File Descriptions

### Core Scripts

**scripts/fetch_1s_bars.py**
- Downloads 1-second OHLCV data from Databento API
- Supports resume capability (skips existing files)
- Month-by-month iteration for date ranges
- Configurable dataset selection

**scripts/resample_bars.py**
- Aggregates 1-second bars to higher timeframes
- Supports: 15s, 30s, 45s, 1min, 2min, 5min, 15min, 30min, 1h
- Proper OHLCV aggregation (first/max/min/last/sum)
- Easily extensible to custom timeframes

**scripts/validate_bars.py**
- Validates data integrity and quality
- Checks: duplicates, OHLC rules, negative values, missing data
- Timestamp alignment validation
- Generates detailed reports

### Utility Scripts

**utils/test_connection.py**
- Tests Databento API connectivity
- Validates API key
- Lists available datasets

**utils/test_pipeline.py**
- Comprehensive end-to-end test suite
- Tests download, aggregation, validation
- Verifies resume capability

**utils/check_symbols.py**
- Checks symbol availability
- Shows contract formats for futures

**utils/explore_datasets.py**
- Lists all available datasets
- Shows supported schemas
- Provides recommendations

**utils/package_for_delivery.sh**
- Creates clean zip package
- Excludes temporary files and data
- Ready for Proton Drive upload

### Documentation

**README.md**
- Complete user guide
- Installation instructions
- Usage examples
- Troubleshooting

**docs/QUICKSTART.md**
- 5-minute setup guide
- Quick commands
- Common workflows

**docs/DATASET_NOTES.md**
- Dataset usage information
- Tested configurations
- Symbol format notes

**docs/DELIVERY.md**
- Packaging instructions
- Delivery checklist
- WhatsApp message template

**docs/PROJECT_OVERVIEW.md**
- Technical specifications
- Code metrics
- Feature list

## Data Organization

### Raw Data Structure
```
data/raw_1s/
└── SPY/
    ├── SPY_2024_01.csv
    ├── SPY_2024_02.csv
    └── SPY_2024_03.csv
```

### Aggregated Data Structure
```
data/aggregated/
├── 15s/
│   ├── SPY_2024_01_15s.csv
│   ├── SPY_2024_02_15s.csv
│   └── SPY_2024_03_15s.csv
├── 30s/
│   └── ...
└── 1min/
    └── ...
```

## Quick Commands

### Setup
```bash
pip install -r requirements.txt
echo "DATABENTO_API_KEY=your-key" > .env
python utils/test_connection.py
```

### Download Data
```bash
python scripts/fetch_1s_bars.py \
  --symbol SPY \
  --dataset DBEQ.BASIC \
  --start 2024-01-01 \
  --end 2024-12-31
```

### Aggregate Data
```bash
python scripts/resample_bars.py \
  --symbol SPY \
  --timeframes 15s,30s,1min
```

### Validate Data
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s
```

### Package for Delivery
```bash
./utils/package_for_delivery.sh
```

## Notes

- All emoticons removed from scripts for cleaner output
- Logs use clear prefixes: SUCCESS, ERROR, WARNING
- Documentation organized in `/docs` folder
- Utilities organized in `/utils` folder
- Tested and working with SPY on DBEQ.BASIC dataset
