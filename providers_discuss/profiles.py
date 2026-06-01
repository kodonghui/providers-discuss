from __future__ import annotations

import copy
import math
import re
from pathlib import Path
from typing import Any


DELIVERABLE_PROFILE_SCHEMA = "providers-discuss.deliverable-profile.v1"
FINAL_ARTIFACT_OPEN_RE = re.compile(r"<!--\s*KDH_FINAL_ARTIFACT\s+([^>]*)-->", re.IGNORECASE)
FINAL_ARTIFACT_CLOSE_RE = re.compile(r"<!--\s*/KDH_FINAL_ARTIFACT\s*-->", re.IGNORECASE)
ATTRIBUTE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*\"([^\"]*)\"")


DEVELOPMENT_CONTRACT_SECTIONS = [
    "Requirements Definition",
    "Functional Spec",
    "Non-Goals",
    "Architecture / Design Proposal",
    "Artifact And State Contract",
    "Data / File Layout Contract",
    "CLI / Command Surface",
    "Verification Plan",
    "Acceptance Criteria",
    "Open Questions / Deferred Items",
    "Final Implementation Recommendation",
]


BUILTIN_DELIVERABLE_PROFILES: dict[str, dict[str, Any]] = {
    "discussion_summary": {
        "schema": DELIVERABLE_PROFILE_SCHEMA,
        "id": "discussion_summary",
        "title": "Discussion Summary",
        "description": "Preserve the current provider discussion flow without a required final artifact.",
        "final_artifacts": [],
        "required_sections": [],
        "convergence": {"mode": "none", "start_round": None},
        "quality_gates": [],
    },
    "development_contract": {
        "schema": DELIVERABLE_PROFILE_SCHEMA,
        "id": "development_contract",
        "title": "Development Contract",
        "description": "Converge on a concrete implementation contract before coding.",
        "final_artifacts": [
            {"path": "final/development-contract.md", "format": "markdown", "required": True},
        ],
        "required_sections": DEVELOPMENT_CONTRACT_SECTIONS,
        "convergence": {"mode": "auto", "start_round": None},
        "quality_gates": [
            "required_sections_present",
            "verification_is_executable",
            "acceptance_criteria_are_testable",
            "open_questions_are_explicit",
        ],
    },
    "readme_or_docs": {
        "schema": DELIVERABLE_PROFILE_SCHEMA,
        "id": "readme_or_docs",
        "title": "README Or Documentation",
        "description": "Converge on a publishable README or documentation artifact.",
        "final_artifacts": [
            {"path": "final/README.md", "format": "markdown", "required": True},
        ],
        "required_sections": [
            "Overview",
            "Install",
            "Usage",
            "Policy / Safety Boundary",
            "Verification",
        ],
        "convergence": {"mode": "auto", "start_round": None},
        "quality_gates": [
            "required_sections_present",
            "policy_boundary_present",
            "verification_is_executable",
        ],
    },
    "research_synthesis": {
        "schema": DELIVERABLE_PROFILE_SCHEMA,
        "id": "research_synthesis",
        "title": "Research Synthesis",
        "description": "Synthesize provider arguments and source evidence into a research note.",
        "final_artifacts": [
            {"path": "final/research-synthesis.md", "format": "markdown", "required": True},
        ],
        "required_sections": [
            "Research Question",
            "Evidence Summary",
            "Provider Positions",
            "Agreements",
            "Disagreements",
            "Risks And Caveats",
            "Recommendation",
        ],
        "convergence": {"mode": "auto", "start_round": None},
        "quality_gates": ["required_sections_present", "source_support_present"],
    },
    "decision_memo": {
        "schema": DELIVERABLE_PROFILE_SCHEMA,
        "id": "decision_memo",
        "title": "Decision Memo",
        "description": "Converge on one decision with accepted, rejected, and deferred options.",
        "final_artifacts": [
            {"path": "final/decision-memo.md", "format": "markdown", "required": True},
        ],
        "required_sections": [
            "Decision",
            "Context",
            "Options Considered",
            "Accepted Rationale",
            "Rejected Alternatives",
            "Risks",
            "Deferred Items",
            "Next Action",
        ],
        "convergence": {"mode": "auto", "start_round": None},
        "quality_gates": ["required_sections_present", "single_decision_present"],
    },
    "implementation_plan": {
        "schema": DELIVERABLE_PROFILE_SCHEMA,
        "id": "implementation_plan",
        "title": "Implementation Plan",
        "description": "Converge on a step-by-step implementation and verification plan.",
        "final_artifacts": [
            {"path": "final/implementation-plan.md", "format": "markdown", "required": True},
        ],
        "required_sections": [
            "Scope",
            "Milestones",
            "Files To Change",
            "State And Artifact Changes",
            "Verification Plan",
            "Acceptance Criteria",
            "Rollback / Recovery",
            "Open Questions",
        ],
        "convergence": {"mode": "auto", "start_round": None},
        "quality_gates": ["required_sections_present", "verification_is_executable"],
    },
}


