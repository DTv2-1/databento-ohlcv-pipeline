"""
Test Tradovate API without SEC field
Some accounts may not require the API key for basic authentication
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_without_sec():
    """Try authentication without sec field"""
    
    credentials_with_sec = {
        'name': os.getenv('TRADOVATE_USERNAME'),
        'password': os.getenv('TRADOVATE_PASSWORD'),
        'appId': os.getenv('TRADOVATE_APP_ID'),
        'appVersion': os.getenv('TRADOVATE_APP_VERSION'),
        'cid': int(os.getenv('TRADOVATE_CID', '0')),
        'deviceId': os.getenv('TRADOVATE_DEVICE_ID'),
        'sec': ''  # Empty
    }
    
    # Try without sec field at all
    credentials_no_sec = {
        'name': os.getenv('TRADOVATE_USERNAME'),
        'password': os.getenv('TRADOVATE_PASSWORD'),
        'appId': os.getenv('TRADOVATE_APP_ID'),
        'appVersion': os.getenv('TRADOVATE_APP_VERSION'),
        'deviceId': os.getenv('TRADOVATE_DEVICE_ID')
        # No cid, no sec
    }
    
    for env_name, url in [('DEMO', 'https://demo.tradovateapi.com/v1'), 
                           ('LIVE', 'https://live.tradovateapi.com/v1')]:
        
        print(f"\n{'='*60}")
        print(f"Testing {env_name} - With empty 'sec' field")
        print(f"{'='*60}")
        
        try:
            resp = requests.post(
                f"{url}/auth/accesstokenrequest",
                headers={'Content-Type': 'application/json'},
                json=credentials_with_sec,
                timeout=10
            )
            
            print(f"Status: {resp.status_code}")
            data = resp.json()
            
            if resp.status_code == 200 and 'accessToken' in data:
                print("✅ SUCCESS! Authentication worked without sec!")
                print(f"Token: {data['accessToken'][:30]}...")
                return
            else:
                print(f"❌ Error: {data.get('errorText', data)}")
        
        except Exception as e:
            print(f"❌ Exception: {e}")
        
        print(f"\n{'='*60}")
        print(f"Testing {env_name} - Without 'sec' and 'cid' fields")
        print(f"{'='*60}")
        
        try:
            resp = requests.post(
                f"{url}/auth/accesstokenrequest",
                headers={'Content-Type': 'application/json'},
                json=credentials_no_sec,
                timeout=10
            )
            
            print(f"Status: {resp.status_code}")
            data = resp.json()
            
            if resp.status_code == 200 and 'accessToken' in data:
                print("✅ SUCCESS! Authentication worked without sec/cid!")
                print(f"Token: {data['accessToken'][:30]}...")
                return
            else:
                print(f"❌ Error: {data.get('errorText', data)}")
        
        except Exception as e:
            print(f"❌ Exception: {e}")
    
    print("\n" + "="*60)
    print("❌ ALL ATTEMPTS FAILED")
    print("="*60)
    print("\nConclusion: You MUST obtain the API key (TRADOVATE_SEC)")
    print("See instructions above for how to get it.")
    print()

if __name__ == "__main__":
    print("\n" + "="*60)
    print("   TESTING WITHOUT API KEY")
    print("="*60)
    test_without_sec()
