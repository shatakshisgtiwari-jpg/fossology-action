
"""
FOSSology Dashboard Generator - Simplified Single File

Generates GitHub Actions license compliance dashboards from SPDX/FOSSology reports.
Supports: SPDX_JSON, SPDX3_JSON, SPDX_TAG_VALUE, SPDX_YAML, TEXT.
No external dependencies - Python standard library only (YAML requires PyYAML).

Usage:
    python3 generate_dashboard.py <report_file> [--format FORMAT] [options]
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

# Risk classification (High: strong copyleft, Medium: weak copyleft, Low: permissive)
HIGH_RISK = {'GPL-1.0', 'GPL-2.0', 'GPL-3.0', 'GPL-1.0-only', 'GPL-2.0-only', 'GPL-3.0-only',
             'GPL-1.0-or-later', 'GPL-2.0-or-later', 'GPL-3.0-or-later', 'AGPL-1.0', 'AGPL-3.0',
             'AGPL-1.0-only', 'AGPL-3.0-only', 'AGPL-1.0-or-later', 'AGPL-3.0-or-later',
             'SSPL-1.0', 'RPL-1.5', 'EUPL-1.1', 'EUPL-1.2', 'OSL-3.0'}

MEDIUM_RISK = {'LGPL-2.0', 'LGPL-2.1', 'LGPL-3.0', 'LGPL-2.0-only', 'LGPL-2.1-only', 'LGPL-3.0-only',
               'LGPL-2.0-or-later', 'LGPL-2.1-or-later', 'LGPL-3.0-or-later', 'MPL-1.0', 'MPL-1.1',
               'MPL-2.0', 'EPL-1.0', 'EPL-2.0', 'CDDL-1.0', 'CDDL-1.1', 'CPL-1.0', 'APSL-2.0'}


def parse_spdx_json(file_path):
    """Parse SPDX JSON and extract licenses and unknown files."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error parsing SPDX file: {e}", file=sys.stderr)
        return None, None

    licenses, unknown_files = [], []
    files = data.get('files', []) or data.get('packages', [])

    for item in files:
        file_name = item.get('fileName') or item.get('name', 'Unknown')
        lic = item.get('licenseConcluded', 'NOASSERTION')
        
        if lic in ('NOASSERTION', 'NONE', None, '', 'Unknown'):
            lic = 'NOASSERTION'
            unknown_files.append(file_name)
        
        licenses.append(lic)

    return licenses, unknown_files


