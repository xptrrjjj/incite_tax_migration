#!/usr/bin/env python3
"""
Salesforce Code Extraction and Analysis
=======================================

This script helps extract and analyze Salesforce code to investigate the PDF viewer implementation.
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def run_command(command, cwd=None):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def check_salesforce_cli():
    """Check if Salesforce CLI is installed."""
    success, stdout, stderr = run_command("sf --version")
    if success:
        print(f"✓ Salesforce CLI found: {stdout.strip()}")
        return True
    else:
        print("❌ Salesforce CLI not found. Installing...")
        return install_salesforce_cli()

def install_salesforce_cli():
    """Install Salesforce CLI."""
    print("Installing Salesforce CLI...")
    success, stdout, stderr = run_command("npm install -g @salesforce/cli")
    if success:
        print("✓ Salesforce CLI installed successfully")
        return True
    else:
        print(f"❌ Failed to install Salesforce CLI: {stderr}")
        print("Please install manually:")
        print("1. Install Node.js from https://nodejs.org/")
        print("2. Run: npm install -g @salesforce/cli")
        return False

def create_package_xml():
    """Create package.xml for retrieving metadata."""
    package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>*</members>
        <name>LightningComponentBundle</name>
    </types>
    <types>
        <members>*</members>
        <name>AuraDefinitionBundle</name>
    </types>
    <types>
        <members>*</members>
        <name>ApexClass</name>
    </types>
    <types>
        <members>*</members>
        <name>StaticResource</name>
    </types>
    <types>
        <members>DocListEntry__c</members>
        <name>CustomObject</name>
    </types>
    <types>
        <members>*</members>
        <name>Flow</name>
    </types>
    <types>
        <members>*</members>
        <name>CustomMetadata</name>
    </types>
    <version>59.0</version>
</Package>"""
    
    with open('package.xml', 'w') as f:
        f.write(package_xml)
    print("✓ Created package.xml")

def extract_salesforce_code():
    """Extract Salesforce code using SFDX."""
    
    print("\n" + "=" * 80)
    print("SALESFORCE CODE EXTRACTION")
    print("=" * 80)
    
    # Check if CLI is available
    if not check_salesforce_cli():
        return False
    
    # Create project directory
    project_name = "pdf-viewer-investigation"
    if os.path.exists(project_name):
        print(f"✓ Project directory {project_name} already exists")
    else:
        print(f"Creating project: {project_name}")
        success, stdout, stderr = run_command(f"sf project generate --name {project_name}")
        if not success:
            print(f"❌ Failed to create project: {stderr}")
            return False
        print(f"✓ Created project: {project_name}")
    
    # Change to project directory
    os.chdir(project_name)
    
    # Check if already authenticated
    success, stdout, stderr = run_command("sf org list")
    if "No results found" in stdout or not success:
        print("\n🔐 Need to authenticate with Salesforce...")
        print("Running authentication command...")
        success, stdout, stderr = run_command("sf org login web --alias incitetax")
        if not success:
            print(f"❌ Authentication failed: {stderr}")
            print("Please run manually: sf org login web --alias incitetax")
            return False
        print("✓ Authenticated successfully")
    else:
        print("✓ Already authenticated with Salesforce")
    
    # Create package.xml
    create_package_xml()
    
    # Retrieve metadata
    print("\n📦 Retrieving Salesforce metadata...")
    print("This may take several minutes...")
    
    retrieval_commands = [
        ("Lightning Components", "sf project retrieve start --metadata LightningComponentBundle"),
        ("Aura Components", "sf project retrieve start --metadata AuraDefinitionBundle"),
        ("Apex Classes", "sf project retrieve start --metadata ApexClass"),
        ("Static Resources", "sf project retrieve start --metadata StaticResource"),
        ("Custom Objects", "sf project retrieve start --metadata CustomObject:DocListEntry__c"),
    ]
    
    for name, command in retrieval_commands:
        print(f"\n📁 Retrieving {name}...")
        success, stdout, stderr = run_command(command)
        if success:
            print(f"✓ {name} retrieved successfully")
        else:
            print(f"⚠️  {name} retrieval had issues: {stderr}")
    
    return True

