#!/usr/bin/env python3
"""
Library Replacement Report Generator

Generates a human-readable Markdown report from library-replacements.json output
produced by advise_replacements.py. Shows per-file replacements, new dependencies
needed, items requiring manual work, and next steps.

Usage:
    python3 generate_replacement_report.py <output_dir> \
        [--output <output_file.md>]

Inputs:
    <output_dir>/library-replacements.json
    <output_dir>/no-replacement-found.json

Output:
    library-replacements.md (or specified --output file)
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict
import argparse
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


def load_json(path: str) -> Dict:
    """Load a JSON file, return empty dict if not found."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {path} not found", file=sys.stderr)
        return {}


def extract_dependencies(replacements_data: Dict) -> Dict[str, List[str]]:
    """Extract third-party libraries that need to be installed."""
    deps = defaultdict(set)
    
    for file_info in replacements_data.get("files", []):
        for repl in file_info.get("replacements", []):
            # Map common replacements to dependencies
            old_import = repl.get("old_import", "")
            
            if old_import == "distutils":
                deps["pip install setuptools"].add("setuptools (for build system)")
            elif old_import in ("crypt",):
                deps["pip install bcrypt"].add("bcrypt")
            elif old_import == "imghdr":
                deps["pip install filetype"].add("filetype")
            elif old_import in ("aifc", "sunau"):
                deps["pip install soundfile"].add("soundfile")
            elif old_import == "audioop":
                deps["pip install pydub"].add("pydub")
            elif old_import == "telnetlib":
                deps["pip install telnetlib3"].add("telnetlib3")
            elif old_import == "nntplib":
                deps["pip install nntplib"].add("nntplib (backport)")
            elif old_import == "xdrlib":
                deps["pip install xdrlib2"].add("xdrlib2")
    
    return {k: sorted(v) for k, v in deps.items()}


