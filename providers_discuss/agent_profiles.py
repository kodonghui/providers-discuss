from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


AGENT_PROFILE_SCHEMA = "kdh.providers-discuss.agent-profile.v1"
AGENT_PROFILE_CATALOG_SCHEMA = "kdh.providers-discuss.agent-profile-catalog.v1"
DEFAULT_AGENT_PROFILE_PRESET = "balanced-kdh"
DEFAULT_AGENT_PROFILE_PRESETS = {
    "balanced-kdh": {
        "description": "General-purpose KDH discussion default: divergent ideas, research, architecture, and verification.",
        "seat_profiles": {
            "codex_exec_file": "kdh-system-architect",
            "claude_k": "kdh-code-reviewer",
            "claude_k_team_agents": None,
            "gemini_cli": "kdh-ideation-catalyst",
            "manual": "kdh-technical-writer",
        },
        "team_agents_roles": [
            {"name": "Ideation Catalyst", "agent_profile_id": "kdh-ideation-catalyst"},
            {"name": "Research Synthesizer", "agent_profile_id": "kdh-research-synthesizer"},
            {"name": "System Architect", "agent_profile_id": "kdh-system-architect"},
            {"name": "QA Verifier", "agent_profile_id": "kdh-qa-verifier"},
        ],
    }
}

TRANSPORT_PROFILE_TARGET = {
    "manual": "manual_import",
    "codex_exec_file": "codex_exec_file",
    "claude_k": "claude_code",
    "claude_k_team_agents": "claude_team_agents",
    "gemini_cli": "gemini_cli",
}

FORBIDDEN_CATALOG_PARTS = {
    ".claude",
    ".codex",
    ".git",
    "node_modules",
}