def analyze_extracted_code():
    """Analyze the extracted code for PDF viewer components."""
    
    print("\n" + "=" * 80)
    print("CODE ANALYSIS")
    print("=" * 80)
    
    findings = {
        "lightning_components": [],
        "aura_components": [],
        "apex_classes": [],
        "static_resources": [],
        "other_files": []
    }
    
    # Search patterns
    pdf_patterns = ["pdf", "viewer", "document", "annotation", "PageCount", "trackland", "s3"]
    
    print("\n🔍 Searching for PDF/Document related code...")
    
    # Find Lightning Web Components
    print("\n📁 Lightning Web Components:")
    lwc_path = Path("force-app/main/default/lwc")
    if lwc_path.exists():
        for component_dir in lwc_path.iterdir():
            if component_dir.is_dir():
                component_files = list(component_dir.glob("*"))
                for file_path in component_files:
                    if file_path.is_file():
                        try:
                            content = file_path.read_text(encoding='utf-8')
                            if any(pattern.lower() in content.lower() for pattern in pdf_patterns):
                                findings["lightning_components"].append(str(file_path))
                                print(f"   ✓ {file_path}")
                        except Exception:
                            pass
    
    # Find Aura Components
    print("\n⚡ Aura Components:")
    aura_path = Path("force-app/main/default/aura")
    if aura_path.exists():
        for component_dir in aura_path.iterdir():
            if component_dir.is_dir():
                component_files = list(component_dir.glob("*"))
                for file_path in component_files:
                    if file_path.is_file():
                        try:
                            content = file_path.read_text(encoding='utf-8')
                            if any(pattern.lower() in content.lower() for pattern in pdf_patterns):
                                findings["aura_components"].append(str(file_path))
                                print(f"   ✓ {file_path}")
                        except Exception:
                            pass
    
    # Find Apex Classes
    print("\n🎯 Apex Classes:")
    apex_path = Path("force-app/main/default/classes")
    if apex_path.exists():
        for apex_file in apex_path.glob("*.cls"):
            try:
                content = apex_file.read_text(encoding='utf-8')
                if any(pattern.lower() in content.lower() for pattern in pdf_patterns):
                    findings["apex_classes"].append(str(apex_file))
                    print(f"   ✓ {apex_file}")
            except Exception:
                pass
    
    # Find Static Resources
    print("\n📦 Static Resources:")
    static_path = Path("force-app/main/default/staticresources")
    if static_path.exists():
        for static_file in static_path.glob("*"):
            if "pdf" in static_file.name.lower() or "viewer" in static_file.name.lower() or "document" in static_file.name.lower():
                findings["static_resources"].append(str(static_file))
                print(f"   ✓ {static_file}")
    
    # Save findings
    with open("analysis_results.json", "w") as f:
        json.dump(findings, f, indent=2)
    
    print(f"\n💾 Analysis results saved to: analysis_results.json")
    
    # Summary
    total_found = (len(findings["lightning_components"]) + 
                  len(findings["aura_components"]) + 
                  len(findings["apex_classes"]) + 
                  len(findings["static_resources"]))
    
    print(f"\n📊 SUMMARY:")
    print(f"   • Lightning Components: {len(findings['lightning_components'])}")
    print(f"   • Aura Components: {len(findings['aura_components'])}")
    print(f"   • Apex Classes: {len(findings['apex_classes'])}")
    print(f"   • Static Resources: {len(findings['static_resources'])}")
    print(f"   • Total relevant files: {total_found}")
    
    return findings

def provide_investigation_tips():
    """Provide tips for manual investigation."""
    
    print("\n" + "=" * 80)
    print("MANUAL INVESTIGATION TIPS")
    print("=" * 80)
    
    print(f"\n🔍 BROWSER INVESTIGATION:")
    print(f"1. Open a DocListEntry__c record in Salesforce")
    print(f"2. Open the PDF viewer")
    print(f"3. Press F12 to open Developer Tools")
    print(f"4. In Console tab, run these commands:")
    print(f"   console.log(document.querySelectorAll('[data-aura-class*=\"pdf\"]'))")
    print(f"   console.log(document.querySelectorAll('iframe'))")
    print(f"   console.log(Array.from(document.scripts).filter(s => s.src.includes('pdf')))")
    
    print(f"\n🌐 NETWORK TAB INVESTIGATION:")
    print(f"1. Go to Network tab in Developer Tools")
    print(f"2. Reload the page with PDF viewer")
    print(f"3. Look for:")
    print(f"   • JavaScript files with 'pdf', 'viewer', 'document' in names")
    print(f"   • Static resource requests")
    print(f"   • Component bundle requests")
    
    print(f"\n📱 SALESFORCE UI INVESTIGATION:")
    print(f"1. Setup → Apps → App Manager")
    print(f"2. Setup → Apps → Installed Packages") 
    print(f"3. Setup → Custom Code → Lightning Components")
    print(f"4. Setup → Custom Code → Apex Classes")
    print(f"5. Setup → Platform Tools → Objects and Fields → Object Manager → DocListEntry__c")

def main():
    """Main execution function."""
    
    print("🔍 Salesforce PDF Viewer Investigation Tool")
    print("=" * 50)
    
    current_dir = os.getcwd()
    
    try:
        # Extract code
        if extract_salesforce_code():
            # Analyze code
            findings = analyze_extracted_code()
            
            # Provide tips
            provide_investigation_tips()
            
            print(f"\n🎯 NEXT STEPS:")
            if findings and any(findings.values()):
                print(f"1. Review the files found above")
                print(f"2. Look for PDF.js, PDFTron, or other PDF libraries")
                print(f"3. Check component markup for viewer implementation")
                print(f"4. Test migration with a single file first")
            else:
                print(f"1. Use browser developer tools for manual investigation")
                print(f"2. Ask your Salesforce admin about PDF viewer implementation")
                print(f"3. Check Setup → Installed Packages for third-party apps")
            
            print(f"\n📁 Files extracted to: {os.getcwd()}")
        else:
            print("❌ Code extraction failed. Please follow manual investigation steps.")
            provide_investigation_tips()
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Return to original directory
        os.chdir(current_dir)

if __name__ == "__main__":
    main() 