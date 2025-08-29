#!/usr/bin/env python3
"""
PDF Editor Action Analysis Script
=================================

Analyzes the PDF_Editor Lightning Quick Action to understand how it accesses S3 files.
Based on the captured network traffic showing:
- Action: DocListEntry__c.PDF_Editor
- Record ID: a1cUU000005vAEHYA2

Usage:
python analyze_pdf_editor_action.py
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


class PDFEditorActionAnalyzer:
    """Analyzes the PDF_Editor Lightning Action to find S3 access mechanism."""
    
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
    
    def find_pdf_editor_action(self) -> Dict:
        """Find the PDF_Editor Lightning Action definition."""
        try:
            self.logger.info("🔍 Finding PDF_Editor Lightning Action...")
            
            # Query QuickActionDefinition for PDF_Editor
            action_query = """
                SELECT Id, DeveloperName, Type, TargetSobjectType, 
                       LightningComponentBundleId, QuickActionLayout,
                       MasterLabel, Description, CreatedDate, LastModifiedDate
                FROM QuickActionDefinition
                WHERE DeveloperName = 'PDF_Editor'
                AND TargetSobjectType = 'DocListEntry__c'
            """
            
            try:
                result = self.sf.query(action_query)
                if result['records']:
                    return result['records'][0]
                else:
                    self.logger.warning("❌ PDF_Editor action not found")
                    return {}
            except Exception as e:
                self.logger.error(f"Error querying PDF_Editor action: {e}")
                return {}
                
        except Exception as e:
            self.logger.error(f"❌ Error finding PDF_Editor action: {e}")
            return {}
    
    def analyze_lightning_component_bundle(self, bundle_id: str) -> Dict:
        """Analyze the Lightning Component Bundle used by PDF_Editor."""
        try:
            self.logger.info(f"🔍 Analyzing Lightning Component Bundle: {bundle_id}")
            
            # Get bundle info
            bundle_query = f"""
                SELECT Id, DeveloperName, NamespacePrefix, Description, MasterLabel,
                       CreatedDate, LastModifiedDate, ApiVersion
                FROM AuraDefinitionBundle
                WHERE Id = '{bundle_id}'
            """
            
            bundle_info = {}
            try:
                bundle_result = self.sf.query(bundle_query)
                if bundle_result['records']:
                    bundle_info = bundle_result['records'][0]
            except Exception as e:
                self.logger.error(f"Error getting bundle info: {e}")
                return {}
            
            # Get all definitions for this bundle
            definitions_query = f"""
                SELECT Id, DefType, Format, Source
                FROM AuraDefinition
                WHERE AuraDefinitionBundleId = '{bundle_id}'
            """
            
            definitions = []
            try:
                def_result = self.sf.query(definitions_query)
                definitions = def_result['records']
            except Exception as e:
                self.logger.error(f"Error getting bundle definitions: {e}")
            
            return {
                'bundle_info': bundle_info,
                'definitions': definitions
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing component bundle: {e}")
            return {}
    
    def extract_s3_access_patterns(self, source_code: str, def_type: str) -> Dict:
        """Extract S3 access patterns from component source code."""
        patterns = {
            'urls': [],
            'api_calls': [],
            'variables': [],
            'methods': [],
            'imports': []
        }
        
        if not source_code:
            return patterns
        
        import re
        
        # Extract URLs
        url_pattern = r'https?://[^\s"\'<>]+'
        urls = re.findall(url_pattern, source_code)
        for url in urls:
            if 'amazonaws' in url or 's3' in url or 'trackland' in url:
                patterns['urls'].append(url)
        
        # Extract API calls and endpoints
        api_patterns = [
            r'/services/apexrest/[^\s"\'<>]+',
            r'callout:[^\s"\'<>]+',
            r'\$A\.enqueueAction\([^)]+\)',
            r'action\.setParams\([^)]+\)',
            r'component\.get\([^)]+\)',
            r'helper\.\w+',
            r'controller\.\w+'
        ]
        
        for pattern in api_patterns:
            matches = re.findall(pattern, source_code, re.IGNORECASE)
            patterns['api_calls'].extend(matches)
        
        # Extract variable declarations that might contain URLs or IDs
        var_patterns = [
            r'(var|let|const)\s+(\w*[Uu]rl\w*)\s*=\s*["\']([^"\']+)["\']',
            r'(var|let|const)\s+(\w*[Ee]ndpoint\w*)\s*=\s*["\']([^"\']+)["\']',
            r'(var|let|const)\s+(\w*[Ii]d\w*)\s*=\s*["\']([^"\']+)["\']',
            r'(var|let|const)\s+(\w*[Dd]ocument\w*)\s*=\s*["\']([^"\']+)["\']'
        ]
        
        for pattern in var_patterns:
            matches = re.findall(pattern, source_code, re.IGNORECASE)
            for match in matches:
                patterns['variables'].append({
                    'type': match[0],
                    'name': match[1],
                    'value': match[2] if len(match) > 2 else ''
                })
        
        # Extract method names that might handle file access
        method_pattern = r'(\w+)\s*:\s*function\s*\([^)]*\)|function\s+(\w+)\s*\([^)]*\)'
        method_matches = re.findall(method_pattern, source_code)
        for match in method_matches:
            method_name = match[0] or match[1]
            if any(keyword in method_name.lower() for keyword in ['download', 'load', 'get', 'fetch', 'view', 'pdf', 'file', 'document']):
                patterns['methods'].append(method_name)
        
        # Extract import statements
        import_patterns = [
            r'import\s+[^;]+;',
            r'from\s+["\'][^"\']+["\']',
            r'lightning/[^"\';\s]+'
        ]
        
        for pattern in import_patterns:
            matches = re.findall(pattern, source_code, re.IGNORECASE)
            patterns['imports'].extend(matches)
        
        return patterns
    
    def test_pdf_editor_with_sample_record(self, record_id: str) -> Dict:
        """Test the PDF Editor with a sample DocListEntry record."""
        try:
            self.logger.info(f"🔍 Testing PDF Editor with record: {record_id}")
            
            # First, get the record details
            record_query = f"""
                SELECT Id, Name, Document__c, Account__c, Account__r.Name
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
                return {}
            
            # Try to access the Lightning Action URL directly
            action_url = f"{self.sf.base_url}lightning/action/quick/DocListEntry__c.PDF_Editor"
            
            test_results = {
                'record_info': record_info,
                'action_url': action_url,
                'access_tests': []
            }
            
            # Test different ways to access the action
            test_urls = [
                f"{action_url}?recordId={record_id}",
                f"{action_url}?objectApiName=DocListEntry__c&recordId={record_id}",
                f"{self.sf.base_url}lightning/r/DocListEntry__c/{record_id}/view"
            ]
            
            for test_url in test_urls:
                try:
                    headers = {
                        'Authorization': f'Bearer {self.sf.session_id}',
                        'Content-Type': 'application/json'
                    }
                    
                    response = requests.get(test_url, headers=headers, timeout=10, allow_redirects=False)
                    
                    test_results['access_tests'].append({
                        'url': test_url,
                        'status_code': response.status_code,
                        'headers': dict(response.headers),
                        'content_preview': response.text[:500] + "..." if response.text and len(response.text) > 500 else response.text
                    })
                    
                except Exception as e:
                    test_results['access_tests'].append({
                        'url': test_url,
                        'error': str(e)
                    })
            
            return test_results
            
        except Exception as e:
            self.logger.error(f"❌ Error testing PDF Editor: {e}")
            return {}
    
    def find_document_url_construction(self) -> List[Dict]:
        """Find how Document__c URLs are constructed by examining related code."""
        try:
            self.logger.info("🔍 Looking for Document URL construction patterns...")
            
            # Look for triggers or processes that might set Document__c URLs
            trigger_patterns = []
            
            # Check for Process Builder or Flow that might set Document__c
            try:
                flow_query = """
                    SELECT Id, MasterLabel, ProcessType, TriggerType, Description
                    FROM FlowDefinitionView
                    WHERE (MasterLabel LIKE '%Document%' 
                       OR MasterLabel LIKE '%PDF%'
                       OR MasterLabel LIKE '%File%'
                       OR Description LIKE '%Document__c%')
                    AND IsActive = TRUE
                """
                
                flow_result = self.sf.query(flow_query)
                trigger_patterns.extend([
                    {
                        'type': 'Flow',
                        'name': r.get('MasterLabel'),
                        'process_type': r.get('ProcessType'),
                        'trigger_type': r.get('TriggerType'),
                        'description': r.get('Description')
                    }
                    for r in flow_result['records']
                ])
                
            except Exception as e:
                self.logger.debug(f"Flow query failed: {e}")
            
            return trigger_patterns
            
        except Exception as e:
            self.logger.error(f"❌ Error finding URL construction: {e}")
            return []
    
    def comprehensive_pdf_editor_analysis(self) -> Dict:
        """Perform comprehensive analysis of the PDF Editor action."""
        self.logger.info("🔍 Starting comprehensive PDF Editor analysis...")
        
        # Get a sample DocListEntry record for testing
        sample_record_id = "a1cUU000005vAEHYA2"  # From the network capture
        
        analysis_results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'pdf_editor_action': {},
            'component_bundle': {},
            'source_code_analysis': {},
            'sample_record_test': {},
            'url_construction_patterns': []
        }
        
        # Find PDF Editor action
        analysis_results['pdf_editor_action'] = self.find_pdf_editor_action()
        
        # Analyze the component bundle
        pdf_action = analysis_results['pdf_editor_action']
        if pdf_action.get('LightningComponentBundleId'):
            bundle_analysis = self.analyze_lightning_component_bundle(pdf_action['LightningComponentBundleId'])
            analysis_results['component_bundle'] = bundle_analysis
            
            # Analyze source code in the bundle
            if bundle_analysis.get('definitions'):
                source_analysis = {}
                for definition in bundle_analysis['definitions']:
                    def_type = definition.get('DefType')
                    source = definition.get('Source', '')
                    
                    if source and def_type:
                        patterns = self.extract_s3_access_patterns(source, def_type)
                        source_analysis[def_type] = {
                            'source_length': len(source),
                            'patterns': patterns,
                            'source_preview': source[:1000] + "..." if len(source) > 1000 else source
                        }
                
                analysis_results['source_code_analysis'] = source_analysis
        
        # Test with sample record
        analysis_results['sample_record_test'] = self.test_pdf_editor_with_sample_record(sample_record_id)
        
        # Find URL construction patterns
        analysis_results['url_construction_patterns'] = self.find_document_url_construction()
        
        return analysis_results
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted analysis results."""
        print("\n" + "=" * 80)
        print("PDF EDITOR ACTION ANALYSIS")
        print("=" * 80)
        
        # PDF Editor Action Info
        pdf_action = analysis.get('pdf_editor_action', {})
        if pdf_action:
            print(f"\n🎯 PDF EDITOR ACTION FOUND")
            print("-" * 50)
            print(f"ID: {pdf_action.get('Id')}")
            print(f"Developer Name: {pdf_action.get('DeveloperName')}")
            print(f"Type: {pdf_action.get('Type')}")
            print(f"Target Object: {pdf_action.get('TargetSobjectType')}")
            print(f"Component Bundle ID: {pdf_action.get('LightningComponentBundleId')}")
            print(f"Label: {pdf_action.get('MasterLabel')}")
            if pdf_action.get('Description'):
                print(f"Description: {pdf_action.get('Description')}")
        
        # Component Bundle Analysis
        component_bundle = analysis.get('component_bundle', {})
        if component_bundle.get('bundle_info'):
            bundle_info = component_bundle['bundle_info']
            print(f"\n⚡ LIGHTNING COMPONENT BUNDLE")
            print("-" * 50)
            print(f"Developer Name: {bundle_info.get('DeveloperName')}")
            print(f"Namespace: {bundle_info.get('NamespacePrefix')}")
            print(f"Description: {bundle_info.get('Description')}")
            print(f"API Version: {bundle_info.get('ApiVersion')}")
            
            definitions = component_bundle.get('definitions', [])
            print(f"Component Definitions: {len(definitions)}")
            for definition in definitions:
                print(f"  • {definition.get('DefType')} ({definition.get('Format')})")
        
        # Source Code Analysis
        source_analysis = analysis.get('source_code_analysis', {})
        if source_analysis:
            print(f"\n🔍 SOURCE CODE ANALYSIS")
            print("-" * 50)
            
            for def_type, analysis_data in source_analysis.items():
                patterns = analysis_data.get('patterns', {})
                print(f"\n{def_type} Analysis:")
                print(f"  Source Length: {analysis_data.get('source_length')} characters")
                
                if patterns.get('urls'):
                    print(f"  🌐 S3/External URLs Found:")
                    for url in patterns['urls']:
                        print(f"    • {url}")
                
                if patterns.get('api_calls'):
                    print(f"  📞 API Calls Found:")
                    for call in patterns['api_calls'][:5]:  # Show top 5
                        print(f"    • {call}")
                
                if patterns.get('methods'):
                    print(f"  🔧 Relevant Methods:")
                    for method in patterns['methods']:
                        print(f"    • {method}")
                
                if patterns.get('variables'):
                    print(f"  📝 Relevant Variables:")
                    for var in patterns['variables'][:3]:  # Show top 3
                        print(f"    • {var['name']}: {var['value']}")
                
                # Show source preview for most relevant components
                if (patterns.get('urls') or patterns.get('api_calls')) and analysis_data.get('source_preview'):
                    print(f"  📄 Source Preview:")
                    preview_lines = analysis_data['source_preview'].split('\n')[:10]
                    for line in preview_lines:
                        print(f"    {line}")
                    if len(preview_lines) >= 10:
                        print(f"    ... (truncated)")
        
        # Sample Record Test
        sample_test = analysis.get('sample_record_test', {})
        if sample_test.get('record_info'):
            print(f"\n📄 SAMPLE RECORD TEST")
            print("-" * 50)
            record_info = sample_test['record_info']
            print(f"Record ID: {record_info.get('Id')}")
            print(f"Name: {record_info.get('Name')}")
            print(f"Document URL: {record_info.get('Document__c')}")
            if record_info.get('Account__r'):
                print(f"Account: {record_info['Account__r'].get('Name')}")
            
            access_tests = sample_test.get('access_tests', [])
            print(f"\nAccess Tests: {len(access_tests)} performed")
            for test in access_tests:
                if 'error' not in test:
                    print(f"  • {test['url']}")
                    print(f"    Status: {test['status_code']}")
                    if test['status_code'] in [200, 302, 301]:
                        print(f"    ✅ Potentially accessible")
                else:
                    print(f"  • Error: {test['error']}")
        
        # URL Construction Patterns
        url_patterns = analysis.get('url_construction_patterns', [])
        if url_patterns:
            print(f"\n🔗 URL CONSTRUCTION PATTERNS")
            print("-" * 50)
            for pattern in url_patterns:
                print(f"Type: {pattern.get('type')}")
                print(f"Name: {pattern.get('name')}")
                if pattern.get('description'):
                    print(f"Description: {pattern.get('description')}")
                print()
        
        # Final Recommendations
        print("\n" + "=" * 80)
        print("🎯 PDF ACCESS STRATEGY RECOMMENDATIONS")
        print("=" * 80)
        
        recommendations = []
        
        if pdf_action.get('LightningComponentBundleId'):
            recommendations.append("✅ Found PDF_Editor Lightning Action with component bundle")
        
        if source_analysis:
            total_urls = sum(len(data.get('patterns', {}).get('urls', [])) for data in source_analysis.values())
            total_api_calls = sum(len(data.get('patterns', {}).get('api_calls', [])) for data in source_analysis.values())
            
            if total_urls > 0:
                recommendations.append(f"🌐 Found {total_urls} S3/external URLs in component source")
            
            if total_api_calls > 0:
                recommendations.append(f"📞 Found {total_api_calls} API calls - may include file proxy endpoints")
        
        if sample_test.get('record_info', {}).get('Document__c'):
            doc_url = sample_test['record_info']['Document__c']
            recommendations.append(f"📄 Sample record has direct S3 URL: {doc_url[:50]}...")
        
        if not recommendations:
            recommendations.append("❌ No obvious file access mechanism found in PDF Editor")
            recommendations.append("💡 The component may be using iframe with direct S3 URLs")
            recommendations.append("💡 Consider browser developer tools inspection of working PDF viewer")
        
        for rec in recommendations:
            print(rec)
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("PDF Editor Action Analysis")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        analyzer = PDFEditorActionAnalyzer(logger)
        
        if not analyzer.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        analysis = analyzer.comprehensive_pdf_editor_analysis()
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