## TRADOVATE getChart

** the most relevant examples are cited in this document
- Google search AI
- Tradovate doc: page 32

___


## GOOGLE AI OVERVIEW

** Search link: https://bit.ly/4qGTzSj

To stream real-time bar data from the Tradovate API in 2026, you must navigate specific licensing requirements and use the Market Data WebSocket endpoint. 

** 1. Mandatory Prerequisites

- Before attempting to stream data, you must meet these regulatory and subscription requirements: 

- API Access Subscription: You must have an active "API Access" add-on, typically costing $25/month.

- CME Sub-Vendor Registration: Standard market data subscriptions (e.g., for the web trader) do not cover API usage. To stream real-time market data through the API, you must sign a CME Information License Agreement (ILA) and become a registered sub-vendor.


** 2. Connect to the Market Data WebSocket

- Streaming occurs via the dedicated Market Data WebSocket URL: 

- Live: wss://md.tradovateapi.com/v1/websocket

- Demo: wss://demo.tradovateapi.com/v1/websocket (Note: Historical/demo data may still require authentication). 


** 3. Request Real-Time Bar Data

- To receive streamed bars, use the md/getChart endpoint within the WebSocket connection. This request initializes a subscription that pushes new bars as they form. 
Request Structure (md/getChart):

{
  "symbol": "ESM6", // Your instrument symbol
  "chartDescription": {
    "underlyingType": "MinuteBar", // Options: Tick, DailyBar, MinuteBar, Custom
    "elementSize": 1,              // For 1-minute bars
    "elementSizeUnit": "UnderlyingUnits",
    "withHistogram": false
  },
  "timeRange": {
    "asMuchAsElements": 100        // Number of historical bars to load first
  }
}


** 4. Handling the Streamed Data

- Subscription ID: The server's first response to md/getChart contains a subscriptionId (or realtimeId). You must use this ID to identify incoming data or to eventually unsubscribe using md/cancelChart.

- End of History (EOH): After the initial historical bars (e.g., the last 100) are sent, the server sends an object: { "id": 12345, "eoh": true }. Every bar received after this flag is a real-time update.

- Data Structure: Incoming bars are usually provided as arrays. New bars are typically added to the end (tail) of the array as they complete.


___


# Getting Bar Data 

As far as I can tell, there are two ways to get sub 1-minute bars. 
The first is to call 1-min bars and use a decimal for anything below


# Minute Bars

{
  "symbol": "ESM6", // Your instrument symbol
  "chartDescription": {
    "underlyingType": "MinuteBar", // Options: Tick, DailyBar, MinuteBar, Custom
    "elementSize": 0.25,              // For 15-sec bars. For 1 minute bars set elementSize to 1
    "elementSizeUnit": "UnderlyingUnits",
    "withHistogram": false
  },
  "timeRange": {
    "asMuchAsElements": 100        // Number of historical bars to load first
  }
}


## Tick Bars

** 1. Request Configuration

Unlike standard minute bars, second-based intervals are requested by setting the underlyingType to "Tick" and the elementSizeUnit to "Seconds". 

* For 15-Second Bars:

{
  "symbol": "ESM6", 
  "chartDescription": {
    "underlyingType": "Tick",
    "elementSize": 15,
    "elementSizeUnit": "Seconds",
    "withHistogram": false
  },
  "timeRange": {
    "asMuchAsElements": 100
  }
}


* For 30-Second Bars:
Simply change the elementSize to 30 while keeping the other parameters the same. 


** 2. Implementation Steps
- WebSocket Connection: Connect to the market data endpoint: wss://md.tradovateapi.com.

- Authentication: Send your authorization token immediately upon opening the connection.

- Subscription: Send the JSON request above. The server will respond with a realtimeId (or subscriptionId).

- Handling History: The API will first stream the requested number of historical bars (e.g., 100).

- Streaming Real-Time: Once the server sends an object containing { "eoh": true } (End of History), every subsequent message for that subscriptionId is a real-time bar update.


** 3. Critical 2026 Requirements

- CME Sub-Vendor Licensing: As of early 2026, streaming real-time data via the API (not the web platform) requires you to be a registered CME sub-vendor, which typically carries a significant monthly fee (often reported between $290–$500/month).

- Heartbeats: You must send a heartbeat frame (typically just the character [] or a specific ping) every 2.5 seconds to prevent the socket from timing out.

- Bar Updates: For sub-minute intervals, you will receive updates as the bar forms. You must track the timestamp to determine when a bar has "closed" and a new one has begun.



///////////////////////////////////


## TRADOVATE API DOCUMENTATION


# getChart

https://api.tradovate.com/#tag/Market-Data/Request-Reference/Get-Chart

** Description: 
Client may have multiple charts for the same contract, so the response for md/getChart request contains a subscription ID to properly track and unsubscribe from a real-time chart subscription. If you're using JavaScript, don't forget to check the section on charts in our API's comprehensive JavaScript tutorial.

** Endpoint: ** md/getChart

** Parameters:

{
  "symbol":"ESM7" | 123456,
  "chartDescription": {
    "underlyingType":"MinuteBar", // Available values: Tick, DailyBar, MinuteBar, Custom, DOM
    "elementSize":15,
    "elementSizeUnit":"UnderlyingUnits", // Available values: Volume, Range, UnderlyingUnits, Renko, MomentumRange, PointAndFigure, OFARange
    "withHistogram": true | false
  },
  "timeRange": {
    // All fields in "timeRange" are optional, but at least anyone is required
    "closestTimestamp":"2017-04-13T11:33Z",
    "closestTickId":123,
    "asFarAsTimestamp":"2017-04-13T11:33Z",
    "asMuchAsElements":66
  },
}


** Response

