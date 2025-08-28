#!/usr/bin/env python3
"""
Debug File Discovery for Salesforce Migration
============================================

This script helps debug why we're not finding all files for an account.
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

def debug_account_files():
    """Debug file discovery for BBarth2559 account."""
    
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
        
        # First, get the Account ID
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
        
        # Debug different types of file relationships
        print(f"\n2. Checking different file relationship types for Account {account_id}...")
        
        # Check ContentDocumentLink with different ShareTypes
        share_types = ['V', 'C', 'I']  # Viewer, Collaborator, Inferred
        all_links = []
        
        for share_type in share_types:
            print(f"\n   Checking ShareType '{share_type}'...")
            try:
                cdl_query = f"""
                    SELECT Id, ContentDocumentId, LinkedEntityId, ShareType, Visibility,
                           ContentDocument.Title, ContentDocument.FileExtension,
                           ContentDocument.ContentSize, ContentDocument.IsDeleted
                    FROM ContentDocumentLink 
                    WHERE LinkedEntityId = '{account_id}'
                    AND ShareType = '{share_type}'
                    ORDER BY ContentDocument.Title
                """
                
                result = sf.query_all(cdl_query)
                print(f"   Found {len(result['records'])} files with ShareType '{share_type}'")
                
                for record in result['records']:
                    all_links.append({
                        'title': record['ContentDocument']['Title'],
                        'extension': record['ContentDocument']['FileExtension'],
                        'size': record['ContentDocument']['ContentSize'],
                        'share_type': record['ShareType'],
                        'visibility': record['Visibility'],
                        'is_deleted': record['ContentDocument']['IsDeleted'],
                        'content_doc_id': record['ContentDocumentId']
                    })
                    
            except SalesforceError as e:
                print(f"   Error with ShareType '{share_type}': {e}")
        
        # Check ALL ContentDocumentLinks for this account (without ShareType filter)
        print(f"\n3. Checking ALL ContentDocumentLinks for Account {account_id}...")
        try:
            all_cdl_query = f"""
                SELECT Id, ContentDocumentId, LinkedEntityId, ShareType, Visibility,
                       ContentDocument.Title, ContentDocument.FileExtension,
                       ContentDocument.ContentSize, ContentDocument.IsDeleted,
                       ContentDocument.CreatedDate
                FROM ContentDocumentLink 
                WHERE LinkedEntityId = '{account_id}'
                ORDER BY ContentDocument.CreatedDate DESC
            """
            
            all_result = sf.query_all(all_cdl_query)
            print(f"✓ Found {len(all_result['records'])} total ContentDocumentLinks")
            
            # Show details of each file
            print(f"\n4. File Details:")
            print("=" * 80)
            for i, record in enumerate(all_result['records'], 1):
                doc = record['ContentDocument']
                print(f"{i:2d}. {doc['Title']}")
                print(f"    Extension: {doc['FileExtension']}")
                print(f"    Size: {doc['ContentSize']:,} bytes")
                print(f"    ShareType: {record['ShareType']}")
                print(f"    Visibility: {record['Visibility']}")
                print(f"    Deleted: {doc['IsDeleted']}")
                print(f"    ContentDocId: {record['ContentDocumentId']}")
                print()
            
        except SalesforceError as e:
            print(f"Error querying all ContentDocumentLinks: {e}")
        
        # Check if there are files linked via other relationships
        print(f"\n5. Checking for files linked via other relationships...")
        
        # Check ContentVersion directly
        try:
            cv_query = f"""
                SELECT Id, Title, FileExtension, ContentSize, FirstPublishLocationId
                FROM ContentVersion 
                WHERE FirstPublishLocationId = '{account_id}'
                AND IsLatest = TRUE
                ORDER BY Title
            """
            
            cv_result = sf.query_all(cv_query)
            print(f"✓ Found {len(cv_result['records'])} files with FirstPublishLocationId = Account")
            
            for record in cv_result['records']:
                print(f"   - {record['Title']} ({record['FileExtension']}, {record['ContentSize']:,} bytes)")
                
        except SalesforceError as e:
            print(f"Error querying ContentVersion: {e}")
        
        # Check for Libraries/Workspaces shared with this account
        print(f"\n6. Checking for Libraries/Workspaces shared with Account...")
        try:
            # Check ContentWorkspaceMember - libraries shared with account
            workspace_query = f"""
                SELECT Id, ContentWorkspaceId, ContentWorkspace.Name, ContentWorkspace.Description
                FROM ContentWorkspaceMember 
                WHERE MemberId = '{account_id}'
                ORDER BY ContentWorkspace.Name
            """
            
            workspace_result = sf.query_all(workspace_query)
            print(f"✓ Found {len(workspace_result['records'])} Libraries/Workspaces shared with account")
            
            total_workspace_files = 0
            for workspace in workspace_result['records']:
                workspace_id = workspace['ContentWorkspaceId']
                workspace_name = workspace['ContentWorkspace']['Name']
                print(f"\n   Library: {workspace_name} (ID: {workspace_id})")
                
                # Get files in this workspace
                try:
                    workspace_files_query = f"""
                        SELECT ContentDocumentId, ContentDocument.Title, 
                               ContentDocument.FileExtension, ContentDocument.ContentSize
                        FROM ContentWorkspaceDoc 
                        WHERE ContentWorkspaceId = '{workspace_id}'
                        AND ContentDocument.IsDeleted = FALSE
                        ORDER BY ContentDocument.Title
                        LIMIT 100
                    """
                    
                    workspace_files_result = sf.query_all(workspace_files_query)
                    file_count = len(workspace_files_result['records'])
                    total_workspace_files += file_count
                    print(f"   Found {file_count} files in this library")
                    
                    # Show first few files
                    for i, file_record in enumerate(workspace_files_result['records'][:5]):
                        doc = file_record['ContentDocument']
                        print(f"     {i+1}. {doc['Title']} ({doc['FileExtension']}, {doc['ContentSize']:,} bytes)")
                    
                    if file_count > 5:
                        print(f"     ... and {file_count - 5} more files")
                        
                except SalesforceError as e:
                    print(f"   Error querying files in workspace: {e}")
            
            print(f"\n   Total files found in all libraries: {total_workspace_files}")
                
        except SalesforceError as e:
            print(f"Error querying ContentWorkspaceMember: {e}")
        
        # Check for folder-based file organization
        print(f"\n7. Checking for folder-based file organization...")
        try:
            # Look for ContentFolderItems that might be linked to this account
            folder_query = f"""
                SELECT Id, ParentContentFolderId, ParentContentFolder.Name
                FROM ContentFolderMember 
                WHERE ChildRecordId = '{account_id}'
                ORDER BY ParentContentFolder.Name
                LIMIT 50
            """
            
            folder_result = sf.query_all(folder_query)
            print(f"✓ Found {len(folder_result['records'])} folders associated with account")
            
            for folder in folder_result['records']:
                folder_id = folder['ParentContentFolderId']
                folder_name = folder['ParentContentFolder']['Name']
                print(f"   Folder: {folder_name} (ID: {folder_id})")
                
        except SalesforceError as e:
            print(f"Error querying ContentFolderMember: {e}")
        
        # Check ContentFolderItem directly for files in folders
        print(f"\n8. Checking for files in content folders...")
        try:
            # This is a more complex query - we need to find folders and then files in them
            # First, let's see what ContentFolders exist
            content_folders_query = """
                SELECT Id, Name, ParentContentFolderId
                FROM ContentFolder
                WHERE IsDeleted = FALSE
                ORDER BY Name
                LIMIT 20
            """
            
            folders_result = sf.query_all(content_folders_query)
            print(f"✓ Found {len(folders_result['records'])} content folders in org")
            
            for folder in folders_result['records'][:5]:  # Show first 5
                print(f"   Folder: {folder['Name']} (ID: {folder['Id']})")
                
        except SalesforceError as e:
            print(f"Error querying ContentFolder: {e}")
        
        # Check what our migration script query would return
        print(f"\n9. Testing our migration script query...")
        try:
            migration_query = f"""
                SELECT Id, ContentDocumentId, LinkedEntityId, LinkedEntity.Name,
                       ContentDocument.Title, ContentDocument.FileExtension,
                       ContentDocument.ContentSize, ContentDocument.CreatedDate,
                       ContentDocument.LastModifiedDate
                FROM ContentDocumentLink 
                WHERE LinkedEntityId = '{account_id}'
                AND ContentDocument.IsDeleted = FALSE
                ORDER BY LinkedEntityId, ContentDocument.Title
            """
            
            migration_result = sf.query_all(migration_query)
            print(f"✓ Migration script query found: {len(migration_result['records'])} files")
            
            if len(migration_result['records']) != len([r for r in all_result['records'] if not r['ContentDocument']['IsDeleted']]):
                print("⚠️  Discrepancy found! Migration query returns different count.")
            
        except SalesforceError as e:
            print(f"Error with migration query: {e}")
        
        # Summary
        print(f"\n" + "=" * 80)
        print("SUMMARY:")
        print(f"- Direct ContentDocumentLinks found: {len(all_result['records']) if 'all_result' in locals() else 0}")
        print(f"- Files our current migration script would process: {len([r for r in all_result['records'] if not r['ContentDocument']['IsDeleted']]) if 'all_result' in locals() else 0}")
        print(f"- Libraries/Workspaces files: {total_workspace_files if 'total_workspace_files' in locals() else 0}")
        print(f"- EXPLANATION: The 31 files you see in Salesforce UI are likely in Libraries/Workspaces")
        print(f"  or folder structures, not directly linked to the Account via ContentDocumentLink.")
        print("=" * 80)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_account_files() 