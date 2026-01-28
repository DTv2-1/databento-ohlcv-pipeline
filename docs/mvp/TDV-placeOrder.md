## TRADOVATE placeOrder

** the most relevant examples are cited in this document
- Google search AI
- Tradovate doc: page 16, 152-55

** Additional examples can be found on pages 142, 174 of the Tradovate API pdf

** page 154 also includes placeOrderResult, 

___


## placeOrder reference code from Google AI search 

** Search link: https://bit.ly/3N0g5XT

The Tradovate API uses specific parameters within a POST request to the /order/placeorder or similar endpoints to execute buy and sell commands. The key "commands" are specific JSON parameters in the request body, such as action: "Buy" or action: "Sell". 

** Key Parameters for Placing Orders

To place an order via the Tradovate API, you construct a JSON object with specific parameters and send it in a POST request. Essential parameters include: 

- accountId: Your specific account identifier.
- accountSpec: Your username or account specification.
- symbol: The symbol of the asset you wish to trade (e.g., "NQZ1", "ESH2").
- action: This defines the "buy" or "sell" command.
   * "Buy" (for spot buying or opening a long position)
   * "Sell" (for spot selling or opening a short position)
- orderQty: The quantity of contracts to trade.
- orderType: The type of order (e.g., "Market", "Limit", "Stop").
- price: The price for limit or stop limit orders. For market orders, the price is not typically specified in the body or is the current market price.
- stopPrice: The stop loss price, used in conjunction with certain order types or bracket orders.


** Requirements for 2026

1. API Subscription: Access still requires a monthly subscription (typically $25/month) through the Tradovate Web Trader under Settings > API Access.

2. Market Data: To receive real-time data via the API (not just sending orders), you may need to register as a sub-vendor with the CME, which involves separate monthly fees.

3. Authentication: All commands must include an Authorization: Bearer [Access_Token] header.

___


** Key API Command Parameters
Parameter 		Description						Valid Options
action			The side of the trade			Buy, Sell
orderType		How the order executes			Market, Limit, Stop, StopLimit
symbol			The contract ticker				e.g., ESH6, MNQH6
orderQty		Number of contracts				Integer (e.g., 1, 5)
price			The price target				Required for Limit and StopLimit (*)
stopPrice		The trigger price				Required for Stop and StopLimit (*)

(*) n/a for our strategy, bc we'll only be using market orders for now


___


**Example JSON Body for a Market Buy Order

Below is an example of a JSON body structure for a simple market buy order. The specific endpoint to use is typically .../order/placeorder.
Note: You must replace YOUR_ACCOUNT_ID, YOUR_USER_NAME, and the symbol with your actual information and desired contract.

{
  "accountId": "YOUR_ACCOUNT_ID",
  "accountSpec": "YOUR_USER_NAME",
  "symbol": "NQH4",
  "action": "Buy",
  "orderQty": 1,
  "orderType": "Market",
  "isAutomated": true
}


___

**Example JSON Body for a Limit Sell Order

This example shows a JSON body for a limit sell order:

{
  "accountId": "YOUR_ACCOUNT_ID",
  "accountSpec": "YOUR_USER_NAME",
  "symbol": "NQH4",
  "action": "Sell",
  "orderQty": 1,
  "orderType": "Limit",
  "price": 14800.00,
  "isAutomated": true
}



///////////////////////////////////


## Found references to placeOrder in the Tradovate API documentation

** Tradovate API site: https://api.tradovate.com/#tag/Orders/operation/placeOrder


Here are all references to placeOrder / /order/placeorder found in Tradovate API (with page numbers):

** Page 16 ** — “For example, /order/placeorder is used to make a request to place order…”

** Page 16 ** — “Here’s a JS example of how to use the placeOrder endpoint with an HTTP POST request.”

** Page 16 ** — JS example line: const response = await fetchURL + '/order/placeorder'

** Page 142 ** — Response type reference: PlaceOrderResult (shown under /order/liquidateposition result block)

** Page 152 ** — Section header: placeOrder (“Make a request to place an order.”)

** Page 152 ** — JS example line: const response = await fetchURL + '/order/placeorder'

** Page 153 ** — JS example line: const response = await fetchURL + '/order/placeorder'

** Page 154 ** — Response type reference: PlaceOrderResult

** Page 154 ** — Endpoint interaction line: Interact POST /order/placeorder

** Page 171 ** — “For more details about working with advanced order types, see placeOrder, placeOCO, and placeOSO.”


