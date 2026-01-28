# Deployment Guide - Platform Adapter

Complete guide for deploying the Platform Adapter in production environments.

## Table of Contents

1. [Production Checklist](#production-checklist)
2. [Environment Setup](#environment-setup)
3. [Security Configuration](#security-configuration)
4. [Monitoring & Logging](#monitoring--logging)
5. [Performance Tuning](#performance-tuning)
6. [Deployment Patterns](#deployment-patterns)
7. [Backup & Recovery](#backup--recovery)
8. [Maintenance](#maintenance)

---

## Production Checklist

### Pre-Deployment

- [ ] Review all code and tests
- [ ] Run full test suite
- [ ] Test with IB Gateway in paper trading mode
- [ ] Review and update configuration
- [ ] Set up monitoring and alerting
- [ ] Prepare rollback plan
- [ ] Document deployment procedure
- [ ] Schedule deployment window

### Security

- [ ] Rotate API credentials
- [ ] Secure `.env` file permissions
- [ ] Enable firewall rules
- [ ] Set up VPN/secure connection to IB Gateway
- [ ] Review audit logs
- [ ] Implement rate limiting
- [ ] Enable TLS/SSL where applicable

### Infrastructure

- [ ] Provision production server
- [ ] Configure backup system
- [ ] Set up log aggregation
- [ ] Configure monitoring dashboards
- [ ] Test disaster recovery procedures
- [ ] Document infrastructure architecture

### Go-Live

- [ ] Switch to live trading credentials
- [ ] Monitor initial trades closely
- [ ] Verify order execution
- [ ] Check position reconciliation
- [ ] Monitor system metrics
- [ ] Have rollback ready

---

## Environment Setup

### Production Server Requirements

**Minimum Specifications:**
- **CPU**: 2 cores, 2.5 GHz+
- **RAM**: 4 GB
- **Storage**: 50 GB SSD
- **Network**: Stable, low-latency connection
- **OS**: Ubuntu 20.04 LTS or macOS 11+

**Recommended Specifications:**
- **CPU**: 4 cores, 3.0 GHz+
- **RAM**: 8 GB
- **Storage**: 100 GB SSD
- **Network**: Dedicated line, <10ms latency to IB servers
- **OS**: Ubuntu 22.04 LTS

### Python Environment

```bash
# 1. Install Python 3.11+
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev

# 2. Create production directory
sudo mkdir -p /opt/platform_adapter
sudo chown $USER:$USER /opt/platform_adapter
cd /opt/platform_adapter

# 3. Clone repository
git clone <repository-url> .

# 4. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 5. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 6. Verify installation
python -c "import ibapi; print(ibapi.__version__)"
```

### IB Gateway Setup

**Option 1: Local IB Gateway**

```bash
# Download IB Gateway
wget https://download2.interactivebrokers.com/installers/ibgateway/latest-standalone/ibgateway-latest-standalone-linux-x64.sh

# Install
chmod +x ibgateway-latest-standalone-linux-x64.sh
./ibgateway-latest-standalone-linux-x64.sh

# Configure for headless operation
# Edit: ~/.IB/gateway/jts.ini
```

**Option 2: Docker IB Gateway**

```yaml
# docker-compose.yml
version: '3.8'

services:
  ibgateway:
    image: ghcr.io/gnzsnz/ib-gateway:latest
    container_name: ibgateway
    environment:
      - TWS_USERNAME=${IB_USERNAME}
      - TWS_PASSWORD=${IB_PASSWORD}
      - TRADING_MODE=paper  # or 'live'
      - VNC_PASSWORD=${VNC_PASSWORD}
    ports:
      - "7497:7497"  # Paper trading
      - "5900:5900"  # VNC
    restart: unless-stopped
```

```bash
# Start IB Gateway
docker-compose up -d

# View logs
docker-compose logs -f ibgateway
```

### Production Configuration

Create `/opt/platform_adapter/.env`:

```bash
# IB Gateway Connection
TWS_HOST=localhost
TWS_PORT=7496  # LIVE TRADING PORT
TWS_CLIENT_ID=1
TWS_AUTO_RECONNECT=true

# Security
ENABLE_API_AUTH=true
API_SECRET_KEY=<generate-strong-secret>

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/platform_adapter/app.log
LOG_ROTATION=daily
LOG_RETENTION_DAYS=90

# State Management
STATE_FILE=/var/lib/platform_adapter/state.json
STATE_BACKUP_DIR=/var/lib/platform_adapter/backups
STATE_RECONCILE_ON_START=true

# Performance
MAX_WORKERS=4
CACHE_SIZE=1000
REQUEST_TIMEOUT=30

# Monitoring
ENABLE_METRICS=true
METRICS_PORT=9090
HEALTHCHECK_PORT=8080

# Alerts
ALERT_EMAIL=alerts@yourcompany.com
ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK
```

### File Permissions

```bash
# Secure configuration files
chmod 600 /opt/platform_adapter/.env
chmod 600 /opt/platform_adapter/config/*

# Create log directory
sudo mkdir -p /var/log/platform_adapter
sudo chown $USER:$USER /var/log/platform_adapter

# Create state directory
sudo mkdir -p /var/lib/platform_adapter/backups
sudo chown $USER:$USER /var/lib/platform_adapter
```

---

## Security Configuration

### 1. Secure Credentials

```bash
# Use environment variables, never hardcode
export IB_USERNAME="your_username"
export IB_PASSWORD="your_password"

# Or use secrets manager (AWS Secrets Manager example)
aws secretsmanager get-secret-value \
  --secret-id prod/ib/credentials \
  --query SecretString \
  --output text
```

### 2. Network Security

**Firewall Configuration:**

```bash
# Allow only necessary ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 7496/tcp  # IB Gateway (live)
sudo ufw allow 8080/tcp  # Health check
sudo ufw enable
```

**IP Whitelisting:**

```bash
# Restrict IB Gateway to localhost only
# Edit /etc/hosts.allow
echo "ibgateway: 127.0.0.1" | sudo tee -a /etc/hosts.allow

# Edit /etc/hosts.deny
echo "ibgateway: ALL" | sudo tee -a /etc/hosts.deny
```

### 3. Access Control

```bash
# Create dedicated user
sudo useradd -r -s /bin/false platform_adapter

# Set ownership
sudo chown -R platform_adapter:platform_adapter /opt/platform_adapter
sudo chown -R platform_adapter:platform_adapter /var/log/platform_adapter
sudo chown -R platform_adapter:platform_adapter /var/lib/platform_adapter
```

### 4. Audit Logging

```python
# Enable audit logging in code
from platform_adapter.utils.logger import logger

# Log all critical operations
logger.info("AUDIT: Order placed", extra={
    "order_id": order_id,
    "symbol": symbol,
    "quantity": quantity,
    "action": action,
    "user": "system"
})
```

---

## Monitoring & Logging

### 1. Application Logging

**Loguru Configuration:**

```python
# src/platform_adapter/utils/logger.py
from loguru import logger
import sys

# Remove default handler
logger.remove()

# Console handler (for development)
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO"
)

# File handler (for production)
logger.add(
    "/var/log/platform_adapter/app.log",
    rotation="00:00",  # Rotate daily at midnight
    retention="90 days",  # Keep logs for 90 days
    compression="gz",  # Compress rotated logs
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} | {message}"
)

# Error file handler
logger.add(
    "/var/log/platform_adapter/error.log",
    rotation="100 MB",
    retention="1 year",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} | {message}\n{exception}"
)
```

### 2. System Monitoring

**Systemd Service:**

```ini
# /etc/systemd/system/platform-adapter.service
[Unit]
Description=Platform Adapter for IB Gateway
After=network.target

[Service]
Type=simple
User=platform_adapter
Group=platform_adapter
WorkingDirectory=/opt/platform_adapter
Environment="PATH=/opt/platform_adapter/venv/bin"
ExecStart=/opt/platform_adapter/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Resource limits
LimitNOFILE=65536
MemoryLimit=2G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable platform-adapter
sudo systemctl start platform-adapter

# Check status
sudo systemctl status platform-adapter

# View logs
sudo journalctl -u platform-adapter -f
```

### 3. Health Checks

```python
# Add to main.py
from flask import Flask, jsonify
import threading

app = Flask(__name__)

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'connected': adapter.connection.is_connected,
        'uptime': time.time() - start_time,
        'version': '1.0.0'
    })

@app.route('/metrics')
def metrics():
    return jsonify({
        'orders_total': len(adapter.orders.get_all_orders()),
        'orders_open': len(adapter.orders.get_open_orders()),
        'positions': len(adapter.account.get_positions()),
        'net_liquidation': adapter.account.get_summary()['net_liquidation']
    })

# Run in separate thread
def run_health_server():
    app.run(host='0.0.0.0', port=8080)

health_thread = threading.Thread(target=run_health_server, daemon=True)
health_thread.start()
```

### 4. Prometheus Metrics

```python
# Install prometheus_client
# pip install prometheus-client

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Metrics
orders_total = Counter('orders_total', 'Total orders placed')
orders_filled = Counter('orders_filled', 'Total orders filled')
order_latency = Histogram('order_latency_seconds', 'Order placement latency')
position_value = Gauge('position_value_usd', 'Total position value')
account_balance = Gauge('account_balance_usd', 'Account balance')

# Start metrics server
start_http_server(9090)

# Update metrics
orders_total.inc()
account_balance.set(adapter.account.get_summary()['net_liquidation'])
```

---

## Performance Tuning

### 1. Connection Pooling

```python
# Use single connection instance
class ConnectionPool:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.adapter = PlatformAdapter()
            cls._instance.adapter.connect()
        return cls._instance

# Usage
pool = ConnectionPool()
adapter = pool.adapter
```

### 2. Caching

```python
from functools import lru_cache
import time

class CachedMarketData:
    def __init__(self, adapter):
        self.adapter = adapter
        self._quote_cache = {}
        self._cache_ttl = 1  # seconds
    
    def get_quote(self, symbol):
        now = time.time()
        if symbol in self._quote_cache:
            quote, timestamp = self._quote_cache[symbol]
            if now - timestamp < self._cache_ttl:
                return quote
        
        quote = self.adapter.market_data.get_latest_quote(symbol)
        self._quote_cache[symbol] = (quote, now)
        return quote
```

### 3. Async Operations

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class AsyncAdapter:
    def __init__(self, adapter):
        self.adapter = adapter
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    async def place_order_async(self, symbol, quantity, action):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.adapter.place_market_order,
            symbol, quantity, action
        )

# Usage
async def main():
    orders = await asyncio.gather(
        adapter.place_order_async("AAPL", 10, "BUY"),
        adapter.place_order_async("MSFT", 10, "BUY"),
        adapter.place_order_async("GOOGL", 10, "BUY")
    )
```

### 4. Resource Limits

```python
# Limit concurrent subscriptions
MAX_SUBSCRIPTIONS = 50

# Limit order rate
from platform_adapter.utils.rate_limiter import RateLimiter
order_limiter = RateLimiter(max_requests=40, time_window=1)

def place_order_safe(symbol, quantity, action):
    order_limiter.wait_if_needed(f"order_{symbol}")
    return adapter.place_market_order(symbol, quantity, action)
```

---

## Deployment Patterns

### Pattern 1: Single Server

```
┌─────────────────────┐
│   IB Gateway        │
│   (localhost:7496)  │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Platform Adapter   │
│  - Main Process     │
│  - State Manager    │
│  - Logging          │
└─────────────────────┘
```

**Pros**: Simple, low latency  
**Cons**: Single point of failure  
**Use Case**: Personal trading, small-scale

### Pattern 2: High Availability

```
┌─────────────┐     ┌─────────────┐
│  Primary    │     │  Secondary  │
│  Adapter    │────▶│  Adapter    │
│  (Active)   │     │  (Standby)  │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └─────────┬─────────┘
                 │
        ┌────────▼────────┐
        │   IB Gateway    │
        │  Load Balancer  │
        └─────────────────┘
```

**Pros**: Fault tolerant  
**Cons**: Complex, requires coordination  
**Use Case**: Production trading, critical systems

### Pattern 3: Microservices

```
┌──────────────┐
│  Connection  │
│   Service    │
└──────┬───────┘
       │
┌──────▼───────┐     ┌──────────────┐
│  Market Data │────▶│   Strategy   │
│   Service    │     │   Service    │
└──────────────┘     └──────┬───────┘
                            │
┌──────────────┐     ┌──────▼───────┐
│   Account    │◀────│    Order     │
│   Service    │     │   Service    │
└──────────────┘     └──────────────┘
```

**Pros**: Scalable, modular  
**Cons**: Network overhead, complex  
**Use Case**: Large-scale, multiple strategies

---

## Backup & Recovery

### 1. State Backups

```bash
#!/bin/bash
# /opt/platform_adapter/scripts/backup_state.sh

BACKUP_DIR="/var/lib/platform_adapter/backups"
STATE_FILE="/var/lib/platform_adapter/state.json"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup
cp "$STATE_FILE" "$BACKUP_DIR/state_$TIMESTAMP.json"

# Compress old backups (older than 1 day)
find "$BACKUP_DIR" -name "state_*.json" -mtime +1 -exec gzip {} \;

# Delete backups older than 90 days
find "$BACKUP_DIR" -name "state_*.json.gz" -mtime +90 -delete

echo "Backup completed: state_$TIMESTAMP.json"
```

```bash
# Schedule with cron
crontab -e
# Add: 0 * * * * /opt/platform_adapter/scripts/backup_state.sh
```

### 2. Database Backups

```python
# Add to StateManager
def backup(self, backup_dir: str = None):
    if backup_dir is None:
        backup_dir = os.getenv('STATE_BACKUP_DIR', 'backups')
    
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(backup_dir, f'state_{timestamp}.json')
    
    shutil.copy2(self.state_file, backup_file)
    logger.info(f"State backed up to {backup_file}")
    
    return backup_file
```

### 3. Disaster Recovery

```bash
#!/bin/bash
# /opt/platform_adapter/scripts/restore_from_backup.sh

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

# Stop service
sudo systemctl stop platform-adapter

# Restore state
cp "$BACKUP_FILE" /var/lib/platform_adapter/state.json

# Start service
sudo systemctl start platform-adapter

echo "Restored from $BACKUP_FILE"
```

---

## Maintenance

### Daily Tasks

```bash
# Check service status
sudo systemctl status platform-adapter

# Review logs
sudo journalctl -u platform-adapter --since today

# Check disk space
df -h /var/log /var/lib

# Monitor resource usage
top -u platform_adapter
```

### Weekly Tasks

```bash
# Review error logs
grep ERROR /var/log/platform_adapter/app.log | tail -100

# Check backup integrity
ls -lh /var/lib/platform_adapter/backups/

# Update dependencies
cd /opt/platform_adapter
source venv/bin/activate
pip list --outdated
```

### Monthly Tasks

```bash
# Rotate logs manually if needed
sudo logrotate -f /etc/logrotate.d/platform-adapter

# Review and archive old backups
# Review system performance metrics
# Update documentation
# Security audit
```

### Version Upgrades

```bash
# 1. Backup current version
cp -r /opt/platform_adapter /opt/platform_adapter.backup

# 2. Stop service
sudo systemctl stop platform-adapter

# 3. Update code
cd /opt/platform_adapter
git fetch
git checkout v2.0.0  # New version

# 4. Update dependencies
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 5. Run migrations (if any)
python scripts/migrate.py

# 6. Test
pytest tests/

# 7. Start service
sudo systemctl start platform-adapter

# 8. Monitor
sudo journalctl -u platform-adapter -f
```

---

## Production Checklist Summary

### Go-Live Day

1. ✅ Verify all tests pass
2. ✅ Switch to live credentials
3. ✅ Enable monitoring
4. ✅ Start with small positions
5. ✅ Monitor for 1 hour
6. ✅ Gradually increase to full size
7. ✅ Document any issues
8. ✅ Have team on standby

### Post-Deployment

1. ✅ Monitor for 24 hours
2. ✅ Review all logs
3. ✅ Verify reconciliation
4. ✅ Check performance metrics
5. ✅ Update runbook
6. ✅ Schedule review meeting

---

**Last Updated**: January 27, 2026  
**Version**: 1.0.0