def builtin_deliverable_profile(profile_id: str) -> dict[str, Any]:
    profile = BUILTIN_DELIVERABLE_PROFILES.get(profile_id)
    if profile is None:
        raise ValueError(f"unknown deliverable profile: {profile_id}")
    return copy.deepcopy(profile)


def deliverable_profile_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": profile["id"],
            "title": profile["title"],
            "description": profile["description"],
        }
        for profile in BUILTIN_DELIVERABLE_PROFILES.values()
    ]


def normalize_deliverable_profile(value: Any) -> dict[str, Any]:
    if value is None or value is False:
        return builtin_deliverable_profile("discussion_summary")
    if isinstance(value, str):
        text = value.strip()
        return builtin_deliverable_profile(text or "discussion_summary")
    if not isinstance(value, dict):
        raise ValueError("deliverable_profile must be an object, string, or null")
    profile_id = str(value.get("id") or value.get("profile_id") or "custom").strip() or "custom"
    base = builtin_deliverable_profile(profile_id) if profile_id in BUILTIN_DELIVERABLE_PROFILES else {
        "schema": DELIVERABLE_PROFILE_SCHEMA,
        "id": profile_id,
        "title": profile_id.replace("_", " ").title(),
        "description": "Custom deliverable profile.",
        "final_artifacts": [],
        "required_sections": [],
        "convergence": {"mode": "auto", "start_round": None},
        "quality_gates": [],
    }
    merged = copy.deepcopy(base)
    for key in ("title", "description", "final_artifacts", "required_sections", "convergence", "quality_gates"):
        if key in value:
            merged[key] = copy.deepcopy(value[key])
    merged["schema"] = DELIVERABLE_PROFILE_SCHEMA
    merged["id"] = profile_id
    merged["final_artifacts"] = _normalize_final_artifacts(merged.get("final_artifacts"))
    merged["required_sections"] = _str_list(merged.get("required_sections"))
    merged["quality_gates"] = _str_list(merged.get("quality_gates"))
    if not isinstance(merged.get("convergence"), dict):
        merged["convergence"] = {"mode": "auto", "start_round": None}
    merged["convergence"] = {
        "mode": str(merged["convergence"].get("mode") or "auto"),
        "start_round": merged["convergence"].get("start_round"),
    }
    return merged


