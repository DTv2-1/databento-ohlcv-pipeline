## TRADOVATE liquidatePosition

** the most relevant examples are cited in this document
- Google search AI
- Tradovate doc: page 16, 152-55

** Additional examples can be found on pages 142, 174 of the Tradovate API pdf

** page 154 also includes placeOrderResult, 

___


## GOOGLE AI OVERVIEW

** Search link: https://bit.ly/4qGDTP0

The liquidatePosition endpoint in the Tradovate API is a POST request used to flatten an open position for a specific contract. 

It functions by placing an order to zero out your position at the market, which means it requires market hours to work. 


# Endpoint Details

** URL: ** https://[environment] (where [environment] is likely demo or live)

** Method: ** POST

** Authentication: ** Requires an API key with appropriate permissions (e.g., for placing orders).

** Body Parameters (JSON):
	* accountId (integer): The ID of your trading account.
	* contractId (integer): The unique ID for the specific contract you want to liquidate.
	* admin (boolean, optional): Set to false for normal user requests. 
	
___


# How to Use liquidatePosition

To liquidate a position successfully, you generally need to perform the following steps in sequence: 

** 1. Get Open Positions: **  First, call the /position/list endpoint to identify all your current open positions and retrieve their respective contractId and accountId values.

** 2. Iterate and Liquidate: **  For each non-flat position found, make a separate POST request to the /order/liquidateposition endpoint, providing the correct accountId and contractId for that specific position.

** 3. Handle Market Hours: ** The liquidation process involves placing a market order, so it must be executed during active market hours. 

This mirrors the functionality of the "Exit at Market and Cancel All" button in the Tradovate web interface, which iterates through your positions and calls this API endpoint for each one.


///////////////////////////////////


## GOOGLE AI DETAILS: liquidatePosition

The liquidatePosition endpoint in the Tradovate API is used to close all open positions for a specific contract in a single account. 


# Endpoint Details

** Path: ** POST /order/liquidatePosition

** Base URL:

	* Live: live.tradovateapi.com

	* Demo: demo.tradovateapi.com 

___


# Request Body Fields

To use this endpoint, you must provide a JSON body with the following fields: 

** accountId (Integer): ** The unique ID of the trading account. You can find this via the /account/list endpoint.

** contractId (Integer): ** The internal ID for the specific instrument (e.g., NQ, ES). This is not the symbol name (like "MNQU1"). You must obtain this ID using the /contract/find or /contract/suggest endpoints.

** admin (Boolean): ** Typically set to false. Setting it to true may require higher-level permissions and can lead to "Access Denied" errors if not authorized.

___


# Behavior and Limitations

** Functionality: ** It attempts to "flatten" your position by placing market orders to zero out your net position for the specified contract. It also cancels pending orders for that specific contract.

** One Contract at a Time: ** This endpoint does not liquidate all positions across an entire account in one call. To liquidate everything, you must iterate through your open positions (found via /position/list) and call liquidatePosition for each unique contractId.

** Market Hours: ** Liquidation requests will only execute during active market hours.

** Permissions: ** Your API Key permissions must include "Trade" or "Order Management" access. 
If you receive a 401 Unauthorized error, ensure your account has paid for the $25/month API Access add-on and your key has the correct scopes. 


___


# Example JSON Request

{
  "accountId": 123456,
  "contractId": 654321,
  "admin": false
}


///////////////////////////////////


# GOOGLE AI: How can I iterate through open positions and use the liquidatePosition endpoint in Python?

To iterate through and liquidate all open positions, you must first retrieve the list of active positions and then loop through them to call the liquidatePosition endpoint for each specific contractId.

** 1. Retrieve Open Positions
Use the /position/list endpoint to get all positions for your user. You must then filter these for positions where the netPos (net position) is not zero. 

** 2. Python Implementation Example
This script assumes you have already obtained a valid access token.

___


** Python 

import requests

# API Configuration
BASE_URL = "demo.tradovateapi.com" # Use 'live' for real trading
ACCESS_TOKEN = "your_access_token_here"
HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

def liquidate_all_positions():
    # Step 1: Get the list of all positions
    pos_response = requests.get(f"{BASE_URL}/position/list", headers=HEADERS)
    
    if pos_response.status_code != 200:
        print(f"Error fetching positions: {pos_response.text}")
        return

    positions = pos_response.json()

    # Step 2: Iterate and liquidate non-flat positions
    for pos in positions:
        # A position is 'open' if netPos is not 0
        if pos.get("netPos") != 0:
            contract_id = pos.get("contractId")
            account_id = pos.get("accountId")
            
            print(f"Liquidating Contract ID {contract_id} for Account {account_id}...")
            
            # Step 3: Call liquidatePosition
            liq_payload = {
                "accountId": account_id,
                "contractId": contract_id,
                "admin": False
            }
            
            liq_response = requests.post(
                f"{BASE_URL}/order/liquidatePosition", 
                headers=HEADERS, 
                json=liq_payload
            )
            
            if liq_response.status_code == 200:
                print(f"Successfully sent liquidation request for {contract_id}")
            else:
                print(f"Failed to liquidate {contract_id}: {liq_response.text}")

if __name__ == "__main__":
    liquidate_all_positions()


___



# Key Considerations for 2026

** API Access Subscription: ** Ensure your Tradovate account has an active API Access add-on ($25/month), or the requests will return a 401 Unauthorized error.

** Market Hours: ** Liquidation requests are technically market orders and will only be processed during active market hours.

** Rate Limits: ** Tradovate typically limits actions to 5,000 unique actions per 60 minutes. If you have a massive number of positions, be mindful of this threshold.

** Admin Flag: ** Always set "admin": false in the payload to avoid permission-related "Access Denied" errors.



///////////////////////////////////


## TRADOVATE API DOCUMENTATION


# Page 141

** liquidatePosition

This request initiates the cancellation process of open orders for an existing position held by this account.

Note: This is a request to cancel orders and close a position, not a guarantee. Any operation could
fail for a number of reasons, ranging from Exchange rejection to incorrect parameterization.

** see full documentation on pages 141-44
