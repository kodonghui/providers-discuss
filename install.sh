#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install.sh [--prefix DIR] [--codex-home DIR] [--with-public-alias] [--dry-run] [--uninstall]

Installs the local providers-discuss command and Codex skill for the current user.
Default prefix: $HOME/.local
Default Codex home: $CODEX_HOME, or $HOME/.codex when CODEX_HOME is unset

This installer only creates or removes local command and skill links. By
default it installs only the canonical `kdh-providers-discuss` skill. Use
`--with-public-alias` to also install the shorter `providers-discuss` alias.
It does not touch provider homes, OAuth files, Claude hooks, browser settings,
cron, daemons, or global system directories.
EOF
}

prefix="${HOME}/.local"
codex_home="${CODEX_HOME:-${HOME}/.codex}"
dry_run=0
uninstall=0
with_public_alias=0

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
    --with-public-alias)
      with_public_alias=1
      shift
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
skill_dir="${codex_home}/skills"
skill_names=(kdh-providers-discuss)
all_managed_skill_names=(providers-discuss kdh-providers-discuss)
if [ "${with_public_alias}" -eq 1 ]; then
  skill_names+=(providers-discuss)
fi

check_skill_target() {
  local name="$1"
  local source="${repo_root}/skills/${name}"
  local target="${skill_dir}/${name}"

  if [ ! -f "${source}/SKILL.md" ]; then
    echo "missing Codex skill source: ${source}/SKILL.md" >&2
    exit 1
  fi

  if [ -e "${target}" ] && [ ! -L "${target}" ]; then
    echo "refusing to overwrite non-symlink Codex skill: ${target}" >&2
    exit 1
  fi

  if [ -L "${target}" ]; then
    local current_skill_target
    current_skill_target="$(readlink "${target}")"
    if [ "${current_skill_target}" != "${source}" ]; then
      echo "refusing to replace Codex skill link ${target} -> ${current_skill_target}" >&2
      exit 1
    fi
  fi
}

link_skill() {
  local name="$1"
  local source="${repo_root}/skills/${name}"
  local target="${skill_dir}/${name}"
  ln -sfn "${source}" "${target}"
  echo "installed ${target}"
}

remove_skill() {
  local name="$1"
  local source="${repo_root}/skills/${name}"
  local target="${skill_dir}/${name}"

  if [ -L "${target}" ] && [ "$(readlink "${target}")" = "${source}" ]; then
    rm -f "${target}"
    echo "removed ${target}"
  elif [ -e "${target}" ]; then
    echo "left existing ${target}; it is not this installer's link" >&2
  fi
}

if [ "$uninstall" -eq 1 ]; then
  if [ "$dry_run" -eq 1 ]; then
    echo "would remove ${target}"
    for skill_name in "${all_managed_skill_names[@]}"; do
      echo "would remove ${skill_dir}/${skill_name} when it links to ${repo_root}/skills/${skill_name}"
    done
  else
    rm -f "${target}"
    for skill_name in "${all_managed_skill_names[@]}"; do
      remove_skill "${skill_name}"
    done
    echo "removed ${target}"
  fi
  exit 0
fi

if [ ! -x "${source_cmd}" ]; then
  echo "missing executable source: ${source_cmd}" >&2
  exit 1
fi

for skill_name in "${skill_names[@]}"; do
  check_skill_target "${skill_name}"
done

if [ "$dry_run" -eq 1 ]; then
  echo "would create ${bin_dir}"
  echo "would link ${target} -> ${source_cmd}"
  echo "would create ${skill_dir}"
  for skill_name in "${skill_names[@]}"; do
    echo "would link ${skill_dir}/${skill_name} -> ${repo_root}/skills/${skill_name}"
  done
  exit 0
fi

mkdir -p "${bin_dir}"
ln -sfn "${source_cmd}" "${target}"
mkdir -p "${skill_dir}"
for skill_name in "${skill_names[@]}"; do
  link_skill "${skill_name}"
done
echo "installed ${target}"
echo "Run: ${target} --help"
if [ "${with_public_alias}" -eq 1 ]; then
  echo "Restart Codex to load the providers-discuss and kdh-providers-discuss skills."
else
  echo "Restart Codex to load the kdh-providers-discuss skill."
fi
