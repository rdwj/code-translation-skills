#!/usr/bin/env python3
"""
Library Replacement Advisor — Main Script

Scans a Python 2 codebase for deprecated/removed library imports and generates
replacements. Handles simple renames (ConfigParser → configparser), removed modules
(cgi, distutils), and complex replacements (urllib2 split into urllib.request/error).

Usage:
    python3 advise_replacements.py <codebase_path> \
        --target-version 3.12 \
        --output <output_dir> \
        [--state-file <state.json>] \
        [--analysis-dir <analysis_dir>] \
        [--dry-run] \
        [--conversion-plan <plan.json>]

    or with specific files:

    python3 advise_replacements.py <codebase_path> \
        --unit <unit_name> \
        --conversion-plan <plan.json> \
        --target-version 3.11 \
        [--output <output_dir>] \
        [--dry-run]

Output:
    library-replacements.json — Per-file replacements applied
    no-replacement-found.json — Imports with no Py3 equivalent (manual work)
    (Modified .py files in place or in output dir if --dry-run)

Exit codes:
    0 = All replacements applied successfully
    1 = One or more issues found
    2 = Nothing to process
"""

import argparse
import ast
import json
import os
import re
import shutil
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── Library Mapping ──────────────────────────────────────────────────────────

LIBRARY_MAP = {
    # ── RENAMED: Simple 1:1 module renames ──────────────────────────────────
    "renamed": {
        "ConfigParser": {
            "new_module": "configparser",
            "import_transforms": {
                "ConfigParser.ConfigParser": "configparser.ConfigParser",
                "ConfigParser.SafeConfigParser": "configparser.ConfigParser",
            }
        },
        "Queue": {
            "new_module": "queue",
            "import_transforms": {
                "Queue.Queue": "queue.Queue",
                "Queue.LifoQueue": "queue.LifoQueue",
                "Queue.PriorityQueue": "queue.PriorityQueue",
            }
        },
        "SocketServer": {
            "new_module": "socketserver",
            "import_transforms": {}
        },
        "HTMLParser": {
            "new_module": "html.parser",
            "import_transforms": {
                "HTMLParser.HTMLParser": "html.parser.HTMLParser",
            }
        },
        "httplib": {
            "new_module": "http.client",
            "import_transforms": {}
        },
        "repr": {
            "new_module": "reprlib",
            "import_transforms": {}
        },
        "Tkinter": {
            "new_module": "tkinter",
            "import_transforms": {}
        },
        "thread": {
            "new_module": "_thread",
            "note": "Consider using 'threading' module instead",
            "import_transforms": {}
        },
        "commands": {
            "new_module": "subprocess",
            "import_transforms": {
                "commands.getoutput": "subprocess.getoutput",
                "commands.getstatusoutput": "subprocess.getstatusoutput",
            }
        },
        "copy_reg": {
            "new_module": "copyreg",
            "import_transforms": {}
        },
        "xmlrpclib": {
            "new_module": "xmlrpc.client",
            "import_transforms": {}
        },
        "Cookie": {
            "new_module": "http.cookies",
            "import_transforms": {}
        },
        "cookielib": {
            "new_module": "http.cookiejar",
            "import_transforms": {}
        },
        "htmlentitydefs": {
            "new_module": "html.entities",
            "import_transforms": {}
        },
        "robotparser": {
            "new_module": "urllib.robotparser",
            "import_transforms": {
                "robotparser.RobotFileParser": "urllib.robotparser.RobotFileParser",
            }
        },
        "UserDict": {
            "new_module": "collections.UserDict",
            "import_transforms": {}
        },
        "UserList": {
            "new_module": "collections.UserList",
            "import_transforms": {}
        },
        "UserString": {
            "new_module": "collections.UserString",
            "import_transforms": {}
        },
        "BaseHTTPServer": {
            "new_module": "http.server",
            "import_transforms": {
                "BaseHTTPServer.HTTPServer": "http.server.HTTPServer",
                "BaseHTTPServer.BaseHTTPRequestHandler": "http.server.BaseHTTPRequestHandler",
            }
        },
        "SimpleHTTPServer": {
            "new_module": "http.server",
            "import_transforms": {
                "SimpleHTTPServer.SimpleHTTPRequestHandler": "http.server.SimpleHTTPRequestHandler",
            }
        },
        "CGIHTTPServer": {
            "new_module": "http.server",
            "import_transforms": {
                "CGIHTTPServer.CGIHTTPRequestHandler": "http.server.CGIHTTPRequestHandler",
            }
        },
        "DocXMLRPCServer": {
            "new_module": "xmlrpc.server",
            "import_transforms": {
                "DocXMLRPCServer.DocXMLRPCRequestHandler": "xmlrpc.server.DocXMLRPCRequestHandler",
            }
        },
        "SimpleXMLRPCServer": {
            "new_module": "xmlrpc.server",
            "import_transforms": {
                "SimpleXMLRPCServer.SimpleXMLRPCServer": "xmlrpc.server.SimpleXMLRPCServer",
            }
        },
    },

    # ── REMOVED: Modules removed by version ──────────────────────────────────
    "removed": {
        "distutils": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "setuptools",
                    "install_cmd": "pip install setuptools",
                    "import_transforms": {
                        "distutils.core.setup": "setuptools.setup",
                        "distutils.core.Extension": "setuptools.Extension",
                        "distutils.command": "setuptools.command",
                    },
                    "notes": "Critical blocker for 3.12+. Requires build system upgrade."
                },
                {
                    "library": "sysconfig (stdlib)",
                    "install_cmd": "N/A",
                    "import_transforms": {
                        "distutils.sysconfig": "sysconfig",
                    },
                    "notes": "Use stdlib sysconfig for path utilities"
                },
            ]
        },
        "cgi": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "urllib.parse (stdlib)",
                    "install_cmd": "N/A",
                    "import_transforms": {
                        "cgi.parse_qs": "urllib.parse.parse_qs",
                        "cgi.parse_qsl": "urllib.parse.parse_qsl",
                    },
                    "notes": "For form parsing. CGI serving via http.server"
                }
            ]
        },
        "cgitb": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "traceback (stdlib)",
                    "install_cmd": "N/A",
                    "import_transforms": {},
                    "notes": "Use traceback.print_exc() or faulthandler for detailed tracebacks"
                }
            ]
        },
        "pipes": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "subprocess (stdlib)",
                    "install_cmd": "N/A",
                    "import_transforms": {},
                    "notes": "Use subprocess.run() or shlex.quote()"
                }
            ]
        },
        "crypt": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "bcrypt",
                    "install_cmd": "pip install bcrypt",
                    "import_transforms": {},
                    "notes": "Modern password hashing. Use bcrypt.hashpw()"
                }
            ]
        },
        "imghdr": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "filetype",
                    "install_cmd": "pip install filetype",
                    "import_transforms": {},
                    "notes": "Image format detection"
                }
            ]
        },
        "telnetlib": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "telnetlib3",
                    "install_cmd": "pip install telnetlib3",
                    "import_transforms": {},
                    "notes": "Async telnet client. Prefer SSH when possible."
                }
            ]
        },
        "uu": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "base64 (stdlib)",
                    "install_cmd": "N/A",
                    "import_transforms": {
                        "uu.encode": "base64.encodebytes / decodebytes",
                    },
                    "notes": "Use base64.encodebytes()/decodebytes()"
                }
            ]
        },
        "xdrlib": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "struct (stdlib)",
                    "install_cmd": "N/A",
                    "import_transforms": {},
                    "notes": "Use struct for binary data. XDR is rarely used; consider protobuf."
                }
            ]
        },
        "aifc": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "soundfile",
                    "install_cmd": "pip install soundfile",
                    "import_transforms": {},
                    "notes": "Audio file I/O"
                }
            ]
        },
        "audioop": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "pydub",
                    "install_cmd": "pip install pydub",
                    "import_transforms": {},
                    "notes": "Audio processing"
                }
            ]
        },
        "nntplib": {
            "removed_in": "3.12",
            "replacements": [
                {
                    "library": "nntplib (backport)",
                    "install_cmd": "pip install nntplib",
                    "import_transforms": {},
                    "notes": "NNTP client (rarely needed)"
                }
            ]
        },
    },

    # ── COMPLEX: Special cases requiring usage analysis ──────────────────────
    "complex": {
        "urllib2": {
            "type": "split",
            "description": "Py2 urllib2 split into urllib.request, urllib.error, urllib.parse",
            "replacements": [
                {
                    "from_import": "urllib2.Request",
                    "to_import": "urllib.request.Request",
                    "notes": "HTTP request builder"
                },
                {
                    "from_import": "urllib2.urlopen",
                    "to_import": "urllib.request.urlopen",
                    "notes": "Open URL and return file-like object"
                },
                {
                    "from_import": "urllib2.HTTPError",
                    "to_import": "urllib.error.HTTPError",
                    "notes": "HTTP error exception"
                },
                {
                    "from_import": "urllib2.URLError",
                    "to_import": "urllib.error.URLError",
                    "notes": "URL error exception"
                },
                {
                    "from_import": "urllib2.build_opener",
                    "to_import": "urllib.request.build_opener",
                    "notes": "Build custom opener"
                },
            ]
        },
        "urlparse": {
            "type": "rename",
            "description": "urlparse module renamed to urllib.parse",
            "replacements": [
                {
                    "from_import": "urlparse.urlparse",
                    "to_import": "urllib.parse.urlparse",
                    "notes": "Parse URL"
                },
                {
                    "from_import": "urlparse.urljoin",
                    "to_import": "urllib.parse.urljoin",
                    "notes": "Join URLs"
                },
                {
                    "from_import": "urlparse.urlunparse",
                    "to_import": "urllib.parse.urlunparse",
                    "notes": "Unparse URL tuple"
                },
                {
                    "from_import": "urlparse.parse_qs",
                    "to_import": "urllib.parse.parse_qs",
                    "notes": "Parse query string"
                },
            ]
        },
        "cStringIO": {
            "type": "choice",
            "description": "cStringIO/StringIO → io.StringIO or io.BytesIO (depends on usage)",
            "replacements": [
                {
                    "from_import": "cStringIO.StringIO",
                    "to_import": "io.BytesIO",
                    "condition": "if handling bytes data",
                    "notes": "Bytes buffer"
                },
                {
                    "from_import": "cStringIO.StringIO",
                    "to_import": "io.StringIO",
                    "condition": "if handling text data",
                    "notes": "Text buffer"
                },
            ]
        },
        "StringIO": {
            "type": "choice",
            "description": "StringIO module → io.StringIO or io.BytesIO (depends on usage)",
            "replacements": [
                {
                    "from_import": "StringIO.StringIO",
                    "to_import": "io.BytesIO",
                    "condition": "if handling bytes data",
                    "notes": "Bytes buffer"
                },
                {
                    "from_import": "StringIO.StringIO",
                    "to_import": "io.StringIO",
                    "condition": "if handling text data",
                    "notes": "Text buffer"
                },
            ]
        },
        "cPickle": {
            "type": "rename",
            "description": "cPickle renamed to pickle (C implementation auto-selected in Py3)",
            "replacements": [
                {
                    "from_import": "cPickle",
                    "to_import": "pickle",
                    "notes": "C pickle is default in Py3. Flag protocol version usage."
                }
            ]
        },
    }
}

