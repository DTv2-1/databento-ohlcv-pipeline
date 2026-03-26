# iVolatility Options Data Pull

## Overview

Script to download historical options EOD data (price, IV, greeks) from the iVolatility REST API via their VS Code Cloud Workspace. Supports any equity symbol (SPY, AAPL, QQQ, TSLA, etc.).

**Default symbol:** SPY  
**Date range:** March 2024 – February 2026 (24 months)  
**Output:** 1 CSV per month, ~50K+ rows each  
**Estimated time:** ~3.5 hours per month, runs unattended  

---

## Files

| File | Description |
|------|-------------|
| `scripts/fetch_ivolatility_options.py` | Main download script |
| `scripts/test_ivolatility.py` | API endpoint tester |
| `data/options/ivolatility/` | Output CSVs land here |
| `logs/` | Detailed logs for each run |

---

## Quick Start (iVolatility VS Code Cloud Workspace)

Open the terminal in VS Code Cloud and run these commands **one at a time**:

### First time setup
```bash
git clone https://github.com/DTv2-1/databento-ohlcv-pipeline.git
cd databento-ohlcv-pipeline
```

### If repo is already cloned (update to latest)
```bash
cd ~/databento-ohlcv-pipeline
git pull
```

### Run the full 2-year download (monthly mode)
```bash
python3 scripts/fetch_ivolatility_options.py --full --monthly --username realpetedavis --password '!EatzC8cLKHUf@jf'
```

> **Important:** The password must use **single quotes** `'...'` not double quotes `"..."` because the `!` character has special meaning in bash.

---

## Command Reference

| Command | What it does |
|---------|-------------|
| `--symbol TICKER` | Symbol to pull (default: SPY). Examples: AAPL, QQQ, TSLA |
| `--full` | Pull Mar 2024 – Feb 2026 |
| `--monthly` | Save 1 CSV per month, auto-continue to next month |
| `--from YYYY-MM-DD --to YYYY-MM-DD` | Custom date range |
| `--dry-run` | Show plan without downloading anything |
| `--username USER` | iVolatility username |
| `--password 'PASS'` | iVolatility password (use single quotes!) |

### Examples

```bash
# Full SPY pull — Mar 2024 to Feb 2026, one CSV per month
python3 scripts/fetch_ivolatility_options.py --full --monthly --username realpetedavis --password '!EatzC8cLKHUf@jf'

# Pull AAPL options for a custom date range
python3 scripts/fetch_ivolatility_options.py --symbol AAPL --from 2024-03-01 --to 2024-12-31 --monthly --username realpetedavis --password '!EatzC8cLKHUf@jf'

# Dry run — see the plan without downloading
python3 scripts/fetch_ivolatility_options.py --full --monthly --dry-run --username realpetedavis --password '!EatzC8cLKHUf@jf'

# Pull just one month of SPY
python3 scripts/fetch_ivolatility_options.py --from 2024-03-01 --to 2024-03-31 --username realpetedavis --password '!EatzC8cLKHUf@jf'

# Pull QQQ for 6 months
python3 scripts/fetch_ivolatility_options.py --symbol QQQ --from 2024-06-01 --to 2024-12-31 --monthly --username realpetedavis --password '!EatzC8cLKHUf@jf'
```

---

## Where are the downloads?

CSVs are saved to:
```
~/databento-ohlcv-pipeline/data/options/ivolatility/
```

Files are named by symbol and month:
```
SPY_options_2024-03.csv
SPY_options_2024-04.csv
AAPL_options_2024-03.csv
QQQ_options_2024-06.csv
...
```

---

## Resume / Crash Recovery

If the script stops for any reason (network error, timeout, browser close, etc.):

1. **Just run the same command again** — it picks up where it left off
2. It uses checkpoint files to track progress
3. Completed months are skipped automatically
4. Partially completed months resume from the last saved contract

---

## Will it keep running if I close my browser?

**Yes.** The iVolatility VS Code Cloud Workspace runs on a remote server. Once you start the script:

- ✅ You can **close your browser** — the script keeps running on the server
- ✅ You can **close your laptop** — the script keeps running on the server
- ✅ If you reconnect later, you'll see the output still going in the terminal
- ✅ If the script finishes while you're away, the CSVs will be in `data/options/ivolatility/`

The only thing that would stop it is if iVolatility shuts down the cloud workspace itself (e.g., after extended inactivity or trial expiration).

---

## Output CSV Columns

Each CSV contains these columns:

| Column | Description |
|--------|-------------|
| `date` | Trading date |
| `underlying_price` | SPY closing price |
| `option_symbol` | OCC option symbol |
| `expiry` | Expiration date |
| `strike` | Strike price |
| `type` | C (Call) or P (Put) |
| `style` | A (American) or E (European) |
| `bid` | Bid price |
| `ask` | Ask price |
| `close` | Close/settlement price |
| `volume` | Daily volume |
| `open_interest` | Open interest |
| `iv` | Implied volatility |
| `delta` | Delta |
| `gamma` | Gamma |
| `vega` | Vega |
| `theta` | Theta |
| `rho` | Rho |

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `bash: !EatzC8cLKHUf@jf: event not found` | Use single quotes `'...'` around the password |
| `can't open file 'fetch_ivolatility_options.py'` | Add `scripts/` — run `python3 scripts/fetch_ivolatility_options.py` |
| `fatal: destination path already exists` | Repo already cloned — just `cd ~/databento-ohlcv-pipeline && git pull` |
| `dubious ownership` | Run `git config --global --add safe.directory /home/coder/databento-ohlcv-pipeline` |
| `Token validation attempt failed` | Check username/password are correct |

---

## Notes

- These are **bash/Linux commands** (not GitBash/Windows). The cloud workspace runs Linux.
- The API rate is ~1 request per 0.2 seconds. Each month takes ~3.5 hours.
- All 24 months = ~84 hours total, but it runs unattended.
- The script logs everything to `logs/` — check there if something looks wrong.
