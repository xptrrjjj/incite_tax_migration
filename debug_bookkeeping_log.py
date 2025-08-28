#!/usr/bin/env python3
"""
BookkeepingLog Debug
===================

This script investigates the BookkeepingLog__c custom object to find file references.
"""

import sys
import json
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

# Import configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)

def investigate_bookkeeping_log():
    """Investigate BookkeepingLog__c custom object in detail."""
    
    try:
        # Authenticate with Salesforce
        print("Connecting to Salesforce...")
        sf = Salesforce(
            username=SALESFORCE_CONFIG["username"],
            password=SALESFORCE_CONFIG["password"],
            security_token=SALESFORCE_CONFIG["security_token"],
            domain=SALESFORCE_CONFIG["domain"]
        )
        print("✓ Successfully connected to Salesforce")
        
        # Get the Account ID
        print("\n1. Looking up Account ID for BBarth2559...")
        account_query = """
            SELECT Id, Name
            FROM Account
            WHERE Name = 'BBarth2559'
            AND IsDeleted = FALSE
            LIMIT 1
        """
        
        account_result = sf.query(account_query)
        if not account_result['records']:
            print("❌ No account found with name: BBarth2559")
            return
        
        account_id = account_result['records'][0]['Id']
        account_name = account_result['records'][0]['Name']
        print(f"✓ Found Account: {account_name} (ID: {account_id})")
        
        # 2. Describe the BookkeepingLog__c object to see its fields
        print(f"\n2. Describing BookkeepingLog__c object structure...")
        try:
            bookkeeping_desc = sf.BookkeepingLog__c.describe()
            
            print(f"✓ BookkeepingLog__c object found")
            print(f"Label: {bookkeeping_desc['label']}")
            print(f"Fields: {len(bookkeeping_desc['fields'])}")
            
            # Show all fields
            print(f"\nAll fields in BookkeepingLog__c:")
            for field in bookkeeping_desc['fields']:
                field_name = field['name']
                field_type = field['type']
                field_label = field['label']
                print(f"  - {field_name} ({field_type}): {field_label}")
            
        except Exception as e:
            print(f"Error describing BookkeepingLog__c: {e}")
            return
        
        # 3. Query all records linked to our account
        print(f"\n3. Querying BookkeepingLog__c records linked to BBarth2559...")
        try:
            # First, try with Account__c field
            bookkeeping_query = f"""
                SELECT Id, Name, Account__c
                FROM BookkeepingLog__c
                WHERE Account__c = '{account_id}'
                AND IsDeleted = FALSE
            """
            
            bookkeeping_result = sf.query_all(bookkeeping_query)
            
            if not bookkeeping_result['records']:
                print("No records found with Account__c field, trying other field names...")
                
                # Try different field names
                for field_suffix in ['AccountId__c', 'Account_Id__c', 'RelatedAccount__c']:
                    try:
                        alt_query = f"""
                            SELECT Id, Name, {field_suffix}
                            FROM BookkeepingLog__c
                            WHERE {field_suffix} = '{account_id}'
                            AND IsDeleted = FALSE
                        """
                        alt_result = sf.query_all(alt_query)
                        if alt_result['records']:
                            bookkeeping_result = alt_result
                            print(f"✓ Found records using {field_suffix} field")
                            break
                    except:
                        continue
            
            if not bookkeeping_result['records']:
                print("❌ No BookkeepingLog__c records found linked to BBarth2559")
                return
            
            print(f"✓ Found {len(bookkeeping_result['records'])} BookkeepingLog__c records")
            
        except Exception as e:
            print(f"Error querying BookkeepingLog__c: {e}")
            return
        
        # 4. Get full details of each record
        print(f"\n4. Getting full details of BookkeepingLog__c records...")
        
        for i, record in enumerate(bookkeeping_result['records'], 1):
            record_id = record['Id']
            record_name = record.get('Name', 'N/A')
            
            print(f"\n--- Record {i}: {record_name} (ID: {record_id}) ---")
            
            # Get all fields for this record
            try:
                # Build a query with all available fields
                field_names = [field['name'] for field in bookkeeping_desc['fields'] if field['name'] not in ['Id']]
                fields_str = ', '.join(field_names)
                
                detailed_query = f"""
                    SELECT Id, {fields_str}
                    FROM BookkeepingLog__c
                    WHERE Id = '{record_id}'
                """
                
                detailed_result = sf.query(detailed_query)
                
                if detailed_result['records']:
                    detailed_record = detailed_result['records'][0]
                    
                    print("All field values:")
                    for field_name, value in detailed_record.items():
                        if field_name != 'attributes' and value is not None:
                            # Check if this field might contain file references
                            if isinstance(value, str) and any(keyword in value.lower() for keyword in ['s3', 'http', 'file', 'document', 'upload', 'aws']):
                                print(f"  🔍 {field_name}: {value} [*** POTENTIAL FILE REFERENCE ***]")
                            else:
                                print(f"  {field_name}: {value}")
                
            except Exception as e:
                print(f"Error getting detailed record: {e}")
                continue
        
        # 5. Check if there are any related records or child objects
        print(f"\n5. Checking for related records or child objects...")
        
        # Look for any objects that might reference BookkeepingLog__c
        try:
            all_objects = sf.describe()['sobjects']
            
            related_objects = []
            for obj in all_objects:
                if obj['name'].endswith('__c'):  # Only custom objects
                    try:
                        obj_desc = getattr(sf, obj['name']).describe()
                        
                        # Check if any fields reference BookkeepingLog__c
                        for field in obj_desc['fields']:
                            if field['type'] == 'reference' and field.get('referenceTo') == ['BookkeepingLog__c']:
                                related_objects.append({
                                    'object': obj['name'],
                                    'field': field['name'],
                                    'label': field['label']
                                })
                    except:
                        continue
            
            if related_objects:
                print(f"✓ Found {len(related_objects)} objects that reference BookkeepingLog__c:")
                for rel_obj in related_objects:
                    print(f"  - {rel_obj['object']}.{rel_obj['field']} ({rel_obj['label']})")
            else:
                print("No related objects found that reference BookkeepingLog__c")
                
        except Exception as e:
            print(f"Error checking related objects: {e}")
        
        print(f"\n" + "=" * 80)
        print("SUMMARY:")
        print(f"- BookkeepingLog__c records found: {len(bookkeeping_result['records'])}")
        print(f"- Related objects found: {len(related_objects) if 'related_objects' in locals() else 0}")
        print("- Check the output above for any fields marked as '*** POTENTIAL FILE REFERENCE ***'")
        print("=" * 80)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    investigate_bookkeeping_log() 