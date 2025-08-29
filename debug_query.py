#!/usr/bin/env python3
"""
Debug Salesforce Query
=====================

Test the Salesforce query that's causing the backup script to hang.
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

def test_salesforce_connection():
    """Test basic Salesforce connection."""
    try:
        print("🔌 Testing Salesforce connection...")
        sf = Salesforce(
            username=SALESFORCE_CONFIG["username"],
            password=SALESFORCE_CONFIG["password"],
            security_token=SALESFORCE_CONFIG["security_token"],
            domain=SALESFORCE_CONFIG["domain"]
        )
        print("✅ Salesforce connection successful")
        return sf
    except Exception as e:
        print(f"❌ Salesforce connection failed: {e}")
        return None

def test_basic_query(sf):
    """Test basic DocListEntry__c query."""
    try:
        print("🔍 Testing basic DocListEntry__c query...")
        
        # First, just count records
        count_result = sf.query("SELECT COUNT() FROM DocListEntry__c")
        total_count = count_result['totalSize']
        print(f"📊 Total DocListEntry__c records: {total_count}")
        
        if total_count == 0:
            print("⚠️  No DocListEntry__c records found!")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Basic query failed: {e}")
        return False

def test_filtered_query(sf):
    """Test the actual filtered query used in migration."""
    try:
        print("🔍 Testing filtered DocListEntry__c query...")
        
        # Test the exact query from the migration script
        query = """
            SELECT COUNT()
            FROM DocListEntry__c 
            WHERE Document__c != NULL 
            AND Account__c != NULL
        """
        
        result = sf.query(query)
        filtered_count = result['totalSize']
        print(f"📊 Filtered DocListEntry__c records (with Document__c and Account__c): {filtered_count}")
        
        if filtered_count == 0:
            print("⚠️  No records match the migration criteria!")
            print("   - Records must have Document__c field populated")
            print("   - Records must have Account__c field populated")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Filtered query failed: {e}")
        return False

def test_sample_query(sf):
    """Test getting a few sample records."""
    try:
        print("🔍 Testing sample record retrieval...")
        
        # Get just 5 records to test the full query structure
        query = """
            SELECT Id, Name, Document__c, Account__c, Account__r.Name, 
                   LastModifiedDate, CreatedDate, SystemModstamp
            FROM DocListEntry__c 
            WHERE Document__c != NULL 
            AND Account__c != NULL
            LIMIT 5
        """
        
        result = sf.query(query)
        records = result['records']
        
        print(f"📊 Sample records retrieved: {len(records)}")
        
        for i, record in enumerate(records, 1):
            print(f"   {i}. {record['Id']} - Account: {record.get('Account__r', {}).get('Name', 'Unknown')}")
            print(f"      Document URL: {record['Document__c'][:50]}..." if record['Document__c'] else "      No Document URL")
        
        return True
    except Exception as e:
        print(f"❌ Sample query failed: {e}")
        return False

def main():
    """Main debug function."""
    print("=" * 60)
    print("SALESFORCE QUERY DEBUGGING")
    print("=" * 60)
    
    # Test connection
    sf = test_salesforce_connection()
    if not sf:
        return
    
    print()
    
    # Test basic query
    if not test_basic_query(sf):
        return
    
    print()
    
    # Test filtered query  
    if not test_filtered_query(sf):
        return
    
    print()
    
    # Test sample records
    test_sample_query(sf)
    
    print()
    print("=" * 60)
    print("✅ All queries successful! The migration should work.")
    print("   If backup_only_migration.py is still hanging, it might be:")
    print("   1. Processing a very large dataset")
    print("   2. Network timeout issue")
    print("   3. Database connection issue")
    print("=" * 60)

if __name__ == "__main__":
    main()