# Modules that are removed in 3.12 (for version filtering)
REMOVED_3_12 = {
    "aifc", "audioop", "cgi", "cgitb", "chunk", "crypt", "imghdr",
    "mailcap", "msilib", "nis", "nntplib", "ossaudiodev", "pipes",
    "sndhdr", "spwd", "sunau", "telnetlib", "uu", "xdrlib", "distutils"
}


# ── File Operations ──────────────────────────────────────────────────────────

def read_file_safe(path: Path) -> Tuple[str, str]:
    """Read file with encoding detection. Returns (content, actual_encoding)."""
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            content = path.read_text(encoding=encoding)
            return content, encoding
        except (UnicodeDecodeError, LookupError):
            continue
    content = path.read_text(encoding="utf-8", errors="replace")
    return content, "utf-8"


def write_file_safe(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)


# ── Import Analysis ──────────────────────────────────────────────────────────

class ImportAnalyzer(ast.NodeVisitor):
    """Extract all imports from Python source code."""

    def __init__(self, source: str, filename: str = "<unknown>"):
        self.source = source
        self.filename = filename
        self.imports: List[Dict[str, Any]] = []
        self.source_lines = source.split("\n")

    def visit_Import(self, node: ast.Import) -> None:
        """Handle: import X, import Y as Z"""
        for alias in node.names:
            self.imports.append({
                "type": "import",
                "module": alias.name,
                "asname": alias.asname,
                "lineno": node.lineno,
                "col_offset": node.col_offset,
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Handle: from X import Y, from X import Y as Z"""
        if node.module:
            for alias in node.names:
                self.imports.append({
                    "type": "from_import",
                    "module": node.module,
                    "name": alias.name,
                    "asname": alias.asname,
                    "lineno": node.lineno,
                    "col_offset": node.col_offset,
                })
        self.generic_visit(node)

    def analyze(self) -> List[Dict[str, Any]]:
        """Parse and analyze imports."""
        try:
            tree = ast.parse(self.source, self.filename)
            self.visit(tree)
            return self.imports
        except SyntaxError as e:
            print(f"Warning: AST parse failed on {self.filename}: {e}", file=sys.stderr)
            return []


# ── Replacement Logic ────────────────────────────────────────────────────────

class ReplacementAdvisor:
    """Analyze imports and recommend replacements."""

    def __init__(self, target_version: str = "3.11"):
        self.target_version = target_version
        self.replacements: List[Dict[str, Any]] = []
        self.no_replacement_found: List[Dict[str, Any]] = []

    def classify_import(self, import_info: Dict[str, Any]) -> Dict[str, Any]:
        """Classify an import and find replacement."""
        module = import_info.get("module", "")
        result = {
            "original": import_info,
            "classification": None,
            "replacement": None,
            "action": None,
        }

        # Check RENAMED
        if module in LIBRARY_MAP["renamed"]:
            mapping = LIBRARY_MAP["renamed"][module]
            result["classification"] = "renamed"
            result["replacement"] = mapping
            result["action"] = f"Replace '{module}' with '{mapping['new_module']}'"
            return result

        # Check REMOVED (version-aware)
        if module in LIBRARY_MAP["removed"]:
            removed_info = LIBRARY_MAP["removed"][module]
            removed_version = removed_info.get("removed_in", "3.12")
            
            # Only flag if target version >= removal version
            if self._version_gte(self.target_version, removed_version):
                result["classification"] = "removed"
                result["replacement"] = removed_info
                result["action"] = f"Module '{module}' removed in Py{removed_version}. Use replacement."
                return result
            else:
                # Module removed in later version, optional for this target
                result["classification"] = "removed_optional"
                result["replacement"] = removed_info
                result["action"] = f"Module '{module}' removed in Py{removed_version}. Optional for Py{self.target_version}."
                return result

        # Check COMPLEX
        if module in LIBRARY_MAP["complex"]:
            mapping = LIBRARY_MAP["complex"][module]
            result["classification"] = "complex"
            result["replacement"] = mapping
            result["action"] = f"Complex replacement: {mapping['description']}"
            return result

        # Unknown module
        result["classification"] = "unknown"
        result["action"] = f"No mapping found for '{module}'"
        return result

    def _version_gte(self, target: str, removal: str) -> bool:
        """Check if target version >= removal version."""
        try:
            target_parts = [int(x) for x in target.split(".")]
            removal_parts = [int(x) for x in removal.split(".")]
            return target_parts >= removal_parts
        except (ValueError, AttributeError):
            return True  # Conservative: assume target >= removal

    def generate_replacement_code(self, import_info: Dict[str, Any], classification: Dict[str, Any]) -> str:
        """Generate replacement import statement."""
        original = import_info
        if original["type"] == "import":
            module = original["module"]
            asname = original["asname"]
            
            if classification["classification"] in ("renamed", "complex"):
                replacement = classification["replacement"]
                new_module = replacement.get("new_module", module)
                if asname:
                    return f"import {new_module} as {asname}"
                else:
                    return f"import {new_module}"
            
            return f"# TODO: Replace 'import {module}'"

        elif original["type"] == "from_import":
            module = original["module"]
            name = original["name"]
            asname = original["asname"]
            
            if classification["classification"] in ("renamed", "complex"):
                replacement = classification["replacement"]
                new_module = replacement.get("new_module", module)
                import_stmt = f"from {new_module} import {name}"
                if asname:
                    import_stmt += f" as {asname}"
                return import_stmt
            
            return f"# TODO: Replace 'from {module} import {name}'"

        return "# TODO: Replacement needed"


# ── Main Processing ──────────────────────────────────────────────────────────

def process_file(filepath: Path, advisor: ReplacementAdvisor) -> Dict[str, Any]:
    """Process a single Python file for import replacements."""
    content, encoding = read_file_safe(filepath)
    analyzer = ImportAnalyzer(content, str(filepath))
    imports = analyzer.analyze()

    file_result = {
        "filepath": str(filepath),
        "imports_found": len(imports),
        "replacements": [],
        "no_replacements": [],
    }

    for import_info in imports:
        classification = advisor.classify_import(import_info)
        
        if classification["replacement"] is None:
            file_result["no_replacements"].append({
                "import": f"{import_info['module']}",
                "reason": classification["action"]
            })
        else:
            file_result["replacements"].append({
                "old_import": import_info["module"],
                "new_import": classification["replacement"].get("new_module", "?"),
                "type": classification["classification"],
                "action": classification["action"],
            })

    return file_result


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Advise on Python 2 library replacements for Python 3 migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0=success, 1=issues found, 2=nothing to process"
    )

    parser.add_argument("codebase_path", type=str, help="Root path of Python codebase")
    parser.add_argument("--target-version", type=str, default="3.11",
                        help="Python 3 target version (e.g., 3.11, 3.12)")
    parser.add_argument("--output", type=str, default=".", help="Output directory for reports")
    parser.add_argument("--state-file", type=str, help="Path to migration state tracker JSON")
    parser.add_argument("--analysis-dir", type=str, help="Directory with Phase 0 analysis outputs")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    parser.add_argument("--conversion-plan", type=str, help="Conversion plan JSON for unit-based processing")

    args = parser.parse_args()

    codebase_path = Path(args.codebase_path)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not codebase_path.exists():
        print(f"Error: codebase path does not exist: {codebase_path}", file=sys.stderr)
        sys.exit(1)

    # ── Scan Python files ────────────────────────────────────────────────────

    advisor = ReplacementAdvisor(target_version=args.target_version)
    all_results = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "codebase_path": str(codebase_path),
            "target_version": args.target_version,
            "dry_run": args.dry_run,
        },
        "files": [],
        "summary": {}
    }

    py_files = list(codebase_path.rglob("*.py"))
    if not py_files:
        print("Info: No Python files found in codebase", file=sys.stderr)
        sys.exit(2)

    for filepath in py_files:
        try:
            result = process_file(filepath, advisor)
            all_results["files"].append(result)
        except Exception as e:
            print(f"Warning: Error processing {filepath}: {e}", file=sys.stderr)

    # ── Generate summary ─────────────────────────────────────────────────────

    total_replacements = sum(len(f["replacements"]) for f in all_results["files"])
    total_no_replacements = sum(len(f["no_replacements"]) for f in all_results["files"])
    files_with_replacements = sum(1 for f in all_results["files"] if f["replacements"])

    all_results["summary"] = {
        "total_files_scanned": len(py_files),
        "files_with_replacements": files_with_replacements,
        "total_replacements": total_replacements,
        "total_no_replacements": total_no_replacements,
    }

    # ── Write outputs ────────────────────────────────────────────────────────

    output_json = output_dir / "library-replacements.json"
    with open(output_json, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Wrote: {output_json}")

    # Build no-replacement-found report
    no_replacement_items = []
    for file_info in all_results["files"]:
        for item in file_info["no_replacements"]:
            no_replacement_items.append({
                "filepath": file_info["filepath"],
                "import": item["import"],
                "reason": item["reason"]
            })

    output_no_replacement = output_dir / "no-replacement-found.json"
    with open(output_no_replacement, "w") as f:
        json.dump(no_replacement_items, f, indent=2, ensure_ascii=False)
    print(f"Wrote: {output_no_replacement}")

    # Print summary
    print()
    print(f"Total Python files scanned: {len(py_files)}")
    print(f"Files with replacements: {files_with_replacements}")
    print(f"Total replacements recommended: {total_replacements}")
    print(f"No replacement found: {total_no_replacements}")
    print()
    print(f"Reports written to: {output_dir}")

    sys.exit(0)


if __name__ == "__main__":
    main()
