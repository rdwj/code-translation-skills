---
name: py2to3-library-replacement
description: >
  Python 2→3 library replacement advisor. Maps Python 2 deprecated/removed library imports to their Python 3 equivalents and
  generate replacement code. Trigger on library replacement, stdlib rename, removed module,
  import update, ConfigParser, urllib2, cPickle, cStringIO, distutils, and similar library
  migration needs.
---

# Library Replacement Advisor

Maps Python 2-only or deprecated standard library modules to their Python 3 equivalents,
generates replacement code, updates imports, and flags third-party dependencies that need
Py3-compatible versions. This skill handles both simple renames (ConfigParser → configparser)
and complex replacements (urllib2 split into urllib.request/urllib.error).

## When to Use

- When you need to replace Py2-only stdlib modules with Py3 equivalents
- When targeting Python 3.12+ and need to handle modules removed in that version
- When a codebase imports deprecated modules like `cPickle`, `cStringIO`, `ConfigParser`
- When you need to understand third-party library compatibility
- When updating an old `setup.py` or requirements that relies on `distutils`

## Inputs

The user provides:
- **codebase_path** or **file_paths**: Root directory or specific Python files to process
- **target_version** (optional): Python 3 version to target (e.g., "3.9", "3.11", "3.12"). Defaults to "3.11"
- **--output**: Directory for replacement output files
- **--state-file**: Path to Migration State Tracker JSON (for integration)
- **--analysis-dir**: Directory containing Phase 0 analysis outputs (for context)
- **--dry-run**: Preview changes without modifying files

## Outputs

All outputs go into the specified `--output` directory:

| File | Format | Purpose |
|------|--------|---------|
| `library-replacements.json` | JSON | Per-file import replacements applied with old→new mappings |
| `no-replacement-found.json` | JSON | Imports with no clear Py3 equivalent (manual work required) |
| `library-replacements.md` | Markdown | Human-readable report with summary and next steps |
| Modified `.py` files | Python | Source files with replaced imports (in-place or in output dir) |

## Workflow

### Step 1: Scan Imports

Walk the codebase (or specified files) and extract all import statements using AST parsing.
Categorize each import by:
- **Renamed**: Module exists in Py3 under a different name (ConfigParser → configparser)
- **Removed**: Module removed from stdlib in target version (cgi in 3.12, pipes in 3.12)
- **Complex**: Multi-part replacement (urllib2 → urllib.request + urllib.error)
- **Third-party**: Known incompatible or needs version bump

### Step 2: Classify

For each import:
1. Check RENAMED mapping (simple 1:1 renames)
2. Check REMOVED mapping for target version (version-aware)
3. Check COMPLEX mapping (special cases requiring code rewrites)
4. Check known third-party replacements
5. If no mapping found, flag as "no-replacement-found"

### Step 3: Generate Replacement Code

For each import style found:
- **`import X`** → update to `import Y` (renamed modules)
- **`from X import A`** → update to `from Y import A` (renamed modules)
- **`from X import *`** → explicit import list needed (usually not supported in Py3)
- **Complex cases**:
  - urllib2 usage split and rewritten to use urllib.request/urllib.error
  - cStringIO/StringIO logic updated based on usage (bytes vs text)
  - cPickle → pickle (simple rename, but flag protocol version concerns)
  - distutils → setuptools (with `import sysconfig` for sysconfig utilities)

### Step 4: Apply Replacements

Rewrite import statements in source files using AST-based replacement.
For each file:
1. Parse with ast module
2. Find all Import and ImportFrom nodes
3. Rewrite import statements
4. Handle usage patterns that change (e.g., urllib2 call sites)
5. Write back to file (or output directory in dry-run mode)

### Step 5: Report

Generate JSON and Markdown reports:
- `library-replacements.json`: Detailed per-file replacements
- `no-replacement-found.json`: Manual work items
- `library-replacements.md`: Summary with installation instructions

## Library Mapping Tables

### Renamed Standard Library Modules (1:1)

Simple renames where old module exists in Py3 under a different name.

