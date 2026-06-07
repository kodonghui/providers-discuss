from __future__ import annotations

import codecs
import os
import shutil
from pathlib import Path
from typing import Any

from .artifacts import SOURCE_INDEX_SCHEMA, sha256_file, write_json


SOURCE_MANIFEST_SCHEMA = "providers-discuss.source-manifest.v1"
INPUT_PACK_SCHEMA = "providers-discuss.input-pack.v1"
DEFAULT_MAX_FILE_BYTES = 64 * 1024
DEFAULT_EXCERPT_LINES = 12
SNIFF_BYTES = 4096

SKIP_DIR_NAMES = {
    ".cache",
    ".claude",
    ".codex",
    ".gemini",
    ".git",
    ".kdh",
    ".mypy_cache",
    ".omo",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "_bmad-output",
    "input-pack",
    "node_modules",
    "venv",
}

SECRET_FILE_NAMES = {
    ".bash_history",
    ".env",
    ".env.local",
    ".envrc",
    ".python_history",
    ".zsh_history",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "known_hosts",
    "service-account.json",
}

SECRET_NAME_PARTS = (
    "cookie",
    "credential",
    "oauth",
    "private_key",
    "provider-config",
    "secret",
    "shell_history",
    "token",
)

TEXT_EXTENSIONS = {
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".py",
    ".rst",
    ".text",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def source_dirs_from_config(config: dict[str, Any], *, config_path: Path | None = None) -> list[Path]:
    input_cfg = config.get("input") if isinstance(config.get("input"), dict) else {}
    raw_dirs = input_cfg.get("source_dirs") if isinstance(input_cfg, dict) else None
    if not isinstance(raw_dirs, list):
        return []
    base = config_path.parent if config_path else Path.cwd()
    dirs: list[Path] = []
    for item in raw_dirs:
        text = str(item).strip()
        if not text:
            continue
        path = Path(text)
        dirs.append(path if path.is_absolute() else base / path)
    return dirs


def build_input_pack(
    *,
    source_dirs: list[Path],
    output_dir: Path,
    objective: str = "",
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    excerpt_lines: int = DEFAULT_EXCERPT_LINES,
) -> dict[str, Any]:
    if max_file_bytes < 1:
        raise ValueError("max_file_bytes must be positive")
    if excerpt_lines < 1:
        raise ValueError("excerpt_lines must be positive")
    roots = _resolve_source_dirs(source_dirs)
    rows = scan_source_dirs(source_dirs=roots, max_file_bytes=max_file_bytes, excerpt_lines=excerpt_lines)
    included = [row for row in rows if row["included"]]
    omitted = [row for row in rows if not row["included"]]
    manifest = {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "generated_at": "not-recorded-for-determinism",
        "source_dirs": [str(item) for item in roots],
        "max_file_bytes": max_file_bytes,
        "excerpt_lines": excerpt_lines,
        "files": rows,
        "excluded": omitted,
        "counts": {
            "total": len(rows),
            "included": len(included),
            "omitted": len(omitted),
        },
    }
    source_index = {
        "schema": SOURCE_INDEX_SCHEMA,
        "sources": [
            {
                "source_id": row["source_id"],
                "path": row["path"],
                "source_dir": row["source_dir"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
                "line_count": row["line_count"],
                "kind": row["kind"],
                "summary": row["summary"],
                "excerpt": row["excerpt"],
            }
            for row in included
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "source-manifest.json"
    index_path = output_dir / "source-index.json"
    pack_path = output_dir / "input-pack.md"
    write_json(manifest_path, manifest)
    write_json(index_path, source_index)
    pack_path.write_text(
        render_input_pack_markdown(objective=objective, source_dirs=roots, included=included, omitted=omitted),
        encoding="utf-8",
    )
    return {
        "schema": INPUT_PACK_SCHEMA,
        "status": "pass",
        "output_dir": str(output_dir),
        "source_manifest_path": str(manifest_path),
        "source_index_path": str(index_path),
        "input_pack_path": str(pack_path),
        "source_count": len(included),
        "omitted_count": len(omitted),
        "source_manifest": manifest,
        "source_index": source_index,
    }


def scan_source_dirs(*, source_dirs: list[Path], max_file_bytes: int, excerpt_lines: int) -> list[dict[str, Any]]:
    # Kept for keyword-only callers in future code; delegates to the positional helper.
    return _scan_source_dirs(source_dirs, max_file_bytes=max_file_bytes, excerpt_lines=excerpt_lines)


def _scan_source_dirs(source_dirs: list[Path], *, max_file_bytes: int, excerpt_lines: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidates: list[tuple[Path, Path]] = []
    for root in source_dirs:
        candidates.extend((root, path) for path in _iter_files(root))
    candidates.sort(key=lambda item: (str(item[0]), _rel_posix(item[1], item[0])))
    source_seq = 1
    for root, path in candidates:
        row = _inspect_file(root=root, path=path, source_seq=source_seq, max_file_bytes=max_file_bytes, excerpt_lines=excerpt_lines)
        source_seq += 1
        rows.append(row)
    return rows


def render_input_pack_markdown(*, objective: str, source_dirs: list[Path], included: list[dict[str, Any]], omitted: list[dict[str, Any]]) -> str:
    lines = [
        "# providers-discuss Input Pack",
        "",
        "This pack is a deterministic convenience projection. Raw source files plus SHA-256 hashes are authoritative.",
        "",
        "## Objective",
        "",
        objective.strip() or "(not supplied)",
        "",
        "## Source Directories",
        "",
    ]
    for root in source_dirs:
        lines.append(f"- `{root}`")
    lines.extend(
        [
            "",
            "## Source Table",
            "",
            "| source_id | path | size_bytes | sha256 |",
            "|---|---|---:|---|",
        ]
    )
    if included:
        for row in included:
            lines.append(f"| `{row['source_id']}` | `{row['path']}` | {row['size_bytes']} | `{row['sha256']}` |")
    else:
        lines.append("| none | none | 0 | none |")
    lines.extend(["", "## Source Excerpts", ""])
    for row in included:
        lines.extend(
            [
                f"### {row['source_id']} - {row['path']}",
                "",
                f"- kind: `{row['kind']}`",
                f"- line_count: `{row['line_count']}`",
                f"- summary: {row['summary']}",
                "",
                "```text",
                row["excerpt"],
                "```",
                "",
            ]
        )
    lines.extend(["## Omitted Files", ""])
    if omitted:
        lines.extend(["| path | reason |", "|---|---|"])
        for row in omitted:
            lines.append(f"| `{row['path']}` | `{row['omitted_reason']}` |")
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def attach_input_pack_to_run(*, output_payload: dict[str, Any], run_root: Path, run_id: str, append_event: Any, write_artifact_hash: Any) -> dict[str, Any]:
    if not run_root.exists():
        raise ValueError(f"run missing: {run_root}")
    inputs_dir = run_root / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    source_index_src = Path(output_payload["source_index_path"])
    source_manifest_src = Path(output_payload["source_manifest_path"])
    input_pack_src = Path(output_payload["input_pack_path"])
    attached = {
        "config/source-index.json": run_root / "config" / "source-index.json",
        "inputs/source-manifest.json": inputs_dir / "source-manifest.json",
        "inputs/input-pack.md": inputs_dir / "input-pack.md",
    }
    _copy_if_different(source_index_src, attached["config/source-index.json"])
    _copy_if_different(source_manifest_src, attached["inputs/source-manifest.json"])
    _copy_if_different(input_pack_src, attached["inputs/input-pack.md"])
    refs = list(attached)
    hashes = {rel: write_artifact_hash(run_root, rel) for rel in refs}
    append_event(
        run_root,
        "input_pack.built",
        run_id=run_id,
        refs=refs,
        source_count=output_payload["source_count"],
        omitted_count=output_payload["omitted_count"],
    )
    return {
        "attached": True,
        "run_root": str(run_root),
        "refs": refs,
        "hashes": hashes,
    }


def _resolve_source_dirs(source_dirs: list[Path]) -> list[Path]:
    if not source_dirs:
        raise ValueError("no source dirs supplied")
    resolved: list[Path] = []
    for item in source_dirs:
        path = item.expanduser().resolve()
        if not path.exists():
            raise ValueError(f"source dir missing: {item}")
        if not path.is_dir():
            raise ValueError(f"source path is not a directory: {item}")
        if _skip_dir(path.name):
            raise ValueError(f"source dir is unsafe/generated: {item}")
        if path not in resolved:
            resolved.append(path)
    if not resolved:
        raise ValueError("no source dirs supplied")
    return resolved


def _copy_if_different(src: Path, dest: Path) -> None:
    if src.resolve() == dest.resolve():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, dirs, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(name for name in dirs if not _skip_dir(name))
        for name in sorted(filenames):
            files.append(current_path / name)
    return files


def _inspect_file(*, root: Path, path: Path, source_seq: int, max_file_bytes: int, excerpt_lines: int) -> dict[str, Any]:
    rel_path = _rel_posix(path, root)
    base = {
        "source_id": f"SRC-{source_seq:04d}",
        "path": rel_path,
        "absolute_path": str(path.resolve()),
        "source_dir": str(root),
        "sha256": "",
        "size_bytes": 0,
        "line_count": 0,
        "kind": "unknown",
        "included": False,
        "omitted_reason": "",
        "summary": "",
        "excerpt": "",
    }
    resolved = path.resolve()
    if not _is_relative_to(resolved, root):
        return {**base, "omitted_reason": "unsafe_path_outside_source_dir"}
    if _secret_like(path):
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        return {**base, "size_bytes": size, "kind": "secret_like", "omitted_reason": "secret_like_path"}
    try:
        size = path.stat().st_size
    except OSError:
        return {**base, "omitted_reason": "stat_failed"}
    if size > max_file_bytes:
        return {**base, "size_bytes": size, "kind": _kind_for_path(path), "omitted_reason": "oversized_file"}
    sniff = _read_prefix(path)
    if _looks_binary(sniff):
        return {**base, "size_bytes": size, "kind": "binary", "omitted_reason": "binary_file"}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    excerpt = "\n".join(lines[:excerpt_lines]).strip()
    return {
        **base,
        "sha256": sha256_file(path),
        "size_bytes": size,
        "line_count": len(lines),
        "kind": _kind_for_path(path),
        "included": True,
        "summary": _summary_for_text(path, lines),
        "excerpt": excerpt,
    }


def _summary_for_text(path: Path, lines: list[str]) -> str:
    headings = [line.strip("# ").strip() for line in lines if line.lstrip().startswith("#") and line.strip("# ").strip()]
    if headings:
        return f"{path.name}; headings: {', '.join(headings[:3])}"
    for line in lines:
        clean = line.strip()
        if clean:
            return f"{path.name}; first line: {clean[:120]}"
    return f"{path.name}; empty text file"


def _kind_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".json":
        return "application/json"
    if suffix == ".jsonl":
        return "application/jsonl"
    if suffix in {".yaml", ".yml"}:
        return "text/yaml"
    if suffix in TEXT_EXTENSIONS or not suffix:
        return "text/plain"
    return f"text/{suffix.lstrip('.')}" if suffix else "text/plain"


def _read_prefix(path: Path) -> bytes:
    with path.open("rb") as fh:
        return fh.read(SNIFF_BYTES)


def _looks_binary(data: bytes) -> bool:
    if b"\x00" in data:
        return True
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        decoder.decode(data, final=False)
    except UnicodeDecodeError:
        return True
    return False


def _skip_dir(name: str) -> bool:
    return name.lower() in SKIP_DIR_NAMES


def _secret_like(path: Path) -> bool:
    name = path.name.lower()
    if name in SECRET_FILE_NAMES:
        return True
    if name.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    return any(part in name for part in SECRET_NAME_PARTS)


def _rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
