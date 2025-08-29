#!/usr/bin/env python3
"""
Trackland Package Discovery Script
==================================

Finds and analyzes the Trackland custom package components to understand:
1. How the PDF viewer accesses S3 files
2. Custom Apex classes that handle file access
3. Custom objects and their relationships
4. Visualforce pages or Lightning components
5. Custom settings that might contain S3 credentials

Usage:
python find_trackland_package.py
"""

import os
import sys
import logging
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


class TracklandPackageFinder:
    """Finds and analyzes Trackland package components."""
    
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
    
    def find_custom_objects(self) -> List[Dict]:
        """Find all custom objects that might be related to Trackland."""
        try:
            self.logger.info("🔍 Finding custom objects...")
            
            # Use the REST API to get all objects
            objects_url = f"{self.sf.base_url}sobjects/"
            response = self.sf.restful(objects_url)
            
            trackland_objects = []
            document_objects = []
            
            for obj_info in response['sobjects']:
                obj_name = obj_info['name']
                obj_label = obj_info['label']
                
                # Look for Trackland-related objects
                if any(keyword in obj_name.lower() for keyword in ['trackland', 'tl', 'doclist', 'doc']):
                    trackland_objects.append({
                        'name': obj_name,
                        'label': obj_label,
                        'custom': obj_info['custom'],
                        'match_reason': 'name_match'
                    })
                elif any(keyword in obj_label.lower() for keyword in ['trackland', 'document', 'pdf', 'doc list']):
                    document_objects.append({
                        'name': obj_name,
                        'label': obj_label,
                        'custom': obj_info['custom'],
                        'match_reason': 'label_match'
                    })
            
            return trackland_objects + document_objects
            
        except Exception as e:
            self.logger.error(f"❌ Error finding custom objects: {e}")
            return []
    
    def find_apex_classes(self) -> List[Dict]:
        """Find Apex classes that might handle file access."""
        try:
            self.logger.info("🔍 Finding Apex classes...")
            
            # Query ApexClass to find Trackland-related classes
            apex_query = """
                SELECT Id, Name, NamespacePrefix, Body, CreatedDate, LastModifiedDate
                FROM ApexClass
                WHERE (Name LIKE '%Track%' 
                   OR Name LIKE '%Doc%'
                   OR Name LIKE '%PDF%'
                   OR Name LIKE '%S3%'
                   OR Name LIKE '%File%'
                   OR Name LIKE '%Download%')
                AND NamespacePrefix != NULL
                ORDER BY Name
            """
            
            try:
                result = self.sf.query(apex_query)
                
                apex_classes = []
                for record in result['records']:
                    # Analyze the class body for S3/file-related keywords
                    body = record.get('Body', '')
                    s3_keywords = ['s3', 'aws', 'bucket', 'download', 'presigned', 'signature', 'trackland-doc-storage']
                    
                    keyword_matches = []
                    if body:
                        body_lower = body.lower()
                        for keyword in s3_keywords:
                            if keyword in body_lower:
                                keyword_matches.append(keyword)
                    
                    apex_classes.append({
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record['NamespacePrefix'],
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate'],
                        'body_preview': body[:500] + "..." if len(body) > 500 else body,
                        'keyword_matches': keyword_matches,
                        'relevance_score': len(keyword_matches)
                    })
                
                # Sort by relevance (most keyword matches first)
                apex_classes.sort(key=lambda x: x['relevance_score'], reverse=True)
                return apex_classes
                
            except Exception as e:
                self.logger.debug(f"ApexClass query failed (might not have access): {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding Apex classes: {e}")
            return []
    
    def find_visualforce_pages(self) -> List[Dict]:
        """Find Visualforce pages that might contain the PDF viewer."""
        try:
            self.logger.info("🔍 Finding Visualforce pages...")
            
            vf_query = """
                SELECT Id, Name, NamespacePrefix, Markup, CreatedDate, LastModifiedDate
                FROM ApexPage
                WHERE (Name LIKE '%PDF%'
                   OR Name LIKE '%Doc%'
                   OR Name LIKE '%View%'
                   OR Name LIKE '%Track%')
                AND NamespacePrefix != NULL
                ORDER BY Name
            """
            
            try:
                result = self.sf.query(vf_query)
                
                vf_pages = []
                for record in result['records']:
                    markup = record.get('Markup', '')
                    
                    # Look for file/PDF-related keywords in markup
                    pdf_keywords = ['pdf', 'document', 'viewer', 'iframe', 's3', 'amazonaws', 'trackland']
                    keyword_matches = []
                    
                    if markup:
                        markup_lower = markup.lower()
                        for keyword in pdf_keywords:
                            if keyword in markup_lower:
                                keyword_matches.append(keyword)
                    
                    vf_pages.append({
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record['NamespacePrefix'],
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate'],
                        'markup_preview': markup[:500] + "..." if len(markup) > 500 else markup,
                        'keyword_matches': keyword_matches,
                        'relevance_score': len(keyword_matches)
                    })
                
                vf_pages.sort(key=lambda x: x['relevance_score'], reverse=True)
                return vf_pages
                
            except Exception as e:
                self.logger.debug(f"ApexPage query failed (might not have access): {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding Visualforce pages: {e}")
            return []
    
    def find_custom_settings(self) -> List[Dict]:
        """Find custom settings that might contain S3 credentials."""
        try:
            self.logger.info("🔍 Finding custom settings...")
            
            # First, find all custom setting objects
            objects_url = f"{self.sf.base_url}sobjects/"
            response = self.sf.restful(objects_url)
            
            custom_settings = []
            
            for obj_info in response['sobjects']:
                obj_name = obj_info['name']
                obj_label = obj_info['label']
                
                # Look for custom settings (usually end with __c and are custom)
                if (obj_info['custom'] and 
                    obj_name.endswith('__c') and
                    any(keyword in obj_name.lower() or keyword in obj_label.lower() 
                        for keyword in ['setting', 'config', 'aws', 's3', 'track', 'credential'])):
                    
                    try:
                        # Try to query this custom setting for data
                        setting_query = f"SELECT Id, Name FROM {obj_name} LIMIT 5"
                        setting_result = self.sf.query(setting_query)
                        
                        # If successful, get field information
                        obj_metadata = getattr(self.sf, obj_name).describe()
                        field_names = [field['name'] for field in obj_metadata['fields'] 
                                     if any(keyword in field['name'].lower() 
                                           for keyword in ['aws', 's3', 'key', 'secret', 'bucket', 'region', 'token'])]
                        
                        custom_settings.append({
                            'name': obj_name,
                            'label': obj_label,
                            'record_count': len(setting_result['records']),
                            'relevant_fields': field_names,
                            'sample_records': setting_result['records']
                        })
                        
                    except Exception as e:
                        # If we can't query it, still note its existence
                        custom_settings.append({
                            'name': obj_name,
                            'label': obj_label,
                            'error': f"Cannot query: {str(e)}",
                            'relevant_fields': []
                        })
            
            return custom_settings
            
        except Exception as e:
            self.logger.error(f"❌ Error finding custom settings: {e}")
            return []
    
    def find_lightning_components(self) -> List[Dict]:
        """Find Lightning components that might handle PDF viewing."""
        try:
            self.logger.info("🔍 Finding Lightning components...")
            
            # Query AuraDefinitionBundle for Lightning components
            aura_query = """
                SELECT Id, DeveloperName, NamespacePrefix, Description, CreatedDate, LastModifiedDate
                FROM AuraDefinitionBundle
                WHERE (DeveloperName LIKE '%PDF%'
                   OR DeveloperName LIKE '%Doc%'
                   OR DeveloperName LIKE '%View%'
                   OR DeveloperName LIKE '%Track%'
                   OR Description LIKE '%PDF%'
                   OR Description LIKE '%document%')
                AND NamespacePrefix != NULL
                ORDER BY DeveloperName
            """
            
            try:
                result = self.sf.query(aura_query)
                
                lightning_components = []
                for record in result['records']:
                    lightning_components.append({
                        'id': record['Id'],
                        'developer_name': record['DeveloperName'],
                        'namespace': record['NamespacePrefix'],
                        'description': record.get('Description', ''),
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate']
                    })
                
                return lightning_components
                
            except Exception as e:
                self.logger.debug(f"AuraDefinitionBundle query failed: {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding Lightning components: {e}")
            return []
    
    def find_rest_endpoints(self) -> List[Dict]:
        """Find custom REST API endpoints that might handle file downloads."""
        try:
            self.logger.info("🔍 Finding REST API endpoints...")
            
            # Look for Apex REST services
            rest_query = """
                SELECT Id, Name, NamespacePrefix, Body, CreatedDate, LastModifiedDate
                FROM ApexClass
                WHERE Body LIKE '%@RestResource%'
                OR Body LIKE '%@HttpGet%'
                OR Body LIKE '%@HttpPost%'
                ORDER BY Name
            """
            
            try:
                result = self.sf.query(rest_query)
                
                rest_endpoints = []
                for record in result['records']:
                    body = record.get('Body', '')
                    
                    # Look for file/download-related patterns
                    download_patterns = ['download', 'file', 'blob', 'stream', 's3', 'presigned']
                    pattern_matches = []
                    
                    if body:
                        body_lower = body.lower()
                        for pattern in download_patterns:
                            if pattern in body_lower:
                                pattern_matches.append(pattern)
                    
                    rest_endpoints.append({
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record['NamespacePrefix'],
                        'created_date': record['CreatedDate'],
                        'pattern_matches': pattern_matches,
                        'body_preview': body[:800] + "..." if len(body) > 800 else body,
                        'relevance_score': len(pattern_matches)
                    })
                
                rest_endpoints.sort(key=lambda x: x['relevance_score'], reverse=True)
                return rest_endpoints
                
            except Exception as e:
                self.logger.debug(f"REST endpoint query failed: {e}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding REST endpoints: {e}")
            return []
    
    def comprehensive_package_analysis(self) -> Dict:
        """Perform comprehensive analysis to find Trackland package components."""
        analysis_results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'custom_objects': [],
            'apex_classes': [],
            'visualforce_pages': [],
            'custom_settings': [],
            'lightning_components': [],
            'rest_endpoints': []
        }
        
        # Find all components
        self.logger.info("🔍 Starting comprehensive Trackland package analysis...")
        
        analysis_results['custom_objects'] = self.find_custom_objects()
        analysis_results['apex_classes'] = self.find_apex_classes()
        analysis_results['visualforce_pages'] = self.find_visualforce_pages()
        analysis_results['custom_settings'] = self.find_custom_settings()
        analysis_results['lightning_components'] = self.find_lightning_components()
        analysis_results['rest_endpoints'] = self.find_rest_endpoints()
        
        return analysis_results
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted analysis results."""
        print("\n" + "=" * 80)
        print("TRACKLAND PACKAGE ANALYSIS")
        print("=" * 80)
        
        # Custom Objects
        custom_objects = analysis['custom_objects']
        print(f"\n📋 CUSTOM OBJECTS FOUND: {len(custom_objects)}")
        print("-" * 50)
        for obj in custom_objects[:10]:  # Show top 10
            print(f"• {obj['name']} ({obj['label']})")
            print(f"  Custom: {obj['custom']}, Match: {obj['match_reason']}")
        
        # Apex Classes
        apex_classes = analysis['apex_classes']
        print(f"\n⚡ APEX CLASSES FOUND: {len(apex_classes)}")
        print("-" * 50)
        for cls in apex_classes[:5]:  # Show top 5 by relevance
            if cls['relevance_score'] > 0:
                print(f"• {cls['name']} (Namespace: {cls['namespace']})")
                print(f"  Relevance: {cls['relevance_score']}, Keywords: {cls['keyword_matches']}")
                if cls['body_preview']:
                    print(f"  Preview: {cls['body_preview'][:200]}...")
        
        if not any(cls['relevance_score'] > 0 for cls in apex_classes[:5]):
            print("No highly relevant Apex classes found with S3/file keywords")
        
        # Visualforce Pages
        vf_pages = analysis['visualforce_pages']
        print(f"\n📄 VISUALFORCE PAGES FOUND: {len(vf_pages)}")
        print("-" * 50)
        for page in vf_pages[:5]:
            if page['relevance_score'] > 0:
                print(f"• {page['name']} (Namespace: {page['namespace']})")
                print(f"  Relevance: {page['relevance_score']}, Keywords: {page['keyword_matches']}")
                if page['markup_preview']:
                    print(f"  Preview: {page['markup_preview'][:200]}...")
        
        if not any(page['relevance_score'] > 0 for page in vf_pages[:5]):
            print("No highly relevant Visualforce pages found")
        
        # Custom Settings
        custom_settings = analysis['custom_settings']
        print(f"\n⚙️ CUSTOM SETTINGS FOUND: {len(custom_settings)}")
        print("-" * 50)
        for setting in custom_settings:
            print(f"• {setting['name']} ({setting['label']})")
            if setting.get('relevant_fields'):
                print(f"  Relevant fields: {setting['relevant_fields']}")
            if setting.get('record_count'):
                print(f"  Records: {setting['record_count']}")
            if setting.get('error'):
                print(f"  Error: {setting['error']}")
        
        # Lightning Components
        lightning_components = analysis['lightning_components']
        print(f"\n⚡ LIGHTNING COMPONENTS FOUND: {len(lightning_components)}")
        print("-" * 50)
        for comp in lightning_components[:5]:
            print(f"• {comp['developer_name']} (Namespace: {comp['namespace']})")
            if comp.get('description'):
                print(f"  Description: {comp['description']}")
        
        # REST Endpoints
        rest_endpoints = analysis['rest_endpoints']
        print(f"\n🌐 REST ENDPOINTS FOUND: {len(rest_endpoints)}")
        print("-" * 50)
        for endpoint in rest_endpoints[:5]:
            if endpoint['relevance_score'] > 0:
                print(f"• {endpoint['name']} (Namespace: {endpoint['namespace']})")
                print(f"  Patterns: {endpoint['pattern_matches']}")
                if endpoint['body_preview']:
                    print(f"  Preview: {endpoint['body_preview'][:300]}...")
        
        print("\n" + "=" * 80)
        print("NEXT STEPS RECOMMENDATIONS")
        print("=" * 80)
        
        recommendations = []
        
        # Check for custom settings with credentials
        cred_settings = [s for s in custom_settings if s.get('relevant_fields')]
        if cred_settings:
            recommendations.append(f"✅ Found {len(cred_settings)} custom settings with credential fields - examine these for S3 access keys")
        
        # Check for relevant Apex classes
        relevant_apex = [c for c in apex_classes if c['relevance_score'] > 0]
        if relevant_apex:
            recommendations.append(f"✅ Found {len(relevant_apex)} Apex classes with file/S3 keywords - analyze their code")
        
        # Check for PDF viewer pages
        pdf_pages = [p for p in vf_pages if 'pdf' in p['name'].lower() or any('pdf' in kw for kw in p['keyword_matches'])]
        if pdf_pages:
            recommendations.append(f"✅ Found {len(pdf_pages)} PDF-related Visualforce pages - examine how they load files")
        
        # Check for REST endpoints
        download_endpoints = [e for e in rest_endpoints if e['relevance_score'] > 0]
        if download_endpoints:
            recommendations.append(f"✅ Found {len(download_endpoints)} REST endpoints with download patterns - check for file proxy services")
        
        if not recommendations:
            recommendations.append("❌ No obvious authentication mechanisms found - may need to examine package namespace directly")
            recommendations.append("💡 Consider checking the package namespace and its remote site settings")
        
        for rec in recommendations:
            print(rec)
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("Trackland Package Discovery")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        finder = TracklandPackageFinder(logger)
        
        if not finder.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        analysis = finder.comprehensive_package_analysis()
        finder.print_analysis_results(analysis)
        
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