///////////////////////////////////


## Page 16

**Submit Data

When using the REST API, the HTTP POST method should be used when we need to submit data. Data
should be formatted as a valid JSON object and passed in the request body for a specified position.

Here's a JS example of how to use the placeOrder endpoint with an HTTP POST request.

const URL = 'demo.tradovateapi.com/v1'
const body = {
    accountSpec : yourUserName,
    accountId : yourAcctId,
    action: "Buy",
    symbol: "MYMM1",
    orderQty : 1,
    orderType : "Market",
    isAutomated : true //must be true if this isn't an order made directly by a human
}

const response = await fetchURL + '/order/placeorder', {  
    method: 'POST',
    headers: {
        'Accept' : 'application/json',
        'Authorization' : $`Bearer myAccessToken `,
    },
    body: JSONstringify(body)
}}

const json = await response json // { orderId: 0000000 }


///////////////////////////////////


## Page 152-55

** placeOrder
Make a request to place an order.
Depending on the order type, the parameters vary. In the Trader application, you can see the details of
placing a standard order ticket by adding the Order Ticket module to your workspace.

** Market Order

const URL = 'demo.tradovateapi.com/v1'
const body = {
    accountSpec: yourUserName,
    accountId: yourAcctId,
    action: "Buy",
    symbol: "MYMM1",
    orderQty: 1,
    orderType: "Market",
    isAutomated: true //must be true if this isn't an order made directly by a human
}

const response = await fetch(URL + '/order/placeorder', {
    method: 'POST',
    headers: {
        'Accept': 'application/json',
        'Authorization': `Bearer ${myAccessToken}`,
    },
    body: JSON.stringify(body)
})

const json = await response.json() // { orderId: 0000000 }

** Responses

PlaceOrderResult

{
	"accountSpec": "string",
	"accountId": 0,
	"clOrdId": "string",
	"action": "Buy",
	"symbol": "string",
	"orderQty": 0,
	"orderType": "Limit",
	"price": 0.1,
	"stopPrice": 0.1,
	"maxShow": 0,
	"pegDifference": 0.1,
	"timeInForce": "Day",
	"expireTime": "2019-08-24T14:15:22Z",
	"text": "string",
	"activationTime": "2019-08-24T14:15:22Z",
	"customTag50": "string",
	"isAutomated": true
}



//////////////////////////////


## placeOrderResult


# Google Search AI: # 
https://bit.ly/451OOdB

The placeOrderResult is likely the JSON object returned by the Tradovate API's /order/placeOrder endpoint, containing details about the success or failure of the order submission and an orderId that you can use to track the order's lifecycle. 

It is not a specific, predefined, singular variable name but rather a generic description of the entire response object or structure you receive after making a call to place an order.


___


** Key Components of the placeOrder Response

While the exact schema is detailed in the official Tradovate API Documentation (which requires a login to view fully), based on forum discussions, the response generally includes:

- id or orderId: A unique identifier for the order you just placed. You use this ID to match subsequent events related to this specific order.

- ordStatus: The initial status of the order, such as "Working" or potentially "Rejected" if there was an immediate issue.

- timestamp: The time the order was processed by the server.

- error (if applicable): If the order submission fails, the response will contain error information, such as "Access is denied" or other validation errors. 

- Success Status: Confirmation that the server has accepted the request.

- Error Details: If the request fails (e.g., due to insufficient margin or incorrect parameters), the result will instead contain error codes such as RiskRejected or Access denied. 


___


** How to Use the Result

The primary purpose of the placeOrderResult is to provide confirmation and the necessary orderId to track the order asynchronously.


** 1. Capture the orderId: 
After successfully submitting the order via the REST endpoint, extract the orderId from the response.


** 2. Use WebSockets for updates: 
The order's actual execution, filling, or cancellation status is communicated via real-time updates through the user/syncRequest WebSocket connection. You should listen for ExecutionReport events on the WebSocket using the captured orderId to know when the order is "Filled" or "Complete".


___


** Usage and Workflow

** 1. Placement: 
You send a POST request to /order/placeOrder with required parameters like symbol, action (Buy/Sell), orderQty, and orderType.

** 2. Handling the Response: 
You receive the placeOrderResult. You should store the orderId immediately.

** 3. Tracking: 
Because the REST response only confirms receipt, you must use a WebSocket subscription to user/syncRequest to listen for an ExecutionReport matching your orderId to know when the order is actually filled.


___


# Tradovate documentation