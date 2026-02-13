---
name: py2to3-c-extension-flagger
description: >
  Identifies C extensions, Cython, ctypes, CFFI, and SWIG usage in a Python 2 codebase.
  Flags deprecated C API usage per target Python 3 version. Assesses migration effort and
  compatibility. Use this skill when you need to inventory native extensions, understand
  C API compatibility risks, plan C extension updates, or determine target version feasibility.
  Also trigger when someone says "find C extensions," "check for ctypes," "what native code
  exists," "assess C API compatibility," or "find deprecated C API usage."
---

# Skill 0.4: C Extension Flagger

## Why C Extensions Matter for Py2→Py3 Migration

C extensions are a major migration blocker because:

- **C API is version-specific**: The C API changed significantly between Py2 and Py3.
  - Py3.2: Removed `PyCObject`, changed unicode handling
  - Py3.8: Changed parameter handling in many API functions
  - Py3.9+: Started removing private API and `_PyObject_*` functions
  - Py3.12: Major removal phase (`wstr`, `tp_print`, `PyUnicode_READY`, `PyCObject`)
  - Py3.13: Continued removals and API hardening

- **Compiled extensions are binary artifacts**: They're tied to a specific Python version.
  Py2 extensions (`.so` files) won't load in Py3. All must be recompiled.

- **Limited API is the escape hatch**: If you use `Py_LIMITED_API`, your extension works
  across multiple Py3 versions without recompilation. But it requires an audit.

- **Cython changes the game**: Cython `.pyx` files must be regenerated with Py3-aware Cython.
  Old `.c` files (pre-generated from `.pyx`) won't compile under Py3.

- **ctypes/CFFI are safer**: These don't depend on the C API; they use the stable ABI.
  But they may have type signature assumptions that break with Py3.

- **SWIG adapts**: SWIG-generated wrappers are re-generated, but the `.i` interface file
  must match the target language version and C API.

This skill audits all of these and flags where the effort lies.

---

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| **codebase_path** | User | Root directory of Python 2 codebase |
| **--target-version** | User | Python 3.x target (3.9, 3.11, 3.12, 3.13) |
| **--output** | User | Output directory for reports (default: current dir) |
| **--strict** | User | Fail if any deprecated C API found (for gate check) |

---

## Outputs

All outputs go into the `--output` directory:

| File | Format | Purpose |
|------|--------|---------|
| `c-extension-report.json` | JSON | Complete inventory of extensions and C API usage |
| `c-extension-report.md` | Markdown | Human-readable summary with remediation guidance |

---

## Workflow

### Step 1: Discover Extension Files

Run the main detection script:

```bash
python3 scripts/flag_extensions.py <codebase_path> \
    --target-version 3.12 \
    --output ./extension-output/
```

This scans for:
- `.c` and `.h` files with `#include <Python.h>`
- `.pyx` and `.pxd` Cython source files
- `.i` SWIG interface files
- `setup.py` and `setup.cfg` with `Extension()` definitions

### Step 2: Analyze C API Usage

For each C file found, scan for:

**Deprecated C API (version-specific)**:
- `PyCObject` (removed in 3.2)
- `Py_UNICODE` (deprecated in 3.3, removed in 3.12)
- `wstr`/`wstr_length` fields (removed in 3.12)
- `tp_print` (removed in 3.12)
- `PyUnicode_READY()` (removed in 3.12)
- `_PyObject_*` functions (internal API, unsafe)
- `Py_TPFLAGS_HAVE_INDEX` (removed in 3.10)

**Safe API patterns**:
- `PyObject_*` functions (public API)
- `Py_LIMITED_API` guard (`#define Py_LIMITED_API 0x03090000` for Py3.9+)
- `PyUnicode_*` functions that survived removals

### Step 3: Inventory ctypes/CFFI/SWIG

Scan Python source for:

**ctypes patterns**:
- `from ctypes import CDLL, windll, WinDLL, Structure, POINTER, byref, cast`
- Function pointer definitions (`CFUNCTYPE`, `WINFUNCTYPE`)
- Type mappings (c_int, c_char_p, etc.)

**CFFI patterns**:
- `from cffi import FFI`
- `ffi.cdef()`, `ffi.dlopen()`, `ffi.verify()`, `ffi.compile()`

**SWIG patterns**:
- `.i` interface files with `%module`, `%include`, type wrapping directives

### Step 4: Check setup.py for Extension Definitions