| Python 2 | Python 3 | Notes |
|----------|----------|-------|
| `ConfigParser` | `configparser` | Config file parsing |
| `Queue` | `queue` | Thread-safe queues |
| `SocketServer` | `socketserver` | Network servers |
| `HTMLParser` | `html.parser` | HTML/XHTML parsing |
| `httplib` | `http.client` | HTTP protocol client |
| `repr` | `reprlib` | Alternative `repr()` |
| `Tkinter` | `tkinter` | GUI toolkit |
| `thread` | `_thread` | Low-level threading (prefer `threading`) |
| `commands` | `subprocess` | Shell command execution |
| `copy_reg` | `copyreg` | Pickle support |
| `xmlrpclib` | `xmlrpc.client` | XML-RPC client |
| `Cookie` | `http.cookies` | HTTP cookies |
| `cookielib` | `http.cookiejar` | HTTP cookie jar |
| `htmlentitydefs` | `html.entities` | HTML character entities |
| `robotparser` | `urllib.robotparser` | robots.txt parsing |
| `UserDict` | `collections.UserDict` | User-defined dict |
| `UserList` | `collections.UserList` | User-defined list |
| `UserString` | `collections.UserString` | User-defined string |
| `BaseHTTPServer` | `http.server` | Basic HTTP server |
| `SimpleHTTPServer` | `http.server` | Simple HTTP server |
| `CGIHTTPServer` | `http.server` | CGI-enabled HTTP server |
| `DocXMLRPCServer` | `xmlrpc.server` | XML-RPC documentation server |
| `SimpleXMLRPCServer` | `xmlrpc.server` | Simple XML-RPC server |

### Removed Standard Library Modules by Version

These modules do not exist in Python 3. Replacement depends on target version.

**Python 3.12 Removals** (critical for 3.12+ targets):

| Module | Replacement | Install | Notes |
|--------|------------|---------|-------|
| `distutils` | `setuptools` | `pip install setuptools` | Build system — largest blocker for 3.12 |
| `cgi` | `urllib.parse.parse_qs`, `email.message` | stdlib | Form parsing and CGI serving |
| `cgitb` | `traceback`, `faulthandler` | stdlib | Detailed error tracebacks |
| `aifc` | `soundfile`, `pydub` | Third-party | Audio file format |
| `audioop` | `pydub`, `numpy` | Third-party | Audio operations |
| `chunk` | Manual implementation | — | IFF chunk reading |
| `crypt` | `bcrypt`, `passlib` | Third-party | Password hashing |
| `imghdr` | `filetype`, `python-magic`, `Pillow` | Third-party | Image type detection |
| `mailcap` | `mimetypes` (partial) | stdlib | MIME type mapping |
| `msilib` | WiX toolset | External | Windows MSI creation |
| `nis` | OS-level auth | External | NIS/YP client |
| `nntplib` | Third-party NNTP | Third-party | NNTP protocol client |
| `ossaudiodev` | `pyaudio`, `sounddevice` | Third-party | Linux OSS audio |
| `pipes` | `subprocess`, `shlex` | stdlib | Shell pipeline construction |
| `sndhdr` | `filetype`, `python-magic` | Third-party | Sound file type detection |
| `spwd` | OS-level auth | External | Shadow password DB |
| `sunau` | `soundfile` | Third-party | Sun AU audio format |
| `telnetlib` | `telnetlib3`, `asynctelnet` | Third-party | Telnet client |
| `uu` | `base64`, `binascii` | stdlib | Uuencode/uudecode |
| `xdrlib` | `struct`, `xdrlib2` | Third-party | XDR serialization |

Refer to `references/stdlib-removals-by-version.md` for the complete version-specific list.

### Complex Replacements (Multi-Step)

These require understanding usage context and rewriting call sites.

#### urllib2 → urllib.request / urllib.error / urllib.parse

Python 2's `urllib2` is split across multiple modules in Py3:

| Py2 Pattern | Py3 Replacement | Example |
|------------|-----------------|---------|
| `urllib2.Request(url)` | `urllib.request.Request(url)` | `from urllib.request import Request` |
| `urllib2.urlopen(url)` | `urllib.request.urlopen(url)` | Same import |
| `urllib2.HTTPError` | `urllib.error.HTTPError` | `from urllib.error import HTTPError` |
| `urllib2.URLError` | `urllib.error.URLError` | Same import |
| `urlparse.urljoin(base, url)` | `urllib.parse.urljoin(base, url)` | `from urllib.parse import urljoin` |
| `urlparse.urlparse(url)` | `urllib.parse.urlparse(url)` | Same import |
| `urllib.quote(str)` | `urllib.parse.quote(str)` | `from urllib.parse import quote` |

**Strategy**: Detect usage patterns and rewrite both imports and call sites.

#### cStringIO / StringIO → io.StringIO / io.BytesIO

Python 2 had three variants; Py3 unifies them based on data type:

| Py2 Pattern | Usage | Py3 Replacement |
|------------|-------|-----------------|
| `cStringIO.StringIO()` | Bytes buffer | `io.BytesIO()` |
| `StringIO.StringIO()` | Text buffer | `io.StringIO()` |
| `import cStringIO as StringIO` | Generic alias | `from io import StringIO, BytesIO` |

