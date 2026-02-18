#!/usr/bin/env python3
"""
CI Dual-Interpreter Configurator — Report Generator

Reads ci-setup-report.json and produces a human-readable Markdown report
describing what CI system was detected, what was generated, and how to use
the dual-interpreter setup.

Usage:
    python3 generate_ci_report.py <ci-setup-report.json> --output <report.md>
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON from file."""
    with open(path, 'r') as f:
        return json.load(f)


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


def generate_report(report_data: Dict[str, Any]) -> str:
    """Generate Markdown report from ci-setup-report.json."""

    ci_system = report_data.get("ci_system_detected", "unknown")
    target_py3 = report_data.get("target_python3_version", "3.9")
    py2_version = report_data.get("python2_version", "2.7")
    coverage = report_data.get("coverage_enabled", False)
    allow_py3_fail = report_data.get("allow_py3_failures", True)
    gen_files = report_data.get("generated_files", {})
    config = report_data.get("configuration", {})
    next_steps = report_data.get("next_steps", [])

    # Start building the report
    lines = []
    lines.append("# CI Dual-Interpreter Setup Report")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"This report documents the CI configuration generated for dual-interpreter")
    lines.append(f"testing (Python {py2_version} and Python {target_py3} side-by-side).")
    lines.append("")

    # Detection section
    lines.append("## Detection Results")
    lines.append("")
    if ci_system == "github":
        lines.append("**CI System Detected:** GitHub Actions")
        lines.append("")
        lines.append("Your project uses GitHub Actions for CI. A new workflow file has been")
        lines.append("generated that adds a test matrix for both Python 2.7 and Python 3.X.")
    elif ci_system == "gitlab":
        lines.append("**CI System Detected:** GitLab CI")
        lines.append("")
        lines.append("Your project uses GitLab CI. The configuration has been updated to run")
        lines.append("parallel jobs for both Python versions.")
    elif ci_system == "travis":
        lines.append("**CI System Detected:** Travis CI")
        lines.append("")
        lines.append("Your project uses Travis CI. The configuration has been updated to test")
        lines.append("both Python versions.")
    elif ci_system == "circle":
        lines.append("**CI System Detected:** CircleCI")
        lines.append("")
        lines.append("Your project uses CircleCI. The configuration has been updated with separate")
        lines.append("jobs for each Python version.")
    elif ci_system == "jenkins":
        lines.append("**CI System Detected:** Jenkins")
        lines.append("")
        lines.append("Your project uses Jenkins. Jenkinsfile configuration has been updated.")
    else:
        lines.append("**CI System Detected:** None")
        lines.append("")
        lines.append("No CI system detected. Use `tox` for local testing and configure your")
        lines.append("preferred CI system manually.")
    lines.append("")

    # Configuration summary
    lines.append("## Configuration Summary")
    lines.append("")
    lines.append("| Setting | Value |")
    lines.append("|---------|-------|")
    lines.append(f"| Python 2 Version | {py2_version} |")
    lines.append(f"| Python 3 Target | {target_py3} |")
    lines.append(f"| Coverage Reporting | {'Enabled' if coverage else 'Disabled'} |")
    lines.append(f"| Allow Python 3 Failures | {'Yes (informational)' if allow_py3_fail else 'No (blocking)'} |")
    if "test_envs" in config:
        lines.append(f"| Test Environments | {', '.join(config['test_envs'])} |")
    if "test_command" in config:
        lines.append(f"| Test Command | `{config['test_command']}` |")
    lines.append("")

    # Generated files
    lines.append("## Generated Files")
    lines.append("")
    if gen_files:
        for name, path in gen_files.items():
            lines.append(f"- **{path}**: ")
            if "tox" in name:
                lines.append(f"  Local dual-interpreter testing configuration. Add to your")
                lines.append(f"  repository so team members can test both versions locally.")
            elif "pytest" in name:
                lines.append(f"  Pytest configuration with test discovery settings.")
            elif "ci_config" in name or "config" in name:
                lines.append(f"  CI system configuration for the detected system.")
            else:
                lines.append(f"  Configuration file")
            lines.append("")
    lines.append("")

    # Setup instructions
    lines.append("## Setup Instructions")
    lines.append("")
    lines.append("### Step 1: Review Generated Files")
    lines.append("")
    lines.append("All generated files are in the output directory. Review them carefully:")
    lines.append("")
    if gen_files.get("tox_ini"):
        lines.append(f"```bash")
        lines.append(f"cat {gen_files.get('tox_ini', 'tox.ini')}")
        lines.append(f"```")
    lines.append("")

    lines.append("### Step 2: Test Locally")
    lines.append("")
    lines.append("Before pushing to CI, test locally using tox:")
    lines.append("")
    lines.append(f"```bash")
    lines.append(f"# Install tox if not already installed")
    lines.append(f"pip install tox")
    lines.append(f"")
    lines.append(f"# Test on Python {py2_version}")
    lines.append(f"tox -e py{py2_version.replace('.', '')}")
    lines.append(f"")
    lines.append(f"# Test on Python {target_py3}")
    lines.append(f"tox -e py{target_py3.replace('.', '')}")
    lines.append(f"")
    lines.append(f"# Test on all configured environments")
    lines.append(f"tox")
    lines.append(f"```")
    lines.append("")

    if ci_system == "github":
        lines.append("### Step 3: Copy GitHub Actions Workflow")
        lines.append("")
        lines.append("```bash")
        lines.append("mkdir -p .github/workflows")
        lines.append("cp python-matrix.yml .github/workflows/python-matrix.yml")
        lines.append("```")
        lines.append("")
    elif ci_system == "gitlab":
        lines.append("### Step 3: Update GitLab CI Config")
        lines.append("")
        lines.append("The generated `.gitlab-ci.yml` can be merged with your existing config.")
        lines.append("")
    elif ci_system == "travis":
        lines.append("### Step 3: Update Travis Configuration")
        lines.append("")
        lines.append("```bash")
        lines.append("cp .travis.yml ./.travis.yml")
        lines.append("```")
        lines.append("")
    elif ci_system == "circle":
        lines.append("### Step 3: Update CircleCI Configuration")
        lines.append("")
        lines.append("```bash")
        lines.append("mkdir -p .circleci")
        lines.append("cp config.yml .circleci/config.yml")
        lines.append("```")
        lines.append("")

    lines.append("### Step 4: Commit Configuration Files")
    lines.append("")
    lines.append("```bash")
    lines.append("git add tox.ini pytest.ini")
    if ci_system == "github":
        lines.append("git add .github/workflows/python-matrix.yml")
    elif ci_system == "gitlab":
        lines.append("git add .gitlab-ci.yml")
    elif ci_system == "travis":
        lines.append("git add .travis.yml")
    elif ci_system == "circle":
        lines.append("git add .circleci/config.yml")
    lines.append("git commit -m 'Configure dual-interpreter CI (Python 2.7 and 3.X)'")
    lines.append("git push")
    lines.append("```")
    lines.append("")

    lines.append("### Step 5: Verify CI Pipeline")
    lines.append("")
    lines.append("After pushing, verify that:")
    lines.append("")
    lines.append(f"1. The CI pipeline triggers automatically")
    if ci_system == "github":
        lines.append(f"2. Check the 'Actions' tab in GitHub for the workflow run")
    elif ci_system == "gitlab":
        lines.append(f"2. Check the 'CI/CD' > 'Pipelines' in GitLab")
    elif ci_system == "travis":
        lines.append(f"2. Check the build status on travis-ci.com")
    elif ci_system == "circle":
        lines.append(f"2. Check the 'Pipelines' page in CircleCI")
    lines.append(f"3. Verify that tests run on both Python {py2_version} and Python {target_py3}")
    if allow_py3_fail:
        lines.append(f"4. Verify that Python {py2_version} failures block the build")
        lines.append(f"5. Verify that Python {target_py3} failures are informational (don't block)")
    else:
        lines.append(f"4. Verify that both Python versions must pass")
    lines.append("")

    # Testing strategy
    lines.append("## Testing Strategy")
    lines.append("")
    lines.append("The generated configuration uses the following strategy:")
    lines.append("")
    lines.append(f"1. **Python {py2_version} (Legacy)**: Tests MUST PASS. This is your baseline.")
    lines.append("")
    if allow_py3_fail:
        lines.append(f"2. **Python {target_py3} (Target)**: Tests are informational during migration.")
        lines.append(f"   Failures do not block the build. As migration progresses, move Python {target_py3}")
        lines.append(f"   to a blocking status.")
    else:
        lines.append(f"2. **Python {target_py3} (Target)**: Tests MUST PASS. Requires immediate fixes.")
    lines.append("")
    lines.append("### Progression")
    lines.append("")
    lines.append("As your migration progresses:")
    lines.append("")
    lines.append(f"- **Phase 1 (Initial)**: {py2_version} passes, {target_py3} may have failures (informational)")
    lines.append(f"- **Phase 2 (Mid-migration)**: Both {py2_version} and {target_py3} pass on most modules")
    lines.append(f"- **Phase 3 (Late)**: {target_py3} passing is required, {py2_version} can fail")
    lines.append(f"- **Phase 4 (Final)**: Only {target_py3} is tested, {py2_version} removed")
    lines.append("")

    # Coverage reporting
    if coverage:
        lines.append("## Coverage Reporting")
        lines.append("")
        lines.append(f"Coverage reporting is enabled and configured to run on Python {target_py3}.")
        lines.append("")
        lines.append("Coverage data is generated from the latest Python 3 version only (to avoid")
        lines.append("duplication and keep CI times reasonable).")
        lines.append("")
    lines.append("")

    # Environment details
    lines.append("## Environment Details")
    lines.append("")
    lines.append(f"Test environments configured: {', '.join(config.get('test_envs', []))}")
    lines.append("")
    lines.append("Each environment is isolated with its own virtualenv and dependencies.")
    lines.append("")

    # Next steps
    if next_steps:
        lines.append("## Next Steps")
        lines.append("")
        for i, step in enumerate(next_steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    # Important notes
    lines.append("## Important Notes")
    lines.append("")
    lines.append("### Python 2.7 is Deprecated")
    lines.append("")
    lines.append("GitHub Actions, GitLab CI, and other CI platforms are deprecating Python 2.7 support.")
    lines.append("The generated configurations use Ubuntu 20.04 (last version with Python 2.7 support)")
    lines.append("for GitHub Actions. Other CI systems may require configuration adjustments.")
    lines.append("")

    lines.append("### Keep tox.ini Committed")
    lines.append("")
    lines.append("Always commit `tox.ini` and `pytest.ini` to your repository. These files enable")
    lines.append("developers to test both versions locally without relying on CI.")
    lines.append("")

    lines.append("### Customize as Needed")
    lines.append("")
    lines.append("The generated configurations are templates. Customize them for your project:")
    lines.append("")
    lines.append("- Add project-specific test commands")
    lines.append("- Configure matrix exclusions (e.g., skip Python 2.7 on certain platforms)")
    lines.append("- Integrate with your existing linting, formatting, or deployment steps")
    lines.append("- Connect to coverage services (Codecov, Coveralls, etc.)")
    lines.append("")

    lines.append("### Test on Both Versions Locally First")
    lines.append("")
    lines.append("Don't rely on CI to catch dual-version issues. Run `tox` locally on each developer")
    lines.append("machine before pushing. This catches problems early and reduces CI cycle time.")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"Report generated: {datetime.now().isoformat()}")
    lines.append("")
    lines.append("For more information, see the CI Dual-Interpreter Configurator skill documentation.")

    return "\n".join(lines)


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate Markdown report from CI setup JSON"
    )
    parser.add_argument(
        "report_json",
        help="Path to ci-setup-report.json"
    )
    parser.add_argument(
        "--output",
        default="ci-setup-report.md",
        help="Output Markdown file (default: ci-setup-report.md)"
    )

    args = parser.parse_args()

    # Validate input
    if not Path(args.report_json).exists():
        print(f"Error: file not found: {args.report_json}", file=sys.stderr)
        sys.exit(1)

    try:
        # Load JSON
        report_data = load_json(args.report_json)

        # Generate report
        report = generate_report(report_data)

        # Write report
        write_file(args.output, report)

        print(f"Report generated: {args.output}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
