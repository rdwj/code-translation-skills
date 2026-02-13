---
name: py2to3-automated-converter
description: >
  Apply automated syntax transformations to convert a single conversion unit (group of
  modules that must migrate together) from Python 2 to Python 3. Use this skill whenever
  you need to perform the actual mechanical code conversion, apply lib2to3 fixers and
  custom AST transformations, generate reviewable diffs of all changes, track what was
  converted and what failed, or produce a conversion report with per-file details. Also
  trigger when someone says "convert this module," "apply the conversion plan," "do the
  mechanical migration," "generate a diff of the changes," "show me what needs to convert,"
  or "run the automatic converter." This is where the actual transformation happens — the
  mechanical equivalent of running 2to3 at scale, but with better tooling, error handling,
  target-version awareness, and reviewability.
---

# Automated Converter

The conversion unit planner (Skill 2.1) tells you what to convert and in what order. This
skill does the actual conversion: it applies lib2to3 fixers, custom AST-based transformations,
produces a unified diff for review, generates a detailed conversion report, and provides
exit codes so orchestration can detect success vs. failure.

This is the main mechanical conversion engine. It's not semantic analysis (that's Phase 3).
It's pure syntax transformation: print statements → print(), xrange → range, except comma →
except-as, old-style string types, relative imports, etc.

## When to Use

- After the conversion unit planner has produced a conversion plan
- For each conversion unit in the plan (in order)
- When you need a reviewable diff before applying changes
- When you need to understand what transformations were applied and why
- When you need to track which files succeeded and which failed
- When you need to integrate with CI/CD to validate the converted code

## Inputs

The user (or orchestration) provides:

| Input | Type | Purpose |
|-------|------|---------|
| **codebase_path** | path | Root directory of the Python 2 codebase |
| **modules** | list of paths | Individual module files to convert (or `--unit <name>` to use conversion plan) |
| **target_version** | string | Target Python 3 version: `3.9`, `3.11`, `3.12`, or `3.13` |
| **--unit** | string | Conversion unit name from conversion-plan.json (resolves to module list automatically) |
| **--output** | path | Output directory for converted files (default: same as source) |
| **--dry-run** | flag | Show what would change without modifying files |
| **--state-file** | path | Path to migration-state.json (for tracking progress) |
| **--conversion-plan** | path | Path to conversion-plan.json from Skill 2.1 (for unit resolution) |

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `conversion-report.json` | JSON | Machine-readable conversion results (files, transforms, errors) |
| `conversion-report.md` | Markdown | Human-readable summary with per-file breakdown |
| `conversion-diff.patch` | Unified diff | Reviewable patch file of all changes |
| `conversion-state.json` | JSON | Updated migration state with unit status |

## Workflow

### Step 1: Dry-Run to Review Changes

Always start with `--dry-run` to see what would change:

```bash
python3 scripts/convert.py \
    --codebase /path/to/codebase \
    --unit "utils-common" \
    --conversion-plan <analysis_dir>/conversion-plan.json \
    --target-version 3.12 \
    --dry-run
```

This outputs:
- `conversion-diff.patch` showing all changes
- `conversion-report.json` with what would be converted
- No files are actually modified

### Step 2: Review the Diff

Open `conversion-diff.patch` and review the changes. Look for:
- Unexpected transformations
- Manual fixes that will be needed (marked with `# TODO: MANUAL` in the diff)
- Files that shouldn't be converted (remove from module list if needed)

### Step 3: Run the Conversion

Once you approve the diff, run without `--dry-run`:

```bash
python3 scripts/convert.py \
    --codebase /path/to/codebase \
    --unit "utils-common" \
    --conversion-plan <analysis_dir>/conversion-plan.json \
    --target-version 3.12 \
    --output <converted_dir>
```

This creates backups of original files and writes converted versions.

### Step 4: Generate the Report

Generate a human-readable markdown report:

