#!/usr/bin/env python3
"""
PDF Viewer Reverse Engineering Script
====================================

Since Trackland no longer exists, this script reverse-engineers how the PDF viewer
works by examining:
1. Client-side JavaScript/Lightning components
2. REST API endpoints that might proxy S3 access
3. Custom Visualforce page implementations
4. Network traffic patterns that might reveal the access method

Usage:
python reverse_engineer_pdf_viewer.py
"""

import os
import sys
import logging
import requests
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

# Import configuration
try:
    from config import SALESFORCE_CONFIG, MIGRATION_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)


def setup_logging() -> logging.Logger:
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    logger = logging.getLogger(__name__)
    return logger


class PDFViewerReverseEngineer:
    """Reverse engineers the PDF viewer implementation to find S3 access method."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.sf = None
        
    def authenticate(self) -> bool:
        """Authenticate with Salesforce."""
        try:
            self.sf = Salesforce(
                username=SALESFORCE_CONFIG["username"],
                password=SALESFORCE_CONFIG["password"],
                security_token=SALESFORCE_CONFIG["security_token"],
                domain=SALESFORCE_CONFIG["domain"]
            )
            
            self.logger.info("✓ Successfully authenticated with Salesforce")
            return True
            
        except SalesforceError as e:
            self.logger.error(f"❌ Salesforce authentication failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Unexpected error during Salesforce authentication: {e}")
            return False
    
    def find_all_rest_endpoints(self) -> List[Dict]:
        """Find all REST API endpoints that might be proxying file access."""
        try:
            self.logger.info("🔍 Finding all REST API endpoints...")
            
            # Look for Apex REST classes
            rest_query = """
                SELECT Id, Name, NamespacePrefix, Body, CreatedDate, LastModifiedDate
                FROM ApexClass
                WHERE (Body LIKE '%@RestResource%'
                   OR Body LIKE '%@HttpGet%'
                   OR Body LIKE '%@HttpPost%'
                   OR Body LIKE '%RestRequest%'
                   OR Body LIKE '%RestResponse%')
                ORDER BY Name
            """
            
            rest_endpoints = []
            
            try:
                result = self.sf.query(rest_query)
                
                for record in result['records']:
                    body = record.get('Body', '')
                    
                    # Extract REST resource URL pattern
                    url_pattern = None
                    if '@RestResource' in body:
                        import re
                        url_match = re.search(r'@RestResource\s*\(\s*urlMapping\s*=\s*["\']([^"\']+)["\']', body, re.IGNORECASE)
                        if url_match:
                            url_pattern = url_match.group(1)
                    
                    # Look for file/download related methods
                    methods = []
                    if '@HttpGet' in body:
                        methods.append('GET')
                    if '@HttpPost' in body:
                        methods.append('POST')
                    
                    # Extract method signatures
                    method_signatures = []
                    method_pattern = r'@Http(Get|Post|Put|Delete|Patch)\s+(?:global\s+)?(?:static\s+)?[\w\s<>]+\s+(\w+)\s*\([^)]*\)'
                    method_matches = re.findall(method_pattern, body, re.IGNORECASE | re.MULTILINE)
                    for http_method, method_name in method_matches:
                        method_signatures.append(f"{http_method.upper()} {method_name}")
                    
                    # Check if this endpoint might handle files
                    file_keywords = ['file', 'download', 'document', 'pdf', 'content', 'stream', 'blob', 's3', 'proxy']
                    file_relevance = sum(1 for keyword in file_keywords if keyword.lower() in body.lower())
                    
                    rest_endpoints.append({
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record.get('NamespacePrefix'),
                        'url_pattern': url_pattern,
                        'methods': methods,
                        'method_signatures': method_signatures,
                        'file_relevance': file_relevance,
                        'body_preview': body[:800] + "..." if len(body) > 800 else body,
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate']
                    })
                
                # Sort by file relevance
                rest_endpoints.sort(key=lambda x: x['file_relevance'], reverse=True)
                return rest_endpoints
                
            except Exception as e:
                self.logger.error(f"Error querying REST endpoints: {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding REST endpoints: {e}")
            return []
    
    def examine_pdf_viewer_components(self) -> Dict:
        """Examine the PDF viewer Lightning components and Visualforce pages in detail."""
        try:
            self.logger.info("🔍 Examining PDF viewer components in detail...")
            
            components_analysis = {
                'visualforce_pages': [],
                'lightning_components': [],
                'static_resources': []
            }
            
            # Get detailed VF page analysis for PDF viewers
            vf_query = """
                SELECT Id, Name, NamespacePrefix, Markup, MasterLabel, Description,
                       CreatedDate, LastModifiedDate, ApiVersion
                FROM ApexPage
                WHERE (Name LIKE '%PDF%' OR Name LIKE '%pdf%'
                   OR Name LIKE '%View%' OR Name LIKE '%view%'
                   OR Name LIKE '%Doc%' OR Name LIKE '%doc%')
                ORDER BY Name
            """
            
            try:
                vf_result = self.sf.query(vf_query)
                
                for record in vf_result['records']:
                    markup = record.get('Markup', '')
                    
                    # Extract JavaScript code
                    js_code = []
                    import re
                    js_matches = re.findall(r'<script[^>]*>(.*?)</script>', markup, re.DOTALL | re.IGNORECASE)
                    for js_match in js_matches:
                        if js_match.strip():
                            js_code.append(js_match.strip())
                    
                    # Extract iframe sources or other external content references
                    iframe_sources = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', markup, re.IGNORECASE)
                    
                    # Extract any URL patterns or endpoint references
                    url_patterns = []
                    url_matches = re.findall(r'https?://[^\s"\'<>]+', markup)
                    for url in url_matches:
                        if 'amazonaws' in url or 'trackland' in url or 's3' in url:
                            url_patterns.append(url)
                    
                    # Look for REST endpoint calls
                    rest_calls = []
                    rest_patterns = [
                        r'/services/apexrest/[^\s"\'<>]+',
                        r'\.apex\s*\(\s*["\']([^"\']+)["\']',
                        r'callout:[^\s"\'<>]+',
                        r'Remote\.Manager\.invokeAction'
                    ]
                    
                    for pattern in rest_patterns:
                        rest_matches = re.findall(pattern, markup, re.IGNORECASE)
                        rest_calls.extend(rest_matches)
                    
                    components_analysis['visualforce_pages'].append({
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record.get('NamespacePrefix'),
                        'master_label': record.get('MasterLabel'),
                        'description': record.get('Description'),
                        'markup_length': len(markup),
                        'javascript_blocks': len(js_code),
                        'javascript_code': js_code,
                        'iframe_sources': iframe_sources,
                        'url_patterns': url_patterns,
                        'rest_calls': rest_calls,
                        'api_version': record.get('ApiVersion'),
                        'created_date': record['CreatedDate']
                    })
                
            except Exception as e:
                self.logger.debug(f"VF page query error: {e}")
            
            # Get Lightning component analysis
            aura_query = """
                SELECT Id, DeveloperName, NamespacePrefix, Description, MasterLabel,
                       CreatedDate, LastModifiedDate, ApiVersion
                FROM AuraDefinitionBundle
                WHERE (DeveloperName LIKE '%PDF%' OR DeveloperName LIKE '%pdf%'
                   OR DeveloperName LIKE '%View%' OR DeveloperName LIKE '%view%'
                   OR DeveloperName LIKE '%Doc%' OR DeveloperName LIKE '%doc%'
                   OR Description LIKE '%PDF%' OR Description LIKE '%pdf%'
                   OR Description LIKE '%view%' OR Description LIKE '%document%')
                ORDER BY DeveloperName
            """
            
            try:
                aura_result = self.sf.query(aura_query)
                
                for record in aura_result['records']:
                    component_id = record['Id']
                    
                    # Get component definitions
                    definition_query = f"""
                        SELECT Id, DefType, Format, Source
                        FROM AuraDefinition
                        WHERE AuraDefinitionBundleId = '{component_id}'
                    """
                    
                    definitions = []
                    javascript_code = []
                    url_patterns = []
                    rest_calls = []
                    
                    try:
                        def_result = self.sf.query(definition_query)
                        
                        for def_record in def_result['records']:
                            source = def_record.get('Source', '')
                            def_type = def_record.get('DefType')
                            
                            definitions.append({
                                'type': def_type,
                                'format': def_record.get('Format'),
                                'source_length': len(source)
                            })
                            
                            if def_type in ['CONTROLLER', 'HELPER'] and source:
                                javascript_code.append({
                                    'type': def_type,
                                    'code': source
                                })
                                
                                # Extract URL patterns from JS
                                import re
                                url_matches = re.findall(r'https?://[^\s"\'<>]+', source)
                                for url in url_matches:
                                    if 'amazonaws' in url or 'trackland' in url or 's3' in url:
                                        url_patterns.append(url)
                                
                                # Look for REST calls in JS
                                rest_patterns = [
                                    r'/services/apexrest/[^\s"\'<>]+',
                                    r'callout:[^\s"\'<>]+',
                                    r'\$A\.enqueueAction',
                                    r'action\.setCallback'
                                ]
                                
                                for pattern in rest_patterns:
                                    rest_matches = re.findall(pattern, source, re.IGNORECASE)
                                    rest_calls.extend(rest_matches)
                    
                    except Exception as def_error:
                        self.logger.debug(f"Could not get definitions for {record['DeveloperName']}: {def_error}")
                    
                    components_analysis['lightning_components'].append({
                        'id': record['Id'],
                        'developer_name': record['DeveloperName'],
                        'namespace': record.get('NamespacePrefix'),
                        'description': record.get('Description'),
                        'master_label': record.get('MasterLabel'),
                        'definitions': definitions,
                        'javascript_code': javascript_code,
                        'url_patterns': url_patterns,
                        'rest_calls': rest_calls,
                        'created_date': record['CreatedDate']
                    })
                
            except Exception as e:
                self.logger.debug(f"Lightning component query error: {e}")
            
            return components_analysis
            
        except Exception as e:
            self.logger.error(f"❌ Error examining PDF viewer components: {e}")
            return {}
    
    def test_potential_proxy_endpoints(self, sample_doclist_entries: List[str]) -> List[Dict]:
        """Test potential proxy endpoints with sample DocListEntry IDs."""
        try:
            self.logger.info("🔍 Testing potential proxy endpoints...")
            
            # Common REST endpoint patterns that might proxy file access
            potential_endpoints = [
                '/services/apexrest/document/',
                '/services/apexrest/file/',
                '/services/apexrest/pdf/',
                '/services/apexrest/download/',
                '/services/apexrest/proxy/',
                '/services/apexrest/viewer/',
                '/services/apexrest/tlnd/document/',
                '/services/apexrest/tlnd/file/',
                '/services/apexrest/tlnd/pdf/'
            ]
            
            test_results = []
            
            for endpoint_pattern in potential_endpoints:
                for doclist_id in sample_doclist_entries[:2]:  # Test with 2 sample IDs
                    
                    # Try different URL constructions
                    test_urls = [
                        f"{self.sf.base_url.rstrip('/')}{endpoint_pattern}{doclist_id}",
                        f"{self.sf.base_url.rstrip('/')}{endpoint_pattern}?id={doclist_id}",
                        f"{self.sf.base_url.rstrip('/')}{endpoint_pattern}?doclistentry={doclist_id}"
                    ]
                    
                    for test_url in test_urls:
                        try:
                            self.logger.debug(f"Testing: {test_url}")
                            
                            headers = {
                                'Authorization': f'Bearer {self.sf.session_id}',
                                'Content-Type': 'application/json'
                            }
                            
                            response = requests.get(test_url, headers=headers, timeout=10)
                            
                            test_results.append({
                                'endpoint_pattern': endpoint_pattern,
                                'test_url': test_url,
                                'doclist_id': doclist_id,
                                'status_code': response.status_code,
                                'content_type': response.headers.get('Content-Type'),
                                'content_length': len(response.content) if response.content else 0,
                                'response_preview': response.text[:200] + "..." if response.text and len(response.text) > 200 else response.text[:200]
                            })
                            
                            # If we get a successful response, this might be a working endpoint
                            if response.status_code == 200 and response.content:
                                self.logger.info(f"✅ Potential working endpoint: {test_url}")
                            
                        except Exception as e:
                            test_results.append({
                                'endpoint_pattern': endpoint_pattern,
                                'test_url': test_url,
                                'doclist_id': doclist_id,
                                'error': str(e)
                            })
            
            return test_results
            
        except Exception as e:
            self.logger.error(f"❌ Error testing proxy endpoints: {e}")
            return []
    
    def comprehensive_reverse_engineering(self) -> Dict:
        """Perform comprehensive reverse engineering of the PDF viewer system."""
        self.logger.info("🔍 Starting comprehensive PDF viewer reverse engineering...")
        
        # Get sample DocListEntry IDs for testing
        sample_query = """
            SELECT Id, Name, Document__c
            FROM DocListEntry__c
            WHERE Document__c != NULL
            AND Document__c LIKE '%trackland-doc-storage%'
            LIMIT 5
        """
        
        sample_doclist_entries = []
        try:
            sample_result = self.sf.query(sample_query)
            sample_doclist_entries = [r['Id'] for r in sample_result['records']]
        except Exception as e:
            self.logger.warning(f"Could not get sample DocListEntry IDs: {e}")
        
        analysis_results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'sample_doclist_entries': sample_doclist_entries,
            'rest_endpoints': [],
            'pdf_viewer_components': {},
            'proxy_endpoint_tests': []
        }
        
        # Find all REST endpoints
        analysis_results['rest_endpoints'] = self.find_all_rest_endpoints()
        
        # Examine PDF viewer components
        analysis_results['pdf_viewer_components'] = self.examine_pdf_viewer_components()
        
        # Test potential proxy endpoints
        if sample_doclist_entries:
            analysis_results['proxy_endpoint_tests'] = self.test_potential_proxy_endpoints(sample_doclist_entries)
        
        return analysis_results
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted reverse engineering analysis results."""
        print("\n" + "=" * 80)
        print("PDF VIEWER REVERSE ENGINEERING ANALYSIS")
        print("=" * 80)
        
        # REST Endpoints
        rest_endpoints = analysis.get('rest_endpoints', [])
        relevant_endpoints = [e for e in rest_endpoints if e['file_relevance'] > 0]
        
        print(f"\n🌐 REST ENDPOINTS: {len(rest_endpoints)} total, {len(relevant_endpoints)} file-relevant")
        print("-" * 50)
        
        for endpoint in relevant_endpoints[:5]:  # Top 5 most relevant
            print(f"🔥 {endpoint['name']}")
            if endpoint.get('namespace'):
                print(f"   Namespace: {endpoint['namespace']}")
            if endpoint.get('url_pattern'):
                print(f"   URL Pattern: {endpoint['url_pattern']}")
            print(f"   Methods: {', '.join(endpoint.get('methods', []))}")
            print(f"   File Relevance: {endpoint['file_relevance']}")
            if endpoint.get('method_signatures'):
                print(f"   Method Signatures: {', '.join(endpoint['method_signatures'])}")
            print()
        
        # PDF Viewer Components
        components = analysis.get('pdf_viewer_components', {})
        
        # Visualforce Pages
        vf_pages = components.get('visualforce_pages', [])
        if vf_pages:
            print(f"\n📄 VISUALFORCE PDF VIEWERS: {len(vf_pages)} found")
            print("-" * 50)
            
            for page in vf_pages:
                print(f"🔍 {page['name']}")
                if page.get('namespace'):
                    print(f"   Namespace: {page['namespace']}")
                if page.get('master_label'):
                    print(f"   Label: {page['master_label']}")
                
                if page.get('javascript_blocks', 0) > 0:
                    print(f"   JavaScript Blocks: {page['javascript_blocks']}")
                
                if page.get('iframe_sources'):
                    print(f"   Iframe Sources: {page['iframe_sources']}")
                
                if page.get('url_patterns'):
                    print(f"   S3/External URLs Found:")
                    for url in page['url_patterns']:
                        print(f"     • {url}")
                
                if page.get('rest_calls'):
                    print(f"   REST Calls Found:")
                    for call in page['rest_calls']:
                        print(f"     • {call}")
                
                # Show JavaScript code if it contains relevant patterns
                if page.get('javascript_code'):
                    for js_block in page['javascript_code']:
                        if any(keyword in js_block.lower() for keyword in ['url', 'endpoint', 'document', 'file']):
                            print(f"   JavaScript Preview:")
                            print(f"     {js_block[:300]}...")
                            break
                print()
        
        # Lightning Components
        lightning_components = components.get('lightning_components', [])
        if lightning_components:
            print(f"\n⚡ LIGHTNING PDF VIEWERS: {len(lightning_components)} found")
            print("-" * 50)
            
            for comp in lightning_components:
                print(f"🔍 {comp['developer_name']}")
                if comp.get('namespace'):
                    print(f"   Namespace: {comp['namespace']}")
                if comp.get('description'):
                    print(f"   Description: {comp['description']}")
                
                if comp.get('url_patterns'):
                    print(f"   S3/External URLs Found:")
                    for url in comp['url_patterns']:
                        print(f"     • {url}")
                
                if comp.get('rest_calls'):
                    print(f"   REST Calls Found:")
                    for call in comp['rest_calls']:
                        print(f"     • {call}")
                
                if comp.get('javascript_code'):
                    for js in comp['javascript_code']:
                        if any(keyword in js['code'].lower() for keyword in ['url', 'endpoint', 'document']):
                            print(f"   {js['type']} JavaScript Preview:")
                            print(f"     {js['code'][:300]}...")
                print()
        
        # Proxy Endpoint Tests
        proxy_tests = analysis.get('proxy_endpoint_tests', [])
        successful_tests = [t for t in proxy_tests if t.get('status_code') == 200 and t.get('content_length', 0) > 100]
        
        print(f"\n🔍 PROXY ENDPOINT TESTS: {len(proxy_tests)} tested, {len(successful_tests)} successful")
        print("-" * 50)
        
        if successful_tests:
            print("✅ WORKING ENDPOINTS FOUND:")
            for test in successful_tests[:3]:
                print(f"   • {test['test_url']}")
                print(f"     Status: {test['status_code']}, Type: {test.get('content_type')}, Size: {test.get('content_length')}")
                if test.get('response_preview'):
                    print(f"     Response: {test['response_preview']}")
                print()
        else:
            print("❌ No working proxy endpoints found in standard patterns")
        
        # Final Strategy Recommendations
        print("\n" + "=" * 80)
        print("🎯 REVERSE ENGINEERING CONCLUSIONS & NEXT STEPS")
        print("=" * 80)
        
        recommendations = []
        
        if successful_tests:
            recommendations.append(f"✅ Found {len(successful_tests)} working proxy endpoints - use these for file access")
            recommendations.append("🔧 Implement file download using discovered proxy endpoint pattern")
        
        if relevant_endpoints:
            recommendations.append(f"✅ Found {len(relevant_endpoints)} file-related REST endpoints - examine their implementation")
        
        # Check for embedded URLs in components
        embedded_urls = []
        for page in vf_pages:
            embedded_urls.extend(page.get('url_patterns', []))
        for comp in lightning_components:
            embedded_urls.extend(comp.get('url_patterns', []))
        
        if embedded_urls:
            recommendations.append(f"✅ Found {len(embedded_urls)} embedded S3 URLs - examine how they're constructed")
        
        # Check for REST calls in components
        rest_calls = []
        for page in vf_pages:
            rest_calls.extend(page.get('rest_calls', []))
        for comp in lightning_components:
            rest_calls.extend(comp.get('rest_calls', []))
        
        if rest_calls:
            recommendations.append(f"✅ Found {len(rest_calls)} REST API calls in components - these may proxy S3 access")
        
        if not recommendations:
            recommendations.append("❌ No obvious proxy mechanism found")
            recommendations.append("💡 PDF viewer may be using pre-signed URLs generated server-side")
            recommendations.append("💡 Consider browser network inspection of working PDF viewer")
            recommendations.append("💡 May need to examine page source when PDF viewer loads")
        
        for rec in recommendations:
            print(rec)
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("PDF Viewer Reverse Engineering")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        engineer = PDFViewerReverseEngineer(logger)
        
        if not engineer.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        analysis = engineer.comprehensive_reverse_engineering()
        engineer.print_analysis_results(analysis)
        
        return True
        
    except KeyboardInterrupt:
        logger.info("⚠️ Analysis interrupted by user")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)