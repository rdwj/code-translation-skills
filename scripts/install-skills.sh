#!/usr/bin/env bash
#
# Install py2to3 migration skills into a project's .claude/skills/ directory.
#
# Usage:
#   ./scripts/install-skills.sh                     # install to ~/.claude/skills/
#   ./scripts/install-skills.sh /path/to/project    # install to project's .claude/skills/
#   ./scripts/install-skills.sh --list              # list available skills
#   ./scripts/install-skills.sh --skill py2to3-codebase-analyzer  # install one skill
#
# Options:
#   --list              List available skills and exit
#   --skill NAME        Install a single skill (repeatable)
#   --dry-run           Show what would be copied without copying
#   --force             Overwrite existing skills without prompting
#   -h, --help          Show this help message

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILLS_SRC="$REPO_ROOT/skills"

# Defaults
TARGET=""
DRY_RUN=false
FORCE=false
SELECTED_SKILLS=()
LIST_ONLY=false

usage() {
    sed -n '3,16p' "$0" | sed 's/^# \?//'
    exit 0
}

die() {
    echo "error: $1" >&2
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)    usage ;;
        --list)       LIST_ONLY=true; shift ;;
        --dry-run)    DRY_RUN=true; shift ;;
        --force)      FORCE=true; shift ;;
        --skill)
            [[ -n "${2:-}" ]] || die "--skill requires a skill name"
            SELECTED_SKILLS+=("$2"); shift 2 ;;
        --skill=*)
            SELECTED_SKILLS+=("${1#--skill=}"); shift ;;
        -*)
            die "unknown option: $1" ;;
        *)
            [[ -z "$TARGET" ]] || die "unexpected argument: $1"
            TARGET="$1"; shift ;;
    esac
done

# Verify source directory
[[ -d "$SKILLS_SRC" ]] || die "skills directory not found at $SKILLS_SRC"

# Collect available skills
available_skills=()
while IFS= read -r dir; do
    available_skills+=("$(basename "$dir")")
done < <(find "$SKILLS_SRC" -mindepth 1 -maxdepth 1 -type d | sort)

[[ ${#available_skills[@]} -gt 0 ]] || die "no skills found in $SKILLS_SRC"

# --list mode
if $LIST_ONLY; then
    echo "Available skills (${#available_skills[@]}):"
    echo ""
    for skill in "${available_skills[@]}"; do
        # YAML descriptions may be inline or multiline (using > or |).
        # For multiline, grab the indented line after "description:".
        desc=$(awk '/^description:/{
            sub(/^description: *>? */, "");
            if (length($0) > 1 && $0 != ">") { print; exit }
            getline; sub(/^ +/, ""); print; exit
        }' "$SKILLS_SRC/$skill/SKILL.md" 2>/dev/null)
        printf "  %-45s %s\n" "$skill" "${desc:0:70}"
    done
    exit 0
fi

# Determine target directory
if [[ -z "$TARGET" ]]; then
    TARGET_DIR="$HOME/.claude/skills"
else
    TARGET_DIR="$TARGET/.claude/skills"
fi

# Determine which skills to install
if [[ ${#SELECTED_SKILLS[@]} -gt 0 ]]; then
    install_skills=()
    for skill in "${SELECTED_SKILLS[@]}"; do
        if [[ -d "$SKILLS_SRC/$skill" ]]; then
            install_skills+=("$skill")
        else
            die "skill not found: $skill (run with --list to see available skills)"
        fi
    done
else
    install_skills=("${available_skills[@]}")
fi

# Summary
echo "py2to3 Migration Skill Suite — Installer"
echo ""
echo "  Source:  $SKILLS_SRC"
echo "  Target:  $TARGET_DIR"
echo "  Skills:  ${#install_skills[@]} of ${#available_skills[@]}"
$DRY_RUN && echo "  Mode:    DRY RUN"
echo ""

# Check for existing skills
existing=()
if [[ -d "$TARGET_DIR" ]]; then
    for skill in "${install_skills[@]}"; do
        [[ -d "$TARGET_DIR/$skill" ]] && existing+=("$skill")
    done
fi

if [[ ${#existing[@]} -gt 0 ]] && ! $FORCE && ! $DRY_RUN; then
    echo "The following ${#existing[@]} skill(s) already exist in the target:"
    for skill in "${existing[@]}"; do
        echo "  $skill"
    done
    echo ""
    read -rp "Overwrite? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy] ]] || { echo "Aborted."; exit 1; }
    echo ""
fi

# Install
if ! $DRY_RUN; then
    mkdir -p "$TARGET_DIR"
fi

installed=0
skipped=0
for skill in "${install_skills[@]}"; do
    if $DRY_RUN; then
        echo "  would copy: $skill"
    else
        cp -r "$SKILLS_SRC/$skill" "$TARGET_DIR/"
        echo "  installed:  $skill"
    fi
    installed=$((installed + 1))
done

echo ""
if $DRY_RUN; then
    echo "Dry run complete. $installed skill(s) would be installed."
else
    echo "Done. $installed skill(s) installed to $TARGET_DIR"
fi