- A response for md/getChart request contains two subscription ID, historicalId and realtimeId. 

- Client needs to store realtimeId value to properly cancel real-time chart subscription via md/cancelChart request.

{
  "s":200,
  "i":13,
  "d":{
    "historicalId":32,
    "realtimeId":31
  }
}


** Data message

{
  "e":"chart",
  "d": {
    "charts": [ // "charts" may contain multiple chart objects
      {
        "id":9, // "id" matches either historicalId or realtimeId values from response
        "td":20170413, // Trade date as a number with value YYYYMMDD
        "bars": [ // "bars" may contain multiple bar objects
          {
            "timestamp":"2017-04-13T11:00:00.000Z",
            "open":2334.25,
            "high":2334.5,
            "low":2333,
            "close":2333.75,
            "upVolume":4712.234,
            "downVolume":201.124,
            "upTicks":1333.567,
            "downTicks":82.890,
            "bidVolume":2857.123,
            "offerVolume":2056.224
          }
        ]
      }
    ]
  }
}

___


## Requesting Tick Charts

https://api.tradovate.com/#tag/Using-Tick-Charts

To get Tick Chart data, we can use the same process described in the Market Data section. Just like with Market Data, we need to open and authorize a WebSocket first. If you're following the comprehensive JavaScript tutorial, you can find tick chart examples here.

Just like requesting regular chart data, we must construct a request body with the symbol, chartDescription, and timeRange fields. 

However, we need to lock elementSize to 1 and set underlyingType to "Tick". For example:

{
  "symbol": "ESU9",
  "chartDescription": {
    "underlyingType": "Tick",
    "elementSize": 1,
    "elementSizeUnit": "UnderlyingUnits"
  },
  "timeRange": {
    ...
  }
}

Then client then calls the standard md/getChart endpoint and passes the request to it. 
The Tradovate server responds with the standard JSON object schema for chart data. 
Because an unsubscription request requires the real-time subscription ID sent with this response, the client should store the ID of each subscription that they create so that they can properly unsubscribe later.

___


## Data stream messages

https://api.tradovate.com/#tag/Using-Tick-Charts/Data-stream-messages

A typical data stream message has the following structure:

{
    "charts": [                     // Array of packets.
        {
            "id": 16335,            // Subscription ID, the same as historical/real-time subscription IDs from request response.
            "s": "db",              // Source of packet data.
            "td": 20210718,         // Trade date YYYYMMDD.
            "bp": 11917,            // Base price of the packet (integer number of contract tick sizes).
                                    // Tick prices are calculated as relative from this one.
            "bt": 1563421179735,    // Base timestamp of the packet.
                                    // Tick timestamps are calculated as relative from this value.
            "ts": 0.25,             // Tick size of the contract for which the tick chart is requested.
            "tks": [                // Array of ticks of this packet.
                {
                    "t": 0,         // Tick relative timestamp.
                                    // Actual tick timestamp is packet.bt + tick.t
                    "p": 0,         // Tick relative price (in contract tick sizes).
                                    // Actual tick price is packet.bp + tick.p
                    "s": 3,         // Tick size (seems more proper name should be tick volume).
                                    // Please don't confuse with contract tick size (packet.ts).
                    "b": -1,        // Bid relative price (optional).
                                    // Actual bid price is packet.bp + tick.b
                    "a": 0,         // Ask relative price (optional).
                                    // Actual ask price is packet.bp + tick.a
                    "bs": 122.21,   // Bid size (optional).
                    "as": 28.35,    // Ask size (optional).
                    "id": 11768401  // Tick ID
                },
                ...
            ]
        },
        // Multiple packets are possible...
        {
            "id": 16335,
            eoh: true               // End of history flag.
                                    // If the request time range assumes historical data,
                                    // this flag indicates that historical ticks are loaded and
                                    // further packets will contain real-time ticks.
        }
    ]
};

___


## Using the Tick Stream

The following code snippet is an example of how to process tick chart data stream messages and calculate actual ticks for client consumption.

The function takes a data stream message and converts its packets into a list of actual ticks. 

Usage of this function assumes that you'll be passing it the message data retrieved from the WebSocket. 

** Because tick stream data can arrive out of chronological order, it is the client's responsibility to store and sort pertinent portions of this data.

___


function processTickChartMessage(msg) {
    const result = [];
    if (msg.charts && msg.charts.length) {
        for (let i = 0; i < msg.charts.length; ++i) {
            const packet = msg.charts[i];
            if (packet.eoh) { //end-of-history,
                // Historical ticks are loaded.
            }
            else if (packet.tks && packet.tks.length) {
                for (let j = 0; j < packet.tks.length; ++j) {
                    const tick = packet.tks[j];

                    const timestamp = packet.bt + tick.t;   // Actual tick timestamp
                    const price = packet.bp + tick.p;       // Actual tick price

                    const bid = tick.bs && (packet.bp + tick.b);    // Actual bid price (if bid size defined)
                    const ask = tick.as && (packet.bp + tick.a);    // Actual ask price (if ask size defined)

                    result.push({
                        id: tick.id,
                        timestamp: new Date(timestamp),

                        price: price * packet.ts,           // Tick price as contract price
                        size: tick.s,                       // Tick size (tick volume)

                        bidPrice: bid && (bid * packet.ts), // Bid price as contract price
                        bidSize: tick.bs,

                        askPrice: ask && (ask * packet.ts), // Ask price as contract price
                        askSize: tick.as,
                    });
                }
            }
        }
    }
    return result;
}



## Cancel Chart

https://api.tradovate.com/#tag/Market-Data/Request-Reference/Cancel-Chart

**Endpoint: ** md/cancelChart

** Parameters:

{
  "subscriptionId": 123456 // The value of historical chart subscription ID from `md/getChart` response
}