def parse_spdx3_json(file_path):
    """Parse SPDX 3.0 JSON-LD and extract licenses and unknown files."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error parsing SPDX3 file: {e}", file=sys.stderr)
        return None, None

    if isinstance(data, list):
        graph = data
    else:
        graph = data.get('@graph', [])
        if not graph:
            graph = [data]

    licenses, unknown_files = [], []
    elements = {}
    relationships = []
    files_and_packages = []

    for item in graph:
        if not isinstance(item, dict):
            continue
        item_type = item.get('type', '')
        if isinstance(item_type, list):
            item_type = ' '.join(item_type)
        item_id = item.get('spdxId', item.get('@id', ''))
        if item_id:
            elements[item_id] = item
        if 'File' in item_type or 'Package' in item_type:
            files_and_packages.append(item)
        elif 'Relationship' in item_type:
            relationships.append(item)

    def extract_license_str(val):
        """Extract a license string from a value that may be str, dict, or list."""
        if not val:
            return None
        if isinstance(val, str):
            # Strip common SPDX URI prefixes
            for prefix in ('https://spdx.org/licenses/', 'http://spdx.org/licenses/'):
                if val.startswith(prefix):
                    return val[len(prefix):]
            # Skip bare URIs / IDs that aren't license names
            if val.startswith('http') or val.startswith('_:'):
                return None
            return val if val not in ('NOASSERTION', 'NONE', '') else None
        if isinstance(val, list):
            parts = [extract_license_str(v) for v in val]
            parts = [p for p in parts if p]
            return ' AND '.join(parts) if parts else None
        if isinstance(val, dict):
            # SPDX 3.0: simplelicensing_LicenseExpression carries the text here
            for key in ('simplelicensing_licenseExpression', 'licenseExpression',
                        'simplelicensing_licenseExpressionParsed',
                        'name', 'spdxId', '@id'):
                v = val.get(key)
                if v and isinstance(v, str):
                    return extract_license_str(v)
        return None

    # Build license map from relationships (SPDX 3.0 HAS_CONCLUDED_LICENSE etc.)
    license_map = {}
    for rel in relationships:
        rel_type = rel.get('relationshipType', '')
        if isinstance(rel_type, str) and ('License' in rel_type or 'license' in rel_type
                                           or 'CONCLUDED' in rel_type.upper()
                                           or 'DECLARED' in rel_type.upper()):
            from_id = rel.get('from', '')
            to_ids = rel.get('to', [])
            if isinstance(to_ids, str):
                to_ids = [to_ids]
            for to_id in to_ids:
                target = elements.get(to_id, {})
                lic_name = extract_license_str(
                    target.get('simplelicensing_licenseExpression')
                    or target.get('licenseExpression')
                    or target.get('name')
                    or to_id
                )
                if lic_name:
                    license_map[from_id] = lic_name

    for item in files_and_packages:
        item_id = item.get('spdxId', item.get('@id', ''))
        file_name = item.get('name', item.get('software_name', 'Unknown'))

        lic = None
        for key in ('software_concludedLicense', 'concludedLicense',
                    'software_declaredLicense', 'declaredLicense'):
            val = item.get(key)
            if val is not None:
                lic = extract_license_str(val)
                if lic:
                    break

        if not lic:
            lic = license_map.get(item_id)

        if not lic or lic in ('NOASSERTION', 'NONE', 'NoAssertionLicense',
                               'https://spdx.org/rdf/3.0.0/terms/Core/NoAssertionLicense'):
            lic = 'NOASSERTION'
            unknown_files.append(file_name)

        licenses.append(lic)

    return licenses, unknown_files


def parse_spdx_tag_value(file_path):
    """Parse SPDX Tag-Value format and extract licenses."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (FileNotFoundError, UnicodeDecodeError) as e:
        print(f"❌ Error reading file: {e}", file=sys.stderr)
        return None, None

    licenses, unknown_files = [], []
    current_name = None

    for line in content.splitlines():
        line = line.strip()
        if line.startswith('FileName:'):
            current_name = line.split(':', 1)[1].strip()
        elif line.startswith('PackageName:'):
            current_name = line.split(':', 1)[1].strip()
        elif line.startswith('LicenseConcluded:'):
            lic = line.split(':', 1)[1].strip()
            if lic in ('NOASSERTION', 'NONE', ''):
                lic = 'NOASSERTION'
                if current_name:
                    unknown_files.append(current_name)
            licenses.append(lic)

    return licenses, unknown_files


def parse_spdx_yaml(file_path):
    """Parse SPDX YAML format (same structure as SPDX JSON)."""
    try:
        import yaml
    except ImportError:
        print("⚠️ PyYAML not available. Install with: pip install pyyaml", file=sys.stderr)
        return None, None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Error parsing YAML: {e}", file=sys.stderr)
        return None, None

    licenses, unknown_files = [], []
    files = data.get('files', []) or data.get('packages', [])

    for item in files:
        file_name = item.get('fileName') or item.get('name', 'Unknown')
        lic = item.get('licenseConcluded', 'NOASSERTION')

        if lic in ('NOASSERTION', 'NONE', None, '', 'Unknown'):
            lic = 'NOASSERTION'
            unknown_files.append(file_name)

        licenses.append(lic)

    return licenses, unknown_files


