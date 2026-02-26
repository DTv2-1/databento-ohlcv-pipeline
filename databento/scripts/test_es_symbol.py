"""Test ES futures symbol formats on Massive.com"""
from massive import RESTClient
from dotenv import load_dotenv
import os

load_dotenv()
client = RESTClient(os.getenv('MASSIVE_API_KEY'))

test_symbols = ['ES', 'ESH24', '/ES', 'ES=F', 'ESH4']
for sym in test_symbols:
    try:
        aggs = list(client.list_aggs(sym, 1, 'minute', '2024-03-01', '2024-03-02', limit=5))
        print(f"{sym}: {len(aggs)} results")
        if aggs:
            print(f"  Sample: o={aggs[0].open} h={aggs[0].high} v={aggs[0].volume}")
    except Exception as e:
        print(f"{sym}: ERROR - {str(e)[:100]}")
