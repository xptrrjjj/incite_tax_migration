#!/usr/bin/env python3
"""
Debug Account Query
==================

Debug script to check why Account__r relationships aren't working.
"""

from simple_salesforce import Salesforce
import sys

# Import configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found.")
    sys.exit(1)

def debug_accounts():
    """Debug account relationship queries."""
    try:
        print("🔌 Connecting to Salesforce...")
        sf = Salesforce(
            username=SALESFORCE_CONFIG["username"],
            password=SALESFORCE_CONFIG["password"],
            security_token=SALESFORCE_CONFIG["security_token"],
            domain=SALESFORCE_CONFIG["domain"]
        )
        print("✅ Connected successfully")
        
        print("\n1. Testing DocListEntry__c access...")
        count_result = sf.query("SELECT COUNT() FROM DocListEntry__c")
        print(f"   Total DocListEntry__c records: {count_result['totalSize']}")
        
        print("\n2. Testing DocListEntry__c with filters...")
        filtered_count = sf.query("""
            SELECT COUNT() 
            FROM DocListEntry__c 
            WHERE Document__c != NULL 
            AND Account__c != NULL
        """)
        print(f"   Filtered records: {filtered_count['totalSize']}")
        
        print("\n3. Testing Account relationship access...")
        try:
            sample_query = """
                SELECT Id, Account__c, Account__r.Name 
                FROM DocListEntry__c 
                WHERE Document__c != NULL 
                AND Account__c != NULL
                LIMIT 5
            """
            sample_result = sf.query(sample_query)
            print(f"   Sample records with Account__r: {len(sample_result['records'])}")
            
            for i, record in enumerate(sample_result['records'], 1):
                account_id = record.get('Account__c', 'None')
                account_name = record.get('Account__r', {}).get('Name', 'No Name') if record.get('Account__r') else 'No Relationship'
                print(f"     {i}. Account ID: {account_id}, Name: {account_name}")
        
        except Exception as e:
            print(f"   ❌ Account relationship query failed: {e}")
            
            print("\n4. Alternative: Testing direct Account access...")
            try:
                # Get some account IDs first
                account_ids_query = """
                    SELECT Account__c
                    FROM DocListEntry__c 
                    WHERE Document__c != NULL 
                    AND Account__c != NULL
                    GROUP BY Account__c
                    LIMIT 5
                """
                account_ids_result = sf.query(account_ids_query)
                account_ids = [r['Account__c'] for r in account_ids_result['records']]
                
                print(f"   Found {len(account_ids)} unique account IDs")
                
                # Try to get account names directly
                for account_id in account_ids:
                    try:
                        account = sf.Account.get(account_id)
                        print(f"     {account_id}: {account['Name']}")
                    except Exception as e:
                        print(f"     {account_id}: ❌ Cannot access ({e})")
                        
            except Exception as e2:
                print(f"   ❌ Direct account access failed: {e2}")
        
        print("\n5. Testing aggregate query...")
        try:
            # Test the aggregate query that was failing
            agg_query = """
                SELECT Account__c, COUNT(Id)
                FROM DocListEntry__c 
                WHERE Document__c != NULL 
                AND Account__c != NULL
                GROUP BY Account__c
                ORDER BY COUNT(Id) DESC
                LIMIT 5
            """
            agg_result = sf.query(agg_query)
            print(f"   Aggregate query successful: {len(agg_result['records'])} account groups")
            
            for record in agg_result['records']:
                account_id = record['Account__c']
                count = record.get('expr0', 0)
                print(f"     Account {account_id}: {count} files")
                
        except Exception as e:
            print(f"   ❌ Aggregate query failed: {e}")
            
    except Exception as e:
        print(f"❌ Debug failed: {e}")

if __name__ == "__main__":
    debug_accounts()