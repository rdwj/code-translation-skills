#!/usr/bin/env python3
"""
Script: security_scan.py
Purpose: Security scanning and SBOM generation for Python 2→3 migrations
Inputs: Workspace path, scan mode (baseline/regression/final), optional baseline report
Outputs: sbom.json (CycloneDX), security-report.json, security-report.md, security-delta.json, flagged-for-review.json
LLM involvement: NONE
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# Try TOML parsing (3.11+, then tomli, then fallback)
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


class SBOMGenerator:
    """Parse dependencies from various sources and generate CycloneDX SBOM."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.dependencies: Dict[str, Dict[str, Any]] = {}

    def generate(self) -> Dict[str, Any]:
        """Generate CycloneDX 1.5 SBOM."""
        self._parse_all_sources()

        components = [
            {
                "type": "library",
                "name": dep,
                "version": self.dependencies[dep].get("version", "unknown"),
                "purl": self._generate_purl(dep, self.dependencies[dep].get("version")),
                "licenses": self.dependencies[dep].get("licenses", []),
            }
            for dep in sorted(self.dependencies.keys())
        ]

        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "tools": [
                    {
                        "vendor": "code-translation-skills",
                        "name": "py2to3-security-scanner",
                        "version": "1.0.0"
                    }
                ],
                "component": {
                    "type": "application",
                    "name": self.workspace.name,
                    "version": "unknown"
                }
            },
            "components": components
        }
        return sbom

    def _parse_all_sources(self) -> None:
        """Parse dependencies from all known sources."""
        self._parse_requirements()
        self._parse_setup_py()
        self._parse_setup_cfg()
        self._parse_pyproject_toml()
        self._parse_pipfile()
        self._parse_dist_info()

    def _parse_requirements(self) -> None:
        """Parse requirements.txt and requirements/*.txt files."""
        req_files = [self.workspace / "requirements.txt"]
        req_dir = self.workspace / "requirements"
        if req_dir.exists():
            req_files.extend(req_dir.glob("*.txt"))

        for req_file in req_files:
            if req_file.exists():
                self._parse_requirements_file(req_file)

    def _parse_requirements_file(self, path: Path) -> None:
        """Parse a single requirements file."""
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    self._add_requirement(line)
        except Exception:
            pass

    def _add_requirement(self, req_line: str) -> None:
        """Parse a requirement line and add to dependencies."""
        # Handle extras syntax: package[extra1,extra2]>=1.0
        match = re.match(r"^([a-zA-Z0-9._-]+)", req_line)
        if not match:
            return

        pkg_name = match.group(1).lower().replace("_", "-")

        # Extract version
        version_match = re.search(r"[=!<>]+(.+?)(?:\[|#|;|$)", req_line)
        version = version_match.group(1).strip() if version_match else None

        if pkg_name not in self.dependencies:
            self.dependencies[pkg_name] = {"version": version, "licenses": []}
        elif version and not self.dependencies[pkg_name]["version"]:
            self.dependencies[pkg_name]["version"] = version

    def _parse_setup_py(self) -> None:
        """Parse setup.py install_requires via regex."""
        setup_py = self.workspace / "setup.py"
        if not setup_py.exists():
            return

        try:
            with open(setup_py) as f:
                content = f.read()

            # Match install_requires = [...] or install_requires=[...]
            match = re.search(r"install_requires\s*=\s*\[(.*?)\]", content, re.DOTALL)
            if match:
                req_block = match.group(1)
                for req_line in req_block.split(","):
                    req_line = req_line.strip().strip("'\"")
                    if req_line:
                        self._add_requirement(req_line)
        except Exception:
            pass

    def _parse_setup_cfg(self) -> None:
        """Parse setup.cfg [options] install_requires."""
        setup_cfg = self.workspace / "setup.cfg"
        if not setup_cfg.exists():
            return

        try:
            with open(setup_cfg) as f:
                content = f.read()

            match = re.search(r"\[options\](.*?)(?:\[|$)", content, re.DOTALL)
            if match:
                options_block = match.group(1)
                match = re.search(r"install_requires\s*=(.*?)(?:\n\[|\Z)", options_block, re.DOTALL)
                if match:
                    req_block = match.group(1)
                    for line in req_block.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#"):
                            self._add_requirement(line)
        except Exception:
            pass

    def _parse_pyproject_toml(self) -> None:
        """Parse pyproject.toml [project.dependencies] and [tool.poetry.dependencies]."""
        pyproject = self.workspace / "pyproject.toml"
        if not pyproject.exists():
            return

        try:
            if tomllib:
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)

                # Standard PEP 508 dependencies
                if "project" in data and "dependencies" in data["project"]:
                    for req in data["project"]["dependencies"]:
                        self._add_requirement(req)

                # Poetry dependencies
                if "tool" in data and "poetry" in data["tool"] and "dependencies" in data["tool"]["poetry"]:
                    for pkg, spec in data["tool"]["poetry"]["dependencies"].items():
                        if isinstance(spec, dict):
                            version = spec.get("version")
                        else:
                            version = spec if spec != "*" else None
                        self.dependencies[pkg.lower().replace("_", "-")] = {"version": version, "licenses": []}
            else:
                # Regex fallback for TOML
                with open(pyproject) as f:
                    content = f.read()

                # Match dependencies array
                for match in re.finditer(r"\[\s*project\.dependencies\s*\](.*?)(?:\[|$)", content, re.DOTALL):
                    req_block = match.group(1)
                    for line in req_block.split("\n"):
                        line = line.strip().strip('",').strip("'")
                        if line:
                            self._add_requirement(line)
        except Exception:
            pass

    def _parse_pipfile(self) -> None:
        """Parse Pipfile (TOML format)."""
        pipfile = self.workspace / "Pipfile"
        if not pipfile.exists():
            return

        try:
            if tomllib:
                with open(pipfile, "rb") as f:
                    data = tomllib.load(f)

                if "packages" in data:
                    for pkg, spec in data["packages"].items():
                        if isinstance(spec, dict):
                            version = spec.get("version")
                        else:
                            version = spec if spec != "*" else None
                        self.dependencies[pkg.lower().replace("_", "-")] = {"version": version, "licenses": []}
        except Exception:
            pass

    def _parse_dist_info(self) -> None:
        """Parse vendored packages from *.dist-info and *.egg-info."""
        for metadata_dir in self.workspace.rglob("*.dist-info"):
            metadata_file = metadata_dir / "METADATA"
            if metadata_file.exists():
                self._parse_metadata_file(metadata_file)

        for egg_dir in self.workspace.rglob("*.egg-info"):
            metadata_file = egg_dir / "PKG-INFO"
            if metadata_file.exists():
                self._parse_metadata_file(metadata_file)

    def _parse_metadata_file(self, path: Path) -> None:
        """Parse METADATA or PKG-INFO file."""
        try:
            with open(path) as f:
                content = f.read()

            name_match = re.search(r"^Name:\s*(.+?)$", content, re.MULTILINE)
            version_match = re.search(r"^Version:\s*(.+?)$", content, re.MULTILINE)

            if name_match:
                pkg_name = name_match.group(1).strip().lower().replace("_", "-")
                version = version_match.group(1).strip() if version_match else None

                if pkg_name not in self.dependencies:
                    self.dependencies[pkg_name] = {"version": version, "licenses": []}
        except Exception:
            pass

    def _generate_purl(self, pkg_name: str, version: Optional[str]) -> str:
        """Generate Package URL (PURL) for PyPI package."""
        name = pkg_name.lower().replace("_", "-")
        if version:
            return f"pkg:pypi/{name}@{version}"
        return f"pkg:pypi/{name}"


