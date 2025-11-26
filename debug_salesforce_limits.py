#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug Salesforce Limits API
============================

Shows EXACTLY what Salesforce is returning from the limits() API.
"""

import sys
import io
from simple_salesforce import Salesforce
import json

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    import config
except ImportError:
    print("❌ Error: config.py not found")
    sys.exit(1)


def main():
    print("=" * 100)
    print("DEBUG: SALESFORCE LIMITS API RAW RESPONSE")
    print("=" * 100)
    print()

    # Connect
    try:
        sf_config = config.SALESFORCE_CONFIG
        sf = Salesforce(
            username=sf_config['username'],
            password=sf_config['password'],
            security_token=sf_config['security_token'],
            domain=sf_config['domain']
        )
        print("✅ Connected to Salesforce")
        print()
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        sys.exit(1)

    # Get limits
    print("Calling sf.limits()...")
    print()

    try:
        limits = sf.limits()

        print("RAW RESPONSE:")
        print(json.dumps(limits, indent=2))
        print()

        print("=" * 100)
        print("ANALYSIS:")
        print("=" * 100)
        print()

        # Check what keys exist
        print("Available keys:", list(limits.keys()))
        print()

        # Check each storage type
        if 'DataStorageMB' in limits:
            print("DataStorageMB exists:")
            print(json.dumps(limits['DataStorageMB'], indent=2))
        else:
            print("❌ DataStorageMB NOT in response")
        print()

        if 'FileStorageMB' in limits:
            print("FileStorageMB exists:")
            print(json.dumps(limits['FileStorageMB'], indent=2))
        else:
            print("❌ FileStorageMB NOT in response")
        print()

        # Try alternate method - query Organization
        print("=" * 100)
        print("ALTERNATE METHOD: Query Organization object")
        print("=" * 100)
        print()

        try:
            org_query = "SELECT Id, Name, OrganizationType FROM Organization"
            org_result = sf.query(org_query)
            print("Organization query result:")
            print(json.dumps(org_result['records'], indent=2))
        except Exception as e:
            print(f"❌ Failed: {e}")

    except Exception as e:
        print(f"❌ Error calling limits(): {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