```bash
python3 scripts/generate_conversion_report.py \
    <output_dir>/conversion-report.json \
    --output <output_dir>/conversion-report.md \
    --unit-name "utils-common"
```

### Step 5: Validate

Run tests and static analysis on the converted code:

```bash
python3 -m pytest <converted_dir>
python3 -m pylint <converted_dir>
```

## Transformation Categories

The converter applies transformations in this order:

### 1. Syntax Transformations (lib2to3)

These are handled by the lib2to3 refactoring framework:

- **Print statement → function**: `print x` → `print(x)`
- **Except syntax**: `except Exception, e:` → `except Exception as e:`
- **Integer types**: `123L` → `123`, `xrange()` → `range()`
- **String prefixes**: `u'string'` → `'string'`
- **Operators**: `<>` → `!=`
- **Metaclass syntax**: Old metaclass syntax → New `metaclass=` parameter
- **Dictionary methods**: `.iteritems()` → `.items()`
- **Raise syntax**: `raise Exception, args` → `raise Exception(args)`
- **Relative imports**: `import foo` (relative) → `from . import foo` (absolute)
- **Old-style classes**: Inherit from `object` explicitly
- **String methods**: `.basestring` → `.str`, etc.

### 2. Custom AST Transformations

Patterns that lib2to3 misses or handles incorrectly:

