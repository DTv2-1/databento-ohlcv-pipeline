#!/usr/bin/env python3
"""Quick test of iVolatility REST API — discover endpoints and data shape."""

import urllib.request
import urllib.parse
import json
import sys

import os

BASE = "https://restapi.ivolatility.com"
USERNAME = os.environ.get("IVOL_USERNAME", "")
PASSWORD = os.environ.get("IVOL_PASSWORD", "")


def api_get(path, params=None, raw=False):
    """Make GET request to iVolatility API."""
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode()
            if raw:
                return data
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, 'read') else ''
        print(f"  HTTP {e.code}: {body[:500]}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def get_token():
    """Get auth token."""
    result = api_get("/token/get", {"username": USERNAME, "password": PASSWORD}, raw=True)
    if result and len(result) > 20:
        print(f"✓ Token obtained: {result[:30]}...")
        return result.strip()
    else:
        print(f"✗ Token failed: {result}")
        return None


def test_endpoint(name, path, params):
    """Test an endpoint and show results."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"  Path: {path}")
    print(f"  Params: {params}")
    result = api_get(path, params)
    if result is None:
        print("  → No response / error")
        return
    if isinstance(result, list):
        print(f"  → {len(result)} records returned")
        if len(result) > 0:
            print(f"  → Keys: {list(result[0].keys())}")
            print(f"  → First record:")
            print(f"    {json.dumps(result[0], indent=4)}")
    elif isinstance(result, dict):
        if 'data' in result:
            data = result['data']
            if isinstance(data, list):
                print(f"  → {len(data)} records in 'data'")
                if len(data) > 0:
                    print(f"  → Keys: {list(data[0].keys())}")
                    print(f"  → First record:")
                    print(f"    {json.dumps(data[0], indent=4)}")
            else:
                print(f"  → data: {json.dumps(data, indent=2)[:500]}")
        else:
            print(f"  → Dict response: {json.dumps(result, indent=2)[:1000]}")
    elif isinstance(result, str):
        print(f"  → String response ({len(result)} chars): {result[:500]}")
    else:
        print(f"  → {type(result)}: {str(result)[:500]}")


def main():
    print("=" * 60)
    print("iVolatility API Explorer")
    print("=" * 60)

    # Step 1: Get token
    token = get_token()
    if not token:
        sys.exit(1)

    # Step 2: Check what subscriptions/info we have
    test_endpoint(
        "Option series for SPY",
        "/equities/option-series",
        {"token": token, "symbol": "SPY"}
    )

    # Step 3: Try EOD options with raw IV (simplest, should work even on basic plan)
    test_endpoint(
        "EOD Options Raw IV — SPY single day",
        "/equities/eod/options-rawiv",
        {
            "token": token,
            "symbol": "SPY",
            "from": "2026-03-10",
            "to": "2026-03-10",
            "strike": "570",
            "optType": "CALL",
        }
    )

    # Step 4: Try intraday options 1-min
    test_endpoint(
        "Intraday Options Raw IV — SPY 1-min (single strike)",
        "/equities/intraday/equity-options-rawiv",
        {
            "token": token,
            "symbol": "SPY",
            "from": "2026-03-10",
            "to": "2026-03-10",
            "strike": "570",
            "optType": "CALL",
            "minuteType": "MINUTE_1",
        }
    )

    # Step 5: Try DD intraday
    test_endpoint(
        "DD Intraday Equity Options — SPY 1-min (single strike)",
        "/dd/intraday/equity/options",
        {
            "token": token,
            "symbol": "SPY",
            "from": "2026-03-10",
            "to": "2026-03-10",
            "strike": "570",
            "optType": "CALL",
            "minuteType": "MINUTE_1",
        }
    )

    # Step 6: Try single option rawiv intraday
    test_endpoint(
        "Single Equity Option Raw IV Intraday",
        "/equities/intraday/single-equity-option-rawiv",
        {
            "token": token,
            "symbol": "SPY",
            "from": "2026-03-10",
            "to": "2026-03-10",
            "strike": "570",
            "optType": "CALL",
            "minuteType": "MINUTE_1",
        }
    )

    # Step 7: Try with expDate
    test_endpoint(
        "Intraday Options — with expDate",
        "/equities/intraday/equity-options-rawiv",
        {
            "token": token,
            "symbol": "SPY",
            "from": "2026-03-10",
            "to": "2026-03-10",
            "expDate": "2026-03-21",
            "strike": "570",
            "optType": "CALL",
            "minuteType": "MINUTE_1",
        }
    )

    # Step 8: Try without strike (full chain) — small date to not overwhelm
    test_endpoint(
        "Intraday Full Chain — SPY (no strike filter)",
        "/equities/intraday/equity-options-rawiv",
        {
            "token": token,
            "symbol": "SPY",
            "from": "2026-03-10",
            "to": "2026-03-10",
            "optType": "ALL",
            "minuteType": "MINUTE_1",
        }
    )

    # Step 9: Try DD intraday single option
    test_endpoint(
        "DD Intraday Single Option",
        "/dd/intraday/single/equity/option",
        {
            "token": token,
            "symbol": "SPY",
            "from": "2026-03-10",
            "to": "2026-03-10",
            "strike": "570",
            "optType": "CALL",
            "minuteType": "MINUTE_1",
        }
    )

    # Step 10: EOD single stock option
    test_endpoint(
        "EOD Single Stock Option",
        "/equities/eod/single-stock-option",
        {
            "token": token,
            "symbol": "SPY",
            "from": "2026-03-10",
            "to": "2026-03-10",
            "strike": "570",
            "optType": "CALL",
        }
    )

    print("\n" + "=" * 60)
    print("Done! Review results above to determine which endpoints work.")
    print("=" * 60)


if __name__ == "__main__":
    main()
