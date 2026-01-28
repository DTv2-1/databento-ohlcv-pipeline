"""
Market Data Adapter
Handles real-time and historical market data from IB
"""

from typing import Optional, Dict, Callable, List
from datetime import datetime
from dataclasses import dataclass
from loguru import logger

from ibapi.contract import Contract as IBContract

# Tick type constants from IB API
TICK_BID = 1
TICK_ASK = 2
TICK_LAST = 4
TICK_BID_SIZE = 0
TICK_ASK_SIZE = 3
TICK_LAST_SIZE = 5
TICK_VOLUME = 8

from ..core.connection_manager import ConnectionManager
from ..models.contract import Contract
from ..utils.rate_limiter import IBRateLimiters


@dataclass
class TickData:
    """Real-time tick data"""
    symbol: str
    timestamp: datetime
    tick_type: str
    value: float
    
    def __repr__(self) -> str:
        return f"Tick({self.symbol} {self.tick_type}={self.value} @ {self.timestamp})"


@dataclass
class Bar:
    """Historical bar data (OHLCV)"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    count: int = 0
    wap: float = 0.0
    
    def __repr__(self) -> str:
        return (f"Bar({self.symbol} {self.timestamp} "
                f"O={self.open} H={self.high} L={self.low} C={self.close} V={self.volume})")


@dataclass
class Quote:
    """Real-time quote (bid/ask)"""
    symbol: str
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    last: Optional[float] = None
    last_size: Optional[int] = None
    volume: Optional[int] = None
    
    def __repr__(self) -> str:
        return (f"Quote({self.symbol} "
                f"bid={self.bid}x{self.bid_size} "
                f"ask={self.ask}x{self.ask_size} "
                f"last={self.last})")


class MarketDataAdapter:
    """Adapter for IB market data."""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.cm = connection_manager
        self._active_subscriptions: Dict[int, Contract] = {}
        self._quotes: Dict[str, Quote] = {}
        self._tick_callbacks: Dict[int, Callable] = {}
        self._historical_data: Dict[int, List[Bar]] = {}
        self._historical_callbacks: Dict[int, Callable] = {}
        self._next_req_id = 1000
        self._register_callbacks()
    
    def _register_callbacks(self):
        original_tick_price = self.cm.tickPrice
        def tick_price_handler(reqId: int, tickType: int, price: float, attrib):
            self._handle_tick_price(reqId, tickType, price, attrib)
            if original_tick_price:
                original_tick_price(reqId, tickType, price, attrib)
        self.cm.tickPrice = tick_price_handler
        
        original_tick_size = self.cm.tickSize
        def tick_size_handler(reqId: int, tickType: int, size: int):
            self._handle_tick_size(reqId, tickType, size)
            if original_tick_size:
                original_tick_size(reqId, tickType, size)
        self.cm.tickSize = tick_size_handler
        
        original_historical_data = self.cm.historicalData
        def historical_data_handler(reqId: int, bar):
            self._handle_historical_data(reqId, bar)
            if original_historical_data:
                original_historical_data(reqId, bar)
        self.cm.historicalData = historical_data_handler
        
        original_historical_data_end = self.cm.historicalDataEnd
        def historical_data_end_handler(reqId: int, start: str, end: str):
            self._handle_historical_data_end(reqId, start, end)
            if original_historical_data_end:
                original_historical_data_end(reqId, start, end)
        self.cm.historicalDataEnd = historical_data_end_handler
        
        logger.info("Market data callbacks registered")
    
    def _get_next_req_id(self) -> int:
        req_id = self._next_req_id
        self._next_req_id += 1
        return req_id
    
    def subscribe_market_data(self, contract: Contract, callback: Optional[Callable[[Quote], None]] = None, snapshot: bool = False) -> int:
        if not self.cm.is_ready():
            raise RuntimeError("Connection manager not ready")
        
        # Apply rate limiting for market data subscriptions
        IBRateLimiters.MARKET_DATA.wait_if_needed(operation=f"subscribe {contract.symbol}")
        
        req_id = self._get_next_req_id()
        self._active_subscriptions[req_id] = contract
        if callback:
            self._tick_callbacks[req_id] = callback
        self._quotes[contract.symbol] = Quote(symbol=contract.symbol, timestamp=datetime.now())
        self.cm.reqMarketDataType(3)
        ib_contract = contract.to_ib_contract()
        self.cm.reqMktData(reqId=req_id, contract=ib_contract, genericTickList="", snapshot=snapshot, regulatorySnapshot=False, mktDataOptions=[])
        logger.info(f"Subscribed to market data: {contract.symbol} (req_id={req_id})")
        return req_id
    
    def unsubscribe_market_data(self, req_id: int):
        if req_id not in self._active_subscriptions:
            logger.warning(f"Request ID {req_id} not found")
            return
        contract = self._active_subscriptions[req_id]
        self.cm.cancelMktData(req_id)
        del self._active_subscriptions[req_id]
        if req_id in self._tick_callbacks:
            del self._tick_callbacks[req_id]
        logger.info(f"Unsubscribed from market data: {contract.symbol} (req_id={req_id})")
    
    def get_quote(self, symbol: str) -> Optional[Quote]:
        return self._quotes.get(symbol)
    
    def get_active_subscriptions(self) -> List[str]:
        return [contract.symbol for contract in self._active_subscriptions.values()]
    
    def request_historical_data(self, contract: Contract, end_datetime: str = "", duration: str = "1 D", bar_size: str = "1 min", what_to_show: str = "TRADES", use_rth: bool = True, callback: Optional[Callable[[List[Bar]], None]] = None) -> int:
        if not self.cm.is_ready():
            raise RuntimeError("Connection manager not ready")
        
        # Apply rate limiting for historical data requests
        IBRateLimiters.HISTORICAL_DATA.wait_if_needed(operation=f"historical {contract.symbol}")
        
        req_id = self._get_next_req_id()
        self._historical_data[req_id] = []
        if callback:
            self._historical_callbacks[req_id] = callback
        ib_contract = contract.to_ib_contract()
        self.cm.reqHistoricalData(reqId=req_id, contract=ib_contract, endDateTime=end_datetime, durationStr=duration, barSizeSetting=bar_size, whatToShow=what_to_show, useRTH=1 if use_rth else 0, formatDate=1, keepUpToDate=False, chartOptions=[])
        logger.info(f"Requested historical data: {contract.symbol} ({duration}, {bar_size}) req_id={req_id}")
        return req_id
    
    def get_historical_data(self, req_id: int) -> Optional[List[Bar]]:
        return self._historical_data.get(req_id)
    
    def _handle_tick_price(self, reqId: int, tickType: int, price: float, attrib):
        if reqId not in self._active_subscriptions:
            return
        contract = self._active_subscriptions[reqId]
        quote = self._quotes.get(contract.symbol)
        if not quote:
            return
        quote.timestamp = datetime.now()
        if tickType == TICK_BID:
            quote.bid = price
        elif tickType == TICK_ASK:
            quote.ask = price
        elif tickType == TICK_LAST:
            quote.last = price
        if reqId in self._tick_callbacks:
            try:
                self._tick_callbacks[reqId](quote)
            except Exception as e:
                logger.error(f"Error in tick callback: {e}")
    
    def _handle_tick_size(self, reqId: int, tickType: int, size: int):
        if reqId not in self._active_subscriptions:
            return
        contract = self._active_subscriptions[reqId]
        quote = self._quotes.get(contract.symbol)
        if not quote:
            return
        quote.timestamp = datetime.now()
        if tickType == TICK_BID_SIZE:
            quote.bid_size = size
        elif tickType == TICK_ASK_SIZE:
            quote.ask_size = size
        elif tickType == TICK_LAST_SIZE:
            quote.last_size = size
        elif tickType == TICK_VOLUME:
            quote.volume = size
        if reqId in self._tick_callbacks:
            try:
                self._tick_callbacks[reqId](quote)
            except Exception as e:
                logger.error(f"Error in tick callback: {e}")
    
    def _handle_historical_data(self, reqId: int, bar):
        if reqId not in self._historical_data:
            return
        bar_obj = Bar(symbol="", timestamp=datetime.strptime(bar.date, "%Y%m%d %H:%M:%S"), open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume, count=bar.barCount if hasattr(bar, 'barCount') else 0, wap=bar.average if hasattr(bar, 'average') else 0.0)
        self._historical_data[reqId].append(bar_obj)
    
    def _handle_historical_data_end(self, reqId: int, start: str, end: str):
        if reqId not in self._historical_data:
            return
        bars = self._historical_data[reqId]
        logger.info(f"Historical data complete: req_id={reqId}, bars={len(bars)}")
        if reqId in self._historical_callbacks:
            try:
                self._historical_callbacks[reqId](bars)
            except Exception as e:
                logger.error(f"Error in historical callback: {e}")
    
    def __repr__(self) -> str:
        active = len(self._active_subscriptions)
        return f"MarketDataAdapter({active} active subscriptions)"
