"""
Databento API Connection Test
Tests basic connectivity and API key validation
"""

import databento as db
import os
from dotenv import load_dotenv


def test_databento_connection():
    """Test basic connection to Databento API"""
    print("Testing Databento API connection...")
    
    # Load API key
    load_dotenv()
    api_key = os.getenv('DATABENTO_API_KEY')
    
    if not api_key:
        print("ERROR: DATABENTO_API_KEY not found in .env")
        print("\nPlease create a .env file with:")
        print("DATABENTO_API_KEY=your-api-key-here")
        return False
    
    try:
        # Create client
        client = db.Historical(api_key)
        print("SUCCESS: Databento client created successfully")
        
        # Test: get available datasets
        datasets = client.metadata.list_datasets()
        print(f"SUCCESS: Available datasets: {len(datasets)}")
        print("\nDatasets:")
        for dataset in datasets[:5]:  # Show first 5
            print(f"  - {dataset}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Connection failed: {str(e)}")
        return False


if __name__ == "__main__":
    success = test_databento_connection()
    if success:
        print("\nSUCCESS: Ready to proceed with development!")
    else:
        print("\nERROR: Fix connection issues before continuing")
