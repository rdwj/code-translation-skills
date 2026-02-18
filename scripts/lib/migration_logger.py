#!/usr/bin/env python3
"""
Shared logging module for the py2to3 migration skill suite.

Provides unified logging across all 70+ scripts so that after a migration
you can check which scripts actually ran, when, with what arguments, and
what happened.

Usage in any skill script:
    import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
    from migration_logger import setup_logging, log_execution
    logger = setup_logging(__name__)

    @log_execution
    def main():
        logger.info("Doing work...")

Usage in phase runner scripts:
    import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'lib'))
    from migration_logger import setup_logging, log_execution, log_invocation
    logger = setup_logging(__name__)
"""

import functools
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

_LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)-5s | %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
_AUDIT_LOG_NAME = "migration-audit.log"
_INVOCATIONS_LOG_NAME = "skill-invocations.jsonl"

# Module-level state
_initialized_loggers = {}
_log_dir = None


# ── Log Directory Discovery ──────────────────────────────────────────────────

def _find_log_dir():
    """Find or create the migration-analysis/logs/ directory.

    Search strategy:
    1. MIGRATION_LOG_DIR env var (explicit override)
    2. Walk up from CWD looking for migration-analysis/
    3. Walk up from the script being run looking for migration-analysis/
    4. Fall back to None (stderr-only logging)
    """
    global _log_dir
    if _log_dir is not None:
        return _log_dir

    # 1. Explicit env var
    env_dir = os.environ.get("MIGRATION_LOG_DIR")
    if env_dir:
        log_path = Path(env_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        _log_dir = log_path
        return _log_dir

    # 2. Walk up from CWD
    candidate = _search_up(Path.cwd())
    if candidate:
        _log_dir = candidate
        return _log_dir

    # 3. Walk up from the main script being run
    if sys.argv and sys.argv[0]:
        script_path = Path(sys.argv[0]).resolve().parent
        candidate = _search_up(script_path)
        if candidate:
            _log_dir = candidate
            return _log_dir

    # 4. No migration-analysis found — return None
    return None


def _search_up(start_path):
    """Walk up from start_path looking for migration-analysis/ directory."""
    current = start_path.resolve()
    for _ in range(10):  # max 10 levels up
        candidate = current / "migration-analysis" / "logs"
        if candidate.parent.exists():
            candidate.mkdir(exist_ok=True)
            return candidate
        if current == current.parent:
            break
        current = current.parent
    return None


# ── Logger Setup ─────────────────────────────────────────────────────────────

def setup_logging(script_name, log_dir=None, level=logging.INFO):
    """Set up logging for a script. Returns a configured logger.

    Args:
        script_name: Name for this logger (typically __name__ or script filename)
        log_dir: Optional explicit log directory. If None, auto-discovers.
        level: Logging level (default: INFO)

    Returns:
        logging.Logger configured with file + stderr handlers
    """
    # Clean up the script name for readability
    if script_name == "__main__":
        script_name = Path(sys.argv[0]).stem if sys.argv else "unknown"

    # Return cached logger if already set up
    if script_name in _initialized_loggers:
        return _initialized_loggers[script_name]

    logger = logging.getLogger(script_name)
    logger.setLevel(level)

    # Avoid duplicate handlers if logger already exists
    if logger.handlers:
        _initialized_loggers[script_name] = logger
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    # stderr handler — WARNING and above only (don't flood the LLM agent)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    # File handler — all levels, to the central audit log
    resolved_dir = Path(log_dir) if log_dir else _find_log_dir()
    if resolved_dir:
        try:
            resolved_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                resolved_dir / _AUDIT_LOG_NAME, mode="a", encoding="utf-8"
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (OSError, PermissionError):
            # Can't write to log dir — stderr only
            pass

    _initialized_loggers[script_name] = logger
    return logger


# ── Execution Decorator ──────────────────────────────────────────────────────

def log_execution(func):
    """Decorator for a script's main() function. Logs start, end, and duration.

    Usage:
        @log_execution
        def main():
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        script_name = Path(sys.argv[0]).stem if sys.argv else "unknown"
        logger = setup_logging(script_name)

        start_time = time.monotonic()
        start_ts = datetime.now(timezone.utc).isoformat()

        logger.info(f"START | args={sys.argv[1:]} cwd={os.getcwd()}")

        exit_code = 0
        try:
            result = func(*args, **kwargs)
            # If main() returns an int, treat it as exit code
            if isinstance(result, int):
                exit_code = result
            return result
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
            raise
        except Exception as e:
            exit_code = 2
            logger.error(f"EXCEPTION | {type(e).__name__}: {e}")
            raise
        finally:
            duration = time.monotonic() - start_time
            logger.info(f"END   | exit={exit_code} duration={duration:.1f}s")

    return wrapper


# ── Invocation Logger (for phase runners) ────────────────────────────────────

def log_invocation(script_path, args, returncode, duration,
                   stdout_size=0, stderr_size=0, log_dir=None):
    """Log a script invocation to the JSONL audit file.

    Called by phase runner scripts after each subprocess.run() call.

    Args:
        script_path: Path to the script that was invoked
        args: List of arguments passed to the script
        returncode: Process exit code
        duration: Execution duration in seconds
        stdout_size: Size of captured stdout in bytes
        stderr_size: Size of captured stderr in bytes
        log_dir: Optional explicit log directory
    """
    resolved_dir = Path(log_dir) if log_dir else _find_log_dir()
    if not resolved_dir:
        return  # No log directory available

    script_path = Path(script_path)

    # Infer skill name from path: skills/<skill-name>/scripts/<script>.py
    skill_name = "unknown"
    parts = script_path.resolve().parts
    if "skills" in parts:
        idx = parts.index("skills")
        if idx + 1 < len(parts):
            skill_name = parts[idx + 1]
    elif "runners" in parts:
        skill_name = "runner"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": script_path.name,
        "skill": skill_name,
        "args": [str(a) for a in args],
        "exit_code": returncode,
        "duration_s": round(duration, 2),
        "stdout_bytes": stdout_size,
        "stderr_bytes": stderr_size,
    }

    try:
        resolved_dir.mkdir(parents=True, exist_ok=True)
        with open(resolved_dir / _INVOCATIONS_LOG_NAME, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except (OSError, PermissionError):
        pass  # Best-effort — don't crash the runner