def generate_report(replacements_file: str, no_replacement_file: str) -> str:
    """Generate the full replacement report."""
    
    replacements = load_json(replacements_file)
    no_replacements = load_json(no_replacement_file)
    
    lines = []
    
    def w(text=""):
        lines.append(text)
    
    # ── Header ───────────────────────────────────────────────────────────
    
    w("# Library Replacement Report")
    w()
    w(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    w()
    
    metadata = replacements.get("metadata", {})
    if metadata:
        w("## Metadata")
        w()
        w(f"- **Codebase**: {metadata.get('codebase_path', 'unknown')}")
        w(f"- **Target Version**: Python {metadata.get('target_version', '3.11')}")
        w(f"- **Dry Run**: {'Yes' if metadata.get('dry_run') else 'No'}")
        w()
    
    # ── Executive Summary ────────────────────────────────────────────────
    
    w("## Executive Summary")
    w()
    
    summary = replacements.get("summary", {})
    total_files = summary.get("total_files_scanned", 0)
    files_with_repls = summary.get("files_with_replacements", 0)
    total_repls = summary.get("total_replacements", 0)
    total_no_repls = summary.get("total_no_replacements", 0)
    
    w(f"| Metric | Count |")
    w(f"|--------|-------|")
    w(f"| Python files scanned | {total_files} |")
    w(f"| Files requiring replacement | {files_with_repls} |")
    w(f"| Total replacements identified | {total_repls} |")
    w(f"| Items needing manual review | {total_no_repls} |")
    w()
    
    if total_repls == 0 and total_no_repls == 0:
        w("> **No library replacements needed.** All imports are already Py3-compatible.")
        w()
    elif total_no_repls == 0:
        w(f"> **{total_repls} imports need replacement.** All have Py3 equivalents.")
        w()
    else:
        w(f"> **{total_repls} imports can be automatically replaced.** {total_no_repls} items require manual review.")
        w()
    
    # ── Replacement Categories ───────────────────────────────────────────
    
    w("## Replacements by Category")
    w()
    
    category_counts = defaultdict(int)
    for file_info in replacements.get("files", []):
        for repl in file_info.get("replacements", []):
            category = repl.get("type", "unknown")
            category_counts[category] += 1
    
    if category_counts:
        w("| Category | Count |")
        w("|----------|-------|")
        for cat in sorted(category_counts.keys()):
            w(f"| {cat} | {category_counts[cat]} |")
        w()
    
    # ── Per-File Breakdown ───────────────────────────────────────────────
    
    files_with_replacements = [f for f in replacements.get("files", []) if f.get("replacements")]
    
    if files_with_replacements:
        w("## Per-File Replacements")
        w()
        
        for file_info in sorted(files_with_replacements, key=lambda f: f["filepath"]):
            filepath = file_info["filepath"]
            repls = file_info.get("replacements", [])
            w(f"### {filepath}")
            w()
            w(f"**{len(repls)} replacement(s) needed:**")
            w()
            
            for repl in repls:
                old = repl.get("old_import", "?")
                new = repl.get("new_import", "?")
                repl_type = repl.get("type", "unknown")
                w(f"- `{old}` → `{new}` ({repl_type})")
            
            w()
    
    # ── New Dependencies ────────────────────────────────────────────────
    
    w("## New Dependencies Required")
    w()
    
    deps = extract_dependencies(replacements)
    if deps:
        w("The following third-party libraries may need to be installed:")
        w()
        for install_cmd, libs in sorted(deps.items()):
            w(f"```bash")
            w(f"{install_cmd}")
            w(f"```")
            w()
            for lib in libs:
                w(f"- {lib}")
            w()
    else:
        w("No new third-party dependencies required. All replacements use stdlib modules.")
        w()
    
    # ── Manual Review Items ──────────────────────────────────────────────
    
    if no_replacements:
        w("## Items Requiring Manual Review")
        w()
        w("The following imports have no automatic Py3 replacement. "
          "Review and update manually:")
        w()
        
        by_file = defaultdict(list)
        for item in no_replacements:
            filepath = item.get("filepath", "unknown")
            by_file[filepath].append(item)
        
        for filepath in sorted(by_file.keys()):
            items = by_file[filepath]
            w(f"### {filepath}")
            w()
            for item in items:
                import_name = item.get("import", "?")
                reason = item.get("reason", "Unknown")
                w(f"- **{import_name}**: {reason}")
            w()
    
    # ── Replacement Details ──────────────────────────────────────────────
    
    w("## Common Replacements Reference")
    w()
    
    w("### Renamed Modules (Simple 1:1)")
    w()
    w("These modules exist in Python 3 under different names:")
    w()
    w("| Python 2 | Python 3 |")
    w("|----------|----------|")
    w("| ConfigParser | configparser |")
    w("| Queue | queue |")
    w("| SocketServer | socketserver |")
    w("| HTMLParser | html.parser |")
    w("| httplib | http.client |")
    w("| repr | reprlib |")
    w("| Tkinter | tkinter |")
    w("| Cookie | http.cookies |")
    w("| cookielib | http.cookiejar |")
    w("| xmlrpclib | xmlrpc.client |")
    w("| BaseHTTPServer, SimpleHTTPServer, CGIHTTPServer | http.server |")
    w()
    
    w("### Removed Modules (3.12+)")
    w()
    w("These stdlib modules were removed in Python 3.12:")
    w()
    w("| Module | Replacement | Notes |")
    w("|--------|-------------|-------|")
    w("| distutils | setuptools | **Critical blocker** for 3.12+ |")
    w("| cgi | urllib.parse | Form parsing and CGI serving |")
    w("| pipes | subprocess, shlex | Shell pipeline construction |")
    w("| telnetlib | telnetlib3 | Telnet client |")
    w("| crypt | bcrypt | Password hashing |")
    w()
    
    w("### Complex Replacements")
    w()
    w("**urllib2 → urllib.request/urllib.error/urllib.parse**")
    w()
    w("Python 2's urllib2 module is split across three modules in Python 3:")
    w()
    w("```")
    w("# Python 2:")
    w("import urllib2")
    w("req = urllib2.Request(url)")
    w("")
    w("# Python 3:")
    w("from urllib.request import Request, urlopen")
    w("from urllib.error import HTTPError, URLError")
    w("req = Request(url)")
    w("```")
    w()
    
    w("**cPickle → pickle**")
    w()
    w("Direct rename. In Python 3, the C implementation is used by default:")
    w()
    w("```")
    w("# Python 2:")
    w("import cPickle as pickle")
    w("")
    w("# Python 3:")
    w("import pickle  # C implementation is default")
    w("```")
    w()
    
    w("**cStringIO/StringIO → io.StringIO/io.BytesIO**")
    w()
    w("Choice depends on whether you're handling bytes or text:")
    w()
    w("```")
    w("# For text data (Py3):")
    w("from io import StringIO")
    w("buf = StringIO()")
    w("")
    w("# For bytes data (Py3):")
    w("from io import BytesIO")
    w("buf = BytesIO()")
    w("```")
    w()
    
    # ── Next Steps ───────────────────────────────────────────────────────
    
    w("## Next Steps")
    w()
    
    if total_repls > 0 or total_no_repls > 0:
        w("1. **Review this report** to understand what replacements are needed")
        w()
        w("2. **Install new dependencies** (if any):")
        if deps:
            for install_cmd, _ in sorted(deps.items()):
                w(f"   ```bash")
                w(f"   {install_cmd}")
                w(f"   ```")
        else:
            w("   No new dependencies needed — only stdlib changes.")
        w()
        w("3. **Update import statements**:")
        w("   - Use `advise_replacements.py` to generate updated code")
        w("   - Manually review complex replacements (urllib2, cStringIO, etc.)")
        w()
        w("4. **Test thoroughly**:")
        w("   - Run existing test suite after import changes")
        w("   - Verify API compatibility of replacement modules")
        w()
        if total_no_repls > 0:
            w("5. **Handle manual items**:")
            w(f"   - Review the {total_no_repls} items flagged for manual work")
            w("   - Consider third-party alternatives or custom implementations")
            w()
        w("6. **Update requirements.txt/setup.py**:")
        if deps:
            w("   - Add/update dependencies listed above")
        w("   - Remove deprecated modules from requirements")
        w()
    else:
        w("No library replacements needed. Imports are Py3-compatible.")
        w()
    
    w("## References")
    w()
    w("- [Python 3 Standard Library Changes](https://docs.python.org/3/library/2to3.html)")
    w("- [Python 3.12 Removed Modules](https://docs.python.org/3.12/whatsnew/3.12.html)")
    w("- [Lib2to3 Documentation](https://docs.python.org/3/library/2to3.html)")
    w()
    
    return "\n".join(lines)


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate a human-readable report from library replacements JSON"
    )
    parser.add_argument("output_dir", type=str, help="Directory containing library-replacements.json")
    parser.add_argument("--output", type=str, help="Output markdown file (default: stdout)")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    replacements_file = output_dir / "library-replacements.json"
    no_replacement_file = output_dir / "no-replacement-found.json"
    
    if not replacements_file.exists():
        print(f"Error: {replacements_file} not found", file=sys.stderr)
        sys.exit(1)
    
    report = generate_report(str(replacements_file), str(no_replacement_file))
    
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report)
        print(f"Report written to: {output_path}", file=sys.stderr)
    else:
        print(report)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