Parse `setup.py`/`setup.cfg` for:
- `Extension()` class usage
- `ext_modules` parameter
- Compile flags and dependencies

### Step 5: Assess Risk and Effort

For each extension found:

**CRITICAL Risk**:
- Uses deprecated C API that's removed in target version
- No `Py_LIMITED_API` and must support multiple versions
- Cython `.pyx` files with old-style syntax

**HIGH Risk**:
- Uses `PyCObject` or `Py_UNICODE`
- Internal API (`_Py*` functions)
- Type assumptions that may break with Py3

**MEDIUM Risk**:
- ctypes/CFFI with type mappings needing verification
- SWIG with version-specific code generation

**LOW Risk**:
- `Py_LIMITED_API` (stable ABI)
- Pure Cython with standard patterns
- CFFI with clean FFI definitions

### Step 6: Generate Report

The report contains:
- Executive summary (total extensions, risk distribution)
- Per-extension details with findings and remediation
- Deprecated API cross-reference table
- Recommendation on whether target version is feasible

---

## Detection Categories

### 1. C Extensions (Native .so/.pyd files)

Looks for:
- `#include <Python.h>` in `.c`/`.h` files
- Module initialization (`PyMODINIT_FUNC`, `PyInit_*`)
- Extension setup in `setup.py`

Risk factors:
- Direct C API usage (must audit all API calls per version)
- Hardcoded version checks (`PY_VERSION_HEX`)
- Custom memory management (`PyMem_*`)

### 2. Cython (.pyx/.pxd files)

Looks for:
- `.pyx` source files (Cython source)
- `.pxd` definition files (C declarations)
- `cimport` statements (Cython imports)

Risk factors:
- Cython version compatibility (old Cython may not support Py3.12+)
- C API calls in `.pyx` files (must be checked)
- Memory management directives

### 3. ctypes

Looks for:
- `from ctypes import ...` (CDLL, Structure, POINTER, etc.)
- `ctypes.CDLL()`, `ctypes.WinDLL()`, `ctypes.WinDLL()`
- Function pointer definitions (`CFUNCTYPE`, `WINFUNCTYPE`)

Risk factors:
- Type signature assumptions (c_char vs. c_wchar, c_void_p semantics)
- Struct layout assumptions
- Platform-specific code

### 4. CFFI

Looks for:
- `from cffi import FFI`
- `ffi.cdef()` declarations
- `ffi.dlopen()` or `ffi.compile()`
- Type definitions in `ffi.cdef()`

Risk factors:
- Type assumptions (integer sizes, pointer semantics)
- Buffer handling (buffer vs. memoryview differences)

### 5. SWIG

Looks for:
- `.i` interface files
- `%module` directives
- `%typemap` type mappings
- `swig_import_helper` functions in generated code

Risk factors:
- SWIG version compatibility with target Py3 version
- Type mapping assumptions
- C API usage in generated wrapper code

### 6. Deprecated C API (Per-Version)

Tracks these deprecated/removed APIs:

**All Py3 versions**:
- `PyCObject` type (removed in 3.2)
- `PyUnicode_READY()` (removed in 3.12)

**Py3.12+**:
- `wstr` field on PyUnicodeObject
- `wstr_length` field
- `tp_print` slot
- Py2-style class (`PyClass_*` functions)

**Py3.13+**:
- Further API removals (check references)

---

## Success Criteria

The skill has succeeded when:

1. All `.c`/`.h` files with `#include <Python.h>` are identified
2. All `.pyx`/`.pxd` Cython files are discovered
3. All `.i` SWIG files are located
4. All `Extension()` definitions in `setup.py`/`setup.cfg` are parsed
5. Deprecated C API calls are flagged with target-version specificity
6. ctypes/CFFI/SWIG usage is inventoried with risk assessment
7. A report is generated recommending target version feasibility
8. Remediation steps are specific (e.g., "Remove `tp_print` slot", "Add `Py_LIMITED_API` guard")

---

## References

- `references/c-api-removed-by-version.md` — Authoritative list of removed C API per version
- `references/limited-api-guide.md` — How to use `Py_LIMITED_API` for version-agnostic code
- `references/cython-py3-migration.md` — Cython-specific migration guidance
- `references/ctypes-cffi-comparison.md` — When to use ctypes vs CFFI
- [Python 3 C API Documentation](https://docs.python.org/3/c-api/)
