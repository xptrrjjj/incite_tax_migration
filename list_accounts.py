#!/usr/bin/env python3
"""
Account Finder for Salesforce Migration
======================================

This helper script lists all accounts that have files attached,
so you can choose which account to test with.

Usage: python list_accounts.py
"""

import sys
import logging
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

# Import configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)

def setup_basic_logging():
    """Set up basic logging for this script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def get_accounts_with_files():
    """Get all accounts that have files attached."""
    logger = setup_basic_logging()
    
    try:
        # Authenticate with Salesforce
        logger.info("Connecting to Salesforce...")
        sf = Salesforce(
            username=SALESFORCE_CONFIG["username"],
            password=SALESFORCE_CONFIG["password"],
            security_token=SALESFORCE_CONFIG["security_token"],
            domain=SALESFORCE_CONFIG["domain"]
        )
        logger.info("✓ Successfully connected to Salesforce")
        
        # Different approach: Query all Accounts first, then check for files
        # Salesforce ContentDocumentLink has strict filtering requirements
        logger.info("Querying all accounts...")
        accounts_query = """
            SELECT Id, Name
            FROM Account
            WHERE IsDeleted = FALSE
            ORDER BY Name
            LIMIT 200
        """
        
        accounts_result = sf.query_all(accounts_query)
        logger.info(f"Found {len(accounts_result['records'])} accounts, checking for files...")
        
        accounts_with_files = []
        total_files = 0
        
        # Check each account for files (in batches)
        account_ids = [acc['Id'] for acc in accounts_result['records']]
        batch_size = 20  # Process accounts in batches
        
        for i in range(0, len(account_ids), batch_size):
            batch_ids = account_ids[i:i + batch_size]
            
            # Create IN clause for batch
            ids_str = "', '".join(batch_ids)
            
            # Query ContentDocumentLinks for this batch of accounts
            cdl_query = f"""
                SELECT LinkedEntityId, COUNT(Id) FileCount
                FROM ContentDocumentLink 
                WHERE LinkedEntityId IN ('{ids_str}')
                AND ContentDocument.IsDeleted = FALSE
                GROUP BY LinkedEntityId
            """
            
            try:
                cdl_result = sf.query_all(cdl_query)
                
                # Map the results
                account_file_counts = {}
                for record in cdl_result['records']:
                    account_file_counts[record['LinkedEntityId']] = record['FileCount']
                
                # Add accounts with files to our list
                for account in accounts_result['records']:
                    if account['Id'] in account_file_counts:
                        file_count = account_file_counts[account['Id']]
                        accounts_with_files.append({
                            'id': account['Id'],
                            'name': account['Name'],
                            'file_count': file_count
                        })
                        total_files += file_count
                        
            except SalesforceError as e:
                logger.warning(f"Error querying files for batch: {e}")
                continue
        
        # Sort by account name
        accounts_with_files.sort(key=lambda x: x['name'])
        
        return accounts_with_files, total_files
        
    except SalesforceError as e:
        logger.error(f"Salesforce error: {e}")
        return [], 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return [], 0

def main():
    """Main function to list accounts."""
    print("Account Finder for Salesforce Migration")
    print("=" * 50)
    
    accounts, total_files = get_accounts_with_files()
    
    if not accounts:
        print("❌ No accounts with files found.")
        return
    
    print(f"\nFound {len(accounts)} account(s) with {total_files} total files:\n")
    
    for i, account in enumerate(accounts, 1):
        print(f"{i:2d}. {account['name']}")
        print(f"     Account ID: {account['id']}")
        print(f"     Files: {account['file_count']}")
        print()
    
    print("=" * 50)
    print("📋 To test with a specific account, update your config.py:")
    print()
    print("Option 1 - Use Account ID:")
    print("   'test_account_id': 'ACCOUNT_ID_HERE',")
    print()
    print("Option 2 - Use Account Name:")
    print("   'test_account_name': 'ACCOUNT_NAME_HERE',")
    print()
    print("Or leave both as None to use the first account found.")
    print("=" * 50)

if __name__ == "__main__":
    main() 