def parse_text_report(file_path):
    """Parse FOSSology text report and extract licenses."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (FileNotFoundError, UnicodeDecodeError) as e:
        print(f"❌ Error reading file: {e}", file=sys.stderr)
        return None, None

    licenses, unknown_files = [], []
    current_file = None

    for line in content.splitlines():
        line = line.strip()
        if line.startswith('File:') or line.startswith('FileName:'):
            current_file = line.split(':', 1)[1].strip()
        elif 'License' in line and ':' in line:
            lic = line.split(':', 1)[1].strip()
            if lic and lic not in ('', 'NOASSERTION', 'NONE', 'No_license_found'):
                licenses.append(lic)
            else:
                licenses.append('NOASSERTION')
                if current_file:
                    unknown_files.append(current_file)

    return licenses, unknown_files


def detect_format(file_path):
    """Detect report format from file extension."""
    path = file_path.lower()
    if path.endswith('.spdx3.json') or path.endswith('.jsonld'):
        return 'SPDX3_JSON'
    elif path.endswith('.spdx.json') or path.endswith('.json'):
        return 'SPDX_JSON'
    elif path.endswith('.spdx.yaml') or path.endswith('.spdx.yml'):
        return 'SPDX_YAML'
    elif path.endswith('.spdx.rdf'):
        return 'SPDX_RDF'
    elif path.endswith('.spdx3.rdf'):
        return 'SPDX3_RDF'
    elif path.endswith('.spdx') or path.endswith('.spdx.tv'):
        return 'SPDX_TAG_VALUE'
    elif path.endswith('.ttl'):
        return 'SPDX3_TTL'
    elif path.endswith('.txt'):
        return 'TEXT'
    return 'SPDX_JSON'


def parse_report(file_path, report_format=None):
    """Parse report file based on format. Returns (licenses, unknown_files)."""
    if not report_format:
        report_format = detect_format(file_path)

    parsers = {
        'SPDX_JSON': parse_spdx_json,
        'SPDX3_JSON': parse_spdx3_json,
        'SPDX_TAG_VALUE': parse_spdx_tag_value,
        'SPDX_YAML': parse_spdx_yaml,
        'TEXT': parse_text_report,
    }

    if report_format in ('SPDX_RDF', 'SPDX3_RDF', 'SPDX3_TTL'):
        print(f"⚠️ Format '{report_format}' requires RDF/Turtle parsing libraries not in standard Python.")
        print("   Supported formats for dashboard: SPDX_JSON, SPDX3_JSON, SPDX_TAG_VALUE, SPDX_YAML, TEXT")
        return None, None

    parser = parsers.get(report_format, parse_spdx_json)
    return parser(file_path)


def classify_risk(license_id):
    """Classify license by risk level."""
    if license_id in HIGH_RISK:
        return 'High', '🔴'
    elif license_id in MEDIUM_RISK:
        return 'Medium', '🟡'
    else:
        return 'Low', '🟢'


def generate_dashboard(licenses, unknown_files, include_charts=True, include_risk=True, include_unknown=True):
    """Generate complete dashboard markdown."""
    # Calculate statistics
    license_counts = Counter(licenses)
    filtered = {k: v for k, v in license_counts.items() if k != 'NOASSERTION'}
    total_files = len(licenses)
    unique_licenses = len(filtered)
    
    # Classify by risk
    high_risk_files = sum(v for k, v in filtered.items() if k in HIGH_RISK)
    medium_risk_files = sum(v for k, v in filtered.items() if k in MEDIUM_RISK)
    low_risk_files = sum(v for k, v in filtered.items() if k not in HIGH_RISK and k not in MEDIUM_RISK)
    
    # Sort licenses by count
    sorted_licenses = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
    
    # Build dashboard
    md = "# 📊 License Compliance Dashboard\n\n"
    
    # Section 1: KPI Overview
    md += "| Metric | Value |\n|--------|-------|\n"
    md += f"| Files Scanned | {total_files} |\n"
    md += f"| Unique Licenses | {unique_licenses} |\n"
    md += f"| Unknown Licenses | {len(unknown_files)} |\n"
    md += f"| High Risk Licenses | {high_risk_files} files |\n"
    md += f"| Medium Risk Licenses | {medium_risk_files} files |\n"
    md += f"| Low Risk Licenses | {low_risk_files} files |\n\n---\n\n"
    
    # Section 2: Charts
    if include_charts and sorted_licenses:
        top_10 = sorted_licenses[:10]
        
        # Pie chart
        md += "## 📈 License Distribution\n\n```mermaid\npie title License Distribution\n"
        for lic, count in top_10:
            md += f'    "{lic}" : {count}\n'
        md += "```\n\n---\n\n"
        
        # Bar chart (using graph for better compatibility)
        md += "## 📊 Top Licenses by File Count\n\n```mermaid\n%%{init: {'theme':'base'}}%%\n"
        md += "graph LR\n    subgraph \" \"\n"
        for i, (lic, count) in enumerate(top_10):
            md += f'    L{i}["{lic}: {count} files"]\n'
        md += "    end\n```\n\n---\n\n"
    
    # Section 3: License Inventory
    md += "## 📋 License Inventory\n\n| License | Files |\n|---------|-------|\n"
    for lic, count in sorted_licenses[:20]:
        md += f"| {lic} | {count} |\n"
    if len(sorted_licenses) > 20:
        md += f"\n*Showing top 20 of {len(sorted_licenses)} unique licenses*\n"
    md += "\n---\n\n"
    
    # Section 4: Risk Analysis
    if include_risk and sorted_licenses:
        md += "## ⚠️ Risk Analysis\n\n| License | Files | Risk Level |\n|---------|-------|------------|\n"
        for lic, count in sorted_licenses:
            risk_level, emoji = classify_risk(lic)
            md += f"| {lic} | {count} | {emoji} {risk_level} |\n"
        md += "\n---\n\n"
    
    # Section 5: Unknown Licenses
    if include_unknown and unknown_files:
        md += f"## ❓ Unknown Licenses\n\nFound **{len(unknown_files)}** files with unknown or unasserted licenses.\n\n"
        md += "| File |\n|------|\n"
        for file_path in unknown_files[:20]:
            md += f"| {file_path} |\n"
        if len(unknown_files) > 20:
            md += f"\n*...and {len(unknown_files) - 20} more files*\n"
        md += "\n---\n\n"
    
    # Footer
    md += "\n---\n\n*Generated by [FOSSology Action](https://github.com/shatakshisgtiwari-jpg/fossology-action)*\n"
    
    return md, {
        'files_scanned': total_files,
        'unique_licenses': unique_licenses,
        'unknown_licenses': len(unknown_files),
        'high_risk': high_risk_files,
        'medium_risk': medium_risk_files,
        'low_risk': low_risk_files
    }


def write_to_github_summary(markdown):
    """Write dashboard to GitHub Actions step summary."""
    summary_path = os.getenv('GITHUB_STEP_SUMMARY')
    if not summary_path:
        print("❌ GITHUB_STEP_SUMMARY not set", file=sys.stderr)
        return False
    
    try:
        with open(summary_path, 'a', encoding='utf-8') as f:
            f.write(markdown)
        return True
    except Exception as e:
        print(f"❌ Error writing summary: {e}", file=sys.stderr)
        return False


def parse_bool_env(var_name, default=True):
    """Parse boolean environment variable."""
    value = os.getenv(var_name, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')


def main():
    parser = argparse.ArgumentParser(description='Generate FOSSology license compliance dashboard')
    parser.add_argument('spdx_file', help='Path to report file (SPDX JSON, Tag-Value, YAML, or text)')
    parser.add_argument('--no-charts', action='store_true', help='Disable Mermaid charts')
    parser.add_argument('--no-risk', action='store_true', help='Disable risk analysis')
    parser.add_argument('--no-unknown', action='store_true', help='Disable unknown licenses table')
    parser.add_argument('--format', choices=['TEXT', 'SPDX_JSON', 'SPDX_YAML', 'SPDX_RDF', 'SPDX_TAG_VALUE',
                                              'SPDX3_JSON', 'SPDX3_TTL', 'SPDX3_RDF'],
                         help='Report format (auto-detected from extension if omitted)')
    parser.add_argument('--output', help='Output file path (default: GITHUB_STEP_SUMMARY)')
    args = parser.parse_args()

    # Check if enabled
    if not parse_bool_env('DASHBOARD_ENABLED', True):
        print("Dashboard generation disabled")
        return 0

    # Get configuration
    include_charts = not args.no_charts and parse_bool_env('DASHBOARD_CHARTS', True)
    include_risk = not args.no_risk and parse_bool_env('DASHBOARD_RISK', True)
    include_unknown = not args.no_unknown and parse_bool_env('DASHBOARD_UNKNOWN', True)

    print(f"📊 Generating dashboard from: {args.spdx_file}")

    # Parse report file
    licenses, unknown_files = parse_report(args.spdx_file, args.format)
    if licenses is None:
        return 1

    if not licenses:
        print("⚠️ No licenses found in SPDX file")
        dashboard_md = "# 📊 License Compliance Dashboard\n\n⚠️ No license information found in scan results.\n"
    else:
        # Generate dashboard
        dashboard_md, stats = generate_dashboard(licenses, unknown_files, include_charts, include_risk, include_unknown)
        
        # Print summary
        print("\n" + "="*60)
        print("LICENSE COMPLIANCE DASHBOARD SUMMARY")
        print("="*60)
        print(f"Files Scanned: {stats['files_scanned']}")
        print(f"Unique Licenses: {stats['unique_licenses']}")
        print(f"Unknown Licenses: {stats['unknown_licenses']}")
        print(f"High Risk: {stats['high_risk']} files")
        print(f"Medium Risk: {stats['medium_risk']} files")
        print(f"Low Risk: {stats['low_risk']} files")
        print("="*60 + "\n")

    # Write output
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(dashboard_md)
            print(f"✅ Dashboard written to {args.output}")
        except Exception as e:
            print(f"❌ Failed to write dashboard: {e}", file=sys.stderr)
            return 1
    else:
        if not write_to_github_summary(dashboard_md):
            return 1
        print("✅ Dashboard generated successfully")

    return 0


if __name__ == '__main__':
    sys.exit(main())