def load_agent_profiles(catalogs: list[dict[str, Any]], *, config_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load profiles from explicitly configured catalog files.

    The loader is intentionally file-only and read-only. It does not execute
    third-party framework code and it does not recursively discover catalogs.
    """

    profiles: dict[str, dict[str, Any]] = {}
    for catalog in catalogs:
        if not isinstance(catalog, dict) or catalog.get("enabled", True) is False:
            continue
        path = _resolve_catalog_path(catalog, config_path=config_path)
        loaded = _load_catalog_file(path=path, catalog=catalog)
        for profile in loaded:
            profile_id = profile["profile_id"]
            if profile_id in profiles:
                raise ValueError(f"duplicate agent profile id: {profile_id}")
            profiles[profile_id] = profile
    return profiles


def catalog_entries_from_paths(paths: list[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, path in enumerate(paths, start=1):
        entries.append(
            {
                "id": path.stem or f"catalog-{index}",
                "type": "explicit_agent_catalog",
                "path": str(path),
                "enabled": True,
                "required": True,
            }
        )
    return entries


def agent_profile_report(
    *,
    catalogs: list[dict[str, Any]],
    config_path: Path | None = None,
    transport: str = "",
    seat_id: str = "",
) -> dict[str, Any]:
    profiles = load_agent_profiles(catalogs, config_path=config_path)
    rows = [
        clean_agent_profile_summary(profile, transport=transport)
        for profile in sorted(profiles.values(), key=lambda item: str(item.get("profile_id") or ""))
    ]
    return {
        "schema": "kdh.providers-discuss.agent-profile-report.v1",
        "status": "pass",
        "config_path": str(config_path or ""),
        "seat_id": seat_id,
        "transport": transport,
        "catalog_count": len([catalog for catalog in catalogs if isinstance(catalog, dict) and catalog.get("enabled", True) is not False]),
        "profile_count": len(rows),
        "profiles": rows,
    }


def clean_agent_profile_summary(profile: dict[str, Any], *, transport: str = "") -> dict[str, Any]:
    return {
        "id": str(profile.get("profile_id") or ""),
        "name": str(profile.get("name") or ""),
        "description": str(profile.get("description") or ""),
        "provider_targets": list(profile.get("provider_targets") or []),
        "team_agents_role_fit": str(profile.get("team_agents_role_fit") or ""),
        "source_profile_count": len(profile.get("source_profile_ids") or []),
        "catalog_id": str(profile.get("catalog_id") or ""),
        "catalog_ref": str(profile.get("source_ref") or ""),
        "compatibility": profile_compatibility(profile, transport=transport),
    }


def profile_compatibility(profile: dict[str, Any], *, transport: str = "") -> dict[str, Any]:
    targets = set(profile.get("provider_targets") or [])
    if not transport:
        return {"checked": False, "compatible": None, "reason": "no transport filter supplied"}
    if not targets or "*" in targets or "all" in targets:
        return {"checked": True, "transport": transport, "compatible": True, "reason": "profile has no restrictive provider_targets"}
    target = TRANSPORT_PROFILE_TARGET.get(transport, transport)
    compatible = target in targets or transport in targets
    return {
        "checked": True,
        "transport": transport,
        "target": target,
        "compatible": compatible,
        "reason": "compatible" if compatible else f"profile targets {sorted(targets)}, not {transport}",
    }


def agent_profile_report_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Agent Profiles",
        "",
        f"- schema: `{payload['schema']}`",
        f"- status: `{payload['status']}`",
        f"- config_path: `{payload.get('config_path', '')}`",
        f"- seat_id: `{payload.get('seat_id', '')}`",
        f"- transport: `{payload.get('transport', '')}`",
        f"- catalog_count: `{payload.get('catalog_count', 0)}`",
        f"- profile_count: `{payload.get('profile_count', 0)}`",
        "",
        "| id | name | targets | team fit | source count | compatible | description |",
        "|---|---|---|---|---:|---|---|",
    ]
    for profile in payload.get("profiles", []):
        compatibility = profile.get("compatibility") if isinstance(profile.get("compatibility"), dict) else {}
        compatible = compatibility.get("compatible")
        compatible_label = "not checked" if compatible is None else ("yes" if compatible else "no")
        lines.append(
            "| `{id}` | {name} | `{targets}` | `{fit}` | {count} | `{compatible}` | {description} |".format(
                id=_md_cell(profile.get("id", "")),
                name=_md_cell(profile.get("name", "")),
                targets=_md_cell(", ".join(profile.get("provider_targets") or []) or "unspecified"),
                fit=_md_cell(profile.get("team_agents_role_fit", "")),
                count=int(profile.get("source_profile_count", 0) or 0),
                compatible=_md_cell(compatible_label),
                description=_md_cell(profile.get("description", "")),
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def apply_agent_profiles_to_seats(
    seats: list[dict[str, Any]],
    catalogs: list[dict[str, Any]] | None,
    *,
    config_path: Path | None = None,
    defaults: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    defaults_enabled = _agent_profile_defaults_enabled(defaults)
    profile_ids = _assigned_profile_ids(seats)
    if not catalogs:
        if profile_ids or defaults_enabled:
            raise ValueError("agent_profile_id requires at least one enabled agent_catalogs entry")
        return seats

    profiles = load_agent_profiles(catalogs, config_path=config_path)
    if defaults_enabled:
        _apply_agent_profile_defaults(seats, defaults=defaults)
    for seat in seats:
        profile_id = str(seat.get("agent_profile_id") or "").strip()
        if profile_id:
            profile = _require_profile(profiles, profile_id)
            _ensure_profile_compatible(profile=profile, seat=seat)
            seat["agent_profile"] = profile
        team_agents = seat.get("team_agents")
        if isinstance(team_agents, dict):
            team_agents["roles"] = _roles_with_profiles(
                team_agents.get("roles") or team_agents.get("required_teammates") or [],
                profiles=profiles,
                seat=seat,
            )
            team_agents["required_teammates"] = [role["name"] for role in team_agents["roles"]]
    return seats


def validate_agent_profile_config(data: dict[str, Any], *, config_path: Path | None = None) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    catalogs = data.get("agent_catalogs")
    defaults = data.get("agent_profile_defaults")
    defaults_blockers = _validate_agent_profile_defaults(defaults)
    blockers.extend(defaults_blockers)
    defaults_enabled = _agent_profile_defaults_enabled(defaults) if not defaults_blockers else False
    assigned = _assigned_profile_ids([seat for seat in data.get("seats", []) if isinstance(seat, dict)])
    if catalogs is None:
        if assigned or defaults_enabled:
            blockers.append({"check": "agent_catalogs_required", "reason": "agent_profile_id or enabled agent_profile_defaults requires agent_catalogs"})
        return blockers
    if not isinstance(catalogs, list):
        return [{"check": "agent_catalogs_array", "reason": "agent_catalogs must be an array"}]
    for index, catalog in enumerate(catalogs, start=1):
        if not isinstance(catalog, dict):
            blockers.append({"check": f"agent_catalog_{index}_object", "reason": "agent catalog entries must be objects"})
            continue
        if catalog.get("enabled", True) is False:
            continue
        if not str(catalog.get("path") or "").strip():
            blockers.append({"check": f"agent_catalog_{index}_path", "reason": "enabled agent catalog requires path"})
    if blockers or config_path is None:
        return blockers
    try:
        seats = [deepcopy(seat) for seat in data.get("seats", []) if isinstance(seat, dict)]
        apply_agent_profiles_to_seats(seats, catalogs, config_path=config_path, defaults=defaults)
    except ValueError as exc:
        blockers.append({"check": "agent_profile_catalogs_load", "reason": str(exc)})
    return blockers


def render_agent_profile_contract(profile: dict[str, Any], *, assigned_to: str = "") -> str:
    lines = [
        "## Agent Profile Contract",
        "",
        "This profile is prompt text only. It grants no tools, credentials, hooks, provider-home access, or filesystem permissions.",
        "",
        f"- assigned_to: `{assigned_to}`",
        f"- profile_id: `{profile.get('profile_id', '')}`",
        f"- name: `{profile.get('name', '')}`",
        f"- catalog_path: `{profile.get('catalog_path', '')}`",
        f"- route_back_ref: `{profile.get('source_ref', '')}`",
        f"- provider_targets: `{', '.join(profile.get('provider_targets') or []) or 'unspecified'}`",
        f"- source_profile_count: `{len(profile.get('source_profile_ids') or [])}`",
        "",
        "### Description",
        "",
        str(profile.get("description") or "").strip(),
        "",
        "### Role Prompt",
        "",
        str(profile.get("role_prompt") or "").strip(),
    ]
    output_contract = str(profile.get("output_contract") or "").strip()
    if output_contract:
        lines.extend(["", "### Output Contract", "", output_contract])
    safety_notes = str(profile.get("safety_notes") or "").strip()
    if safety_notes:
        lines.extend(["", "### Safety Notes", "", safety_notes])
    return "\n".join(lines).rstrip() + "\n"


def team_role_specs(team_agents: dict[str, Any]) -> list[dict[str, Any]]:
    roles = team_agents.get("roles") or team_agents.get("required_teammates") or ["Ideation Catalyst", "Research Synthesizer", "System Architect", "QA Verifier"]
    specs: list[dict[str, Any]] = []
    for role in roles:
        if isinstance(role, dict):
            name = str(role.get("name") or role.get("role") or role.get("agent_profile", {}).get("name") or role.get("agent_profile_id") or "").strip()
            profile = role.get("agent_profile") if isinstance(role.get("agent_profile"), dict) else None
        else:
            name = str(role).strip()
            profile = None
        if not name:
            continue
        specs.append({"name": name, "artifact_label": safe_artifact_label(name), "agent_profile": profile})
    return specs or [{"name": "Ideation Catalyst", "artifact_label": "ideation-catalyst", "agent_profile": None}]


def safe_artifact_label(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip().lower()).strip("-")
    return safe or "role"


def _resolve_catalog_path(catalog: dict[str, Any], *, config_path: Path | None) -> Path:
    raw = str(catalog.get("path") or "").strip()
    if not raw:
        raise ValueError("enabled agent catalog requires path")
    path = Path(raw).expanduser()
    if not path.is_absolute() and config_path is not None:
        path = config_path.parent / path
    resolved = path.resolve()
    if resolved == Path.home().resolve():
        raise ValueError(f"refusing broad home catalog path: {raw}")
    if any(part in FORBIDDEN_CATALOG_PARTS for part in resolved.parts):
        raise ValueError(f"refusing provider/runtime catalog path: {raw}")
    if not resolved.exists():
        raise ValueError(f"agent catalog path missing: {raw}")
    if not resolved.is_file():
        raise ValueError(f"agent catalog path must be an explicit file: {raw}")
    if resolved.suffix.lower() not in {".json", ".md", ".markdown"}:
        raise ValueError(f"unsupported agent catalog file type: {raw}")
    return resolved


def _load_catalog_file(*, path: Path, catalog: dict[str, Any]) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        rows = _json_profile_rows(payload)
    else:
        rows = [_markdown_profile_row(path)]
    return [_normalize_profile(row, path=path, catalog=catalog) for row in rows]


def _json_profile_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("profiles"), list):
        return [row for row in payload["profiles"] if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    raise ValueError("agent catalog JSON root must be an object or array")


def _markdown_profile_row(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            meta = _parse_front_matter(text[4:end])
            body = text[end + 4 :].strip()
    if "name" not in meta:
        heading = next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), "")
        if heading:
            meta["name"] = heading
    meta.setdefault("id", path.stem)
    meta.setdefault("description", _first_paragraph(body))
    meta.setdefault("role_prompt", body.strip())
    return meta


def _parse_front_matter(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if value.startswith("[") and value.endswith("]"):
            data[key] = [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
        elif "," in value and key.endswith("targets"):
            data[key] = [item.strip() for item in value.split(",") if item.strip()]
        else:
            data[key] = value
    return data


def _first_paragraph(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return lines[0] if lines else ""


def _normalize_profile(row: dict[str, Any], *, path: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(row.get("profile_id") or row.get("id") or row.get("kdh_agent_id") or "").strip()
    name = str(row.get("name") or row.get("title") or "").strip()
    description = str(row.get("description") or row.get("summary") or row.get("best_use_cases") or "").strip()
    role_prompt = str(row.get("role_prompt") or row.get("prompt") or "").strip()
    if not profile_id:
        raise ValueError(f"agent profile missing id in {path}")
    if not name:
        raise ValueError(f"agent profile {profile_id} missing name")
    if not role_prompt:
        raise ValueError(f"agent profile {profile_id} missing role_prompt")
    provider_targets = _string_list(row.get("provider_targets"))
    return {
        "schema": AGENT_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "name": name,
        "description": description,
        "role_prompt": role_prompt,
        "output_contract": str(row.get("output_contract") or "").strip(),
        "provider_targets": provider_targets,
        "team_agents_role_fit": str(row.get("team_agents_role_fit") or "").strip(),
        "source_profile_ids": _string_list(row.get("source_profile_ids")),
        "source_repo_paths": _string_list(row.get("source_repo_paths")),
        "catalog_id": str(catalog.get("id") or "").strip(),
        "catalog_type": str(catalog.get("type") or "").strip(),
        "catalog_path": str(path),
        "source_ref": f"{path}#{profile_id}",
        "safety_notes": str(row.get("safety_notes") or "").strip(),
    }


def _assigned_profile_ids(seats: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for seat in seats:
        profile_id = str(seat.get("agent_profile_id") or "").strip()
        if profile_id:
            ids.add(profile_id)
        team_agents = seat.get("team_agents")
        if not isinstance(team_agents, dict):
            continue
        for role in team_agents.get("roles") or team_agents.get("required_teammates") or []:
            if isinstance(role, dict):
                role_profile_id = str(role.get("agent_profile_id") or "").strip()
                if role_profile_id:
                    ids.add(role_profile_id)
    return ids


def _roles_with_profiles(roles: list[Any], *, profiles: dict[str, dict[str, Any]], seat: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for role in roles:
        if isinstance(role, dict):
            profile_id = str(role.get("agent_profile_id") or "").strip()
            profile = _require_profile(profiles, profile_id) if profile_id else None
            if profile is not None:
                _ensure_profile_compatible(profile=profile, seat=seat)
            name = str(role.get("name") or role.get("role") or (profile or {}).get("name") or profile_id).strip()
            item = {"name": name, **({"agent_profile_id": profile_id, "agent_profile": profile} if profile is not None else {})}
        else:
            item = {"name": str(role).strip()}
        if item["name"]:
            normalized.append(item)
    return normalized


def _agent_profile_defaults_enabled(defaults: dict[str, Any] | None) -> bool:
    return isinstance(defaults, dict) and defaults.get("enabled") is True


def _validate_agent_profile_defaults(defaults: Any) -> list[dict[str, str]]:
    if defaults is None:
        return []
    if not isinstance(defaults, dict):
        return [{"check": "agent_profile_defaults_object", "reason": "agent_profile_defaults must be an object"}]
    if defaults.get("enabled") is not True:
        return []
    preset = str(defaults.get("preset") or DEFAULT_AGENT_PROFILE_PRESET).strip()
    if preset not in DEFAULT_AGENT_PROFILE_PRESETS:
        return [{"check": "agent_profile_defaults_preset", "reason": f"unknown agent_profile_defaults preset: {preset}"}]
    return []


def _apply_agent_profile_defaults(seats: list[dict[str, Any]], *, defaults: dict[str, Any] | None) -> None:
    preset_name = str((defaults or {}).get("preset") or DEFAULT_AGENT_PROFILE_PRESET).strip()
    preset = DEFAULT_AGENT_PROFILE_PRESETS[preset_name]
    seat_profiles = preset["seat_profiles"]
    for seat in seats:
        transport = str(seat.get("transport") or "")
        if not str(seat.get("agent_profile_id") or "").strip():
            profile_id = seat_profiles.get(transport)
            if profile_id:
                seat["agent_profile_id"] = profile_id
        if transport == "claude_k_team_agents" and isinstance(seat.get("team_agents"), dict):
            team_agents = seat["team_agents"]
            roles = team_agents.get("roles") or team_agents.get("required_teammates") or []
            if not _roles_have_profile_ids(roles):
                team_agents["roles"] = [dict(role) for role in preset["team_agents_roles"]]
                team_agents["required_teammates"] = [role["name"] for role in team_agents["roles"]]


def _roles_have_profile_ids(roles: list[Any]) -> bool:
    for role in roles:
        if isinstance(role, dict) and str(role.get("agent_profile_id") or "").strip():
            return True
    return False


def _require_profile(profiles: dict[str, dict[str, Any]], profile_id: str) -> dict[str, Any]:
    if not profile_id:
        raise ValueError("agent_profile_id is empty")
    try:
        return profiles[profile_id]
    except KeyError as exc:
        raise ValueError(f"unknown agent_profile_id: {profile_id}") from exc


def _ensure_profile_compatible(*, profile: dict[str, Any], seat: dict[str, Any]) -> None:
    targets = set(profile.get("provider_targets") or [])
    if not targets or "*" in targets or "all" in targets:
        return
    seat_target = TRANSPORT_PROFILE_TARGET.get(str(seat.get("transport") or ""), str(seat.get("transport") or ""))
    if seat_target not in targets and str(seat.get("transport") or "") not in targets:
        raise ValueError(
            "agent profile {profile_id} targets {targets}, not seat {seat_id} transport {transport}".format(
                profile_id=profile.get("profile_id", ""),
                targets=sorted(targets),
                seat_id=seat.get("seat_id", ""),
                transport=seat.get("transport", ""),
            )
        )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("`", "'").strip()