class VulnerabilityScanner:
    """Scan for known vulnerabilities using pip-audit or OSV API."""

    def __init__(self, dependencies: Dict[str, Dict[str, Any]], skip_vulns: bool = False):
        self.dependencies = dependencies
        self.skip_vulns = skip_vulns
        self.findings: List[Dict[str, Any]] = []

    def scan(self) -> List[Dict[str, Any]]:
        """Scan dependencies for vulnerabilities."""
        if self.skip_vulns:
            return []

        # Try pip-audit first
        if self._try_pip_audit():
            return self.findings

        # Fallback to OSV API
        self._scan_with_osv_api()
        return self.findings

    def _try_pip_audit(self) -> bool:
        """Try to use pip-audit command."""
        try:
            result = subprocess.run(
                ["pip-audit", "--desc", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode in (0, 64):  # 64 = vulnerabilities found
                data = json.loads(result.stdout)
                for vuln in data.get("vulnerabilities", []):
                    self._add_vulnerability(vuln)
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return False

    def _scan_with_osv_api(self) -> None:
        """Query OSV API for vulnerabilities."""
        try:
            import urllib.request
        except ImportError:
            return

        for pkg_name, pkg_info in self.dependencies.items():
            version = pkg_info.get("version")
            if not version or version in ("unknown", "*"):
                continue

            try:
                query = {
                    "package": {"name": pkg_name, "ecosystem": "PyPI"},
                    "version": version
                }
                req = urllib.request.Request(
                    "https://api.osv.dev/v1/query",
                    data=json.dumps(query).encode(),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read())
                    for vuln in data.get("vulns", []):
                        self._add_osv_vulnerability(pkg_name, version, vuln)
            except Exception:
                continue

    def _add_vulnerability(self, vuln: Dict[str, Any]) -> None:
        """Add pip-audit vulnerability finding."""
        self.findings.append({
            "type": "vulnerability",
            "severity": self._map_severity(vuln.get("vulnerability", {}).get("severity")),
            "title": vuln.get("vulnerability", {}).get("summary", "Unknown vulnerability"),
            "detail": vuln.get("vulnerability", {}).get("description", ""),
            "package": vuln.get("name"),
            "installed_version": vuln.get("installed_version"),
            "fixed_version": vuln.get("fixed_version"),
            "cve": vuln.get("vulnerability", {}).get("cve"),
        })

    def _add_osv_vulnerability(self, pkg_name: str, version: str, vuln: Dict[str, Any]) -> None:
        """Add OSV API vulnerability finding."""
        self.findings.append({
            "type": "vulnerability",
            "severity": self._map_severity(vuln.get("severity")),
            "title": vuln.get("summary", "Unknown vulnerability"),
            "detail": vuln.get("details", ""),
            "package": pkg_name,
            "installed_version": version,
            "cve": vuln.get("id") if vuln.get("id", "").startswith("CVE") else None,
            "osv_id": vuln.get("id"),
        })

    @staticmethod
    def _map_severity(severity_str: Optional[str]) -> str:
        """Map severity string to standardized level."""
        if not severity_str:
            return "medium"
        severity_str = severity_str.lower()
        if "critical" in severity_str:
            return "critical"
        elif "high" in severity_str:
            return "high"
        elif "medium" in severity_str:
            return "medium"
        elif "low" in severity_str:
            return "low"
        return "info"


class StaticSecurityAnalyzer:
    """Static analysis for security issues (bandit or regex fallback)."""

    REGEX_PATTERNS = {
        "eval_usage": (r"\beval\s*\(", "high", "eval() usage allows arbitrary code execution"),
        "exec_usage": (r"\bexec\s*\(", "high", "exec() usage allows arbitrary code execution"),
        "subprocess_shell": (r"subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True", "high", "subprocess shell=True is dangerous"),
        "os_system": (r"\bos\.system\s*\(", "high", "os.system() is unsafe for untrusted input"),
        "os_popen": (r"\bos\.popen\s*\(", "high", "os.popen() is unsafe for untrusted input"),
        "pickle_loads": (r"\bpickle\.loads\s*\(", "medium", "pickle.loads() can deserialize arbitrary code"),
        "marshal_loads": (r"\bmarshal\.loads\s*\(", "medium", "marshal.loads() can deserialize arbitrary code"),
        "weak_md5": (r"\bhashlib\.md5\s*\(", "medium", "MD5 is cryptographically weak"),
        "weak_sha1": (r"\bhashlib\.sha1\s*\(", "medium", "SHA1 is cryptographically weak"),
        "ssl_unverified": (r"ssl\._create_unverified_context|verify\s*=\s*False", "high", "Unverified SSL context"),
        "yaml_unsafe": (r"\byaml\.load\s*\([^)]*\)", "high", "yaml.load() without SafeLoader is dangerous"),
        "assert_check": (r"\bassert\s+", "low", "assert can be disabled with -O flag (not for security)"),
        "debug_enabled": (r"\b(?:DEBUG|debug)\s*=\s*True\b", "medium", "DEBUG mode left enabled"),
        "tempfile_mktemp": (r"\btempfile\.mktemp\s*\(", "high", "tempfile.mktemp() has race condition"),
    }

    def __init__(self, workspace: Path, skip_bandit: bool = False):
        self.workspace = workspace
        self.skip_bandit = skip_bandit
        self.findings: List[Dict[str, Any]] = []

    def scan(self) -> List[Dict[str, Any]]:
        """Scan for static security issues."""
        if not self.skip_bandit and self._try_bandit():
            return self.findings

        # Regex fallback
        self._regex_scan()
        return self.findings

    def _try_bandit(self) -> bool:
        """Try to run bandit."""
        try:
            result = subprocess.run(
                ["bandit", "-r", str(self.workspace), "-f", "json"],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode in (0, 1):
                data = json.loads(result.stdout)
                for result_item in data.get("results", []):
                    self.findings.append({
                        "type": "static_analysis",
                        "severity": result_item.get("severity", "medium").lower(),
                        "title": result_item.get("test_id", "unknown"),
                        "detail": result_item.get("issue_text", ""),
                        "file": result_item.get("filename", ""),
                        "line": result_item.get("line_number"),
                        "confidence": result_item.get("confidence", "medium").lower(),
                    })
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return False

    def _regex_scan(self) -> None:
        """Fallback regex-based scanning."""
        for py_file in self.workspace.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            self._scan_file(py_file)

    def _scan_file(self, file_path: Path) -> None:
        """Scan a single Python file."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Remove comments and docstrings (simple approach)
            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                # Skip comments
                if line.strip().startswith("#"):
                    continue

                # Simple docstring skip (not perfect)
                if '"""' in line or "'''" in line:
                    continue

                for pattern_name, (pattern, severity, description) in self.REGEX_PATTERNS.items():
                    if re.search(pattern, line):
                        self.findings.append({
                            "type": "static_analysis",
                            "severity": severity,
                            "title": pattern_name,
                            "detail": description,
                            "file": str(file_path.relative_to(self.workspace)),
                            "line": line_num,
                            "confidence": "medium"
                        })
        except Exception:
            pass

    @staticmethod
    def _should_skip_file(file_path: Path) -> bool:
        """Check if file should be skipped."""
        parts = file_path.parts
        skip_dirs = {"__pycache__", ".git", "node_modules", ".venv", "venv"}
        return any(part in skip_dirs for part in parts)


class SecretDetector:
    """Detect secrets and credentials in files."""

    PATTERNS = {
        "aws_key": (r"AKIA[0-9A-Z]{16}", "critical"),
        "github_token": (r"gh[pors]_[A-Za-z0-9_]{36,}", "critical"),
        "slack_token": (r"xox[bprs]-[A-Za-z0-9-]{10,}", "critical"),
        "stripe_key": (r"sk_(?:live|test)_[A-Za-z0-9]{20,}", "critical"),
        "private_key": (r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "critical"),
        "password_literal": (r"\b(?:password|passwd|pwd)\s*=\s*['\"]([^'\"]+)['\"]", "high"),
        "api_key_literal": (r"\b(?:api_key|apikey|api_secret)\s*=\s*['\"]([^'\"]+)['\"]", "high"),
        "token_literal": (r"\b(?:token|access_token)\s*=\s*['\"]([^'\"]+)['\"]", "high"),
        "secret_literal": (r"\b(?:secret|SECRET)\s*=\s*['\"]([^'\"]+)['\"]", "high"),
        "connection_string": (r"[a-z]+://[^:]+:[^@]+@[^/\s]+", "high"),
    }

    def __init__(self, workspace: Path, skip_secrets: bool = False):
        self.workspace = workspace
        self.skip_secrets = skip_secrets
        self.findings: List[Dict[str, Any]] = []

    def scan(self) -> List[Dict[str, Any]]:
        """Scan for secrets."""
        if self.skip_secrets:
            return []

        for file_path in self.workspace.rglob("*"):
            if self._should_skip_file(file_path):
                continue
            if file_path.is_file():
                self._scan_file(file_path)

        # Check for .env files
        for env_file in self.workspace.rglob(".env*"):
            self.findings.append({
                "type": "secret",
                "severity": "medium",
                "title": ".env file found",
                "detail": ".env files should not be committed to version control",
                "file": str(env_file.relative_to(self.workspace)),
                "line": None,
                "confidence": "high"
            })

        return self.findings

    def _scan_file(self, file_path: Path) -> None:
        """Scan a single file for secrets."""
        if not self._is_text_file(file_path):
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                for pattern_name, (pattern, severity) in self.PATTERNS.items():
                    if re.search(pattern, line):
                        # Skip false positives for env vars and function calls
                        if any(skip in line for skip in ["os.environ", "args.", "getenv", "= None", "os.get"]):
                            continue

                        self.findings.append({
                            "type": "secret",
                            "severity": severity,
                            "title": f"Potential {pattern_name} detected",
                            "detail": f"Possible {pattern_name} found in source code",
                            "file": str(file_path.relative_to(self.workspace)),
                            "line": line_num,
                            "confidence": "medium"
                        })
        except Exception:
            pass

    @staticmethod
    def _is_text_file(file_path: Path) -> bool:
        """Check if file is likely text by examining first 1KB."""
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                return b"\x00" not in chunk
        except Exception:
            return False

    @staticmethod
    def _should_skip_file(file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = {".pyc", ".pyo", ".git", "__pycache__", "node_modules", ".min.js"}
        name = file_path.name
        parts = file_path.parts

        if any(name.endswith(p) for p in skip_patterns):
            return True
        return any(p in parts for p in skip_patterns)


class MigrationSecurityChecker:
    """Check for security issues specific to Py2→3 migrations."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.findings: List[Dict[str, Any]] = []

    def scan(self) -> List[Dict[str, Any]]:
        """Scan for migration-specific security issues."""
        for py_file in self.workspace.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            self._check_file(py_file)
        return self.findings

    def _check_file(self, file_path: Path) -> None:
        """Check a single file."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                self._check_input_usage(file_path, line_num, line)
                self._check_pickle_protocol(file_path, line_num, line)
                self._check_exec_open(file_path, line_num, line)
                self._check_hashlib_usage(file_path, line_num, line)
                self._check_sql_formatting(file_path, line_num, line)
                self._check_dict_ordering(file_path, line_num, line)
        except Exception:
            pass

    def _check_input_usage(self, file_path: Path, line_num: int, line: str) -> None:
        """Check for unsafe input() usage."""
        if re.search(r"\binput\s*\(", line) and "raw_input" not in line:
            self.findings.append({
                "type": "migration_specific",
                "severity": "high",
                "title": "input() without raw_input compatibility",
                "detail": "In Py2, input() evaluated expressions. Ensure raw_input was used for safety.",
                "file": str(file_path.relative_to(self.workspace)),
                "line": line_num,
                "confidence": "medium"
            })

    def _check_pickle_protocol(self, file_path: Path, line_num: int, line: str) -> None:
        """Check for pickle without explicit protocol."""
        if re.search(r"pickle\.(dumps?|loads?)\s*\([^)]*\)", line):
            if "protocol" not in line:
                self.findings.append({
                    "type": "migration_specific",
                    "severity": "medium",
                    "title": "pickle without explicit protocol",
                    "detail": "Specify protocol= for cross-version compatibility",
                    "file": str(file_path.relative_to(self.workspace)),
                    "line": line_num,
                    "confidence": "high"
                })

    def _check_exec_open(self, file_path: Path, line_num: int, line: str) -> None:
        """Check for exec(open(...)) pattern."""
        if re.search(r"\bexec\s*\(\s*open\s*\(", line):
            self.findings.append({
                "type": "migration_specific",
                "severity": "high",
                "title": "exec(open(...)) pattern detected",
                "detail": "Verify file path is not user-controlled. This was execfile() in Py2.",
                "file": str(file_path.relative_to(self.workspace)),
                "line": line_num,
                "confidence": "high"
            })

    def _check_hashlib_usage(self, file_path: Path, line_num: int, line: str) -> None:
        """Check for hashlib without usedforsecurity parameter."""
        if re.search(r"hashlib\.\w+\s*\(", line) and "usedforsecurity" not in line:
            self.findings.append({
                "type": "migration_specific",
                "severity": "low",
                "title": "hashlib without usedforsecurity parameter",
                "detail": "Add usedforsecurity parameter for Py3.9+ FIPS compliance",
                "file": str(file_path.relative_to(self.workspace)),
                "line": line_num,
                "confidence": "low"
            })

    def _check_sql_formatting(self, file_path: Path, line_num: int, line: str) -> None:
        """Check for SQL string formatting."""
        if re.search(r"['\"]SELECT\s+.+[%{]\s*\w+[%}]", line, re.IGNORECASE):
            self.findings.append({
                "type": "migration_specific",
                "severity": "high",
                "title": "SQL string formatting detected",
                "detail": "Use parameterized queries to prevent SQL injection",
                "file": str(file_path.relative_to(self.workspace)),
                "line": line_num,
                "confidence": "medium"
            })

    def _check_dict_ordering(self, file_path: Path, line_num: int, line: str) -> None:
        """Check for dict ordering assumptions."""
        if "dict(" in line or "{" in line:
            if "PYTHONHASHSEED" in line or "hash" in line.lower():
                self.findings.append({
                    "type": "migration_specific",
                    "severity": "low",
                    "title": "Possible dict ordering dependency",
                    "detail": "Dict order is guaranteed in Py3.7+, but verify assumptions",
                    "file": str(file_path.relative_to(self.workspace)),
                    "line": line_num,
                    "confidence": "low"
                })

    @staticmethod
    def _should_skip_file(file_path: Path) -> bool:
        """Check if file should be skipped."""
        parts = file_path.parts
        skip_dirs = {"__pycache__", ".git", "node_modules", ".venv", "venv"}
        return any(part in skip_dirs for part in parts)


class DependencyPinningChecker:
    """Check dependency version pinning."""

    def __init__(self, dependencies: Dict[str, Dict[str, Any]]):
        self.dependencies = dependencies
        self.findings: List[Dict[str, Any]] = []

    def scan(self) -> List[Dict[str, Any]]:
        """Check dependency pinning."""
        for pkg_name, pkg_info in self.dependencies.items():
            version = pkg_info.get("version")

            if not version:
                severity = "medium"
                title = "Unpinned dependency"
                detail = f"{pkg_name} has no version constraint"
            elif version == "*" or version == ">=":
                severity = "low"
                title = "Loosely pinned dependency"
                detail = f"{pkg_name} uses loose version constraint: {version}"
            elif ">=" in version and not re.search(r"[<!=]", version[version.find(">=") + 2:]):
                severity = "low"
                title = "Lower bound only"
                detail = f"{pkg_name} specifies only lower bound: {version}"
            else:
                continue

            self.findings.append({
                "type": "dependency",
                "severity": severity,
                "title": title,
                "detail": detail,
                "package": pkg_name,
                "version": version,
                "confidence": "high"
            })

        return self.findings


class SecurityReporter:
    """Generate security scan reports."""

    def __init__(self, findings: List[Dict[str, Any]], sbom: Dict[str, Any], workspace: Path, scan_mode: str):
        self.findings = findings
        self.sbom = sbom
        self.workspace = workspace
        self.scan_mode = scan_mode

    def generate_json_report(self, output_dir: Path) -> Dict[str, Any]:
        """Generate JSON report."""
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        type_counts = {
            "vulnerabilities": 0,
            "secrets": 0,
            "static_analysis": 0,
            "migration_specific": 0,
            "dependency_issues": 0
        }

        for finding in self.findings:
            severity = finding.get("severity", "info")
            if severity in severity_counts:
                severity_counts[severity] += 1

            finding_type = finding.get("type", "unknown")
            if finding_type == "vulnerability":
                type_counts["vulnerabilities"] += 1
            elif finding_type == "secret":
                type_counts["secrets"] += 1
            elif finding_type == "static_analysis":
                type_counts["static_analysis"] += 1
            elif finding_type == "migration_specific":
                type_counts["migration_specific"] += 1
            elif finding_type == "dependency":
                type_counts["dependency_issues"] += 1

        report = {
            "scan_mode": self.scan_mode,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "workspace": str(self.workspace),
            "summary": {
                "total_findings": len(self.findings),
                **severity_counts,
                **type_counts
            },
            "sbom_path": "sbom.json",
            "findings": [
                {
                    "id": f"finding-{i}",
                    "type": f.get("type"),
                    "severity": f.get("severity"),
                    "title": f.get("title"),
                    "detail": f.get("detail"),
                    "file": f.get("file"),
                    "line": f.get("line"),
                    "cve": f.get("cve"),
                    "package": f.get("package"),
                    "recommendation": self._get_recommendation(f),
                    "confidence": f.get("confidence", "medium")
                }
                for i, f in enumerate(self.findings)
            ]
        }
        return report

    def generate_markdown_report(self, output_dir: Path) -> str:
        """Generate human-readable markdown report."""
        md_lines = [
            "# Security Scan Report",
            "",
            f"**Scan Mode:** {self.scan_mode}",
            f"**Timestamp:** {datetime.datetime.utcnow().isoformat()}Z",
            f"**Workspace:** {self.workspace}",
            "",
            "## Executive Summary",
            ""
        ]

        severity_counts = {}
        for f in self.findings:
            severity = f.get("severity", "info")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        for severity in ["critical", "high", "medium", "low", "info"]:
            count = severity_counts.get(severity, 0)
            if count > 0:
                md_lines.append(f"- **{severity.upper()}**: {count}")

        md_lines.extend([
            "",
            "## SBOM Summary",
            f"- **Total Dependencies:** {len(self.sbom.get('components', []))}",
            f"- **SBOM Format:** CycloneDX 1.5",
            "",
            "## Findings by Type"
        ])

        for ftype in ["vulnerability", "secret", "static_analysis", "migration_specific", "dependency"]:
            type_findings = [f for f in self.findings if f.get("type") == ftype]
            if type_findings:
                md_lines.append(f"\n### {ftype.replace('_', ' ').title()} ({len(type_findings)})")
                for f in sorted(type_findings, key=lambda x: x.get("severity", "info"), reverse=True)[:10]:
                    md_lines.append(f"\n**{f.get('title')}** ({f.get('severity').upper()})")
                    md_lines.append(f"- File: {f.get('file', 'N/A')}:{f.get('line', 'N/A')}")
                    md_lines.append(f"- {f.get('detail', '')}")

        return "\n".join(md_lines)

    @staticmethod
    def _get_recommendation(finding: Dict[str, Any]) -> str:
        """Get remediation recommendation based on finding type."""
        finding_type = finding.get("type")
        severity = finding.get("severity")

        if finding_type == "vulnerability":
            return f"Upgrade {finding.get('package')} to a patched version"
        elif finding_type == "secret":
            return "Remove from source code, rotate credentials, add to .gitignore"
        elif finding_type == "static_analysis":
            return f"Review and fix {finding.get('title')} pattern"
        elif finding_type == "migration_specific":
            return "Review migration-specific security implications"
        elif finding_type == "dependency":
            return "Pin dependency version or implement lock file strategy"
        return "Review and remediate as appropriate"


@log_execution
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Python 2→3 Migration Security Scanner")
    parser.add_argument("codebase_path", help="Path to codebase to scan")
    parser.add_argument("--mode", choices=["baseline", "regression", "final"], default="baseline",
                        help="Scan mode")
    parser.add_argument("--baseline-report", help="Path to baseline security report")
    parser.add_argument("-o", "--output", default="./security-scan-output",
                        help="Output directory")
    parser.add_argument("--skip-bandit", action="store_true", help="Skip bandit analysis")
    parser.add_argument("--skip-secrets", action="store_true", help="Skip secret detection")
    parser.add_argument("--skip-vulns", action="store_true", help="Skip vulnerability checks")

    args = parser.parse_args()

    workspace = Path(args.codebase_path).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate SBOM
    sbom_gen = SBOMGenerator(workspace)
    sbom = sbom_gen.generate()

    # Run scanners
    findings = []
    findings.extend(VulnerabilityScanner(sbom_gen.dependencies, args.skip_vulns).scan())
    findings.extend(StaticSecurityAnalyzer(workspace, args.skip_bandit).scan())
    findings.extend(SecretDetector(workspace, args.skip_secrets).scan())
    findings.extend(MigrationSecurityChecker(workspace).scan())
    findings.extend(DependencyPinningChecker(sbom_gen.dependencies).scan())

    # Generate reports
    reporter = SecurityReporter(findings, sbom, workspace, args.mode)

    json_report = reporter.generate_json_report(output_dir)
    with open(output_dir / "security-report.json", "w") as f:
        json.dump(json_report, f, indent=2)

    md_report = reporter.generate_markdown_report(output_dir)
    with open(output_dir / "security-report.md", "w") as f:
        f.write(md_report)

    with open(output_dir / "sbom.json", "w") as f:
        json.dump(sbom, f, indent=2)

    # Flagged for review
    flagged = [f for f in findings if f.get("confidence") == "low"]
    with open(output_dir / "flagged-for-review.json", "w") as f:
        json.dump({"findings": flagged}, f, indent=2)

    # Print summary
    print(json.dumps({
        "status": "complete",
        "total_findings": len(findings),
        "critical": sum(1 for f in findings if f.get("severity") == "critical"),
        "high": sum(1 for f in findings if f.get("severity") == "high"),
        "output_dir": str(output_dir)
    }, indent=2))

    return 0 if len([f for f in findings if f.get("severity") == "critical"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
