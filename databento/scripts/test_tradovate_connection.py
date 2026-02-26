"""
Test Tradovate API Connection

This script tests the authentication and basic connectivity to the Tradovate API.
Based on official Tradovate API documentation examples.
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Tradovate API Configuration
DEMO_URL = "https://demo.tradovateapi.com/v1"
LIVE_URL = "https://live.tradovateapi.com/v1"
MARKET_DATA_WS_URL = "wss://md.tradovateapi.com/v1/websocket"

def get_credentials():
    """Load credentials from .env file"""
    credentials = {
        'name': os.getenv('TRADOVATE_USERNAME'),
        'password': os.getenv('TRADOVATE_PASSWORD'),
        'appId': os.getenv('TRADOVATE_APP_ID'),
        'appVersion': os.getenv('TRADOVATE_APP_VERSION'),
        'cid': int(os.getenv('TRADOVATE_CID', '0')),
        'deviceId': os.getenv('TRADOVATE_DEVICE_ID'),
        'sec': os.getenv('TRADOVATE_SEC', '')  # API key/secret
    }
    
    # Validate required credentials
    missing = [k for k, v in credentials.items() if not v and k != 'sec']
    if missing:
        print(f"❌ Missing required credentials: {', '.join(missing)}")
        print("\nPlease check your .env file contains:")
        for key in missing:
            print(f"  TRADOVATE_{key.upper()}=<value>")
        sys.exit(1)
    
    if not credentials['sec']:
        print("⚠️  WARNING: TRADOVATE_SEC (API key) is empty!")
        print("   You may not be able to authenticate without it.")
        print("   Check your email from Tradovate or contact support.\n")
    
    return credentials


def test_authentication(use_demo=True):
    """Test authentication with Tradovate API"""
    url = DEMO_URL if use_demo else LIVE_URL
    endpoint = f"{url}/auth/accesstokenrequest"
    
    credentials = get_credentials()
    
    print(f"\n{'='*60}")
    print(f"Testing Authentication on {'DEMO' if use_demo else 'LIVE'} Environment")
    print(f"{'='*60}")
    print(f"Endpoint: {endpoint}")
    print(f"Username: {credentials['name']}")
    print(f"App ID:   {credentials['appId']}")
    print(f"Device:   {credentials['deviceId']}")
    print(f"CID:      {credentials['cid']}")
    print(f"Sending request...")
    
    try:
        response = requests.post(
            endpoint,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            json=credentials,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Track which environment worked
            data['_source'] = 'demo' if use_demo else 'live'
            
            if 'errorText' in data:
                print(f"\n❌ Authentication Failed!")
                print(f"   Error: {data['errorText']}")
                return None
            
            print(f"\n✅ Authentication Successful!")
            print(f"\n📊 Response Details:")
            print(f"   User ID:        {data.get('userId')}")
            print(f"   User Name:      {data.get('name')}")
            print(f"   User Status:    {data.get('userStatus')}")
            print(f"   Has Live:       {data.get('hasLive', False)}")
            print(f"   Access Token:   {data.get('accessToken')[:20]}...") 
            print(f"   MD Access Token:{data.get('mdAccessToken')[:20]}...")
            print(f"   Expires:        {data.get('expirationTime')}")
            
            return data
        
        else:
            print(f"\n❌ HTTP Error {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data}")
            except:
                print(f"   Response: {response.text}")
            return None
    
    except requests.exceptions.Timeout:
        print(f"\n❌ Request timed out after 10 seconds")
        return None
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Connection error - check your internet connection")
        return None
    except Exception as e:
        print(f"\n❌ Unexpected error: {type(e).__name__}: {e}")
        return None


def test_account_list(access_token, use_demo=True):
    """Test fetching account list with the access token"""
    url = DEMO_URL if use_demo else LIVE_URL
    endpoint = f"{url}/account/list"
    
    print(f"\n{'='*60}")
    print(f"Testing Account List Endpoint")
    print(f"{'='*60}")
    print(f"Endpoint: {endpoint}")
    
    try:
        response = requests.get(
            endpoint,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            accounts = response.json()
            
            if isinstance(accounts, list):
                print(f"\n✅ Retrieved {len(accounts)} account(s)")
                
                for i, acc in enumerate(accounts, 1):
                    print(f"\n   Account {i}:")
                    print(f"   - ID:          {acc.get('id')}")
                    print(f"   - Name:        {acc.get('name')}")
                    print(f"   - Type:        {acc.get('accountType')}")
                    print(f"   - Active:      {acc.get('active')}")
                    print(f"   - Margin Type: {acc.get('marginAccountType')}")
                
                return accounts
            else:
                print(f"\n❌ Unexpected response format: {accounts}")
                return None
        
        else:
            print(f"\n❌ HTTP Error {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data}")
            except:
                print(f"   Response: {response.text}")
            return None
    
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        return None


def main():
    """Main test function"""
    print("\n" + "="*60)
    print("   TRADOVATE API CONNECTION TEST")
    print("="*60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Try DEMO first
    print("\n🔍 Attempting DEMO environment first...")
    auth_data = test_authentication(use_demo=True)
    
    # If DEMO fails, try LIVE
    if not auth_data:
        print("\n🔍 DEMO failed. Trying LIVE environment...")
        print("   (Pete's credentials may be for LIVE account only)")
        auth_data = test_authentication(use_demo=False)
    
    if not auth_data:
        print("\n" + "="*60)
        print("❌ BOTH DEMO AND LIVE AUTHENTICATION FAILED")
        print("="*60)
        print("\nPossible reasons:")
        print("1. Missing TRADOVATE_SEC (API key) - check Pete's email from Tradovate")
        print("2. Credentials are incorrect or expired")
        print("3. Account needs API access enabled")
        print("4. Two-factor authentication required")
        print("\nAction items:")
        print("• Check email from Tradovate for API key (TRADOVATE_SEC)")
        print("• Verify username/password are correct")
        print("• Contact Tradovate support if issues persist")
        print("\n")
        sys.exit(1)
    
    # Test account list
    use_demo = auth_data.get('_source') == 'demo'
    access_token = auth_data.get('accessToken')
    if access_token:
        test_account_list(access_token, use_demo=use_demo)
    
    print("\n" + "="*60)
    print("   ✅ TEST COMPLETE - AUTHENTICATION SUCCESSFUL")
    print("="*60)
    print("\nNext Steps:")
    print("1. ✅ Authentication working!")
    print("2. Test WebSocket connections for real-time data")
    print("3. Explore market data endpoints (bars, ticks)")
    print("4. Test order placement on demo account")
    print("\n")


if __name__ == "__main__":
    main()
