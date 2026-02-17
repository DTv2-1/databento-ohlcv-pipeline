"""
MIC (Module Interface Contracts)

Defines the exact inputs PA accepts and outputs PA emits.
PA is a thin broker pipe — these contracts are its boundaries.
"""

from .pa_outputs import (
    QuoteEvent,
    BarEvent,
    OrderUpdateEvent,
    FillEvent,
    PositionEvent,
    AccountValueEvent,
    ConnectionEvent,
    PAOutputStream,
)

from .pa_inputs import (
    PlaceOrderCommand,
    CancelOrderCommand,
    ModifyOrderCommand,
    FlattenCommand,
    SubscribeMarketDataCommand,
    UnsubscribeMarketDataCommand,
    HistoricalDataCommand,
    PAInputStream,
)

__all__ = [
    # Outputs (PA → downstream)
    "QuoteEvent",
    "BarEvent",
    "OrderUpdateEvent",
    "FillEvent",
    "PositionEvent",
    "AccountValueEvent",
    "ConnectionEvent",
    "PAOutputStream",
    # Inputs (OE → PA)
    "PlaceOrderCommand",
    "CancelOrderCommand",
    "ModifyOrderCommand",
    "FlattenCommand",
    "SubscribeMarketDataCommand",
    "UnsubscribeMarketDataCommand",
    "HistoricalDataCommand",
    "PAInputStream",
]
