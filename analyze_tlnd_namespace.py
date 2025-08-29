#!/usr/bin/env python3
"""
TLND Namespace Analysis Script
=============================

Specifically analyzes the Trackland Platform Core (tlnd namespace) and 
TL - Document Manager package components to understand how the PDF viewer
accesses S3 files and find the authentication mechanism.

Usage:
python analyze_tlnd_namespace.py
"""

import os
import sys
import logging
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


class TLNDAnalyzer:
    """Analyzes TLND namespace components for S3 access patterns."""
    
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
    
    def find_tlnd_apex_classes(self) -> List[Dict]:
        """Find all Apex classes in the tlnd namespace."""
        try:
            self.logger.info("🔍 Finding TLND namespace Apex classes...")
            
            apex_query = """
                SELECT Id, Name, NamespacePrefix, Body, CreatedDate, LastModifiedDate,
                       ApiVersion, Status
                FROM ApexClass
                WHERE NamespacePrefix = 'tlnd'
                ORDER BY Name
            """
            
            try:
                result = self.sf.query(apex_query)
                
                apex_classes = []
                for record in result['records']:
                    body = record.get('Body', '')
                    
                    # Analyze for S3/file-related keywords
                    s3_keywords = [
                        's3', 'aws', 'amazon', 'bucket', 'presigned', 'signature',
                        'trackland-doc-storage', 'download', 'file', 'blob',
                        'credential', 'access', 'secret', 'token', 'auth',
                        'pdf', 'document', 'viewer', 'stream'
                    ]
                    
                    keyword_matches = []
                    keyword_contexts = {}
                    
                    if body:
                        body_lines = body.split('\n')
                        for i, line in enumerate(body_lines):
                            line_lower = line.lower()
                            for keyword in s3_keywords:
                                if keyword in line_lower:
                                    if keyword not in keyword_matches:
                                        keyword_matches.append(keyword)
                                    
                                    # Capture context around the keyword
                                    context_start = max(0, i-2)
                                    context_end = min(len(body_lines), i+3)
                                    context = '\n'.join(body_lines[context_start:context_end])
                                    
                                    if keyword not in keyword_contexts:
                                        keyword_contexts[keyword] = []
                                    keyword_contexts[keyword].append(context)
                    
                    apex_classes.append({
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record['NamespacePrefix'],
                        'api_version': record.get('ApiVersion'),
                        'status': record.get('Status'),
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate'],
                        'body_length': len(body),
                        'keyword_matches': keyword_matches,
                        'keyword_contexts': keyword_contexts,
                        'relevance_score': len(keyword_matches)
                    })
                
                # Sort by relevance
                apex_classes.sort(key=lambda x: x['relevance_score'], reverse=True)
                return apex_classes
                
            except Exception as e:
                self.logger.error(f"Error querying TLND Apex classes: {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding TLND Apex classes: {e}")
            return []
    
    def find_tlnd_visualforce_pages(self) -> List[Dict]:
        """Find all Visualforce pages in the tlnd namespace."""
        try:
            self.logger.info("🔍 Finding TLND namespace Visualforce pages...")
            
            vf_query = """
                SELECT Id, Name, NamespacePrefix, Markup, MasterLabel,
                       CreatedDate, LastModifiedDate, ApiVersion
                FROM ApexPage
                WHERE NamespacePrefix = 'tlnd'
                ORDER BY Name
            """
            
            try:
                result = self.sf.query(vf_query)
                
                vf_pages = []
                for record in result['records']:
                    markup = record.get('Markup', '')
                    
                    # Look for file/PDF-related patterns
                    pdf_keywords = [
                        'pdf', 'document', 'viewer', 'iframe', 's3', 'amazonaws',
                        'trackland', 'download', 'file', 'blob', 'stream',
                        'presigned', 'signature', 'auth', 'token', 'credential'
                    ]
                    
                    keyword_matches = []
                    keyword_contexts = {}
                    
                    if markup:
                        markup_lines = markup.split('\n')
                        for i, line in enumerate(markup_lines):
                            line_lower = line.lower()
                            for keyword in pdf_keywords:
                                if keyword in line_lower:
                                    if keyword not in keyword_matches:
                                        keyword_matches.append(keyword)
                                    
                                    # Capture context
                                    context_start = max(0, i-2)
                                    context_end = min(len(markup_lines), i+3)
                                    context = '\n'.join(markup_lines[context_start:context_end])
                                    
                                    if keyword not in keyword_contexts:
                                        keyword_contexts[keyword] = []
                                    keyword_contexts[keyword].append(context)
                    
                    vf_pages.append({
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record['NamespacePrefix'],
                        'master_label': record.get('MasterLabel'),
                        'api_version': record.get('ApiVersion'),
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate'],
                        'markup_length': len(markup),
                        'keyword_matches': keyword_matches,
                        'keyword_contexts': keyword_contexts,
                        'relevance_score': len(keyword_matches)
                    })
                
                vf_pages.sort(key=lambda x: x['relevance_score'], reverse=True)
                return vf_pages
                
            except Exception as e:
                self.logger.error(f"Error querying TLND VF pages: {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding TLND VF pages: {e}")
            return []
    
    def find_tlnd_lightning_components(self) -> List[Dict]:
        """Find Lightning components in the tlnd namespace."""
        try:
            self.logger.info("🔍 Finding TLND namespace Lightning components...")
            
            # AuraDefinitionBundle for Lightning components
            aura_query = """
                SELECT Id, DeveloperName, NamespacePrefix, Description, MasterLabel,
                       CreatedDate, LastModifiedDate, ApiVersion
                FROM AuraDefinitionBundle
                WHERE NamespacePrefix = 'tlnd'
                ORDER BY DeveloperName
            """
            
            try:
                result = self.sf.query(aura_query)
                
                lightning_components = []
                for record in result['records']:
                    # Also try to get the component definition
                    component_id = record['Id']
                    
                    # Query for AuraDefinition to get the actual component code
                    definition_query = f"""
                        SELECT Id, DefType, Format, Source
                        FROM AuraDefinition
                        WHERE AuraDefinitionBundleId = '{component_id}'
                        AND DefType IN ('COMPONENT', 'CONTROLLER', 'HELPER')
                    """
                    
                    definitions = []
                    keyword_matches = []
                    keyword_contexts = {}
                    
                    try:
                        def_result = self.sf.query(definition_query)
                        
                        for def_record in def_result['records']:
                            source = def_record.get('Source', '')
                            def_type = def_record.get('DefType')
                            
                            definitions.append({
                                'type': def_type,
                                'format': def_record.get('Format'),
                                'source_length': len(source),
                                'source_preview': source[:500] + "..." if len(source) > 500 else source
                            })
                            
                            # Analyze source for keywords
                            if source:
                                source_lines = source.split('\n')
                                for i, line in enumerate(source_lines):
                                    line_lower = line.lower()
                                    for keyword in ['s3', 'aws', 'download', 'file', 'pdf', 'document', 'trackland']:
                                        if keyword in line_lower:
                                            if keyword not in keyword_matches:
                                                keyword_matches.append(keyword)
                                            
                                            context_start = max(0, i-2)
                                            context_end = min(len(source_lines), i+3)
                                            context = '\n'.join(source_lines[context_start:context_end])
                                            
                                            if keyword not in keyword_contexts:
                                                keyword_contexts[keyword] = []
                                            keyword_contexts[keyword].append(f"{def_type}: {context}")
                    
                    except Exception as def_error:
                        self.logger.debug(f"Could not query definitions for {record['DeveloperName']}: {def_error}")
                    
                    lightning_components.append({
                        'id': record['Id'],
                        'developer_name': record['DeveloperName'],
                        'namespace': record['NamespacePrefix'],
                        'description': record.get('Description', ''),
                        'master_label': record.get('MasterLabel', ''),
                        'api_version': record.get('ApiVersion'),
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate'],
                        'definitions': definitions,
                        'keyword_matches': keyword_matches,
                        'keyword_contexts': keyword_contexts,
                        'relevance_score': len(keyword_matches)
                    })
                
                lightning_components.sort(key=lambda x: x['relevance_score'], reverse=True)
                return lightning_components
                
            except Exception as e:
                self.logger.error(f"Error querying TLND Lightning components: {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding TLND Lightning components: {e}")
            return []
    
    def find_custom_settings_and_metadata(self) -> Dict:
        """Find custom settings and metadata types that might contain S3 configuration."""
        try:
            self.logger.info("🔍 Finding TLND custom settings and metadata...")
            
            # Look for custom settings objects
            objects_url = f"{self.sf.base_url}sobjects/"
            response = self.sf.restful(objects_url)
            
            tlnd_settings = []
            
            for obj_info in response['sobjects']:
                obj_name = obj_info['name']
                obj_label = obj_info['label']
                
                # Look for tlnd namespace objects that might be settings
                if (obj_name.startswith('tlnd__') or 
                    any(keyword in obj_name.lower() for keyword in ['setting', 'config', 'credential', 'aws', 's3'])):
                    
                    try:
                        # Get object metadata
                        obj_metadata = getattr(self.sf, obj_name).describe()
                        
                        # Look for relevant fields
                        relevant_fields = []
                        for field in obj_metadata['fields']:
                            field_name = field['name']
                            field_label = field['label']
                            
                            if any(keyword in field_name.lower() or keyword in field_label.lower()
                                   for keyword in ['s3', 'aws', 'bucket', 'key', 'secret', 'token', 'region', 'credential', 'access']):
                                relevant_fields.append({
                                    'name': field_name,
                                    'label': field_label,
                                    'type': field['type'],
                                    'encrypted': field.get('encrypted', False)
                                })
                        
                        if relevant_fields or obj_name.startswith('tlnd__'):
                            # Try to query for actual data
                            try:
                                sample_query = f"SELECT Id, Name FROM {obj_name} LIMIT 5"
                                sample_result = self.sf.query(sample_query)
                                
                                tlnd_settings.append({
                                    'name': obj_name,
                                    'label': obj_label,
                                    'custom': obj_info['custom'],
                                    'relevant_fields': relevant_fields,
                                    'record_count': len(sample_result['records']),
                                    'sample_records': sample_result['records']
                                })
                                
                            except Exception as query_error:
                                tlnd_settings.append({
                                    'name': obj_name,
                                    'label': obj_label,
                                    'custom': obj_info['custom'],
                                    'relevant_fields': relevant_fields,
                                    'query_error': str(query_error)
                                })
                    
                    except Exception as desc_error:
                        self.logger.debug(f"Could not describe {obj_name}: {desc_error}")
            
            return {
                'custom_settings': tlnd_settings,
                'total_found': len(tlnd_settings)
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error finding TLND settings: {e}")
            return {'error': str(e)}
    
    def find_remote_site_settings(self) -> List[Dict]:
        """Find remote site settings that allow S3 access."""
        try:
            self.logger.info("🔍 Finding remote site settings...")
            
            remote_site_query = """
                SELECT Id, SiteName, EndpointUrl, Description, IsActive,
                       CreatedDate, LastModifiedDate
                FROM RemoteSiteSetting
                WHERE (EndpointUrl LIKE '%amazonaws%'
                   OR EndpointUrl LIKE '%s3%'
                   OR EndpointUrl LIKE '%trackland%'
                   OR SiteName LIKE '%trackland%'
                   OR SiteName LIKE '%s3%')
                ORDER BY SiteName
            """
            
            try:
                result = self.sf.query(remote_site_query)
                return result['records']
            except Exception as e:
                self.logger.debug(f"Remote site query failed: {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding remote site settings: {e}")
            return []
    
    def comprehensive_tlnd_analysis(self) -> Dict:
        """Perform comprehensive analysis of TLND namespace components."""
        self.logger.info("🔍 Starting comprehensive TLND namespace analysis...")
        
        analysis_results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'namespace': 'tlnd',
            'apex_classes': [],
            'visualforce_pages': [],
            'lightning_components': [],
            'custom_settings': {},
            'remote_site_settings': []
        }
        
        # Analyze all components
        analysis_results['apex_classes'] = self.find_tlnd_apex_classes()
        analysis_results['visualforce_pages'] = self.find_tlnd_visualforce_pages()
        analysis_results['lightning_components'] = self.find_tlnd_lightning_components()
        analysis_results['custom_settings'] = self.find_custom_settings_and_metadata()
        analysis_results['remote_site_settings'] = self.find_remote_site_settings()
        
        return analysis_results
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted analysis results with focus on S3 access patterns."""
        print("\n" + "=" * 80)
        print("TLND NAMESPACE ANALYSIS - S3 ACCESS DISCOVERY")
        print("=" * 80)
        
        # Apex Classes Analysis
        apex_classes = analysis['apex_classes']
        relevant_apex = [c for c in apex_classes if c['relevance_score'] > 0]
        
        print(f"\n⚡ APEX CLASSES: {len(apex_classes)} total, {len(relevant_apex)} relevant")
        print("-" * 50)
        
        for cls in relevant_apex[:5]:  # Top 5 most relevant
            print(f"🔥 {cls['name']} (Score: {cls['relevance_score']})")
            print(f"   Keywords: {', '.join(cls['keyword_matches'])}")
            
            # Show relevant code contexts
            for keyword, contexts in cls['keyword_contexts'].items():
                if keyword in ['s3', 'aws', 'presigned', 'signature', 'credential', 'trackland-doc-storage']:
                    print(f"   📝 {keyword.upper()} context:")
                    for context in contexts[:1]:  # Show first context
                        lines = context.split('\n')
                        for line in lines:
                            if keyword.lower() in line.lower():
                                print(f"      → {line.strip()}")
            print()
        
        # Visualforce Pages Analysis
        vf_pages = analysis['visualforce_pages']
        relevant_vf = [p for p in vf_pages if p['relevance_score'] > 0]
        
        print(f"\n📄 VISUALFORCE PAGES: {len(vf_pages)} total, {len(relevant_vf)} relevant")
        print("-" * 50)
        
        for page in relevant_vf[:3]:
            print(f"🔥 {page['name']} (Score: {page['relevance_score']})")
            if page.get('master_label'):
                print(f"   Label: {page['master_label']}")
            print(f"   Keywords: {', '.join(page['keyword_matches'])}")
            
            # Show relevant markup contexts
            for keyword, contexts in page['keyword_contexts'].items():
                if keyword in ['pdf', 'viewer', 'iframe', 's3', 'amazonaws', 'document']:
                    print(f"   📝 {keyword.upper()} context:")
                    for context in contexts[:1]:
                        lines = context.split('\n')
                        for line in lines:
                            if keyword.lower() in line.lower():
                                print(f"      → {line.strip()}")
            print()
        
        # Lightning Components Analysis
        lightning_components = analysis['lightning_components']
        relevant_lightning = [c for c in lightning_components if c['relevance_score'] > 0]
        
        print(f"\n⚡ LIGHTNING COMPONENTS: {len(lightning_components)} total, {len(relevant_lightning)} relevant")
        print("-" * 50)
        
        for comp in relevant_lightning[:3]:
            print(f"🔥 {comp['developer_name']} (Score: {comp['relevance_score']})")
            if comp.get('description'):
                print(f"   Description: {comp['description']}")
            print(f"   Keywords: {', '.join(comp['keyword_matches'])}")
            
            for definition in comp['definitions']:
                if definition['source_preview']:
                    print(f"   📝 {definition['type']} preview:")
                    print(f"      {definition['source_preview'][:200]}...")
            print()
        
        # Custom Settings Analysis
        custom_settings = analysis['custom_settings']
        
        print(f"\n⚙️ CUSTOM SETTINGS: {custom_settings.get('total_found', 0)} found")
        print("-" * 50)
        
        for setting in custom_settings.get('custom_settings', []):
            print(f"🔧 {setting['name']} ({setting['label']})")
            
            if setting.get('relevant_fields'):
                print("   🔑 Relevant fields:")
                for field in setting['relevant_fields']:
                    encrypted_flag = " (ENCRYPTED)" if field.get('encrypted') else ""
                    print(f"      • {field['name']}: {field['label']} ({field['type']}){encrypted_flag}")
            
            if setting.get('record_count'):
                print(f"   📊 Records: {setting['record_count']}")
            
            if setting.get('query_error'):
                print(f"   ⚠️  Query error: {setting['query_error']}")
            print()
        
        # Remote Site Settings Analysis
        remote_sites = analysis['remote_site_settings']
        
        print(f"\n🌐 REMOTE SITE SETTINGS: {len(remote_sites)} found")
        print("-" * 50)
        
        for site in remote_sites:
            status = "✅ Active" if site.get('IsActive') else "❌ Inactive"
            print(f"{status} {site.get('SiteName')}")
            print(f"   URL: {site.get('EndpointUrl')}")
            if site.get('Description'):
                print(f"   Description: {site.get('Description')}")
            print()
        
        # Generate Action Items
        print("=" * 80)
        print("🎯 ACTION ITEMS FOR S3 ACCESS")
        print("=" * 80)
        
        action_items = []
        
        if relevant_apex:
            action_items.append(f"✅ Examine {len(relevant_apex)} Apex classes with S3/file keywords for authentication logic")
        
        if relevant_vf:
            pdf_viewers = [p for p in relevant_vf if 'pdf' in p['name'].lower() or any('viewer' in kw for kw in p['keyword_matches'])]
            if pdf_viewers:
                action_items.append(f"✅ Found {len(pdf_viewers)} PDF viewer pages - examine how they construct file URLs")
        
        if custom_settings.get('custom_settings'):
            cred_settings = [s for s in custom_settings['custom_settings'] if s.get('relevant_fields')]
            if cred_settings:
                action_items.append(f"✅ Query {len(cred_settings)} custom settings for actual S3 credentials")
        
        if remote_sites:
            s3_sites = [s for s in remote_sites if 's3' in s.get('EndpointUrl', '').lower()]
            if s3_sites:
                action_items.append(f"✅ Found {len(s3_sites)} S3 remote site settings - S3 access is configured")
        
        if not action_items:
            action_items.append("❌ No obvious S3 authentication patterns found in TLND namespace")
            action_items.append("💡 May need to examine package installation or contact Trackland for API access")
        
        for item in action_items:
            print(item)
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("TLND Namespace Analysis")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        analyzer = TLNDAnalyzer(logger)
        
        if not analyzer.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        analysis = analyzer.comprehensive_tlnd_analysis()
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