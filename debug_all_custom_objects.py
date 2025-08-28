#!/usr/bin/env python3
"""
All Custom Objects Debug
========================

This script investigates all custom objects with records linked to BBarth2559 to find S3 file references.
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

def investigate_all_custom_objects():
    """Investigate all custom objects with records linked to BBarth2559."""
    
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
        
        # 2. Get all custom objects
        print(f"\n2. Getting all custom objects...")
        all_objects = sf.describe()['sobjects']
        custom_objects = [obj['name'] for obj in all_objects if obj['name'].endswith('__c')]
        
        print(f"✓ Found {len(custom_objects)} custom objects")
        
        # 3. Check each custom object for records related to our account
        print(f"\n3. Checking each custom object for records linked to BBarth2559...")
        
        objects_with_records = []
        
        for obj_name in custom_objects:
            try:
                print(f"\n🔍 Checking {obj_name}...")
                
                # Get object description to understand its fields
                obj_desc = getattr(sf, obj_name).describe()
                
                # Look for account reference fields
                account_fields = []
                for field in obj_desc['fields']:
                    if (field['type'] == 'reference' and 
                        field.get('referenceTo') and 
                        'Account' in field.get('referenceTo', [])):
                        account_fields.append(field['name'])
                
                if not account_fields:
                    print(f"  ❌ No account reference fields found")
                    continue
                
                # Try to find records linked to our account
                for field_name in account_fields:
                    try:
                        test_query = f"""
                            SELECT Id, Name
                            FROM {obj_name}
                            WHERE {field_name} = '{account_id}'
                            AND IsDeleted = FALSE
                            LIMIT 10
                        """
                        
                        test_result = sf.query_all(test_query)
                        
                        if test_result['records']:
                            print(f"  ✓ Found {len(test_result['records'])} records via {field_name}")
                            objects_with_records.append({
                                'object': obj_name,
                                'field': field_name,
                                'count': len(test_result['records']),
                                'records': test_result['records']
                            })
                            break
                    except Exception as e:
                        print(f"  ❌ Error querying {field_name}: {e}")
                        continue
                
            except Exception as e:
                print(f"  ❌ Error with {obj_name}: {e}")
                continue
        
        print(f"\n" + "=" * 80)
        print(f"OBJECTS WITH RECORDS LINKED TO BBarth2559:")
        print(f"Found {len(objects_with_records)} objects with linked records")
        print("=" * 80)
        
        # 4. Investigate each object with records in detail
        s3_references = []
        
        for obj_info in objects_with_records:
            obj_name = obj_info['object']
            field_name = obj_info['field']
            count = obj_info['count']
            records = obj_info['records']
            
            print(f"\n🔍 INVESTIGATING {obj_name} ({count} records)")
            print("-" * 50)
            
            try:
                # Get object description
                obj_desc = getattr(sf, obj_name).describe()
                
                # Get all field names
                field_names = [field['name'] for field in obj_desc['fields']]
                
                # Get full details for each record
                for i, record in enumerate(records[:3], 1):  # Check first 3 records
                    record_id = record['Id']
                    record_name = record.get('Name', 'N/A')
                    
                    print(f"\n  Record {i}: {record_name} (ID: {record_id})")
                    
                    # Get all fields for this record
                    try:
                        fields_str = ', '.join(field_names)
                        
                        detailed_query = f"""
                            SELECT {fields_str}
                            FROM {obj_name}
                            WHERE Id = '{record_id}'
                        """
                        
                        detailed_result = sf.query(detailed_query)
                        
                        if detailed_result['records']:
                            detailed_record = detailed_result['records'][0]
                            
                            # Check each field for potential S3/file references
                            for field_name_check, value in detailed_record.items():
                                if field_name_check == 'attributes' or value is None:
                                    continue
                                
                                if isinstance(value, str):
                                    # Check for S3, AWS, or file-related keywords
                                    if any(keyword in value.lower() for keyword in ['s3', 'aws', 'bucket', 'http', 'file', 'document', 'upload', '.pdf', '.doc', '.xls']):
                                        print(f"    🔍 {field_name_check}: {value} [*** POTENTIAL FILE REFERENCE ***]")
                                        s3_references.append({
                                            'object': obj_name,
                                            'record_id': record_id,
                                            'record_name': record_name,
                                            'field': field_name_check,
                                            'value': value
                                        })
                                    elif len(value) > 50:  # Long text fields might contain file references
                                        print(f"    {field_name_check}: {value[:100]}..." if len(value) > 100 else f"    {field_name_check}: {value}")
                                    else:
                                        print(f"    {field_name_check}: {value}")
                    
                    except Exception as e:
                        print(f"    ❌ Error getting detailed record: {e}")
                        continue
                
            except Exception as e:
                print(f"❌ Error investigating {obj_name}: {e}")
                continue
        
        # 5. Summary of S3 references found
        print(f"\n" + "=" * 80)
        print("SUMMARY OF POTENTIAL S3/FILE REFERENCES:")
        print(f"Found {len(s3_references)} potential file references")
        print("=" * 80)
        
        if s3_references:
            for ref in s3_references:
                print(f"\n🔍 {ref['object']}.{ref['field']}:")
                print(f"   Record: {ref['record_name']} ({ref['record_id']})")
                print(f"   Value: {ref['value']}")
                print("-" * 50)
        else:
            print("\n❌ No S3 or file references found in custom objects")
            print("The 31 files might be:")
            print("1. In a different Salesforce org")
            print("2. In a third-party app connected to Salesforce")
            print("3. In a different type of integration")
            print("4. In standard objects we haven't checked yet")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    investigate_all_custom_objects() 