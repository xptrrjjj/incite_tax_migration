#!/usr/bin/env python3
"""
API Endpoint Discovery Script
============================

This script systematically discovers the actual Trackland API endpoints
by analyzing various patterns and testing different approaches.
"""

import os
import sys
import requests
import json
import re
from urllib.parse import urlparse
from typing import List, Dict, Optional
import time

# Import our configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)

from simple_salesforce import Salesforce


class EndpointDiscovery:
    """Systematically discover Trackland API endpoints."""
    
    def __init__(self):
        self.sf = None
        self.test_identifier = "5b0f2ed0-6577-11ef-8650-b5e663407c89"  # From our logs
        self.working_endpoints = []
        
    def authenticate_salesforce(self) -> bool:
        """Authenticate with Salesforce."""
        try:
            print("🔐 Authenticating with Salesforce...")
            self.sf = Salesforce(
                username=SALESFORCE_CONFIG["username"],
                password=SALESFORCE_CONFIG["password"],
                security_token=SALESFORCE_CONFIG["security_token"],
                domain=SALESFORCE_CONFIG["domain"]
            )
            print(f"✓ Authenticated with {self.sf.sf_instance}")
            return True
        except Exception as e:
            print(f"❌ Salesforce authentication failed: {e}")
            return False
    
    def extract_javascript_patterns(self):
        """Extract API patterns from the JavaScript code we already have."""
        print("\n🔍 Analyzing JavaScript patterns from PDF viewer...")
        
        # Read our extracted output
        output_file = "output.txt"
        if not os.path.exists(output_file):
            print("❌ output.txt not found - need to run extract_pdf_editor.py first")
            return []
        
        patterns = []
        
        try:
            with open(output_file, 'r') as f:
                content = f.read()
            
            # Look for API endpoint patterns
            api_patterns = [
                r'https://[^/]+/api/[^"\']+',
                r'fetch\([^)]*["\']([^"\']*api[^"\']*)["\']',
                r'["\']([^"\']*api/[^"\']*)["\']',
                r'orgUrl[^"\']*["\']([^"\']+)["\']',
                r'baseUrl[^"\']*["\']([^"\']+)["\']',
                r'apiUrl[^"\']*["\']([^"\']+)["\']'
            ]
            
            for pattern in api_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if 'api' in match.lower() and match not in patterns:
                        patterns.append(match)
                        print(f"  📍 Found pattern: {match}")
        
        except Exception as e:
            print(f"❌ Error reading output.txt: {e}")
        
        return patterns
    
    def generate_endpoint_candidates(self) -> List[str]:
        """Generate candidate API endpoints to test."""
        print("\n🎯 Generating API endpoint candidates...")
        
        # Base domains to try
        org_domain = self.sf.sf_instance.replace('https://', '').replace('/', '')
        org_name = org_domain.split('.')[0]
        
        base_domains = [
            # Salesforce org itself
            self.sf.sf_instance,
            # Heroku patterns
            f"https://trackland-api.herokuapp.com",
            f"https://trackland-{org_name}.herokuapp.com",
            f"https://{org_name}-trackland.herokuapp.com",
            f"https://incite-trackland.herokuapp.com",
            f"https://trackland-incite.herokuapp.com",
            # Custom domain patterns
            f"https://api.trackland.com",
            f"https://trackland-api.com",
            f"https://api.incitetax.com",
            f"https://{org_name}.trackland.com",
            f"https://trackland.{org_name}.com",
            # Lightning Experience patterns (common for managed packages)
            f"https://{org_domain}/lightning/n/TL_PDF_Editor",
            f"https://{org_domain}/apex/TL_PDF_Editor",
            # Visualforce page patterns
            f"https://{org_domain}/apex/TL_DocumentManager",
            f"https://{org_domain}/apex/TracklandAPI",
        ]
        
        # API paths to test
        api_paths = [
            "/api/generate/presigned-url",
            "/api/document/versions",
            "/services/apexrest/trackland/api",
            "/services/apexrest/TL/api",
            "/services/apexrest/api/generate/presigned-url",
            "/lightning/n/TL_PDF_Editor",
            "/apex/TL_PDF_Editor",
        ]
        
        candidates = []
        for domain in base_domains:
            for path in api_paths:
                candidate = f"{domain.rstrip('/')}{path}"
                candidates.append(candidate)
                print(f"  🎯 Candidate: {candidate}")
        
        return candidates
    
    def test_endpoint(self, url: str, method: str = "POST") -> Dict:
        """Test a specific endpoint."""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.sf.session_id}",
                "User-Agent": "simple-salesforce/1.0"
            }
            
            if method.upper() == "POST":
                payload = {
                    "identifier": self.test_identifier,
                    "app": "pdf-editor-sf",
                    "action": "read"
                }
                response = requests.post(url, json=payload, headers=headers, timeout=5)
            else:
                response = requests.get(url, headers=headers, timeout=5)
            
            return {
                'url': url,
                'status': response.status_code,
                'content_type': response.headers.get('content-type', ''),
                'response_size': len(response.content),
                'response_text': response.text[:200] if response.text else "",
                'working': response.status_code in [200, 201, 302]
            }
            
        except requests.exceptions.Timeout:
            return {'url': url, 'status': 'timeout', 'working': False}
        except requests.exceptions.ConnectionError:
            return {'url': url, 'status': 'connection_error', 'working': False}
        except Exception as e:
            return {'url': url, 'status': f'error: {str(e)}', 'working': False}
    
    def scan_endpoints(self):
        """Systematically scan all endpoint candidates."""
        print("\n🕵️ Starting systematic endpoint scan...")
        
        candidates = self.generate_endpoint_candidates()
        
        results = {
            'working': [],
            'interesting': [],  # Non-404, non-connection error
            'failed': []
        }
        
        print(f"\n🔍 Testing {len(candidates)} endpoint candidates...")
        
        for i, url in enumerate(candidates, 1):
            print(f"\n[{i}/{len(candidates)}] Testing: {url}")
            
            # Test with POST (for API endpoints)
            result = self.test_endpoint(url, "POST")
            
            if result['working']:
                print(f"  ✅ WORKING: {result['status']} - {result.get('response_text', '')[:100]}")
                results['working'].append(result)
                self.working_endpoints.append(url)
            elif result['status'] not in ['timeout', 'connection_error', 404]:
                print(f"  🤔 INTERESTING: {result['status']} - {result.get('response_text', '')[:100]}")
                results['interesting'].append(result)
            else:
                print(f"  ❌ Failed: {result['status']}")
                results['failed'].append(result)
            
            # Small delay to be respectful
            time.sleep(0.1)
        
        return results
    
    def test_salesforce_apex_rest(self):
        """Test Salesforce Apex REST endpoints specifically."""
        print("\n🔧 Testing Salesforce Apex REST endpoints...")
        
        apex_patterns = [
            "/services/apexrest/trackland/generatePresignedUrl",
            "/services/apexrest/TL/generatePresignedUrl", 
            "/services/apexrest/DocumentManager/generatePresignedUrl",
            "/services/apexrest/PDF/generatePresignedUrl",
            "/services/apexrest/trackland/api/generate/presigned-url",
            "/services/apexrest/TL/api/generate/presigned-url"
        ]
        
        base_url = self.sf.sf_instance.rstrip('/')
        
        for pattern in apex_patterns:
            url = f"{base_url}{pattern}"
            print(f"Testing Apex REST: {url}")
            
            result = self.test_endpoint(url, "POST")
            if result['working'] or result['status'] not in [404, 'connection_error']:
                print(f"  🎯 Apex result: {result['status']} - {result.get('response_text', '')[:100]}")
                if result['working']:
                    self.working_endpoints.append(url)
    
    def analyze_page_source(self):
        """Try to get the actual PDF viewer page and analyze its source."""
        print("\n📄 Attempting to analyze PDF viewer page source...")
        
        # Try to access the PDF viewer page directly
        viewer_urls = [
            f"{self.sf.sf_instance}/lightning/n/TL_PDF_Editor",
            f"{self.sf.sf_instance}/apex/TL_PDF_Editor",
            f"{self.sf.sf_instance}/c/TL_PDF_Editor.app"
        ]
        
        headers = {
            "Authorization": f"Bearer {self.sf.session_id}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        
        for url in viewer_urls:
            try:
                print(f"Trying to access: {url}")
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    print(f"✅ Got page source ({len(response.text)} chars)")
                    
                    # Look for API endpoints in the page source
                    api_matches = re.findall(r'https://[^"\'\s]+/api/[^"\'\s]+', response.text)
                    for match in api_matches:
                        print(f"  📍 Found API in page: {match}")
                        if match not in self.working_endpoints:
                            test_result = self.test_endpoint(match)
                            if test_result['working']:
                                self.working_endpoints.append(match)
                else:
                    print(f"  Status: {response.status_code}")
                    
            except Exception as e:
                print(f"  Error: {e}")
    
    def run_discovery(self):
        """Run the complete discovery process."""
        print("🔍 TRACKLAND API ENDPOINT DISCOVERY")
        print("=" * 50)
        
        if not self.authenticate_salesforce():
            return
        
        # Step 1: Extract patterns from JavaScript
        js_patterns = self.extract_javascript_patterns()
        
        # Step 2: Test endpoint candidates
        results = self.scan_endpoints()
        
        # Step 3: Test Salesforce Apex REST specifically
        self.test_salesforce_apex_rest()
        
        # Step 4: Try to analyze actual page source
        self.analyze_page_source()
        
        # Report results
        print("\n" + "=" * 50)
        print("📊 DISCOVERY RESULTS")
        print("=" * 50)
        
        if self.working_endpoints:
            print(f"\n🎉 WORKING ENDPOINTS FOUND ({len(self.working_endpoints)}):")
            for endpoint in self.working_endpoints:
                print(f"  ✅ {endpoint}")
        else:
            print("\n❌ No working endpoints found")
        
        if results['interesting']:
            print(f"\n🤔 INTERESTING RESPONSES ({len(results['interesting'])}):")
            for result in results['interesting'][:10]:  # Show top 10
                print(f"  {result['status']}: {result['url']}")
                if result['response_text']:
                    print(f"    Response: {result['response_text'][:100]}")
        
        print(f"\n📈 SUMMARY:")
        print(f"  Working endpoints: {len(self.working_endpoints)}")
        print(f"  Interesting responses: {len(results['interesting'])}")
        print(f"  Total failed: {len(results['failed'])}")
        print(f"  Total tested: {len(results['working']) + len(results['interesting']) + len(results['failed'])}")
        
        # Save results
        discovery_results = {
            'working_endpoints': self.working_endpoints,
            'interesting': results['interesting'][:20],  # Top 20
            'test_identifier': self.test_identifier,
            'sf_instance': self.sf.sf_instance,
            'timestamp': time.time()
        }
        
        with open('api_discovery_results.json', 'w') as f:
            json.dump(discovery_results, f, indent=2)
        
        print(f"\n💾 Results saved to: api_discovery_results.json")


def main():
    """Main entry point."""
    discovery = EndpointDiscovery()
    discovery.run_discovery()


if __name__ == "__main__":
    main()