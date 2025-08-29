#!/usr/bin/env python3
"""
Aura Action Analysis Script
===========================

Analyzes the Aura framework calls used by the PDF viewer to understand
how it retrieves file content from S3. Based on the captured network traffic:

URL: https://incitetax.lightning.force.com/aura?r=50&aura.ApexAction.execute=1
Method: POST
Record: a1cUU000005bmkLYAQ

Usage:
python analyze_aura_action.py
"""

import os
import sys
import logging
import requests
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
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


class AuraActionAnalyzer:
    """Analyzes Aura framework actions used by the PDF viewer."""
    
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
    
    def find_pdf_editor_apex_methods(self) -> List[Dict]:
        """Find Apex methods that might be called by the PDF Editor."""
        try:
            self.logger.info("🔍 Finding PDF Editor Apex methods...")
            
            # Look for classes that might contain PDF-related methods
            apex_query = """
                SELECT Id, Name, NamespacePrefix, ApiVersion, CreatedDate, LastModifiedDate
                FROM ApexClass
                WHERE (Name LIKE '%PDF%'
                   OR Name LIKE '%Document%'
                   OR Name LIKE '%File%'
                   OR Name LIKE '%TL_%')
                ORDER BY Name
            """
            
            try:
                result = self.sf.query(apex_query)
                
                apex_classes = []
                for record in result['records']:
                    apex_classes.append({
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record.get('NamespacePrefix'),
                        'api_version': record.get('ApiVersion'),
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate']
                    })
                
                return apex_classes
                
            except Exception as e:
                self.logger.error(f"Error querying Apex classes: {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding PDF Editor Apex methods: {e}")
            return []
    
    def test_aura_action_patterns(self, record_id: str) -> List[Dict]:
        """Test common Aura action patterns that might be used by PDF viewer."""
        try:
            self.logger.info(f"🔍 Testing Aura action patterns for record: {record_id}")
            
            # Get the record details first
            record_query = f"""
                SELECT Id, Name, Document__c, Account__c
                FROM DocListEntry__c
                WHERE Id = '{record_id}'
            """
            
            record_info = {}
            try:
                record_result = self.sf.query(record_query)
                if record_result['records']:
                    record_info = record_result['records'][0]
            except Exception as e:
                self.logger.error(f"Error getting record info: {e}")
                return []
            
            # Common Aura action patterns for file/document access
            action_patterns = [
                # PDF Editor specific actions
                {
                    'name': 'PDF Editor - Get Document',
                    'action': 'c.getDocument',
                    'params': {'recordId': record_id}
                },
                {
                    'name': 'PDF Editor - Get File Content',
                    'action': 'c.getFileContent',
                    'params': {'recordId': record_id}
                },
                {
                    'name': 'PDF Editor - Get PDF URL',
                    'action': 'c.getPDFUrl',
                    'params': {'recordId': record_id}
                },
                # Generic document actions
                {
                    'name': 'Document Controller - Get Content',
                    'action': 'c.getDocumentContent',
                    'params': {'docListEntryId': record_id}
                },
                {
                    'name': 'File Controller - Download',
                    'action': 'c.downloadFile',
                    'params': {'id': record_id}
                },
                # Trackland specific patterns
                {
                    'name': 'TL Document - Get URL',
                    'action': 'c.getDocumentUrl',
                    'params': {'recordId': record_id, 'objectType': 'DocListEntry__c'}
                }
            ]
            
            test_results = []
            
            # Base Aura endpoint from the network capture
            aura_base_url = f"{self.sf.base_url.replace('/services/data/v59.0/', '')}aura"
            
            for pattern in action_patterns:
                try:
                    self.logger.info(f"Testing: {pattern['name']}")
                    
                    # Construct Aura action payload
                    aura_payload = {
                        "message": json.dumps({
                            "actions": [{
                                "id": "1",
                                "descriptor": pattern['action'],
                                "callingDescriptor": "UNKNOWN",
                                "params": pattern['params']
                            }]
                        }),
                        "aura.context": json.dumps({
                            "mode": "PROD",
                            "fwuid": "dummy",
                            "app": "c:TL_PDF_Editor",
                            "loaded": {"APPLICATION@markup://c:TL_PDF_Editor": "dummy"},
                            "dn": [],
                            "globals": {},
                            "uad": False
                        }),
                        "aura.pageURI": f"/lightning/action/quick/DocListEntry__c.PDF_Editor?recordId={record_id}",
                        "aura.token": None
                    }
                    
                    # Convert to form data
                    form_data = {}
                    for key, value in aura_payload.items():
                        if isinstance(value, (dict, list)):
                            form_data[key] = json.dumps(value)
                        else:
                            form_data[key] = value
                    
                    # Make the Aura request
                    headers = {
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Cookie': f"sid={self.sf.session_id}",
                        'Referer': f"{self.sf.base_url.replace('/services/data/v59.0/', '')}lightning/action/quick/DocListEntry__c.PDF_Editor?recordId={record_id}"
                    }
                    
                    response = requests.post(
                        f"{aura_base_url}?r=1&aura.ApexAction.execute=1",
                        data=form_data,
                        headers=headers,
                        timeout=30
                    )
                    
                    result = {
                        'pattern': pattern,
                        'status_code': response.status_code,
                        'content_type': response.headers.get('Content-Type'),
                        'content_length': len(response.content) if response.content else 0
                    }
                    
                    if response.status_code == 200:
                        try:
                            response_json = response.json()
                            result['response_data'] = response_json
                            
                            # Check if we got file content or URL
                            if 'actions' in response_json:
                                for action in response_json['actions']:
                                    if 'returnValue' in action:
                                        return_value = action['returnValue']
                                        if isinstance(return_value, str):
                                            if 'trackland-doc-storage' in return_value:
                                                result['found_s3_url'] = return_value
                                            elif len(return_value) > 1000:  # Might be file content
                                                result['found_file_content'] = True
                                                result['content_preview'] = return_value[:200] + "..."
                            
                        except json.JSONDecodeError:
                            result['response_text'] = response.text[:500] + "..." if len(response.text) > 500 else response.text
                    else:
                        result['error_response'] = response.text[:200] + "..." if response.text else None
                    
                    test_results.append(result)
                    
                    # If we found a working pattern, note it
                    if result.get('found_s3_url') or result.get('found_file_content'):
                        self.logger.info(f"✅ Found working pattern: {pattern['name']}")
                    
                except Exception as e:
                    test_results.append({
                        'pattern': pattern,
                        'error': str(e)
                    })
            
            return test_results
            
        except Exception as e:
            self.logger.error(f"❌ Error testing Aura actions: {e}")
            return []
    
    def analyze_static_resources(self) -> List[Dict]:
        """Analyze static resources that might be used by PDF viewer."""
        try:
            self.logger.info("🔍 Analyzing static resources...")
            
            # Look for PDF-related static resources
            static_query = """
                SELECT Id, Name, NamespacePrefix, Description, ContentType, BodyLength,
                       CreatedDate, LastModifiedDate
                FROM StaticResource
                WHERE (Name LIKE '%PDF%'
                   OR Name LIKE '%TL_%'
                   OR Name LIKE '%Document%'
                   OR Name LIKE '%Editor%')
                ORDER BY Name
            """
            
            try:
                result = self.sf.query(static_query)
                
                static_resources = []
                for record in result['records']:
                    resource_info = {
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record.get('NamespacePrefix'),
                        'description': record.get('Description'),
                        'content_type': record.get('ContentType'),
                        'body_length': record.get('BodyLength'),
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate']
                    }
                    
                    # Try to get the static resource URL
                    if record.get('NamespacePrefix'):
                        resource_url = f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/{record['NamespacePrefix']}__{record['Name']}"
                    else:
                        resource_url = f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/{record['Name']}"
                    
                    resource_info['resource_url'] = resource_url
                    static_resources.append(resource_info)
                
                return static_resources
                
            except Exception as e:
                self.logger.error(f"Error querying static resources: {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error analyzing static resources: {e}")
            return []
    
    def comprehensive_aura_analysis(self) -> Dict:
        """Perform comprehensive analysis of Aura actions and PDF viewer."""
        self.logger.info("🔍 Starting comprehensive Aura action analysis...")
        
        # Test with the record ID from network capture
        test_record_id = "a1cUU000005bmkLYAQ"
        
        analysis_results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'test_record_id': test_record_id,
            'apex_methods': [],
            'aura_action_tests': [],
            'static_resources': []
        }
        
        # Find PDF Editor Apex methods
        analysis_results['apex_methods'] = self.find_pdf_editor_apex_methods()
        
        # Test Aura action patterns
        analysis_results['aura_action_tests'] = self.test_aura_action_patterns(test_record_id)
        
        # Analyze static resources
        analysis_results['static_resources'] = self.analyze_static_resources()
        
        return analysis_results
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted analysis results."""
        print("\n" + "=" * 80)
        print("AURA ACTION ANALYSIS - PDF VIEWER REVERSE ENGINEERING")
        print("=" * 80)
        
        test_record_id = analysis.get('test_record_id')
        print(f"Test Record ID: {test_record_id}")
        
        # Apex Methods
        apex_methods = analysis.get('apex_methods', [])
        if apex_methods:
            print(f"\n⚡ APEX METHODS FOUND: {len(apex_methods)}")
            print("-" * 50)
            
            for method in apex_methods[:10]:  # Show top 10
                print(f"• {method['name']}")
                if method.get('namespace'):
                    print(f"  Namespace: {method['namespace']}")
                print(f"  Modified: {method['modified_date']}")
                print()
        
        # Aura Action Tests
        aura_tests = analysis.get('aura_action_tests', [])
        successful_tests = [t for t in aura_tests if t.get('found_s3_url') or t.get('found_file_content')]
        
        print(f"\n🎯 AURA ACTION TESTS: {len(aura_tests)} tested, {len(successful_tests)} successful")
        print("-" * 50)
        
        if successful_tests:
            print("✅ SUCCESSFUL AURA ACTIONS FOUND:")
            for test in successful_tests:
                pattern = test['pattern']
                print(f"🔥 {pattern['name']}")
                print(f"   Action: {pattern['action']}")
                print(f"   Status: {test['status_code']}")
                
                if test.get('found_s3_url'):
                    print(f"   🌐 S3 URL Found: {test['found_s3_url']}")
                
                if test.get('found_file_content'):
                    print(f"   📄 File Content Found: {test['content_preview']}")
                
                if test.get('response_data'):
                    print(f"   📊 Response Data Available")
                print()
        else:
            print("❌ No successful Aura actions found")
            
            # Show failed attempts
            failed_tests = [t for t in aura_tests if not t.get('error') and t.get('status_code') != 200][:3]
            if failed_tests:
                print("\n❌ Failed attempts (showing first 3):")
                for test in failed_tests:
                    pattern = test['pattern']
                    print(f"  • {pattern['name']}: Status {test.get('status_code', 'N/A')}")
                    if test.get('error_response'):
                        print(f"    Error: {test['error_response'][:100]}...")
        
        # Static Resources
        static_resources = analysis.get('static_resources', [])
        pdf_resources = [r for r in static_resources if 'pdf' in r['name'].lower() or 'TL_PDF' in r['name']]
        
        print(f"\n📦 STATIC RESOURCES: {len(static_resources)} total, {len(pdf_resources)} PDF-related")
        print("-" * 50)
        
        if pdf_resources:
            for resource in pdf_resources:
                print(f"• {resource['name']}")
                if resource.get('namespace'):
                    print(f"  Namespace: {resource['namespace']}")
                print(f"  Type: {resource.get('content_type', 'Unknown')}")
                print(f"  Size: {resource.get('body_length', 0)} bytes")
                print(f"  URL: {resource.get('resource_url')}")
                print()
        
        # Final Recommendations
        print("\n" + "=" * 80)
        print("🎯 BREAKTHROUGH ANALYSIS & NEXT STEPS")
        print("=" * 80)
        
        recommendations = []
        
        if successful_tests:
            recommendations.append(f"✅ BREAKTHROUGH: Found {len(successful_tests)} working Aura actions!")
            
            for test in successful_tests:
                if test.get('found_s3_url'):
                    recommendations.append(f"🌐 Direct S3 URL access discovered via: {test['pattern']['action']}")
                if test.get('found_file_content'):
                    recommendations.append(f"📄 File content streaming discovered via: {test['pattern']['action']}")
            
            recommendations.append("🔧 IMPLEMENTATION STRATEGY:")
            recommendations.append("  1. Use successful Aura action pattern in backup script")
            recommendations.append("  2. Implement Aura framework calls instead of direct S3 access")
            recommendations.append("  3. Update backup script to use Salesforce session + Aura calls")
            
        else:
            recommendations.append("❌ No working Aura actions found with standard patterns")
            
            if apex_methods:
                tlnd_methods = [m for m in apex_methods if m.get('namespace') == 'tlnd']
                if tlnd_methods:
                    recommendations.append(f"💡 Found {len(tlnd_methods)} TLND namespace methods - examine these")
            
            if pdf_resources:
                recommendations.append(f"💡 Found {len(pdf_resources)} PDF static resources - may contain client logic")
            
            recommendations.append("💡 ALTERNATIVE APPROACHES:")
            recommendations.append("  1. Examine TL_PDF_Editor static resource for client-side logic")
            recommendations.append("  2. Use browser dev tools to capture exact Aura payload")
            recommendations.append("  3. Look for hidden iframe or proxy endpoints")
        
        for rec in recommendations:
            print(rec)
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("Aura Action Analysis")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        analyzer = AuraActionAnalyzer(logger)
        
        if not analyzer.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        analysis = analyzer.comprehensive_aura_analysis()
        analyzer.print_analysis_results(analysis)
        
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