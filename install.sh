#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install.sh [--prefix DIR] [--dry-run] [--uninstall]

Installs the local providers-discuss command for the current user.
Default prefix: $HOME/.local

This installer only creates or removes a command link/copy. It does not touch
provider homes, OAuth files, Claude hooks, browser settings, cron, daemons, or
global system directories.
EOF
}

prefix="${HOME}/.local"
dry_run=0
uninstall=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      prefix="${2:?missing value for --prefix}"
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

if [ "$uninstall" -eq 1 ]; then
  if [ "$dry_run" -eq 1 ]; then
    echo "would remove ${target}"
  else
    rm -f "${target}"
    echo "removed ${target}"
  fi
  exit 0
fi

if [ ! -x "${source_cmd}" ]; then
  echo "missing executable source: ${source_cmd}" >&2
  exit 1
fi

if [ "$dry_run" -eq 1 ]; then
  echo "would create ${bin_dir}"
  echo "would link ${target} -> ${source_cmd}"
  exit 0
fi

mkdir -p "${bin_dir}"
ln -sfn "${source_cmd}" "${target}"
echo "installed ${target}"
echo "Run: ${target} --help"
