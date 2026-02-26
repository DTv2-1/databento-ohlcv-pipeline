# Tradovate API Discovery Report

**Date:** 2026-01-12  
**Phase:** Discovery (Phase 2 of PA MVP)  
**Status:** 🔴 BLOCKED - Awaiting API Key

---

## Current Status

### ✅ Completed
- Created test connection script (`scripts/test_tradovate_connection.py`)
- Stored username/password credentials in `.env`
- Researched Tradovate API documentation
- Tested both DEMO and LIVE endpoints

### 🔴 Blockers
**Missing: `TRADOVATE_SEC` (API Key)**

Both DEMO and LIVE authentication fail with:
```
"Incorrect username or password. Please try again, noting that passwords are case-sensitive."
```

**Root Cause:** According to Tradovate docs, the `sec` field is REQUIRED for API authentication, not optional.

---

## Credentials Status

From `.env` file:
```bash
TRADOVATE_USERNAME=PeterDavis80           ✅
TRADOVATE_PASSWORD=C5487P5329S1807tv=     ✅
TRADOVATE_APP_ID=PA_MVP                   ✅
TRADOVATE_APP_VERSION=1.0                 ✅
TRADOVATE_CID=8                           ✅
TRADOVATE_DEVICE_ID=pa-mvp-dev-001        ✅
TRADOVATE_SEC=                            ❌ EMPTY
```

---

## What We Learned from Internet Research

### Authentication Flow
1. **REST API Authentication**
   - Endpoint: `POST https://demo.tradovateapi.com/v1/auth/accesstokenrequest`
   - Required fields: name, password, appId, appVersion, cid, **sec**, deviceId
   - Returns: `accessToken`, `mdAccessToken`, `expirationTime`
   - Token lifetime: 90 minutes
   - Can be renewed via `/auth/renewAccessToken`

2. **WebSocket for Market Data**
   - URL: `wss://md.tradovateapi.com/v1/websocket`
   - Authorize first: `authorize\n0\n\n${accessToken}`
   - Subscribe: `md/subscribeQuote\n1\n\n{"symbol":"MESM1"}`

3. **Two-Factor Authentication**
   - `deviceId`: Unique device identifier (we set: `pa-mvp-dev-001`)
   - `cid`: Client app ID from Tradovate (we have: `8`)
   - `sec`: API secret/key from Tradovate (**MISSING**)

### Example Code Patterns

**Python REST Authentication:**
```python
import requests

response = requests.post(
    'https://demo.tradovateapi.com/v1/auth/accesstokenrequest',
    headers={'Content-Type': 'application/json'},
    json={
        'name': 'PeterDavis80',
        'password': 'C5487P5329S1807tv=',
        'appId': 'PA_MVP',
        'appVersion': '1.0',
        'cid': 8,
        'deviceId': 'pa-mvp-dev-001',
        'sec': 'f03741b6-f634-48d6-9308-c8fb871150c2'  # Example from docs
    }
)

data = response.json()
access_token = data['accessToken']
```

**WebSocket Connection:**
```python
import websocket

ws = websocket.WebSocketApp('wss://md.tradovateapi.com/v1/websocket')

# Authorize
ws.send(f'authorize\n0\n\n{access_token}')

# Subscribe to market data
ws.send('md/subscribeQuote\n1\n\n{"symbol":"MESM1"}')

# Listen for messages
ws.on_message = lambda ws, msg: print(msg)
```

---

## API Endpoints of Interest

### Market Data (After Auth)
- `md/subscribeQuote` - Real-time quotes
- `md/subscribeDOM` - Depth of Market
- `md/getChart` - Historical bars
  - Supports: 1s, 5s, 10s, 15s, 30s, 1m, 2m, 3m, 4m, 5m, 10m, etc.
- `md/subscribeTick` - Tick-by-tick data

### Order Management
- `/order/placeorder` - Place new order
- `/order/cancelorder` - Cancel order
- `/order/modifyorder` - Modify order
- `/order/liquidateposition` - Close position

### Account Data
- `/account/list` - List accounts
- `/cashBalance/getCashBalanceSnapshot` - Current balance
- `/position/list` - Current positions
- `/fill/list` - Execution fills

---

## Known Issues & Solutions

### Issue 1: API Key Format
**Problem:** Don't know format of `sec` field  
**Example from docs:** `f03741b6-f634-48d6-9308-c8fb871150c2` (UUID format)  
**Action:** Check Pete's Tradovate email

### Issue 2: Rate Limits
**Problem:** API has rate limits (not yet tested)  
**Solution:** Implement exponential backoff and request throttling

### Issue 3: Session Management
**Problem:** Tokens expire after 90 minutes  
**Solution:** Call `/auth/renewAccessToken` every ~75 minutes

### Issue 4: Connection Limits
**Problem:** Max 2 concurrent sessions per user  
**Solution:** Reuse tokens across services, don't create new sessions unnecessarily

---

## Next Steps (Once API Key Obtained)

### Phase 2A: Basic Connectivity ✅➡️
1. ✅ Create connection test script
2. ⏳ Obtain `TRADOVATE_SEC` from email
3. ⏳ Verify authentication works
4. ⏳ Test account listing

### Phase 2B: Market Data Exploration
1. Connect WebSocket
2. Subscribe to quotes for test symbols (ES, MES, GC)
3. Test bar intervals (1s, 15s, 30s, 1m)
4. Document data format and seq IDs
5. Test replay/reconnect behavior

### Phase 2C: Order Flow
1. Test order placement on DEMO
2. Verify order status updates via WebSocket
3. Test order cancellation
4. Document fill events format

### Phase 2D: Edge Cases
1. Test rate limiting
2. Test connection drops
3. Test invalid symbols
4. Test market hours vs closed

### Deliverable
Create `DISCOVERY_REPORT.md` with:
- Data formats
- Seq ID semantics
- Rate limits observed
- Reconnect behavior
- Recommendations for PA design

---

## Resources

- **API Docs:** https://api.tradovate.com
- **JS Examples:** https://github.com/tradovate/example-api-js
- **C# Examples:** https://github.com/tradovate/example-api-csharp-trading
- **Community:** https://community.tradovate.com/c/api-developers/15

---

## Time Tracking

| Task | Estimate | Actual |
|------|----------|--------|
| Research Tradovate API | 1h | 0.5h |
| Create connection script | 0.5h | 0.5h |
| Test authentication | 0.5h | 0.5h ⏸️ |
| **Total Phase 2 so far** | **2h** | **1.5h** |

**Status:** Paused until `TRADOVATE_SEC` obtained  
**ETA to Resume:** Depends on Pete checking email