- **`dict.has_key()`**: `d.has_key(k)` → `k in d`
- **`dict.keys() as list`**: `list(d.keys())` → `d.keys()` (in Python 3, it's a view)
- **`unicode()` builtin**: `unicode(x)` → `str(x)`
- **`raw_input()` builtin**: `raw_input()` → `input()`
- **`long` type**: `long(x)` → `int(x)`
- **Backtick repr**: `` `x` `` → `repr(x)`
- **Octal literals**: `0777` → `0o777`
- **String type checks**: `isinstance(x, basestring)` → `isinstance(x, str)` (with fallback for Py2/3 compat)
- **Open with encoding**: Flag `open()` without `encoding=` parameter for review (needs context-aware fix)
- **`reduce()` function**: `reduce(f, lst)` → `functools.reduce(f, lst)` (imports automatically)

### 3. Target Version-Aware Transformations

Different Python 3.x versions removed or deprecated different things:

| All Versions | 3.12+ | 3.13+ |
|--------------|-------|-------|
| Print statement | Remove `distutils` | |
| Except comma | Flag stdlib removals | |
| String types | `setuptools` migration | |
| Dictionary iterators | | |

**3.12+ transformations:**
- Flag/transform `distutils` imports → `setuptools`
- Flag removed stdlib modules (`aifc`, `audioop`, `chunk`, `cgi`, `cgitb`, `crypt`, `imaplib`, `mailcap`, `nis`, `nntplib`, `ossaudiodev`, `pipes`, `smtpd`, `spwd`, `sunau`, `telnetlib`, `uu`, `xdrlib`)

**3.13+ transformations:**
- (As they're defined)

## Integration with Other Skills

### Inputs From:

- **Skill 2.1 (Conversion Unit Planner)**: `conversion-plan.json` to resolve unit names to module lists
- **Skill 0.1 (Codebase Analyzer)**: Dependency graph and migration-order (optional, for context)
- **Orchestration (Migration State Tracker)**: `migration-state.json` for progress tracking

### Outputs To:

- **Skill 3.X (Semantic Validator)**: Converted files for deeper analysis
- **Orchestration (Migration State Tracker)**: Updated unit status and file-level results
- **CI/CD pipeline**: Exit codes, conversion report, and diff for automation

## Important Considerations

### 1. Backups and Safety

- Original files are always backed up (`.py.bak` extension) before conversion
- Backups are stored in the same directory as originals
- Use `--output` to write converted files to a separate directory without modifying originals

### 2. Dry-Run is Your Friend

**Always run `--dry-run` first.** The diff is your chance to:
- Catch unexpected transformations
- Review for context-specific issues (e.g., encoding on `open()`)
- Identify files that need manual fixes before running the full conversion

### 3. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All modules converted successfully |
| 1 | One or more modules failed to convert (see conversion-report.json for details) |
| 2 | Nothing to convert (module list empty or all files already converted) |

### 4. lib2to3 Limitations

lib2to3 is powerful but not perfect. Known limitations:

- **Context-blind**: Can't tell if `open()` is for text or binary, so can't add `encoding=`
- **Relative imports**: Converts `import foo` to `from . import foo`, but this is sometimes wrong in test files
- **Unicode/bytes confusion**: Can't automatically convert `b'string'` literals or `.encode()` chains
- **Complex metaclass patterns**: Edge cases in metaclass transformation may fail
- **Comments and formatting**: Tries to preserve formatting, but may corrupt comments near transformed code

These limitations are why manual review (Step 2 above) is essential.

### 5. Custom Transforms Have Priorities

If both lib2to3 and a custom transform would apply to the same code, the custom transform
takes priority (custom transforms run second, after lib2to3).

### 6. Migration State Tracking

If `--state-file` is provided, the converter writes back:

```json
{
  "units": {
    "utils-common": {
      "status": "converted",
      "files_converted": 5,
      "timestamp": "ISO-8601",
      "errors": []
    }
  }
}
```

This allows orchestration to track which units are done, in progress, or failed.

### 7. Encoding and Newlines

- Source files are read as UTF-8 (with fallback to latin-1)
- Output files preserve the original encoding
- Newlines are normalized to `\n` (Unix-style) during conversion, then normalized to match original style on output
- Files with encoding declarations (`# -*- coding: utf-8 -*-`) preserve them

## Troubleshooting

### "Nothing to convert"

The module list is empty. Check:
- Is the unit name correct in the conversion plan?
- Do the module files exist?
- Were they already converted in a previous run?

### "Conversion failed for X files"

Check `conversion-report.json` for the specific errors. Common causes:

- **Syntax error in original file**: The source file has Python 2 syntax that breaks parsing
  - Fix: Run tests on the original file first to confirm it's valid Python 2
- **lib2to3 crash**: A specific pattern triggered a bug in lib2to3
  - Fix: Open a ticket with the pattern. As a workaround, exclude that file and convert manually
- **AST parsing failure**: The file has non-standard encoding or binary content mixed in
  - Fix: Ensure it's a pure Python source file

### Unexpected Transformations

If the diff shows a transformation you don't want:

- For lib2to3 issues: Edit the file manually before conversion
- For custom transforms: File a ticket describing the pattern and desired behavior
- Use `--dry-run` to iterate and review before committing to changes

## Examples

### Convert a Single Unit

```bash
python3 scripts/convert.py \
    --codebase /home/user/legacy_py2_project \
    --unit "data-models" \
    --conversion-plan migration-analysis/conversion-plan.json \
    --target-version 3.12 \
    --dry-run
```

Review the diff, then:

```bash
python3 scripts/convert.py \
    --codebase /home/user/legacy_py2_project \
    --unit "data-models" \
    --conversion-plan migration-analysis/conversion-plan.json \
    --target-version 3.12
```

### Convert Multiple Files

```bash
python3 scripts/convert.py \
    --codebase /home/user/legacy_py2_project \
    --modules src/utils/common.py src/utils/helpers.py \
    --target-version 3.11 \
    --output /tmp/converted
```

### Batch Convert All Units in a Plan

```bash
for unit in $(jq -r '.waves[].units[].name' conversion-plan.json); do
    python3 scripts/convert.py \
        --codebase /home/user/legacy_py2_project \
        --unit "$unit" \
        --conversion-plan migration-analysis/conversion-plan.json \
        --target-version 3.12
    if [ $? -ne 0 ]; then
        echo "Conversion of $unit failed"
        break
    fi
done
```

