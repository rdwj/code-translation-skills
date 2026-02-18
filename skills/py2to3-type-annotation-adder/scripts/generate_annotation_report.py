#!/usr/bin/env python3
"""
Annotation Report Generator: Creates markdown report from typing-report.json

Reads JSON output from add_annotations.py and generates a comprehensive markdown report
with coverage metrics, annotation sources, confidence breakdowns, mypy configuration,
and unannotated items requiring manual work.

Usage:
    python3 generate_annotation_report.py --report typing-report.json --output report.md
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

def load_json(filepath: str) -> Dict[str, Any]:
    """Load JSON from file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: Failed to load {filepath}: {e}", file=sys.stderr)
        return {}


def generate_markdown_report(report_data: Dict[str, Any]) -> str:
    """Generate comprehensive markdown report."""

    lines = []

    # Header
    lines.append("# Type Annotation Report\n")
    lines.append(f"**Generated**: {report_data.get('timestamp', 'unknown')}")
    lines.append(f"**Codebase**: {report_data.get('codebase_path', 'unknown')}")
    lines.append(f"**Target Version**: Python {report_data.get('target_version', 'unknown')}")
    lines.append(f"**Mode**: {'Dry-run (no modifications)' if report_data.get('dry_run') else 'Annotations applied'}\n")

    # Coverage Summary
    coverage = report_data.get('coverage', {})
    total = coverage.get('total_functions', 0)
    annotated = coverage.get('annotated_functions', 0)
    pct = coverage.get('coverage_percent', 0)

    lines.append("## Coverage Summary\n")
    lines.append(f"**Functions with return type hints**: {annotated}/{total} ({pct:.1f}%)\n")

    # Confidence breakdown
    lines.append("### Annotation Confidence\n")
    lines.append(f"- **High confidence** (explicit docstring/literal): {coverage.get('high_confidence', 0)}")
    lines.append(f"- **Medium confidence** (inferred from usage): {coverage.get('medium_confidence', 0)}")
    lines.append(f"- **Low confidence** (heuristics, suggestion only): {coverage.get('low_confidence', 0)}\n")

    # Files analyzed
    lines.append(f"**Files analyzed**: {report_data.get('files_analyzed', 0)}\n")

    # Detailed findings
    analyses = report_data.get('analyses', [])
    if analyses:
        lines.append("## Analyzed Functions\n")

        for analysis in analyses:
            filepath = analysis.get('filepath', 'unknown')
            functions = analysis.get('functions', [])

            if not functions:
                continue

            lines.append(f"### {filepath}\n")

            for func in functions:
                name = func.get('name', 'unknown')
                return_type = func.get('return_type')
                confidence = func.get('return_confidence', 'low')
                params = func.get('parameters', [])

                # Function signature
                param_strs = []
                for param in params:
                    pname = param.get('name', 'arg')
                    ptype = param.get('type')
                    if ptype:
                        param_strs.append(f"{pname}: {ptype}")
                    else:
                        param_strs.append(pname)

                param_sig = ', '.join(param_strs)
                return_sig = f" -> {return_type}" if return_type else ""

                lines.append(f"**{name}**({param_sig}){return_sig}")
                if confidence != 'high':
                    lines.append(f"- Confidence: {confidence}")
                lines.append()

    # Type Syntax Guidance
    target_version = report_data.get('target_version', '3.9')
    lines.append("## Type Annotation Syntax Guide\n")

    if target_version >= '3.9':
        lines.append("""### Python 3.9+ Modern Syntax

Use built-in collection types directly (PEP 585):

```python
def process_items(items: list[str]) -> dict[str, int]:
    return {item: len(item) for item in items}
```

**Before** (compatible with older Python):
```python
from typing import List, Dict
def process_items(items: List[str]) -> Dict[str, int]: ...
```

**After** (Python 3.9+):
```python
def process_items(items: list[str]) -> dict[str, int]: ...
```

""")

    if target_version >= '3.10':
        lines.append("""### Python 3.10+ Union Syntax

Use `|` operator for unions (PEP 604):

```python
def process(value: int | str) -> None: ...

def optional_value() -> str | None:
    return None
```

**Before** (compatible with older Python):
```python
from typing import Union, Optional
def process(value: Union[int, str]) -> None: ...
def optional_value() -> Optional[str]: ...
```

**After** (Python 3.10+):
```python
def process(value: int | str) -> None: ...
def optional_value() -> str | None: ...
```

""")

    # Mypy Configuration
    lines.append("## Mypy Configuration\n")
    lines.append("""
A `py.typed` marker file has been created. You should also configure mypy:

### Using pyproject.toml

```toml
[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false  # Set to true for strict mode
disallow_incomplete_defs = false
check_untyped_defs = true
no_implicit_optional = true
warn_unused_ignores = true
```

### Or using mypy.ini

```ini
[mypy]
python_version = 3.9
warn_return_any = True
warn_unused_configs = True
check_untyped_defs = True
no_implicit_optional = True
warn_unused_ignores = True
```

### Running mypy

```bash
# Check your code
mypy src/

# Generate report
mypy src/ --html reports/mypy

# Strict mode (requires all annotations)
mypy src/ --disallow-untyped-defs
```

""")

    # Common Type Patterns
    lines.append("## Common Type Patterns\n")
    lines.append("""
### Collections and Generics

```python
from typing import Iterable, Sequence, Mapping

def process_list(items: list[str]) -> None: ...
def process_tuple(coords: tuple[int, int]) -> None: ...
def process_dict(mapping: dict[str, int]) -> None: ...
def process_iterable(items: Iterable[str]) -> None: ...
```

### Optional and Union Types

```python
from typing import Optional

def get_value(key: str) -> str | None: ...  # Python 3.10+
def get_value(key: str) -> Optional[str]: ...  # Older Python

def convert(value: int | str) -> float: ...  # Python 3.10+
from typing import Union
def convert(value: Union[int, str]) -> float: ...  # Older Python
```

### Any and TypeVar

```python
from typing import Any, TypeVar

T = TypeVar('T')

def identity(x: T) -> T:
    return x

def flexible(x: Any) -> Any:
    return x
```

### Callable

```python
from typing import Callable

def register_handler(func: Callable[[str], int]) -> None: ...
```

""")

    # Next Steps
    lines.append("## Next Steps\n")
    lines.append("""
1. **Review annotations** in the JSON report (`typing-report.json`)
2. **Add missing annotations** for functions marked as low-confidence
3. **Update imports** - Add `from __future__ import annotations` for forward references (if needed)
4. **Run mypy** to validate all type hints:
   ```bash
   mypy src/ --strict
   ```
5. **Resolve any type errors** reported by mypy
6. **Update dependencies** - Ensure mypy and stubs are in requirements-dev.txt:
   ```
   mypy>=1.0
   types-requests
   types-urllib3
   ```
7. **Integrate into CI/CD** - Add mypy check to your test pipeline

""")

    # Unannotated Items
    unannotated = []
    for analysis in analyses:
        for func in analysis.get('functions', []):
            if not func.get('return_type'):
                unannotated.append({
                    'file': analysis.get('filepath', 'unknown'),
                    'function': func.get('name', 'unknown'),
                    'lineno': func.get('lineno', 0),
                })

    if unannotated:
        lines.append(f"## Remaining Work ({len(unannotated)} functions)\n")
        lines.append("These functions require manual annotation:\n")

        # Group by file
        by_file = {}
        for item in unannotated:
            fname = item['file']
            if fname not in by_file:
                by_file[fname] = []
            by_file[fname].append(item)

        for fname, items in by_file.items():
            lines.append(f"### {fname}\n")
            for item in items:
                lines.append(f"- Line {item['lineno']}: `{item['function']}`")
            lines.append()

    return '\n'.join(lines)


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description='Generate markdown report from typing-report.json'
    )
    parser.add_argument(
        '--report',
        required=True,
        help='Path to typing-report.json'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output markdown file path'
    )

    args = parser.parse_args()

    # Load report
    report_data = load_json(args.report)
    if not report_data:
        print("Error: Could not load report data", file=sys.stderr)
        return 1

    # Generate markdown
    markdown = generate_markdown_report(report_data)

    # Write output
    try:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(markdown)
        print(f"Report written to {args.output}", file=sys.stderr)
    except Exception as e:
        print(f"Error writing report: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