**Strategy**: Analyze usage — if it receives/returns bytes, use `BytesIO`; if text, use `StringIO`.

#### cPickle → pickle

Direct module rename. Flag protocol version awareness:

| Py2 | Py3 |
|-----|-----|
| `import cPickle` | `import pickle` |
| `cPickle.dumps(obj)` | `pickle.dumps(obj)` |

**Important**: Check for hardcoded protocol versions:
- `cPickle.dumps(obj, protocol=2)` → works in Py3, but protocol 3+ is recommended
- `cPickle.dumps(obj, protocol=0)` → works in Py3, but less efficient

#### distutils → setuptools (3.12+)

Critical blocker for Python 3.12+ targets:

| Py2 (setup.py) | Py3 Replacement |
|----------------|-----------------|
| `from distutils.core import setup` | `from setuptools import setup` |
| `from distutils.core import Extension` | `from setuptools import Extension` |
| `from distutils.command import build` | `from setuptools.command import build` |
| `distutils.sysconfig` | `sysconfig` (stdlib) |
| `distutils.util.strtobool(val)` | `val.lower() in ('yes', 'true', '1')` |
| `distutils.version.LooseVersion` | `packaging.version.Version` |
| `distutils.version.StrictVersion` | `packaging.version.Version` |
| `distutils.dir_util` | `shutil` |
| `distutils.file_util` | `shutil` |
| `distutils.spawn.find_executable` | `shutil.which` |

## Target Version Awareness

Module removals are **version-specific**. The skill should:

1. Check target version
2. Only flag removed modules that apply to target version
3. Provide version-appropriate replacements
4. For 3.11 targets, modules removed in 3.12 should be noted but not required

Example:
- Target 3.11: `cgi` warning but optional replacement
- Target 3.12: `cgi` replacement required

## Integration with Migration State Tracker

If `--state-file` provided:
- Load current migration state from JSON
- Update with library replacement tracking
- Record per-file import changes
- Save updated state for next skill

State file records:
```json
{
  "library_replacements": {
    "file1.py": [
      {"old_import": "ConfigParser", "new_import": "configparser", "type": "renamed"}
    ]
  },
  "unresolved_imports": ["my_custom_module"],
  "third_party_updates": ["setuptools"]
}
```

## Scripts Reference

### `scripts/advise_replacements.py`
Main script: analyzes imports, applies replacements, generates output.

Usage:
```
python3 advise_replacements.py <codebase_path> \
    --target-version 3.12 \
    --output <output_dir> \
    [--state-file <state.json>] \
    [--analysis-dir <analysis_dir>] \
    [--dry-run] \
    [--conversion-plan <plan.json>]
```

### `scripts/generate_replacement_report.py`
Generates markdown report from library-replacements.json.

Usage:
```
python3 generate_replacement_report.py <output_dir> \
    --output <output_dir>/library-replacements.md
```

## Important Considerations

**Import statements are structural.** Unlike code that can be fuzzy-matched, import
statements must be exact. Always use AST parsing to identify and replace them.

**Usage context matters for complex replacements.** For `cStringIO`/`StringIO` and
`urllib2`, you may need to analyze call sites to determine the right replacement. When
in doubt, flag as "manual review needed."

**Third-party libraries need version checks.** If the codebase imports something like
`requests` or `numpy`, check if there's a Py3-compatible version. The script should
cross-reference against known Py3-compatible library versions.

**distutils is a critical blocker for 3.12+.** If the codebase has a `setup.py` using
`distutils`, this must be converted before targeting 3.12. This often triggers a
build system upgrade (setuptools, pyproject.toml, etc.), which may be out of scope for
this skill but should be flagged prominently.

**Relative imports may be hidden in `from __future__`** — the codebase may already be
using `from __future__ import absolute_import`, which helps. Check for this.

**The skill should preserve import order and formatting as much as possible** to avoid
unnecessary diffs in the final code. Use AST-based replacement, not regex-based
find-and-replace.

## Model Tier

**Haiku.** Library replacement is pattern-based import rewriting from a known mapping table (ConfigParser→configparser, urllib2→urllib.request, etc.). Always use Haiku.

## References

- `references/stdlib-removals-by-version.md` — Complete list of modules removed in each Python 3 minor version with replacement recommendations
- `references/py2-py3-syntax-changes.md` — Catalog of syntax differences (includes import-related changes)
- `references/serialization-migration.md` — cPickle→pickle migration details and protocol version guidance
- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
