#!/usr/bin/env python3
"""
Extract Trackland Package Components
===================================

This script extracts the TL - Document Manager package components
so you can see how they built the PDF viewer.
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

def extract_trackland_package():
    """Extract the Trackland package components."""
    
    print("🔍 Extracting Trackland Package Components")
    print("=" * 50)
    
    # Package details from the screenshot
    package_id = "033RQ000000cJXt"
    package_name = "TL - Document Manager"
    
    print(f"📦 Package: {package_name}")
    print(f"🆔 Package ID: {package_id}")
    print(f"🏢 Publisher: Trackland")
    print(f"📋 Version: 1.5.22")
    
    # Create project directory
    project_name = "trackland-package-extraction"
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
    
    # Check authentication
    success, stdout, stderr = run_command("sf org list")
    if "No results found" in stdout or not success:
        print("\n🔐 Need to authenticate with Salesforce...")
        success, stdout, stderr = run_command("sf org login web --alias incitetax")
        if not success:
            print(f"❌ Authentication failed: {stderr}")
            return False
    
    print("\n📦 Retrieving package components...")
    
    # Method 1: Try to retrieve by package ID
    print("\n1️⃣ Attempting to retrieve by package ID...")
    success, stdout, stderr = run_command(f"sf package installed list")
    if success:
        print("✓ Found installed packages:")
        print(stdout)
    
    # Method 2: Retrieve all metadata and filter for Trackland components
    print("\n2️⃣ Retrieving all Lightning components...")
    success, stdout, stderr = run_command("sf project retrieve start --metadata LightningComponentBundle")
    if success:
        print("✓ Lightning components retrieved")
    else:
        print(f"⚠️  Lightning components: {stderr}")
    
    print("\n3️⃣ Retrieving all Aura components...")
    success, stdout, stderr = run_command("sf project retrieve start --metadata AuraDefinitionBundle")
    if success:
        print("✓ Aura components retrieved")
    else:
        print(f"⚠️  Aura components: {stderr}")
    
    print("\n4️⃣ Retrieving Apex classes...")
    success, stdout, stderr = run_command("sf project retrieve start --metadata ApexClass")
    if success:
        print("✓ Apex classes retrieved")
    else:
        print(f"⚠️  Apex classes: {stderr}")
    
    print("\n5️⃣ Retrieving Static resources...")
    success, stdout, stderr = run_command("sf project retrieve start --metadata StaticResource")
    if success:
        print("✓ Static resources retrieved")
    else:
        print(f"⚠️  Static resources: {stderr}")
    
    print("\n6️⃣ Retrieving Custom objects...")
    success, stdout, stderr = run_command("sf project retrieve start --metadata CustomObject")
    if success:
        print("✓ Custom objects retrieved")
    else:
        print(f"⚠️  Custom objects: {stderr}")
    
    return True

def analyze_trackland_components():
    """Analyze the extracted components for Trackland/PDF functionality."""
    
    print("\n" + "=" * 50)
    print("🔍 ANALYZING TRACKLAND COMPONENTS")
    print("=" * 50)
    
    findings = {
        "lightning_components": [],
        "aura_components": [],
        "apex_classes": [],
        "static_resources": [],
        "custom_objects": []
    }
    
    # Search patterns for Trackland components
    trackland_patterns = [
        "trackland", "pdf", "viewer", "document", "manager", 
        "annotation", "s3", "doclist", "folder", "upload"
    ]
    
    # Analyze Lightning Web Components
    print("\n📱 Lightning Web Components:")
    lwc_path = Path("force-app/main/default/lwc")
    if lwc_path.exists():
        for component_dir in lwc_path.iterdir():
            if component_dir.is_dir():
                component_name = component_dir.name.lower()
                if any(pattern in component_name for pattern in trackland_patterns):
                    findings["lightning_components"].append(str(component_dir))
                    print(f"   ✓ {component_dir.name}")
                    
                    # Check component files
                    for file_path in component_dir.glob("*"):
                        if file_path.is_file():
                            try:
                                content = file_path.read_text(encoding='utf-8')
                                if any(pattern in content.lower() for pattern in trackland_patterns):
                                    print(f"     📄 {file_path.name} - Contains relevant code")
                            except:
                                pass
    
    # Analyze Aura Components
    print("\n⚡ Aura Components:")
    aura_path = Path("force-app/main/default/aura")
    if aura_path.exists():
        for component_dir in aura_path.iterdir():
            if component_dir.is_dir():
                component_name = component_dir.name.lower()
                if any(pattern in component_name for pattern in trackland_patterns):
                    findings["aura_components"].append(str(component_dir))
                    print(f"   ✓ {component_dir.name}")
                    
                    # List all files in this component
                    for file_path in component_dir.glob("*"):
                        if file_path.is_file():
                            print(f"     📄 {file_path.name}")
    
    # Analyze Apex Classes
    print("\n🎯 Apex Classes:")
    apex_path = Path("force-app/main/default/classes")
    if apex_path.exists():
        for apex_file in apex_path.glob("*.cls"):
            try:
                content = apex_file.read_text(encoding='utf-8')
                if any(pattern in content.lower() for pattern in trackland_patterns):
                    findings["apex_classes"].append(str(apex_file))
                    print(f"   ✓ {apex_file.name}")
            except:
                pass
    
    # Analyze Static Resources
    print("\n📦 Static Resources:")
    static_path = Path("force-app/main/default/staticresources")
    if static_path.exists():
        for static_file in static_path.glob("*"):
            file_name = static_file.name.lower()
            if any(pattern in file_name for pattern in trackland_patterns):
                findings["static_resources"].append(str(static_file))
                print(f"   ✓ {static_file.name}")
    
    # Analyze Custom Objects
    print("\n🗂️  Custom Objects:")
    objects_path = Path("force-app/main/default/objects")
    if objects_path.exists():
        for object_dir in objects_path.iterdir():
            if object_dir.is_dir():
                object_name = object_dir.name.lower()
                if any(pattern in object_name for pattern in trackland_patterns):
                    findings["custom_objects"].append(str(object_dir))
                    print(f"   ✓ {object_dir.name}")
    
    # Save findings
    with open("trackland_analysis.json", "w") as f:
        json.dump(findings, f, indent=2)
    
    print(f"\n💾 Analysis saved to: trackland_analysis.json")
    
    # Summary
    total_found = sum(len(v) for v in findings.values())
    print(f"\n📊 SUMMARY:")
    print(f"   • Lightning Components: {len(findings['lightning_components'])}")
    print(f"   • Aura Components: {len(findings['aura_components'])}")
    print(f"   • Apex Classes: {len(findings['apex_classes'])}")
    print(f"   • Static Resources: {len(findings['static_resources'])}")
    print(f"   • Custom Objects: {len(findings['custom_objects'])}")
    print(f"   • Total relevant components: {total_found}")
    
    return findings

def provide_next_steps():
    """Provide guidance on what to do with the extracted components."""
    
    print("\n" + "=" * 50)
    print("📋 NEXT STEPS")
    print("=" * 50)
    
    print("\n🔍 What to examine:")
    print("1. Lightning/Aura components for PDF viewer UI")
    print("2. Apex classes for S3 integration logic")
    print("3. Static resources for PDF libraries (PDF.js, etc.)")
    print("4. Custom objects for data structure")
    
    print("\n🛠️  How to build your own:")
    print("1. Study the component architecture")
    print("2. Identify the PDF library they're using")
    print("3. Understand the S3 integration pattern")
    print("4. Look at the annotation storage mechanism")
    print("5. Recreate with your own custom components")
    
    print("\n💡 Key files to focus on:")
    print("- PDF viewer component (Lightning/Aura)")
    print("- S3 controller (Apex)")
    print("- PDF library (Static resource)")
    print("- DocListEntry__c object definition")
    
    print(f"\n📁 All extracted code is in: {os.getcwd()}")

def main():
    """Main execution function."""
    
    print("🔓 Trackland Package Extraction Tool")
    print("=" * 40)
    
    current_dir = os.getcwd()
    
    try:
        # Extract package
        if extract_trackland_package():
            # Analyze components
            findings = analyze_trackland_components()
            
            # Provide next steps
            provide_next_steps()
            
            if findings and any(findings.values()):
                print(f"\n🎉 SUCCESS! Found Trackland components to study")
                print(f"📖 Start by examining the files listed above")
            else:
                print(f"\n⚠️  No obvious Trackland components found")
                print(f"💡 Try looking in the 'force-app' directory manually")
                print(f"📋 Or click 'View Components' in Salesforce Setup")
        else:
            print("❌ Package extraction failed")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(current_dir)

if __name__ == "__main__":
    main() 