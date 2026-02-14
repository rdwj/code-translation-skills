---
name: py2to3-type-annotation-adder
description: >
  Python 2→3 type annotation adder. Adds type annotations to Python code using AST analysis, docstring inference, and API knowledge. Targets function signatures, returns, variables. Version-aware for 3.9+ (list[str]) and 3.10+ (X|Y unions).
---

# Type Annotation Adder (Skill 3.4)

## Overview

This skill performs AST-based type inference on converted Python code to add comprehensive type annotations. It analyzes function bodies, docstrings, variable assignments, and standard library API knowledge to infer types with confidence scoring. Annotations are only applied at high/medium confidence; low-confidence inferences are flagged as suggestions.

**Key responsibility**: Bridge the gap from Python 2→3 mechanical conversion to semantically type-hinted code, generating mypy-compatible type hints and configuration.

## Inputs

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| codebase_path | string | yes | Root directory of Python project to analyze |
| target_version | string | yes | Target Python version (3.9, 3.10, 3.11, 3.12, 3.13) |
| modules | string | no | Comma-separated module patterns to annotate (e.g., 'src/,lib/') or 'all' |
| bytes_str_report | string | no | Path to bytes_str_boundary.json from Skill 3.1 (refines bytes vs str inference) |
| strict | boolean | no | Annotate all functions vs only public interfaces (default: false = public only) |
| dry_run | boolean | no | Preview annotations without modifying files (default: false) |
| output_dir | string | no | Directory for JSON report outputs (default: codebase root) |

## Outputs

| Output | Type | Description |
|--------|------|-------------|
| modified_files | list[string] | Python files modified with annotations (or would be in dry-run) |
| typing-report.json | file | Detailed annotation findings: coverage metrics, per-function confidence scores, suggestions |
| py.typed | file | PEP 561 marker file (indicates package has inline type hints) |
| mypy.ini or pyproject.toml [tool.mypy] | file | Generated or updated mypy configuration for the target version |
| typing-report.md | file | Markdown report with coverage breakdown, unannotated items, mypy guidance |
| exit_status | int | 0 = success, 1 = analysis errors, 2 = write errors |

## Workflow Steps

1. **Scan codebase** for Python modules matching --modules filter

2. **Parse AST** for each module to extract:
   - Function definitions (name, parameters, return statements, docstring)
   - Variable assignments with literal values (e.g., `x = 42`)
   - Class definitions and instance variables
   - Import statements (to track type aliases)

3. **Infer parameter types** from:
   - Default values: `def f(x=0)` → `x: int`
   - Docstring type hints (Google, NumPy, Sphinx formats)
   - Variable usage patterns (assignments, comparisons)

4. **Infer return types** from:
   - Explicit docstring `:return:` or `Returns:` annotations
   - Literal return statements: `return True` → `bool`, `return []` → `list`
   - Constructor calls: `return MyClass()` → `MyClass`
   - Standard library APIs (json.loads → Any, socket.recv → bytes, etc.)
   - bytes/str boundary report (if available) for precise bytes vs str typing

5. **Infer variable types** for non-obvious names:
   - `count` variables → int (if assigned from numeric operations)
   - Loop variables from iteration source
   - Assignment chains (track flow from initialization)

6. **Confidence scoring**:
   - **High**: Explicit in docstring, literal value match, stdlib API
   - **Medium**: Inferred from usage, docstring partial match
   - **Low**: Variable name heuristics (only suggest, don't apply)

7. **Version-aware typing**:
   - Python 3.9+: Use `list[str]` instead of `List[str]` (PEP 585)
   - Python 3.10+: Use `X | Y` instead of `Union[X, Y]` (PEP 604)
   - Generate appropriate imports and type aliases for earlier versions

8. **Scope filtering** (if --strict=false):
   - Only annotate public functions (not leading underscore)
   - Annotate class __init__ and public methods

9. **Update/create mypy configuration** (mypy.ini or pyproject.toml):
   - Set python_version to target
   - Configure check_untyped_defs, warn_unused_ignores, etc.

10. **Generate py.typed marker** (PEP 561) in package root

## References

- [PEP 484: Type hints](https://www.python.org/dev/peps/pep-0484/)
- [PEP 585: Type hinting generics in collections (3.9+)](https://www.python.org/dev/peps/pep-0585/)
- [PEP 604: Union as X | Y (3.10+)](https://www.python.org/dev/peps/pep-0604/)
- [PEP 561: Distributing type information](https://www.python.org/dev/peps/pep-0561/)
- [Google Python docstring style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
- [NumPy docstring style](https://numpydoc.readthedocs.io/en/latest/format.html)
- [mypy documentation](https://mypy.readthedocs.io/)
- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution

## Success Criteria

- All public functions have parameter and return type hints at high/medium confidence
- Type hints use modern syntax appropriate to target_version (list[str] for 3.9+, X|Y for 3.10+)
- py.typed marker file created in package root
- mypy configuration generated/updated for target Python version
- Coverage metrics report accurate percentages of annotated functions
- Low-confidence suggestions clearly separated in JSON and markdown reports
- Dry-run mode produces accurate preview without modifying files
- Markdown report includes mypy command examples and common patterns
