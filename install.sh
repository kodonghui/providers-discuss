#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install.sh [--prefix DIR] [--codex-home DIR] [--dry-run] [--uninstall]

Installs the local providers-discuss command and Codex skill for the current user.
Default prefix: $HOME/.local
Default Codex home: $CODEX_HOME, or $HOME/.codex when CODEX_HOME is unset

This installer only creates or removes local command and skill links. It does
not touch provider homes, OAuth files, Claude hooks, browser settings, cron,
daemons, or global system directories.
EOF
}

prefix="${HOME}/.local"
codex_home="${CODEX_HOME:-${HOME}/.codex}"
dry_run=0
uninstall=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      prefix="${2:?missing value for --prefix}"
      shift 2
      ;;
    --codex-home)
      codex_home="${2:?missing value for --codex-home}"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --uninstall)
      uninstall=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bin_dir="${prefix}/bin"
target="${bin_dir}/providers-discuss"
source_cmd="${repo_root}/bin/providers-discuss"
skill_source="${repo_root}/skills/providers-discuss"
skill_dir="${codex_home}/skills"
skill_target="${skill_dir}/providers-discuss"

if [ "$uninstall" -eq 1 ]; then
  if [ "$dry_run" -eq 1 ]; then
    echo "would remove ${target}"
    echo "would remove ${skill_target} when it links to ${skill_source}"
  else
    rm -f "${target}"
    if [ -L "${skill_target}" ] && [ "$(readlink "${skill_target}")" = "${skill_source}" ]; then
      rm -f "${skill_target}"
      echo "removed ${skill_target}"
    elif [ -e "${skill_target}" ]; then
      echo "left existing ${skill_target}; it is not this installer's link" >&2
    fi
    echo "removed ${target}"
  fi
  exit 0
fi

if [ ! -x "${source_cmd}" ]; then
  echo "missing executable source: ${source_cmd}" >&2
  exit 1
fi

if [ ! -f "${skill_source}/SKILL.md" ]; then
  echo "missing Codex skill source: ${skill_source}/SKILL.md" >&2
  exit 1
fi

if [ -e "${skill_target}" ] && [ ! -L "${skill_target}" ]; then
  echo "refusing to overwrite non-symlink Codex skill: ${skill_target}" >&2
  exit 1
fi

if [ -L "${skill_target}" ]; then
  current_skill_target="$(readlink "${skill_target}")"
  if [ "${current_skill_target}" != "${skill_source}" ]; then
    echo "refusing to replace Codex skill link ${skill_target} -> ${current_skill_target}" >&2
    exit 1
  fi
fi

if [ "$dry_run" -eq 1 ]; then
  echo "would create ${bin_dir}"
  echo "would link ${target} -> ${source_cmd}"
  echo "would create ${skill_dir}"
  echo "would link ${skill_target} -> ${skill_source}"
  exit 0
fi

mkdir -p "${bin_dir}"
ln -sfn "${source_cmd}" "${target}"
mkdir -p "${skill_dir}"
ln -sfn "${skill_source}" "${skill_target}"
echo "installed ${target}"
echo "installed ${skill_target}"
echo "Run: ${target} --help"
echo "Restart Codex to load the providers-discuss skill."
