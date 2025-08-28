#!/usr/bin/env python3
"""
External Files & S3 Integration Debug
====================================

This script finds external file references and S3 integrations in Salesforce.
"""

import sys
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

# Import configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)

def find_external_files():
    """Find external files and S3 integrations in Salesforce."""
    
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
        
        account_id = "001Dn00000S5AWVIA3"  # BBarth2559 account ID
        
        print(f"\n🔍 Searching for External Files and S3 Integrations...")
        print("=" * 60)
        
        # 1. Check for External Data Sources
        print(f"\n1. Checking External Data Sources...")
        try:
            eds_query = """
                SELECT Id, DeveloperName, MasterLabel, Type, Endpoint
                FROM ExternalDataSource
                ORDER BY DeveloperName
            """
            
            eds_result = sf.query_all(eds_query)
            print(f"✓ Found {len(eds_result['records'])} External Data Sources")
            
            for eds in eds_result['records']:
                print(f"   - {eds['MasterLabel']} ({eds['DeveloperName']})")
                print(f"     Type: {eds['Type']}")
                print(f"     Endpoint: {eds['Endpoint']}")
                print()
                
        except SalesforceError as e:
            print(f"Error querying External Data Sources: {e}")
        
        # 2. Check for External Objects
        print(f"\n2. Checking External Objects...")
        try:
            # Get metadata about external objects
            metadata = sf.describe()
            external_objects = [obj for obj in metadata['sobjects'] if obj['name'].endswith('__x')]
            
            print(f"✓ Found {len(external_objects)} External Objects")
            for obj in external_objects:
                print(f"   - {obj['label']} ({obj['name']})")
                
                # Try to query records from this external object
                try:
                    sample_query = f"SELECT Id FROM {obj['name']} LIMIT 5"
                    sample_result = sf.query(sample_query)
                    print(f"     Records: {sample_result['totalSize']}")
                except:
                    print(f"     Records: Unable to query")
                print()
                
        except SalesforceError as e:
            print(f"Error checking External Objects: {e}")
        
        # 3. Check for Custom Objects that might store file references
        print(f"\n3. Checking Custom Objects for file references...")
        try:
            # Look for custom objects that might contain file/document references
            custom_objects = [obj for obj in metadata['sobjects'] 
                            if obj['name'].endswith('__c') and 
                            ('file' in obj['name'].lower() or 'document' in obj['name'].lower() or 
                             'attachment' in obj['name'].lower() or 's3' in obj['name'].lower())]
            
            print(f"✓ Found {len(custom_objects)} file-related Custom Objects")
            for obj in custom_objects:
                print(f"   - {obj['label']} ({obj['name']})")
                
                # Try to get field information
                try:
                    obj_describe = sf.__getattr__(obj['name'].replace('__c', '')).describe()
                    file_fields = [field for field in obj_describe['fields'] 
                                 if 'file' in field['name'].lower() or 'url' in field['name'].lower() or 
                                    's3' in field['name'].lower() or 'path' in field['name'].lower()]
                    
                    if file_fields:
                        print(f"     File-related fields:")
                        for field in file_fields[:5]:  # Show first 5
                            print(f"       * {field['label']} ({field['name']})")
                        print()
                except:
                    print(f"     Unable to describe object")
                    print()
                
        except Exception as e:
            print(f"Error checking Custom Objects: {e}")
        
        # 4. Check Attachment object (legacy files)
        print(f"\n4. Checking legacy Attachments...")
        try:
            all_related_ids = [account_id]  # Add related record IDs if needed
            
            for i, record_id in enumerate(all_related_ids):
                attachments_query = f"""
                    SELECT Id, Name, ContentType, BodyLength, ParentId, Parent.Name
                    FROM Attachment
                    WHERE ParentId = '{record_id}'
                    ORDER BY Name
                    LIMIT 50
                """
                
                attachments_result = sf.query_all(attachments_query)
                if attachments_result['records']:
                    print(f"✓ Found {len(attachments_result['records'])} Attachments for {record_id}")
                    for att in attachments_result['records'][:5]:
                        size_mb = att['BodyLength'] / (1024 * 1024) if att['BodyLength'] else 0
                        print(f"   - {att['Name']} ({att['ContentType']}, {size_mb:.2f} MB)")
                    print()
                    
        except SalesforceError as e:
            print(f"Error querying Attachments: {e}")
        
        # 5. Check for Files Connect or Lightning Connect
        print(f"\n5. Checking for Files Connect configuration...")
        try:
            # Look for ExternalDataSource with Files Connect
            files_connect_query = """
                SELECT Id, DeveloperName, MasterLabel, Type, Endpoint
                FROM ExternalDataSource
                WHERE Type = 'Files Connect' OR Type LIKE '%Files%'
                ORDER BY DeveloperName
            """
            
            fc_result = sf.query_all(files_connect_query)
            print(f"✓ Found {len(fc_result['records'])} Files Connect Data Sources")
            
            for fc in fc_result['records']:
                print(f"   - {fc['MasterLabel']}")
                print(f"     Type: {fc['Type']}")
                print(f"     Endpoint: {fc['Endpoint']}")
                print()
                
        except SalesforceError as e:
            print(f"Error checking Files Connect: {e}")
        
        # 6. Check for any objects with S3 or AWS in the name
        print(f"\n6. Checking for S3/AWS-related objects...")
        try:
            s3_objects = [obj for obj in metadata['sobjects'] 
                         if 's3' in obj['name'].lower() or 'aws' in obj['name'].lower()]
            
            print(f"✓ Found {len(s3_objects)} S3/AWS-related objects")
            for obj in s3_objects:
                print(f"   - {obj['label']} ({obj['name']})")
                
                # Try to query sample records
                try:
                    sample_query = f"SELECT Id FROM {obj['name']} LIMIT 1"
                    sample_result = sf.query(sample_query)
                    print(f"     Has records: {'Yes' if sample_result['totalSize'] > 0 else 'No'}")
                except:
                    print(f"     Queryable: No")
                print()
                
        except Exception as e:
            print(f"Error checking S3/AWS objects: {e}")
        
        # 7. Check installed packages that might handle S3 integration
        print(f"\n7. Checking installed packages...")
        try:
            # This might not work in all orgs, but worth trying
            packages_query = """
                SELECT SubscriberPackage.Name, SubscriberPackage.NamespacePrefix
                FROM SubscriberPackageVersion
                WHERE SubscriberPackage.Name LIKE '%S3%' 
                   OR SubscriberPackage.Name LIKE '%AWS%'
                   OR SubscriberPackage.Name LIKE '%File%'
                ORDER BY SubscriberPackage.Name
            """
            
            packages_result = sf.query_all(packages_query)
            print(f"✓ Found {len(packages_result['records'])} relevant packages")
            
            for pkg in packages_result['records']:
                print(f"   - {pkg['SubscriberPackage']['Name']}")
                if pkg['SubscriberPackage']['NamespacePrefix']:
                    print(f"     Namespace: {pkg['SubscriberPackage']['NamespacePrefix']}")
                print()
                
        except SalesforceError as e:
            print(f"Note: Could not query packages: {e}")
        
        print(f"\n" + "=" * 60)
        print("NEXT STEPS:")
        print("1. Check the External Data Sources and External Objects above")
        print("2. Look for custom objects that store S3 file references")
        print("3. The 31 files are likely represented in one of these external systems")
        print("4. We'll need to query the external objects to get the S3 file paths")
        print("=" * 60)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    find_external_files() 