def validate_deliverable_profile(profile: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    profile_id = str(profile.get("id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", profile_id):
        blockers.append({"check": "deliverable_profile_id", "reason": f"invalid deliverable profile id: {profile_id}"})
    if profile.get("schema") != DELIVERABLE_PROFILE_SCHEMA:
        blockers.append({"check": "deliverable_profile_schema", "reason": f"expected {DELIVERABLE_PROFILE_SCHEMA}"})
    if not str(profile.get("title") or "").strip():
        blockers.append({"check": "deliverable_profile_title", "reason": "deliverable profile title is required"})
    if not isinstance(profile.get("required_sections"), list):
        blockers.append({"check": "deliverable_required_sections", "reason": "required_sections must be an array"})
    if not isinstance(profile.get("quality_gates"), list):
        blockers.append({"check": "deliverable_quality_gates", "reason": "quality_gates must be an array"})
    artifacts = profile.get("final_artifacts")
    if not isinstance(artifacts, list):
        blockers.append({"check": "deliverable_final_artifacts", "reason": "final_artifacts must be an array"})
    else:
        for index, artifact in enumerate(artifacts, start=1):
            if not isinstance(artifact, dict):
                blockers.append({"check": "deliverable_final_artifact", "reason": f"final_artifacts[{index}] must be an object"})
                continue
            path = str(artifact.get("path") or "").strip()
            if not path:
                blockers.append({"check": "deliverable_final_artifact_path", "reason": f"final_artifacts[{index}].path is required"})
            elif not is_safe_relative_artifact_path(path):
                blockers.append({"check": "deliverable_final_artifact_path", "reason": f"unsafe final artifact path: {path}"})
            fmt = str(artifact.get("format") or "markdown")
            if fmt != "markdown":
                blockers.append({"check": "deliverable_final_artifact_format", "reason": f"unsupported artifact format: {fmt}"})
    return blockers


def config_deliverable_profile(config: dict[str, Any]) -> dict[str, Any]:
    return normalize_deliverable_profile(config.get("deliverable_profile"))


def annotate_rounds_with_deliverable_profile(rounds: list[dict[str, str]], profile: dict[str, Any]) -> list[dict[str, str]]:
    if str(profile.get("id") or "") == "discussion_summary":
        return [dict(item) for item in rounds]
    annotated: list[dict[str, str]] = []
    for index, item in enumerate(rounds, start=1):
        phase = convergence_phase(profile=profile, round_index=index, total_rounds=len(rounds))
        enriched = dict(item)
        enriched["deliverable_phase"] = phase
        if phase != "explore":
            enriched["title"] = f"{enriched.get('title') or item.get('round_id')}: {phase.replace('_', ' ').title()}"
        annotated.append(enriched)
    return annotated


def convergence_phase(*, profile: dict[str, Any], round_index: int, total_rounds: int) -> str:
    if total_rounds <= 0:
        return "explore"
    convergence = profile.get("convergence") if isinstance(profile.get("convergence"), dict) else {}
    if convergence.get("mode") == "none":
        return "explore"
    start = convergence_start_round(total_rounds=total_rounds, profile=profile)
    if round_index < start:
        return "explore"
    span = total_rounds - start + 1
    offset = round_index - start
    if span <= 1:
        return "finalize"
    if span == 2:
        return "draft" if offset == 0 else "finalize"
    if span == 3:
        return ("draft", "resolve", "finalize")[offset]
    if offset < span - 4:
        return "structure"
    return ("draft", "challenge", "resolve", "finalize")[offset - (span - 4)]


def convergence_start_round(*, total_rounds: int, profile: dict[str, Any]) -> int:
    convergence = profile.get("convergence") if isinstance(profile.get("convergence"), dict) else {}
    configured = convergence.get("start_round")
    if isinstance(configured, int) and configured > 0:
        return max(1, min(total_rounds, configured))
    if total_rounds <= 3:
        return total_rounds
    if total_rounds <= 6:
        return total_rounds - 1
    return max(2, min(total_rounds, math.ceil(total_rounds * 0.7)))


def render_deliverable_profile_contract(*, run: dict[str, Any], spec: dict[str, Any]) -> str:
    profile = normalize_deliverable_profile(run.get("deliverable_profile"))
    if str(profile.get("id") or "") == "discussion_summary":
        return ""
    rounds = run.get("rounds") if isinstance(run.get("rounds"), list) else []
    total_rounds = len(rounds)
    round_id = str(spec.get("round_id") or "")
    round_index = _round_index(rounds, round_id)
    phase = str(spec.get("deliverable_phase") or convergence_phase(profile=profile, round_index=round_index, total_rounds=total_rounds))
    artifact_lines = [
        f"- `{artifact['path']}` format `{artifact.get('format', 'markdown')}` required `{artifact.get('required') is not False}`"
        for artifact in profile.get("final_artifacts", [])
    ]
    section_lines = [f"- {section}" for section in profile.get("required_sections", [])]
    lines = [
        "## Deliverable Profile Contract",
        "",
        f"- profile_id: `{profile['id']}`",
        f"- title: `{profile['title']}`",
        f"- convergence_phase: `{phase}`",
        f"- convergence_start_round: `R{convergence_start_round(total_rounds=total_rounds, profile=profile)}`",
        "",
        "Final artifact targets:",
        *(artifact_lines or ["- none configured"]),
        "",
        "Required sections:",
        *(section_lines or ["- none configured"]),
        "",
        "Provider obligations:",
        "- Keep accepted, rejected, deferred, and unresolved decisions separate.",
        "- Do not present orchestrator inference as provider consensus.",
        "- Fill weak or missing required sections from prior prompt deltas before adding new ideas.",
    ]
    if phase in {"draft", "challenge", "resolve", "finalize"}:
        lines.extend(
            [
                "- Converge toward the deliverable profile instead of starting another unrelated draft.",
                "- Explicitly state which required sections are strong, weak, missing, or blocked.",
            ]
        )
    if phase == "finalize":
        lines.extend(
            [
                "",
                "Final artifact block required:",
                "- Emit the final Markdown artifact inside exactly one `KDH_FINAL_ARTIFACT` block.",
                "- The block path must match one configured final artifact target.",
                "- Use this shape:",
                "",
                '```markdown\n<!-- KDH_FINAL_ARTIFACT path="final/development-contract.md" profile="development_contract" -->\n# Title\n\n...\n<!-- /KDH_FINAL_ARTIFACT -->\n```',
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def extract_final_artifact_blocks(text: str, *, source_ref: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    pos = 0
    while True:
        start = FINAL_ARTIFACT_OPEN_RE.search(text, pos)
        if not start:
            break
        close = FINAL_ARTIFACT_CLOSE_RE.search(text, start.end())
        if not close:
            break
        attrs = dict(ATTRIBUTE_RE.findall(start.group(1)))
        body = text[start.end() : close.start()].strip()
        blocks.append(
            {
                "path": str(attrs.get("path") or "").strip(),
                "profile": str(attrs.get("profile") or "").strip(),
                "format": str(attrs.get("format") or "markdown").strip() or "markdown",
                "content": body.rstrip() + "\n",
                "source_ref": source_ref,
            }
        )
        pos = close.end()
    return blocks


def section_presence(text: str, required_sections: list[str]) -> dict[str, str]:
    return {section: ("present" if has_markdown_section(text, section) else "missing") for section in required_sections}


def has_markdown_section(text: str, section: str) -> bool:
    escaped = re.escape(section).replace(r"\ ", r"\s+")
    pattern = rf"^#{{1,6}}\s+(?:[0-9]+[\.\)]\s*)?{escaped}\s*$"
    if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
        return True
    loose = rf"^#{{1,6}}\s+(?:[0-9]+[\.\)]\s*)?.*{escaped}.*$"
    return re.search(loose, text, flags=re.IGNORECASE | re.MULTILINE) is not None


def is_safe_relative_artifact_path(value: str) -> bool:
    path = Path(value)
    if path.is_absolute():
        return False
    return ".." not in path.parts and bool(path.parts)


def safe_artifact_path(base: Path, rel_path: str) -> Path:
    if not is_safe_relative_artifact_path(rel_path):
        raise ValueError(f"unsafe final artifact path: {rel_path}")
    resolved = (base / rel_path).resolve()
    base_resolved = base.resolve()
    if base_resolved not in resolved.parents and resolved != base_resolved:
        raise ValueError(f"final artifact path escapes run root: {rel_path}")
    return resolved


def _normalize_final_artifacts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    artifacts: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        artifacts.append(
            {
                "path": path,
                "format": str(item.get("format") or "markdown").strip() or "markdown",
                "required": item.get("required") is not False,
            }
        )
    return artifacts


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _round_index(rounds: list[Any], round_id: str) -> int:
    for index, item in enumerate(rounds, start=1):
        if isinstance(item, dict) and item.get("round_id") == round_id:
            return index
    return 1
