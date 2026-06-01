from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .artifacts import (
    ALLOWED_CLAIM_STATUSES,
    ALLOWED_GATE_VERDICTS,
    CLAIM_MAP_SCHEMA,
    DEFAULT_ROOT,
    DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    GATE_SCHEMA,
    RUN_SCHEMA,
    SOURCE_INDEX_SCHEMA,
    VERIFY_SCHEMA,
    ROUND_PLANS,
    append_event,
    ensure_run_dirs,
    load_run,
    new_run_id,
    next_round_id,
    provider_seats,
    provider_seats_for_preset,
    read_events,
    read_json,
    round_spec,
    run_root,
    save_run,
    sha256_file,
    utc_now,
    write_artifact_hash,
    write_json,
)
from .agent_profiles import (
    agent_profile_report,
    agent_profile_report_markdown,
    catalog_entries_from_paths,
    render_agent_profile_contract,
    team_role_specs,
)
from .claude_smoke import run_claude_k_smoke
from .claude_team_agents_smoke import run_claude_team_agents_smoke
from .codex_live import run_codex_live_dispatch
from .gemini_smoke import run_gemini_headless_smoke, run_gemini_live_dispatch
from .claude_workspace_trust import (
    inspect_hook_config,
    inspect_permissions,
    inspect_runtime_preflight,
    inspect_workspace_trust,
    remove_hook_config,
    repair_hook_config,
    repair_permissions,
    repair_workspace_trust,
)
from .configure import (
    CONFIGURE_SCHEMA,
    configure_from_answers,
    configure_interactive,
    read_answers,
    validate_generated_config,
    write_config,
)
from .input_pack import (
    DEFAULT_EXCERPT_LINES,
    DEFAULT_MAX_FILE_BYTES,
    attach_input_pack_to_run,
    build_input_pack,
    source_dirs_from_config,
)
from .model_refresh import refresh_models
from .proofs import validate_team_agents_proof, validate_transport_proof
from .profiles import (
    annotate_rounds_with_deliverable_profile,
    builtin_deliverable_profile,
    config_deliverable_profile,
    convergence_start_round,
    extract_final_artifact_blocks,
    has_markdown_section,
    normalize_deliverable_profile,
    safe_artifact_path,
    section_presence,
)
from .provider_auth import inspect_seat_auth, login_hint_for_transport, parse_cli_path_overrides, run_auth_preflight
from .provider_adapters import (
    ADAPTER_RESULT_SCHEMA,
    ADAPTER_PREVIEW_SCHEMA,
    ADAPTER_STATUS_SCHEMA,
    FAILURE_INSTALLED_NOT_LOGGED_IN,
    FAILURE_MISSING_CLI,
    FAILURE_OPTIONAL_PROVIDER_SKIPPED,
    FAILURE_PROOF_FAILED,
    FAILURE_UNSUPPORTED_LIVE_DISPATCH,
    adapter_for_seat,
    adapter_summary,
    effective_timeout_seconds,
    existing_required_provider_failures,
    required_provider_blockers_for_round,
    validate_adapter_seat,
    write_dry_run_result,
    write_manual_import_result,
    write_round_prompt,
)
from .public_config import (
    example_public_config,
    provider_seats_from_public_config,
    read_public_config,
    rounds_from_public_config,
    validate_public_config,
)
from .team_agents_hooks import DEFAULT_TRIGGER_REGEX, STATUS_SCHEMA as TEAM_AGENTS_STATUS_SCHEMA, handle_dispatch, handle_hook, parse_roles


def default_harness_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "scripts" / "kdh-providers-discuss").exists():
            return parent
        if (parent / "bin" / "providers-discuss").exists():
            return parent
    return Path.cwd()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    argv = ["--help" if item == "-help" else item for item in argv]
    parser = argparse.ArgumentParser(prog="kdh-providers-discuss")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--objective")
    init.add_argument("--preset", choices=sorted(ROUND_PLANS))
    init.add_argument("--config", type=Path, help="providers-discuss.public-config.v1 JSON file for dynamic rounds and seats")
    init.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    init.add_argument("--run-id")

    config_template = sub.add_parser("config-template")
    config_template.add_argument("--output", type=Path, help="write example config JSON to this path instead of stdout")

    validate_config = sub.add_parser("validate-config")
    validate_config.add_argument("config", type=Path)
    validate_config.add_argument("--json", action="store_true")

    configure = sub.add_parser("configure")
    configure.add_argument("--output", type=Path, default=Path("providers-discuss.config.json"))
    configure.add_argument("--answers-json", type=Path, help="non-interactive wizard answers JSON")
    configure.add_argument("--run-auth-preflight", action="store_true")
    configure.add_argument("--auth-report-dir", type=Path)
    configure.add_argument("--cli-path", action="append", default=[], help="auth probe CLI override as key=/path")
    configure.add_argument("--auth-timeout-seconds", type=int, default=30)
    configure.add_argument("--json", action="store_true")

    model_refresh = sub.add_parser("model-refresh")
    model_refresh.add_argument("--provider", choices=["gemini"], default="gemini")
    model_refresh.add_argument("--timeout-seconds", type=int, default=15)
    model_refresh.add_argument("--json", action="store_true")

    auth_preflight = sub.add_parser("auth-preflight")
    auth_preflight.add_argument("config", type=Path)
    auth_preflight.add_argument("--report-dir", type=Path, default=Path("config"))
    auth_preflight.add_argument("--cli-path", action="append", default=[], help="auth probe CLI override as key=/path")
    auth_preflight.add_argument("--timeout-seconds", type=int, default=30)
    auth_preflight.add_argument("--json", action="store_true")

    build_input = sub.add_parser("build-input-pack")
    build_input.add_argument("--config", type=Path)
    build_input.add_argument("--source-dir", action="append", type=Path, default=[])
    build_input.add_argument("--output-dir", type=Path)
    build_input.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    build_input.add_argument("--run-id")
    build_input.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    build_input.add_argument("--excerpt-lines", type=int, default=DEFAULT_EXCERPT_LINES)
    build_input.add_argument("--json", action="store_true")

    adapter_capabilities = sub.add_parser("adapter-capabilities")
    adapter_capabilities.add_argument("run_id", nargs="?", help="existing run id; omit when using --config")
    adapter_capabilities.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    adapter_capabilities.add_argument("--config", type=Path, help="providers-discuss.public-config.v1 JSON file")
    adapter_capabilities.add_argument("--report-dir", type=Path, help="write adapter-capabilities JSON/Markdown to this directory")
    adapter_capabilities.add_argument("--cli-path", action="append", default=[], help="auth probe CLI override as key=/path")
    adapter_capabilities.add_argument("--auth-timeout-seconds", type=int, default=30)
    adapter_capabilities.add_argument("--no-auth-probe", action="store_true", help="do not execute provider auth probes; report CLI/login hints only")
    adapter_capabilities.add_argument("--json", action="store_true")

    agent_profiles = sub.add_parser("agent-profiles")
    agent_profiles.add_argument("--config", type=Path, help="providers-discuss.public-config.v1 JSON file")
    agent_profiles.add_argument("--catalog", action="append", type=Path, default=[], help="explicit agent catalog file; may be repeated")
    agent_profiles.add_argument("--seat", help="seat id from --config to check compatibility")
    agent_profiles.add_argument("--transport", help="transport to check compatibility, e.g. codex_exec_file")
    agent_profiles.add_argument("--markdown", action="store_true", help="print Markdown instead of JSON")
    agent_profiles.add_argument("--json", action="store_true", help="print JSON; this is the default")

    preflight = sub.add_parser("preflight")
    add_run_args(preflight)

    status = sub.add_parser("status")
    add_run_args(status)
    status.add_argument("--json", action="store_true")

    run_round = sub.add_parser("run-round")
    add_run_args(run_round)
    run_round.add_argument("--round", required=True)
    run_round.add_argument("--mode", choices=["dry-run", "manual-import", "live-dispatch"], required=True)
    run_round.add_argument("--answer", action="append", default=[], help="manual-import answer as seat_id=/path/file.md")
    run_round.add_argument("--cli-path", action="append", default=[], help="live dispatch CLI override as key=/path")

    gate = sub.add_parser("gate")
    add_run_args(gate)
    gate.add_argument("--round", required=True)
    gate.add_argument("--terminal", action="store_true")

    orchestrate = sub.add_parser("orchestrate")
    add_run_args(orchestrate)
    orchestrate.add_argument("--after-round", required=True)

    verify = sub.add_parser("verify")
    add_run_args(verify)
    verify.add_argument("--json", action="store_true")

    verify_proof = sub.add_parser("verify-proof")
    add_run_args(verify_proof)
    verify_proof.add_argument("--kind", choices=["transport", "team-agents"], required=True)
    verify_proof.add_argument("--proof", type=Path, required=True)
    verify_proof.add_argument("--json", action="store_true")

    smoke_claude = sub.add_parser("smoke-claude-k")
    add_run_args(smoke_claude)
    smoke_claude.add_argument("--round", required=True)
    smoke_claude.add_argument("--seat", required=True)
    smoke_claude.add_argument("--claude-bin", type=Path, required=True)
    smoke_claude.add_argument("--launch-cwd", type=Path, help="trusted workspace cwd for launching Claude; defaults to the run root")
    smoke_claude.add_argument("--auto-trust", action="store_true", help="accept Claude workspace/folder trust prompt for this smoke run")
    smoke_claude.add_argument("--timeout-seconds", type=int, help="override the seat timeout_seconds for this smoke run")
    smoke_claude.add_argument("--override-reason", default="", help="required when --timeout-seconds changes the configured seat timeout")
    smoke_claude.add_argument("--json", action="store_true")

    smoke_team = sub.add_parser("smoke-claude-team-agents")
    add_run_args(smoke_team)
    smoke_team.add_argument("--round", required=True)
    smoke_team.add_argument("--seat", required=True)
    smoke_team.add_argument("--claude-bin", type=Path, required=True)
    smoke_team.add_argument("--launch-cwd", type=Path, help="trusted workspace cwd for launching Claude; defaults to the run root")
    smoke_team.add_argument("--auto-trust", action="store_true", help="accept Claude workspace/folder trust prompt for this smoke run")
    smoke_team.add_argument(
        "--experimental-agent-teams",
        action="store_true",
        help="set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 for this child Claude process only",
    )
    smoke_team.add_argument("--timeout-seconds", type=int, help="override the seat timeout_seconds for this smoke run")
    smoke_team.add_argument("--override-reason", default="", help="required when --timeout-seconds changes the configured seat timeout")
    smoke_team.add_argument(
        "--trigger-mode",
        choices=["prompt_only", "providers_discuss_hook", "global_hook"],
        default="prompt_only",
        help="label how Team Agents behavior was triggered; this command does not install hooks",
    )
    smoke_team.add_argument("--json", action="store_true")

    smoke_gemini = sub.add_parser("smoke-gemini-headless")
    add_run_args(smoke_gemini)
    smoke_gemini.add_argument("--round", required=True)
    smoke_gemini.add_argument("--seat", required=True)
    smoke_gemini.add_argument("--gemini-bin", type=Path, required=True)
    smoke_gemini.add_argument("--timeout-seconds", type=int, help="override the seat timeout_seconds for this smoke run")
    smoke_gemini.add_argument("--override-reason", default="", help="required when --timeout-seconds changes the configured seat timeout")
    smoke_gemini.add_argument("--json", action="store_true")

    team_prompt = sub.add_parser("team-agents-prompt")
    add_run_args(team_prompt)
    team_prompt.add_argument("--round", help="round id; defaults to the run current_round")
    team_prompt.add_argument("--seat", default="claude_team")
    team_prompt.add_argument("--output", type=Path, help="write Markdown prompt to this path; defaults to run prompts/")
    team_prompt.add_argument("--json", action="store_true")

    team_report = sub.add_parser("team-agents-proof-report")
    add_run_args(team_report)
    team_report.add_argument("--proof", type=Path, required=True)
    team_report.add_argument("--output", type=Path, help="write JSON when suffix is .json, otherwise Markdown")
    team_report.add_argument("--json", action="store_true")

    resume = sub.add_parser("resume")
    add_run_args(resume)

    advance = sub.add_parser("advance")
    add_run_args(advance)
    advance.add_argument(
        "--round-mode",
        choices=["dry-run", "live-dispatch"],
        default="dry-run",
        help="provider collection mode to use when the next legal action is run-round",
    )
    advance.add_argument("--cli-path", action="append", default=[], help="live dispatch CLI override as key=/path")
    advance.add_argument("--max-steps", type=int, default=20)
    advance.add_argument("--json", action="store_true")

    cancel = sub.add_parser("cancel")
    add_run_args(cancel)
    cancel.add_argument("--reason", required=True)

    finalize = sub.add_parser("finalize")
    add_run_args(finalize)

    trust_workspace = sub.add_parser("trust-workspace")
    trust_workspace.add_argument("--workspace", type=Path, default=Path.cwd())
    trust_workspace.add_argument("--claude-json", type=Path, default=Path.home() / ".claude.json")
    trust_workspace.add_argument("--repair", action="store_true", help="backup and set hasTrustDialogAccepted=true for this workspace")
    trust_workspace.add_argument("--json", action="store_true")

    permissions = sub.add_parser("permissions")
    permissions.add_argument("--settings-json", type=Path, default=Path.home() / ".claude" / "settings.json")
    permissions.add_argument("--repair", action="store_true", help="backup and set permissions.defaultMode=auto plus skipAutoPermissionPrompt=true")
    permissions.add_argument("--json", action="store_true")

    hook_config = sub.add_parser("hook-config")
    add_hook_config_args(hook_config)
    hook_config.add_argument("--repair", action="store_true", help="backup and install missing always-on providers-discuss hook dispatcher entries")
    hook_config.add_argument("--remove", action="store_true", help="backup and remove matching providers-discuss hook dispatcher entries for this root")
    hook_config.add_argument("--json", action="store_true")

    runtime_preflight = sub.add_parser("runtime-preflight")
    runtime_preflight.add_argument("--workspace", type=Path, default=Path.cwd())
    runtime_preflight.add_argument("--claude-json", type=Path, default=Path.home() / ".claude.json")
    runtime_preflight.add_argument("--repair", action="store_true", help="backup and repair workspace trust plus auto permission mode")
    runtime_preflight.add_argument("--install-hook", action="store_true", help="backup and install always-on providers-discuss hook dispatcher entries")
    add_hook_config_args(runtime_preflight, include_prompt_only=True, default_trigger_mode="prompt_only")
    runtime_preflight.add_argument("--json", action="store_true")

    hook = sub.add_parser("hook")
    hook.add_argument("--event", choices=["UserPromptSubmit", "TaskCreated", "TeammateIdle", "TaskCompleted"], required=True)
    hook.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    hook.add_argument("--run-id", required=True)
    hook.add_argument("--round", default="R1")
    hook.add_argument("--seat", default="claude_team")
    hook.add_argument("--trigger-mode", choices=["providers_discuss_hook", "global_hook"], default="providers_discuss_hook")
    hook.add_argument("--trigger-regex", default=DEFAULT_TRIGGER_REGEX)
    hook.add_argument("--roles", default="source-reader,skeptic,recorder")

    hook_dispatch = sub.add_parser("hook-dispatch")
    hook_dispatch.add_argument("--event", choices=["UserPromptSubmit", "TaskCreated", "TeammateIdle", "TaskCompleted"], required=True)
    hook_dispatch.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    hook_dispatch.add_argument("--seat", default="claude_team")
    hook_dispatch.add_argument("--trigger-mode", choices=["providers_discuss_hook", "global_hook"], default="providers_discuss_hook")
    hook_dispatch.add_argument("--roles", default="source-reader,skeptic,recorder")

    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "config-template":
            return cmd_config_template(args)
        if args.command == "validate-config":
            return cmd_validate_config(args)
        if args.command == "configure":
            return cmd_configure(args)
        if args.command == "model-refresh":
            return cmd_model_refresh(args)
        if args.command == "auth-preflight":
            return cmd_auth_preflight(args)
        if args.command == "build-input-pack":
            return cmd_build_input_pack(args)
        if args.command == "adapter-capabilities":
            return cmd_adapter_capabilities(args)
        if args.command == "agent-profiles":
            return cmd_agent_profiles(args)
        if args.command == "preflight":
            return cmd_preflight(args)
        if args.command == "status":
            return cmd_status(args)
        if args.command == "run-round":
            return cmd_run_round(args)
        if args.command == "gate":
            return cmd_gate(args)
        if args.command == "orchestrate":
            return cmd_orchestrate(args)
        if args.command == "verify":
            return cmd_verify(args)
        if args.command == "verify-proof":
            return cmd_verify_proof(args)
        if args.command == "smoke-claude-k":
            return cmd_smoke_claude_k(args)
        if args.command == "smoke-claude-team-agents":
            return cmd_smoke_claude_team_agents(args)
        if args.command == "smoke-gemini-headless":
            return cmd_smoke_gemini_headless(args)
        if args.command == "team-agents-prompt":
            return cmd_team_agents_prompt(args)
        if args.command == "team-agents-proof-report":
            return cmd_team_agents_proof_report(args)
        if args.command == "resume":
            return cmd_resume(args)
        if args.command == "advance":
            return cmd_advance(args)
        if args.command == "cancel":
            return cmd_cancel(args)
        if args.command == "finalize":
            return cmd_finalize(args)
        if args.command == "trust-workspace":
            return cmd_trust_workspace(args)
        if args.command == "permissions":
            return cmd_permissions(args)
        if args.command == "hook-config":
            return cmd_hook_config(args)
        if args.command == "runtime-preflight":
            return cmd_runtime_preflight(args)
        if args.command == "hook":
            return cmd_hook(args)
        if args.command == "hook-dispatch":
            return cmd_hook_dispatch(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(args.command)


def add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("run_id")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)


def add_hook_config_args(
    parser: argparse.ArgumentParser,
    *,
    include_prompt_only: bool = False,
    default_trigger_mode: str = "providers_discuss_hook",
) -> None:
    trigger_modes = ["providers_discuss_hook", "global_hook"]
    if include_prompt_only:
        trigger_modes = ["prompt_only", *trigger_modes]
    parser.add_argument("--settings-json", type=Path, default=Path.home() / ".claude" / "settings.json")
    parser.add_argument("--harness-root", type=Path, default=default_harness_root())
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--round", default="R1")
    parser.add_argument("--seat", default="claude_team")
    parser.add_argument("--trigger-mode", choices=trigger_modes, default=default_trigger_mode)
    parser.add_argument("--trigger-regex", default="")
    parser.add_argument("--roles", default="source-reader,skeptic,recorder")


def cmd_init(args: argparse.Namespace) -> int:
    run_id = args.run_id or new_run_id()
    base = run_root(args.root, run_id)
    if base.exists():
        raise ValueError(f"run already exists: {base}")
    if bool(args.preset) == bool(args.config):
        raise ValueError("init requires exactly one of --preset or --config")
    config_ref = None
    dynamic_config: dict[str, Any] | None = None
    if args.config:
        dynamic_config = read_public_config(args.config)
        validation = validate_public_config(dynamic_config, config_path=args.config)
        if validation["status"] != "pass":
            raise ValueError("invalid public config: " + json.dumps(validation["blockers"], ensure_ascii=False))
        rounds = rounds_from_public_config(dynamic_config)
        provider_seats = provider_seats_from_public_config(dynamic_config, config_path=args.config)
        deliverable_profile = config_deliverable_profile(dynamic_config)
        objective = args.objective or str(dynamic_config.get("objective") or "").strip()
        preset = "custom"
        config_ref = str(args.config)
    else:
        if not args.objective:
            raise ValueError("--objective is required with --preset")
        rounds = [dict(item) for item in ROUND_PLANS[args.preset]]
        deliverable_profile = builtin_deliverable_profile("discussion_summary")
        rounds = annotate_rounds_with_deliverable_profile(rounds, deliverable_profile)
        provider_seats = provider_seats_for_preset(args.preset)
        objective = args.objective
        preset = args.preset
    ensure_run_dirs(base)
    write_json(base / "config" / "provider-seats.json", provider_seats)
    if dynamic_config is not None:
        write_json(base / "config" / "providers-discuss.config.json", dynamic_config)
    write_json(
        base / "config" / "source-index.json",
        {
            "schema": SOURCE_INDEX_SCHEMA,
            "sources": [],
        },
    )
    run = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "objective": objective,
        "preset": preset,
        **({"public_config_path": config_ref, "public_config_run_copy": "config/providers-discuss.config.json"} if config_ref else {}),
        "state": "created",
        "current_round": rounds[0]["round_id"],
        "root": str(base),
        "rounds": rounds,
        "deliverable_profile": deliverable_profile,
        "provider_seats_path": "config/provider-seats.json",
        "source_index_path": "config/source-index.json",
        "policy": {
            "no_claude_p_dependency": True,
            "claude_live_transport": "claude -k",
            "no_hidden_automation": True,
            "team_agents_require_direct_messages": True,
            "no_output_length_caps_unless_requested": True,
        },
    }
    write_json(base / "run.json", run)
    (base / "summary.md").write_text(
        f"# kdh-providers-discuss Run\n\nrun_id: `{run_id}`\n\nobjective: {objective}\n",
        encoding="utf-8",
    )
    (base / "raw-output-manifest.md").write_text("# Raw Output Manifest\n\n", encoding="utf-8")
    append_event(base, "run.created", run_id=run_id, preset=preset, refs=["run.json"])
    refs = ["run.json", "config/provider-seats.json", "config/source-index.json", "summary.md"]
    if dynamic_config is not None:
        refs.append("config/providers-discuss.config.json")
    for rel in refs:
        write_artifact_hash(base, rel)
    print(run_id)
    return 0


def cmd_config_template(args: argparse.Namespace) -> int:
    payload = example_public_config()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(args.output)
    else:
        print(text, end="")
    return 0


def cmd_validate_config(args: argparse.Namespace) -> int:
    payload = read_public_config(args.config)
    result = validate_public_config(payload, config_path=args.config)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"validate-config: {result['status']}")
        for blocker in result["blockers"]:
            print(f"- {blocker['check']}: {blocker['reason']}")
    return 0 if result["status"] == "pass" else 1


def cmd_configure(args: argparse.Namespace) -> int:
    config = configure_from_answers(read_answers(args.answers_json)) if args.answers_json else configure_interactive()
    validation = validate_generated_config(config, config_path=args.output)
    if validation["status"] != "pass":
        if args.json:
            print(json.dumps({"schema": CONFIGURE_SCHEMA, "status": "fail", "validation": validation}, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("configure: fail", file=sys.stderr)
            for blocker in validation["blockers"]:
                print(f"- {blocker['check']}: {blocker['reason']}", file=sys.stderr)
        return 1
    write_config(args.output, config)
    auth_payload = None
    if args.run_auth_preflight:
        report_dir = args.auth_report_dir or args.output.parent
        auth_payload = run_auth_preflight(
            config=config,
            config_path=args.output,
            report_dir=report_dir,
            cli_overrides=parse_cli_path_overrides(args.cli_path),
            timeout_seconds=args.auth_timeout_seconds,
        )
    payload = {
        "schema": CONFIGURE_SCHEMA,
        "status": "pass" if not auth_payload or auth_payload["status"] != "fail" else "auth_blocked",
        "config_path": str(args.output),
        "validation": validation,
        "auth_preflight": auth_payload,
        "next_commands": [
            f"scripts/kdh-providers-discuss validate-config {args.output}",
            f"scripts/kdh-providers-discuss init --config {args.output} --root <run-root>",
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"configure: {payload['status']}")
        print(f"config: {args.output}")
        if auth_payload:
            print(f"auth-preflight: {auth_payload['status']}")
        print("next:")
        for command in payload["next_commands"]:
            print(f"- {command}")
    return 0 if payload["status"] == "pass" else 1


def cmd_model_refresh(args: argparse.Namespace) -> int:
    payload = refresh_models(provider=args.provider, timeout_seconds=args.timeout_seconds)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"model-refresh: {payload['status']}")
        print(f"provider: {payload['provider']}")
        print("sources:")
        for source in payload["sources"]:
            suffix = f" ({source['error']})" if source.get("error") else ""
            print(f"- {source['status']}: {source['url']}{suffix}")
        print(f"[{payload['provider']}]")
        for item in payload["models"][:8]:
            source_count = len(item.get("sources") or [])
            print(f"- model: {item['model']} (official sources: {source_count})")
    return 0 if payload["status"] == "pass" else 1


def cmd_agent_profiles(args: argparse.Namespace) -> int:
    if args.json and args.markdown:
        raise ValueError("agent-profiles accepts only one of --json or --markdown")
    if not args.config and not args.catalog:
        raise ValueError("agent-profiles requires --config or at least one --catalog")
    config_path = args.config
    catalogs: list[dict[str, Any]] = []
    seat_id = str(args.seat or "")
    transport = str(args.transport or "")
    if args.config:
        config = read_public_config(args.config)
        configured_catalogs = config.get("agent_catalogs")
        if isinstance(configured_catalogs, list):
            catalogs.extend([dict(item) for item in configured_catalogs if isinstance(item, dict)])
        if args.seat:
            seats = config.get("seats") if isinstance(config.get("seats"), list) else []
            matches = [seat for seat in seats if isinstance(seat, dict) and str(seat.get("seat_id") or "") == args.seat]
            if not matches:
                raise ValueError(f"seat not found in config: {args.seat}")
            transport = transport or str(matches[0].get("transport") or "")
    catalogs.extend(catalog_entries_from_paths(args.catalog))
    if not catalogs:
        raise ValueError("agent-profiles found no configured agent catalogs")
    payload = agent_profile_report(catalogs=catalogs, config_path=config_path, transport=transport, seat_id=seat_id)
    if args.markdown:
        print(agent_profile_report_markdown(payload), end="")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_auth_preflight(args: argparse.Namespace) -> int:
    config = read_public_config(args.config)
    validation = validate_public_config(config, config_path=args.config)
    if validation["status"] != "pass":
        raise ValueError("invalid public config: " + json.dumps(validation["blockers"], ensure_ascii=False))
    payload = run_auth_preflight(
        config=config,
        config_path=args.config,
        report_dir=args.report_dir,
        cli_overrides=parse_cli_path_overrides(args.cli_path),
        timeout_seconds=args.timeout_seconds,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"auth-preflight: {payload['status']}")
        print(f"report-json: {args.report_dir / 'provider-auth-preflight.json'}")
        print(f"report-md: {args.report_dir / 'provider-auth-preflight.md'}")
        for blocker in payload["blockers"]:
            print(f"- blocker {blocker['seat_id']}: {blocker['login_hint']}")
    return 0 if payload["status"] != "fail" else 1


def cmd_build_input_pack(args: argparse.Namespace) -> int:
    config = None
    source_dirs = list(args.source_dir)
    objective = ""
    if args.config:
        config = read_public_config(args.config)
        validation = validate_public_config(config, config_path=args.config)
        if validation["status"] != "pass":
            raise ValueError("invalid public config: " + json.dumps(validation["blockers"], ensure_ascii=False))
        source_dirs.extend(source_dirs_from_config(config, config_path=args.config))
        objective = str(config.get("objective") or "").strip()
    run_base = must_run_root(args.root, args.run_id) if args.run_id else None
    output_dir = args.output_dir or (run_base / "inputs" if run_base else Path("input-pack"))
    payload = build_input_pack(
        source_dirs=source_dirs,
        output_dir=output_dir,
        objective=objective,
        max_file_bytes=args.max_file_bytes,
        excerpt_lines=args.excerpt_lines,
    )
    attachment = None
    if run_base is not None:
        attachment = attach_input_pack_to_run(
            output_payload=payload,
            run_root=run_base,
            run_id=args.run_id,
            append_event=append_event,
            write_artifact_hash=write_artifact_hash,
        )
    result = {
        "schema": payload["schema"],
        "status": payload["status"],
        "source_count": payload["source_count"],
        "omitted_count": payload["omitted_count"],
        "output_dir": payload["output_dir"],
        "source_manifest_path": payload["source_manifest_path"],
        "source_index_path": payload["source_index_path"],
        "input_pack_path": payload["input_pack_path"],
        "attachment": attachment,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"build-input-pack: {result['status']}")
        print(f"sources: {result['source_count']}")
        print(f"omitted: {result['omitted_count']}")
        print(f"input-pack: {result['input_pack_path']}")
        if attachment:
            print(f"attached-run: {attachment['run_root']}")
    return 0


def cmd_adapter_capabilities(args: argparse.Namespace) -> int:
    if bool(args.config) == bool(args.run_id):
        raise ValueError("adapter-capabilities requires exactly one of --config or run_id")
    cli_overrides = parse_cli_path_overrides(args.cli_path)
    run: dict[str, Any] | None = None
    base: Path | None = None
    config_path = ""
    if args.config:
        config = read_public_config(args.config)
        validation = validate_public_config(config, config_path=args.config)
        if validation["status"] != "pass":
            raise ValueError("invalid public config: " + json.dumps(validation["blockers"], ensure_ascii=False))
        seats = provider_seats_from_public_config(config, config_path=args.config, include_disabled=True)["seats"]
        config_path = str(args.config)
        round_id = str((config.get("rounds") or [{"round_id": "R1"}])[0].get("round_id") or "R1")
        run_id = ""
    else:
        base = must_run_root(args.root, args.run_id)
        run = load_run(base)
        seats = [dict(seat) for seat in provider_seats(base)]
        round_id = str(run.get("current_round") or "R1")
        run_id = args.run_id

    capabilities = [
        _adapter_capability_entry(
            seat=seat,
            run_id=run_id,
            round_id=round_id,
            auth_probe=not args.no_auth_probe,
            cli_overrides=cli_overrides,
            auth_timeout_seconds=args.auth_timeout_seconds,
        )
        for seat in seats
    ]
    blockers = [
        {
            "seat_id": item["seat_id"],
            "provider": item["provider"],
            "transport": item["transport"],
            "failure_classification": item["failure_classification"],
            "next_action": item["next_action"],
        }
        for item in capabilities
        if item["enabled"] and item["required"] and item["failure_classification"] in {FAILURE_MISSING_CLI, FAILURE_INSTALLED_NOT_LOGGED_IN}
    ]
    optional_issues = [
        {
            "seat_id": item["seat_id"],
            "failure_classification": item["failure_classification"],
            "next_action": item["next_action"],
        }
        for item in capabilities
        if item["failure_classification"]
        and (not item["enabled"] or not item["required"] or item["failure_classification"] == FAILURE_UNSUPPORTED_LIVE_DISPATCH)
    ]
    status = "fail" if blockers else ("partial" if optional_issues else "pass")
    payload = {
        "schema": "kdh.providers-discuss.adapter-capabilities.v1",
        "status": status,
        "run_id": run_id,
        "config_path": config_path,
        "round_id": round_id,
        "auth_probe": not args.no_auth_probe,
        "seats": capabilities,
        "blockers": blockers,
        "optional_issues": optional_issues,
        "secret_policy": "OAuth tokens, cookies, provider-home raw config, credential file bodies, and shell history are not collected or stored.",
    }

    report_dir = args.report_dir
    if base is not None and report_dir is None:
        report_dir = base / "config"
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        json_path = report_dir / "adapter-capabilities.json"
        md_path = report_dir / "adapter-capabilities.md"
        write_json(json_path, payload)
        md_path.write_text(_adapter_capabilities_markdown(payload), encoding="utf-8")
        if base is not None and _is_relative_to(json_path, base) and _is_relative_to(md_path, base):
            json_rel = json_path.relative_to(base).as_posix()
            md_rel = md_path.relative_to(base).as_posix()
            write_artifact_hash(base, json_rel)
            write_artifact_hash(base, md_rel)
            append_event(base, "adapter_capabilities.reported", run_id=run_id, round_id=round_id, refs=[json_rel, md_rel])

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"adapter-capabilities: {payload['status']}")
        for item in payload["seats"]:
            print(
                "{seat_id}: {provider}/{transport} adapter={adapter_id} maturity={maturity} "
                "live_dispatch={live_dispatch} timeout={timeout_seconds} auth={auth_status} failure={failure}".format(
                    seat_id=item["seat_id"],
                    provider=item["provider"],
                    transport=item["transport"],
                    adapter_id=item["adapter_id"],
                    maturity=item["maturity"],
                    live_dispatch=item["live_dispatch"],
                    timeout_seconds=item["timeout_seconds"],
                    auth_status=item["auth_status"],
                    failure=item["failure_classification"] or "none",
                )
            )
    return 0


def _adapter_capability_entry(
    *,
    seat: dict[str, Any],
    run_id: str,
    round_id: str,
    auth_probe: bool,
    cli_overrides: dict[str, Path],
    auth_timeout_seconds: int,
) -> dict[str, Any]:
    seat_id = str(seat.get("seat_id") or "")
    enabled = seat.get("enabled", True) is not False
    prompt_rel = f"prompts/round-{round_id}/{seat_id}.prompt.md" if seat_id else "<prompt>"
    answer_rel = f"answers/round-{round_id}/{seat_id}.md" if seat_id else "<answer>"
    summary = adapter_summary(seat, prompt_path=prompt_rel, answer_path=answer_rel)
    adapter = adapter_for_seat(seat)
    if not enabled:
        auth_status = "disabled"
        cli_path = ""
        probe = "disabled"
        login_hint = "Seat is disabled in config."
        blocker = False
        optional_issue = False
        next_action = "enable this seat before live dispatch"
        auth_failure = FAILURE_OPTIONAL_PROVIDER_SKIPPED
    elif auth_probe:
        auth = inspect_seat_auth(seat=seat, cli_overrides=cli_overrides, timeout_seconds=auth_timeout_seconds)
        auth_status = auth["status"]
        cli_path = auth["cli_path"]
        probe = auth["probe"]
        login_hint = auth["login_hint"]
        blocker = auth["blocker"]
        optional_issue = auth["optional_issue"]
        next_action = auth["next_action"]
        auth_failure = _failure_from_auth_status(auth_status)
    else:
        auth_status = "not_probed"
        cli_path = ""
        probe = "not_probed"
        login_hint = login_hint_for_transport(str(seat.get("transport") or ""))
        blocker = False
        optional_issue = False
        next_action = "run auth-preflight or adapter-capabilities without --no-auth-probe before live dispatch"
        auth_failure = ""
    live_dispatch_failure = "" if summary["live_dispatch_available"] else FAILURE_UNSUPPORTED_LIVE_DISPATCH
    failure = auth_failure or live_dispatch_failure
    return {
        "schema": ADAPTER_PREVIEW_SCHEMA,
        "run_id": run_id,
        "round_id": round_id,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "model": summary["model"],
        "reasoning_effort": summary["reasoning_effort"],
        "required": summary["required"],
        "enabled": enabled,
        "timeout_seconds": effective_timeout_seconds(seat),
        "adapter_id": summary["adapter_id"],
        "maturity": summary["maturity"],
        "live_dispatch": summary["live_dispatch"],
        "live_dispatch_available": summary["live_dispatch_available"],
        "live_dispatch_truth": _live_dispatch_truth(summary),
        "cli_name": adapter.cli_name,
        "cli_path": cli_path,
        "auth_status": auth_status,
        "auth_probe": probe,
        "login_hint": login_hint,
        "blocker": blocker,
        "optional_issue": optional_issue,
        "next_action": next_action,
        "failure_classification": failure,
        "command_preview": summary["command_preview"],
    }


def _failure_from_auth_status(status: str) -> str:
    if status == "missing_cli":
        return FAILURE_MISSING_CLI
    if status == "installed_not_logged_in":
        return FAILURE_INSTALLED_NOT_LOGGED_IN
    return ""


def _live_dispatch_truth(summary: dict[str, Any]) -> str:
    if summary.get("live_dispatch_available") is True:
        return "normal runner can collect this adapter through the declared live dispatch path"
    return "normal multiround live dispatch is not implemented; use the named smoke/proof path or manual import"


def _adapter_capabilities_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Adapter Capabilities",
        "",
        f"- schema: `{payload['schema']}`",
        f"- status: `{payload['status']}`",
        f"- run_id: `{payload.get('run_id', '')}`",
        f"- config_path: `{payload.get('config_path', '')}`",
        f"- round_id: `{payload.get('round_id', '')}`",
        "- secret_policy: OAuth tokens, cookies, provider-home raw config, credential file bodies, and shell history are not collected or stored.",
        "",
        "## Seats",
        "",
        "| seat_id | provider | transport | required | enabled | timeout | adapter | maturity | live_dispatch | auth | failure |",
        "|---|---|---|---:|---:|---:|---|---|---|---|---|",
    ]
    for seat in payload.get("seats", []):
        lines.append(
            "| `{seat_id}` | `{provider}` | `{transport}` | {required} | {enabled} | {timeout} | `{adapter_id}` | `{maturity}` | `{live_dispatch}` | `{auth_status}` | `{failure}` |".format(
                seat_id=seat.get("seat_id", ""),
                provider=seat.get("provider", ""),
                transport=seat.get("transport", ""),
                required=seat.get("required") is True,
                enabled=seat.get("enabled") is True,
                timeout=seat.get("timeout_seconds", ""),
                adapter_id=seat.get("adapter_id", ""),
                maturity=seat.get("maturity", ""),
                live_dispatch=seat.get("live_dispatch", ""),
                auth_status=seat.get("auth_status", ""),
                failure=seat.get("failure_classification", "") or "none",
            )
        )
    lines.extend(["", "## Command Previews", ""])
    for seat in payload.get("seats", []):
        lines.append(f"### {seat.get('seat_id', '')}")
        for item in seat.get("command_preview", []):
            safe_item = str(item).replace("`", "'")
            lines.append(f"- `{safe_item}`")
        lines.append("")
    if payload.get("blockers"):
        lines.extend(["## Blockers", ""])
        for item in payload["blockers"]:
            lines.append(f"- `{item['seat_id']}`: `{item['failure_classification']}` {item['next_action']}")
    return "\n".join(lines).rstrip() + "\n"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def cmd_preflight(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    issues: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    provider_config = read_json(base / "config" / "provider-seats.json")

    _check(checks, "run_json_parseable", "pass", ["run.json"])
    _check(checks, "provider_seats_parseable", "pass", ["config/provider-seats.json"])
    for directory in ("prompts", "answers", "logs", "claims", "gates", "orchestrator", "hashes"):
        status = "pass" if (base / directory).is_dir() else "fail"
        _check(checks, f"dir_exists_{directory}", status, [directory])
        if status == "fail":
            issues.append({"check": f"dir_exists_{directory}", "reason": "directory missing"})

    transports = [seat.get("transport", "") for seat in provider_config.get("seats", [])]
    if any(transport == "claude_p" or "headless-p" in transport or "claude -p" in transport for transport in transports):
        _check(checks, "no_claude_p_dependency", "fail", ["config/provider-seats.json"])
        issues.append({"check": "no_claude_p_dependency", "reason": "claude -p style transport configured"})
    else:
        _check(checks, "no_claude_p_dependency", "pass", ["config/provider-seats.json"])

    for seat in provider_config.get("seats", []):
        if seat.get("transport") != "codex_exec_file":
            continue
        execution = seat.get("execution") or {}
        refs = ["config/provider-seats.json"]
        if execution.get("sandbox") == "read-only":
            _check(checks, "codex_exec_file_writable_output", "fail", refs)
            issues.append({"check": "codex_exec_file_writable_output", "reason": f"{seat.get('seat_id')} uses read-only sandbox"})
        elif execution.get("answer_path_required") is True and execution.get("stdout_capture_fallback") is True:
            _check(checks, "codex_exec_file_writable_output", "pass", refs)
        else:
            _check(checks, "codex_exec_file_writable_output", "fail", refs)
            issues.append(
                {
                    "check": "codex_exec_file_writable_output",
                    "reason": f"{seat.get('seat_id')} must require answer file output plus stdout capture fallback",
                }
            )

    if run.get("policy", {}).get("no_hidden_automation") is True:
        _check(checks, "no_hidden_automation_policy", "pass", ["run.json"])
    else:
        _check(checks, "no_hidden_automation_policy", "fail", ["run.json"])
        issues.append({"check": "no_hidden_automation_policy", "reason": "policy disabled or missing"})

    if any(seat.get("team_agents", {}).get("enabled") for seat in provider_config.get("seats", [])):
        _check(
            checks,
            "team_agents_preflight_instructions_emitted",
            "pass",
            ["preflight.md", "config/provider-seats.json"],
            note="live Team Agents tool surface is not called in v0 preflight",
        )

    for seat in provider_config.get("seats", []):
        adapter_blockers = validate_adapter_seat(seat)
        refs = ["config/provider-seats.json"]
        if adapter_blockers:
            for blocker in adapter_blockers:
                check_name = f"adapter_{seat.get('seat_id', '')}_{blocker['check']}"
                _check(checks, check_name, "fail", refs)
                issues.append({"check": check_name, "reason": blocker["reason"]})
        else:
            summary = adapter_summary(seat)
            _check(
                checks,
                f"adapter_{seat.get('seat_id', '')}_registered",
                "pass",
                refs,
                note=f"{summary['adapter_id']} maturity={summary['maturity']} live_dispatch={summary['live_dispatch']}",
            )

    status = "pass" if not issues else "fail"
    verify = {"schema": VERIFY_SCHEMA, "run_id": args.run_id, "status": status, "checks": checks, "blockers": issues}
    write_json(base / "verify.json", verify)
    (base / "preflight.md").write_text(_preflight_markdown(run, provider_config, checks, issues), encoding="utf-8")
    write_artifact_hash(base, "verify.json")
    write_artifact_hash(base, "preflight.md")
    append_event(base, "preflight.completed", run_id=args.run_id, status=status, refs=["preflight.md", "verify.json"])
    if status == "pass":
        run["state"] = "preflight_passed"
        save_run(base, run)
        print("preflight: pass")
        return 0
    run["state"] = "failed"
    save_run(base, run)
    print("preflight: fail", file=sys.stderr)
    return 3


def cmd_status(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    events = read_events(base) if (base / "events.jsonl").exists() else []
    last_event = events[-1] if events else {}
    payload = {
        "schema": "kdh.providers-discuss.status.v1",
        "run_id": args.run_id,
        "state": run.get("state"),
        "current_round": run.get("current_round"),
        "active_round": run.get("active_round", ""),
        "active_seats": run.get("active_seats", []),
        "dispatch_mode": run.get("dispatch_mode", ""),
        "dispatch_started_at": run.get("dispatch_started_at", ""),
        "deliverable_profile": (run.get("deliverable_profile") or {}).get("id", "") if isinstance(run.get("deliverable_profile"), dict) else "",
        "preset": run.get("preset"),
        "last_event": last_event,
        "next_action": _next_action_for_state(run),
        "run_root": str(base),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"run_id: {args.run_id}")
        print(f"state: {payload['state']}")
        print(f"current_round: {payload['current_round']}")
        if payload["active_round"]:
            print(f"active_round: {payload['active_round']}")
            print(f"active_seats: {', '.join(payload['active_seats'])}")
        print(f"next_action: {payload['next_action']}")
        print(f"last_event: {last_event.get('event_id', '')} {last_event.get('type', '')}")
    return 0


def cmd_run_round(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    ensure_round_allowed(run)
    spec = round_spec(run, args.round)
    if args.mode == "dry-run":
        return run_round_dry(base, run, spec)
    if args.mode == "manual-import":
        return run_round_manual_import(base, run, spec, args.answer)
    return run_round_live_dispatch(base, run, spec, parse_cli_path_overrides(args.cli_path))


def run_round_dry(base: Path, run: dict[str, Any], spec: dict[str, Any]) -> int:
    round_id = spec["round_id"]
    seats = provider_seats(base)
    prompt_dir = base / "prompts" / f"round-{round_id}"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    for seat in seats:
        result = write_dry_run_result(base=base, run=run, spec=spec, seat=seat)
        append_event(
            base,
            "provider.dry_run_previewed",
            run_id=run["run_id"],
            round_id=round_id,
            actor="runner",
            seat_id=seat["seat_id"],
            adapter_id=result["adapter"]["adapter_id"],
            required=result["required"],
            status=result["status"],
            failure_classification=result["failure_classification"],
            refs=result["refs"],
        )
    run["state"] = "round_prompt_ready"
    run["current_round"] = round_id
    save_run(base, run)
    print(f"round {round_id}: prompts written")
    return 0


def run_round_manual_import(base: Path, run: dict[str, Any], spec: dict[str, Any], answer_args: list[str]) -> int:
    round_id = spec["round_id"]
    provided = parse_answer_args(answer_args)
    seats = provider_seats(base)
    known = {seat["seat_id"] for seat in seats}
    unknown = sorted(set(provided) - known)
    if unknown:
        raise ValueError(f"manual-import answer supplied for unknown seats: {', '.join(unknown)}")
    manifest_lines = ["# Raw Output Manifest", ""]
    results: list[dict[str, Any]] = []
    for seat in seats:
        seat_id = seat["seat_id"]
        result = write_manual_import_result(base=base, run=run, round_id=round_id, seat=seat, source_path=provided.get(seat_id))
        results.append(result)
        manifest_lines.append(
            "- round: `{round}` seat: `{seat}` status: `{status}` answer: `{answer}` status_path: `{status_path}` proof: `{proof}` failure: `{failure}`".format(
                round=round_id,
                seat=seat_id,
                status=result["status"],
                answer=result["answer_path"] or "none",
                status_path=result["status_path"],
                proof=result["proof_path"],
                failure=result["failure_classification"] or "none",
            )
        )
        event_type = "provider.completed" if result["status"] == "completed" else ("provider.skipped" if result["status"] == "skipped" else "provider.failed")
        append_event(
            base,
            event_type,
            run_id=run["run_id"],
            round_id=round_id,
            actor=seat_id,
            mode="manual-import",
            required=result["required"],
            status=result["status"],
            failure_classification=result["failure_classification"],
            refs=result["refs"],
        )
    (base / "raw-output-manifest.md").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    write_artifact_hash(base, "raw-output-manifest.md")
    failed_required = [item for item in results if item["required"] and item["status"] != "completed"]
    if failed_required:
        verify = {
            "schema": VERIFY_SCHEMA,
            "run_id": run["run_id"],
            "status": "fail",
            "checks": [
                {
                    "check_id": f"VR-{index:03d}",
                    "name": f"provider_required_output_{item['seat_id']}",
                    "status": "fail",
                    "refs": [item["status_path"], item["proof_path"]],
                }
                for index, item in enumerate(failed_required, start=1)
            ],
            "blockers": [
                {
                    "check": "provider_required_output",
                    "seat_id": item["seat_id"],
                    "reason": item["failure_classification"],
                }
                for item in failed_required
            ],
        }
        write_json(base / "verify.json", verify)
        write_artifact_hash(base, "verify.json")
        run["state"] = "failed"
        run["current_round"] = round_id
        save_run(base, run)
        print(f"round {round_id}: required provider failure", file=sys.stderr)
        return 3
    run["state"] = "round_outputs_collected"
    run["current_round"] = round_id
    save_run(base, run)
    print(f"round {round_id}: manual answers imported")
    return 0


def run_round_live_dispatch(base: Path, run: dict[str, Any], spec: dict[str, Any], cli_overrides: dict[str, Path]) -> int:
    round_id = spec["round_id"]
    seats = provider_seats(base)
    manifest_lines = ["# Raw Output Manifest", ""]
    indexed_results: dict[int, dict[str, Any]] = {}
    seats_to_dispatch: list[tuple[int, dict[str, Any]]] = []
    for index, seat in enumerate(seats):
        reused = _completed_live_dispatch_result(base=base, run=run, spec=spec, seat=seat)
        if reused is None:
            seats_to_dispatch.append((index, seat))
        else:
            indexed_results[index] = reused
    run["state"] = "round_running"
    run["current_round"] = round_id
    run["active_round"] = round_id
    run["active_seats"] = [seat["seat_id"] for _, seat in seats_to_dispatch]
    run["dispatch_mode"] = "live-dispatch"
    run["dispatch_started_at"] = utc_now()
    save_run(base, run)
    append_event(
        base,
        "round.live_dispatch_started",
        run_id=run["run_id"],
        round_id=round_id,
        seats=[seat["seat_id"] for seat in seats],
        dispatch_seats=[seat["seat_id"] for _, seat in seats_to_dispatch],
        reused_completed_seats=[result["seat_id"] for result in indexed_results.values()],
    )
    if seats_to_dispatch:
        with ThreadPoolExecutor(max_workers=len(seats_to_dispatch)) as executor:
            futures = {
                executor.submit(_live_dispatch_seat, base, run, spec, seat, cli_overrides): index
                for index, seat in seats_to_dispatch
            }
            for future in as_completed(futures):
                indexed_results[futures[future]] = future.result()
    results = [indexed_results[index] for index in range(len(seats))]
    for result in results:
        seat_id = result["seat_id"]
        manifest_lines.append(
            "- round: `{round}` seat: `{seat}` mode: `live-dispatch` reused: `{reused}` status: `{status}` answer: `{answer}` status_path: `{status_path}` proof: `{proof}` failure: `{failure}`".format(
                round=round_id,
                seat=seat_id,
                reused=result.get("reused") is True,
                status=result["status"],
                answer=result["answer_path"] or "none",
                status_path=result["status_path"],
                proof=result["proof_path"],
                failure=result["failure_classification"] or "none",
            )
        )
        if result.get("reused") is True:
            event_type = "provider.reused"
        else:
            event_type = (
                "provider.completed"
                if result["status"] == "completed"
                else ("provider.skipped" if result["status"] == "skipped" else ("provider.pending" if result["status"] == "pending" else "provider.failed"))
            )
        append_event(
            base,
            event_type,
            run_id=run["run_id"],
            round_id=round_id,
            actor=seat_id,
            mode="live-dispatch",
            required=result["required"],
            status=result["status"],
            failure_classification=result["failure_classification"],
            refs=result["refs"],
        )
    (base / "raw-output-manifest.md").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    write_artifact_hash(base, "raw-output-manifest.md")
    unsupported_required = [
        item
        for item in results
        if item["required"] and item["status"] != "completed" and item["failure_classification"] == FAILURE_UNSUPPORTED_LIVE_DISPATCH
    ]
    failed_required = [
        item
        for item in results
        if item["required"] and item["status"] != "completed" and item["failure_classification"] != FAILURE_UNSUPPORTED_LIVE_DISPATCH
    ]
    _clear_active_dispatch(run)
    if failed_required:
        verify = {
            "schema": VERIFY_SCHEMA,
            "run_id": run["run_id"],
            "status": "fail",
            "checks": [
                {
                    "check_id": f"VR-{index:03d}",
                    "name": f"provider_required_output_{item['seat_id']}",
                    "status": "fail",
                    "refs": [item["status_path"], item["proof_path"]],
                }
                for index, item in enumerate(failed_required, start=1)
            ],
            "blockers": [
                {
                    "check": "provider_required_output",
                    "seat_id": item["seat_id"],
                    "reason": item["failure_classification"],
                }
                for item in failed_required
            ],
        }
        write_json(base / "verify.json", verify)
        write_artifact_hash(base, "verify.json")
        run["state"] = "failed"
        run["current_round"] = round_id
        save_run(base, run)
        print(f"round {round_id}: required provider failure", file=sys.stderr)
        return 3
    if unsupported_required:
        run["state"] = "round_prompt_ready"
        run["current_round"] = round_id
        save_run(base, run)
        append_event(
            base,
            "round.live_dispatch_partial",
            run_id=run["run_id"],
            round_id=round_id,
            pending_seats=[item["seat_id"] for item in unsupported_required],
            refs=["raw-output-manifest.md"],
        )
        print(f"round {round_id}: live dispatch partial; provider answers still needed", file=sys.stderr)
        return 2
    run["state"] = "round_outputs_collected"
    run["current_round"] = round_id
    save_run(base, run)
    print(f"round {round_id}: live dispatch completed")
    return 0


def _completed_live_dispatch_result(base: Path, run: dict[str, Any], spec: dict[str, Any], seat: dict[str, Any]) -> dict[str, Any] | None:
    round_id = spec["round_id"]
    seat_id = str(seat.get("seat_id") or "")
    status_rel = f"logs/round-{round_id}/{seat_id}.status.json"
    answer_rel = f"answers/round-{round_id}/{seat_id}.md"
    status_path = base / status_rel
    if not status_path.exists():
        return None
    try:
        status = read_json(status_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(status, dict):
        return None
    if status.get("status") != "completed":
        return None
    answer_from_status = str(status.get("answer_path") or answer_rel)
    proof_from_status = str(status.get("proof_path") or f"logs/round-{round_id}/{seat_id}.proof.json")
    if not answer_from_status or not (base / answer_from_status).exists():
        return None
    if not proof_from_status or not (base / proof_from_status).exists():
        return None
    return {
        "schema": ADAPTER_RESULT_SCHEMA,
        "seat_id": seat_id,
        "provider": status.get("provider") or seat.get("provider", ""),
        "transport": status.get("transport") or seat.get("transport", ""),
        "model": status.get("model") or seat.get("model") or (seat.get("execution") if isinstance(seat.get("execution"), dict) else {}).get("model") or "",
        "status": "completed",
        "answer_path": answer_from_status,
        "status_path": status_rel,
        "proof_path": proof_from_status,
        "log_path": status.get("log_path", ""),
        "exit_code": status.get("exit_code"),
        "failure_classification": "",
        "required": seat.get("required", True) is not False,
        "refs": [answer_from_status, status_rel, proof_from_status],
        "adapter": adapter_summary(seat),
        "reused": True,
    }


def _clear_active_dispatch(run: dict[str, Any]) -> None:
    for key in ("active_round", "active_seats", "dispatch_mode", "dispatch_started_at"):
        run.pop(key, None)


def _live_dispatch_seat(
    base: Path,
    run: dict[str, Any],
    spec: dict[str, Any],
    seat: dict[str, Any],
    cli_overrides: dict[str, Path],
) -> dict[str, Any]:
    transport = seat.get("transport")
    if transport == "codex_exec_file":
        return run_codex_live_dispatch(
            base=base,
            run=run,
            spec=spec,
            seat=seat,
            codex_bin=_resolve_live_cli(seat=seat, cli_overrides=cli_overrides, default_name="codex"),
            timeout_seconds=effective_timeout_seconds(seat),
        )
    if transport == "gemini_cli":
        return run_gemini_live_dispatch(
            base=base,
            run=run,
            spec=spec,
            seat=seat,
            gemini_bin=_resolve_live_cli(seat=seat, cli_overrides=cli_overrides, default_name="gemini"),
            timeout_seconds=effective_timeout_seconds(seat),
        )
    if transport == "claude_k_team_agents":
        claude_bin = _resolve_live_cli(seat=seat, cli_overrides=cli_overrides, default_name="claude")
        if not claude_bin:
            return _missing_live_cli_result(base=base, run=run, spec=spec, seat=seat, cli_name="claude")
        result = run_claude_team_agents_smoke(
            base=base,
            run=run,
            round_id=spec["round_id"],
            seat=seat,
            claude_bin=claude_bin,
            launch_cwd=None,
            auto_trust=True,
            experimental_agent_teams=True,
            timeout_seconds=None,
            trigger_mode="prompt_only",
            provider_result_artifacts=True,
        )
        return {
            "schema": ADAPTER_RESULT_SCHEMA,
            "seat_id": seat["seat_id"],
            "provider": seat.get("provider", ""),
            "transport": "claude_k_team_agents",
            "model": seat.get("model") or seat.get("execution", {}).get("model") or "",
            "status": "completed" if result["status"] == "pass" else "failed",
            "answer_path": result.get("answer_path", ""),
            "status_path": result.get("status_path", ""),
            "proof_path": result["proof_path"],
            "log_path": f"logs/round-{spec['round_id']}/{seat['seat_id']}.transcript.ansi",
            "exit_code": None,
            "failure_classification": "" if result["status"] == "pass" else FAILURE_PROOF_FAILED,
            "required": seat.get("required", True) is not False,
            "refs": [
                ref
                for ref in (
                    result.get("answer_path", ""),
                    result.get("status_path", ""),
                    result.get("proof_path", ""),
                )
                if ref
            ],
            "adapter": adapter_summary(seat),
        }
    prompt_result = write_round_prompt(base=base, run=run, spec=spec, seat=seat)
    return {
        **prompt_result,
        "status": "pending",
        "answer_path": "",
        "status_path": "",
        "proof_path": "",
        "exit_code": None,
        "failure_classification": FAILURE_UNSUPPORTED_LIVE_DISPATCH,
        "refs": prompt_result["refs"],
    }


def _missing_live_cli_result(*, base: Path, run: dict[str, Any], spec: dict[str, Any], seat: dict[str, Any], cli_name: str) -> dict[str, Any]:
    prompt_result = write_round_prompt(base=base, run=run, spec=spec, seat=seat)
    round_id = spec["round_id"]
    seat_id = seat["seat_id"]
    status_rel = prompt_result["status_path"]
    proof_rel = prompt_result["proof_path"]
    status_payload = {
        "schema": ADAPTER_STATUS_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "adapter_id": adapter_summary(seat)["adapter_id"],
        "mode": "live-dispatch",
        "status": "failed",
        "required": seat.get("required", True) is not False,
        "answer_path": "",
        "proof_path": proof_rel,
        "exit_code": None,
        "timed_out": False,
        "failure_classification": FAILURE_MISSING_CLI,
        "cli_name": cli_name,
    }
    proof_payload = {
        "schema": "kdh.providers-discuss.transport-proof.v1",
        "transport": seat.get("transport", ""),
        "answer_path": "",
        "status_path": status_rel,
        "completion_marker": "",
        "exit_code": None,
        "timed_out": False,
        "killed": False,
        "blocked_reason": FAILURE_MISSING_CLI,
    }
    write_json(base / status_rel, status_payload)
    status_sha = write_artifact_hash(base, status_rel)
    write_json(base / proof_rel, proof_payload)
    proof_sha = write_artifact_hash(base, proof_rel)
    return {
        **prompt_result,
        "status": "failed",
        "answer_path": "",
        "status_path": status_rel,
        "proof_path": proof_rel,
        "exit_code": None,
        "failure_classification": FAILURE_MISSING_CLI,
        "refs": [*prompt_result["refs"], status_rel, proof_rel],
        "sha256": {"prompt": prompt_result["sha256"], "status": status_sha, "proof": proof_sha},
    }


def cmd_gate(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    ensure_not_terminal(run, "write a gate")
    round_spec(run, args.round)
    provider_checks, provider_blockers = required_provider_blockers_for_round(base, args.round, provider_seats(base))
    claim_map_path = base / "claims" / f"round-{args.round}-claim-map.json"
    claim_result = validate_claim_map(claim_map_path)
    unsupported = claim_result["unsupported_load_bearing_claims"]
    blockers = [*provider_blockers, *claim_result["blockers"]]
    deliverable_gate: dict[str, Any] | None = None
    if args.terminal:
        _write_final_artifacts_from_answers(base=base, run=run, final_round=args.round)
        deliverable_gate = _deliverable_gate_payload(base=base, run=run, final_round=args.round)
        blockers.extend(deliverable_gate.get("blockers", []))
    if claim_result.get("semantic_claim_count", 0) == 0:
        blockers.append(
            {
                "check": "semantic_claims_missing",
                "reason": "claim-map contains no semantic claims; provider-output receipts are not enough for a discussion gate",
            }
        )
    if claim_result.get("load_bearing_claim_count", 0) == 0:
        blockers.append(
            {
                "check": "load_bearing_claims_missing",
                "reason": "claim-map contains no load-bearing claims to evaluate or carry forward",
            }
        )
    if blockers:
        verdict = "return_to_round"
    elif unsupported > 0:
        verdict = "return_to_round"
        blockers = [
            *blockers,
            {
                "reason": "unsupported load-bearing claims",
                "unsupported_load_bearing_claims": unsupported,
            },
        ]
    elif args.terminal:
        verdict = "proceed_to_implementation"
    else:
        verdict = "proceed_to_next_round"
    gate_payload = {
        "schema": GATE_SCHEMA,
        "run_id": args.run_id,
        "round_id": args.round,
        "verdict": verdict,
        "unsupported_load_bearing_claims": unsupported,
        "semantic_claims": claim_result.get("semantic_claim_count", 0),
        "load_bearing_claims": claim_result.get("load_bearing_claim_count", 0),
        "blockers": blockers,
        "basis": claim_result["basis"] + [item.get("seat_id", "") for item in provider_blockers if item.get("seat_id")],
        "next_action": _next_action_for_gate(run, args.round, verdict),
    }
    if deliverable_gate is not None:
        gate_payload["deliverable_gate"] = deliverable_gate
    gate_rel = f"gates/round-{args.round}-gate.md"
    (base / gate_rel).write_text(_gate_markdown(args.round, gate_payload), encoding="utf-8")
    write_artifact_hash(base, gate_rel)
    verify = {
        "schema": VERIFY_SCHEMA,
        "run_id": args.run_id,
        "status": "pass" if verdict.startswith("proceed") else "fail",
        "checks": provider_checks + claim_result["checks"] + ((deliverable_gate or {}).get("checks", [])),
        "blockers": blockers,
    }
    write_json(base / "verify.json", verify)
    write_artifact_hash(base, "verify.json")
    append_event(base, "gate.written", run_id=args.run_id, round_id=args.round, verdict=verdict, refs=[gate_rel])
    run["state"] = "round_gated" if verdict.startswith("proceed") else "failed"
    run["current_round"] = args.round
    save_run(base, run)
    print(verdict)
    return 0 if verdict.startswith("proceed") else 1


def cmd_orchestrate(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    ensure_not_terminal(run, "orchestrate")
    after = args.after_round
    claim_map_path = base / "claims" / f"round-{after}-claim-map.json"
    gate_path = base / "gates" / f"round-{after}-gate.md"
    if not gate_path.exists():
        raise ValueError(f"gate missing: {gate_path}")
    gate_payload = _read_gate_payload(gate_path)
    claim_map = read_json(claim_map_path)
    carried = [
        claim
        for claim in claim_map.get("claims", [])
        if claim.get("status") in {"unsupported", "contested", "deferred"} or claim.get("load_bearing") is True
    ]
    next_round = "" if gate_payload.get("verdict") in terminal_verdicts() else next_round_id(run, after)
    review_rel = f"orchestrator/round-{after}-review.md"
    delta_rel = f"prompts/round-{next_round}.prompt-delta.md" if next_round else f"prompts/round-{after}.terminal-delta.md"
    (base / review_rel).write_text(_orchestrator_review(base, run, after, next_round, carried, gate_path), encoding="utf-8")
    (base / delta_rel).write_text(_prompt_delta(base, run, after, next_round, carried), encoding="utf-8")
    write_artifact_hash(base, review_rel)
    write_artifact_hash(base, delta_rel)
    append_event(base, "orchestrator.review_written", run_id=args.run_id, round_id=after, refs=[review_rel])
    append_event(base, "prompt_delta.written", run_id=args.run_id, round_id=next_round or after, refs=[delta_rel])
    run["state"] = "next_round_ready" if next_round else "finalizing"
    run["current_round"] = next_round or after
    save_run(base, run)
    print(delta_rel)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    blockers = []
    checks = []
    for rel in ("run.json", "events.jsonl", "config/provider-seats.json"):
        path = base / rel
        status = "pass" if path.exists() else "fail"
        _check(checks, f"{rel}_exists", status, [rel])
        if status == "fail":
            blockers.append({"check": f"{rel}_exists", "reason": "missing"})
    try:
        read_events(base)
        _check(checks, "events_jsonl_parseable", "pass", ["events.jsonl"])
    except ValueError as exc:
        _check(checks, "events_jsonl_parseable", "fail", ["events.jsonl"], str(exc))
        blockers.append({"check": "events_jsonl_parseable", "reason": str(exc)})
    try:
        provider_checks, provider_blockers = existing_required_provider_failures(base, provider_seats(base))
        checks.extend(provider_checks)
        blockers.extend(provider_blockers)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _check(checks, "provider_status_scan", "fail", ["logs"], str(exc))
        blockers.append({"check": "provider_status_scan", "reason": str(exc)})
    hash_checks, hash_blockers = verify_recorded_artifact_hashes(base)
    checks.extend(hash_checks)
    blockers.extend(hash_blockers)
    status = "pass" if not blockers else "fail"
    payload = {"schema": VERIFY_SCHEMA, "run_id": args.run_id, "status": status, "checks": checks, "blockers": blockers}
    write_json(base / "verify.json", payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"verify: {status}")
    return 0 if status == "pass" else 1


def cmd_verify_proof(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    proof_path = args.proof if args.proof.is_absolute() else base / args.proof
    proof = read_json(proof_path)
    proof_ref = _proof_ref(base, proof_path)
    if args.kind == "transport":
        result = validate_transport_proof(proof, base)
    else:
        result = validate_team_agents_proof(proof, base)
    payload = {
        "schema": VERIFY_SCHEMA,
        "run_id": args.run_id,
        "status": result["status"],
        "proof_kind": args.kind,
        "proof_path": proof_ref,
        "checks": result["checks"],
        "blockers": result["blockers"],
    }
    proof_verify_ref = _proof_verify_ref(base, proof_path)
    write_json(base / proof_verify_ref, payload)
    write_artifact_hash(base, proof_verify_ref)
    append_event(base, "proof.verified", run_id=args.run_id, proof_kind=args.kind, status=result["status"], refs=[proof_ref, proof_verify_ref])
    if args.kind == "team-agents" and result["status"] == "pass":
        _reconcile_team_agents_smoke(base, args.run_id, proof, proof_path, proof_ref)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"verify-proof: {result['status']}")
    return 0 if result["status"] == "pass" else 1


def _proof_ref(base: Path, proof_path: Path) -> str:
    try:
        return str(proof_path.relative_to(base))
    except ValueError:
        return str(proof_path)


def _proof_verify_ref(base: Path, proof_path: Path) -> str:
    try:
        rel = proof_path.relative_to(base)
    except ValueError:
        rel = Path("proof-verifications") / (proof_path.name + ".verify.json")
    return rel.with_name(rel.stem + ".verify.json").as_posix()


def _reconcile_team_agents_smoke(base: Path, run_id: str, proof: dict[str, Any], proof_path: Path, proof_ref: str) -> None:
    run = load_run(base)
    last = run.get("last_team_agents_smoke")
    if not isinstance(last, dict):
        return
    last_proof = str(last.get("proof_path") or "")
    if not _same_proof_ref(base, last_proof, proof_path, proof_ref):
        return

    previous_state = str(run.get("state") or "")
    previous_status = str(last.get("status") or "")
    changed_refs = ["run.json"]

    run["state"] = "team_agents_smoke_completed"
    last["status"] = "pass"
    last["blocked_reason"] = ""
    last["team_name"] = str(proof.get("team_name") or last.get("team_name") or "")
    if "timed_out" in proof:
        last["timed_out"] = proof.get("timed_out")
    if "killed" in proof:
        last["killed"] = proof.get("killed")
    if "workspace_trust_auto_accepted" in proof:
        last["workspace_trust_auto_accepted"] = proof.get("workspace_trust_auto_accepted")
    if "experimental_agent_teams_enabled" in proof:
        last["experimental_agent_teams_enabled"] = proof.get("experimental_agent_teams_enabled")
    if "tmux_env_stripped" in proof:
        last["tmux_env_stripped"] = proof.get("tmux_env_stripped")
    if "team_runtime_cleanup" in proof:
        last["team_runtime_cleanup"] = proof.get("team_runtime_cleanup")
    last["trigger_mode"] = proof.get("trigger_mode") or last.get("trigger_mode") or "legacy_unspecified"
    run["last_team_agents_smoke"] = last
    save_run(base, run)
    write_artifact_hash(base, "run.json")

    if _reconcile_summary_status(base, [proof_ref, str(proof_path)], "pass"):
        changed_refs.append("summary.md")
        write_artifact_hash(base, "summary.md")

    append_event(
        base,
        "proof.reconciled",
        run_id=run_id,
        proof_kind="team-agents",
        status="pass",
        previous_state=previous_state,
        previous_status=previous_status,
        refs=changed_refs + [proof_ref],
    )


def _same_proof_ref(base: Path, current_ref: str, proof_path: Path, proof_ref: str) -> bool:
    if current_ref in {proof_ref, str(proof_path)}:
        return True
    try:
        return (base / current_ref).resolve() == proof_path.resolve()
    except OSError:
        return False


def _reconcile_summary_status(base: Path, proof_refs: list[str], status: str) -> bool:
    summary = base / "summary.md"
    if not summary.exists():
        return False
    lines = summary.read_text(encoding="utf-8").splitlines()
    proof_markers = {f"- proof: `{ref}`" for ref in proof_refs if ref}
    proof_index = -1
    for index, line in enumerate(lines):
        if line.strip() in proof_markers:
            proof_index = index
    if proof_index < 0:
        return False
    start = proof_index
    while start > 0 and not lines[start].startswith("## "):
        start -= 1
    end = proof_index + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    changed = False
    for index in range(start, end):
        if lines[index].startswith("- status: `"):
            new_line = f"- status: `{status}`"
            if lines[index] != new_line:
                lines[index] = new_line
                changed = True
            break
    if not any(line == "- reconciled_by: `verify-proof`" for line in lines[start:end]):
        lines.insert(proof_index + 1, "- reconciled_by: `verify-proof`")
        changed = True
    if changed:
        summary.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return changed


def cmd_smoke_claude_k(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    ensure_not_terminal(run, "run claude-k smoke")
    round_spec(run, args.round)
    seat = find_provider_seat(base, args.seat)
    if seat.get("transport") != "claude_k":
        raise ValueError(f"seat {args.seat} is not claude_k transport")
    result = run_claude_k_smoke(
        base=base,
        run=run,
        round_id=args.round,
        seat=seat,
        claude_bin=args.claude_bin,
        launch_cwd=args.launch_cwd,
        auto_trust=args.auto_trust,
        timeout_seconds=args.timeout_seconds,
        timeout_override_reason=args.override_reason,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"smoke-claude-k: {result['status']}")
        print(f"proof: {result['proof_path']}")
    return 0 if result["status"] == "pass" else 1


def cmd_smoke_claude_team_agents(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    ensure_not_terminal(run, "run claude-k Team Agents smoke")
    round_spec(run, args.round)
    seat = find_provider_seat(base, args.seat)
    if seat.get("transport") != "claude_k_team_agents":
        raise ValueError(f"seat {args.seat} is not claude_k_team_agents transport")
    result = run_claude_team_agents_smoke(
        base=base,
        run=run,
        round_id=args.round,
        seat=seat,
        claude_bin=args.claude_bin,
        launch_cwd=args.launch_cwd,
        auto_trust=args.auto_trust,
        experimental_agent_teams=args.experimental_agent_teams,
        timeout_seconds=args.timeout_seconds,
        trigger_mode=args.trigger_mode,
        timeout_override_reason=args.override_reason,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"smoke-claude-team-agents: {result['status']}")
        print(f"team: {result['team_name']}")
        print(f"proof: {result['proof_path']}")
    return 0 if result["status"] == "pass" else 1


def cmd_smoke_gemini_headless(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    ensure_not_terminal(run, "run gemini headless smoke")
    round_spec(run, args.round)
    seat = find_provider_seat(base, args.seat)
    if seat.get("transport") != "gemini_cli":
        raise ValueError(f"seat {args.seat} is not gemini_cli transport")
    result = run_gemini_headless_smoke(
        base=base,
        run=run,
        round_id=args.round,
        seat=seat,
        gemini_bin=args.gemini_bin,
        timeout_seconds=_effective_smoke_timeout(seat, args.timeout_seconds, args.override_reason),
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"smoke-gemini-headless: {result['status']}")
        print(f"proof: {result['proof_path']}")
    return 0 if result["status"] == "pass" else 1


def _effective_smoke_timeout(seat: dict[str, Any], override: int | None, override_reason: str = "") -> int:
    selected = effective_timeout_seconds(seat)
    if override is None:
        return selected
    if override < 1:
        raise ValueError("timeout-seconds must be positive")
    if override != selected and not override_reason.strip():
        raise ValueError(
            "timeout override requires --override-reason; "
            f"selected timeout_seconds={selected}, requested={override}"
        )
    return override


def cmd_team_agents_prompt(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    round_id = args.round or str(run.get("current_round") or "R1")
    round_spec(run, round_id)
    seat = find_provider_seat(base, args.seat)
    if seat.get("transport") != "claude_k_team_agents":
        raise ValueError(f"seat {args.seat} is not claude_k_team_agents transport")
    payload = _team_agents_prompt_payload(base=base, run=run, round_id=round_id, seat=seat)
    output_path = _run_output_path(base, args.output) if args.output else (base / payload["prompt_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload["prompt_markdown"], encoding="utf-8")
    payload["output_path"] = str(output_path)
    payload["output_ref"] = _proof_ref(base, output_path)
    if _is_relative_to(output_path, base):
        rel = output_path.relative_to(base).as_posix()
        payload["prompt_path"] = rel
        payload["sha256"] = write_artifact_hash(base, rel)
        append_event(base, "team_agents_prompt.written", run_id=args.run_id, round_id=round_id, actor=args.seat, refs=[rel])
    if args.json:
        printable = {key: value for key, value in payload.items() if key != "prompt_markdown"}
        print(json.dumps(printable, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"team-agents-prompt: {output_path}")
    return 0


def cmd_team_agents_proof_report(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    proof_path = args.proof if args.proof.is_absolute() else base / args.proof
    proof = read_json(proof_path)
    payload = _team_agents_proof_report_payload(base=base, run_id=args.run_id, proof=proof, proof_path=proof_path)
    if args.output:
        output_path = _run_output_path(base, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix == ".json":
            write_json(output_path, payload)
        else:
            output_path.write_text(_team_agents_proof_report_markdown(payload), encoding="utf-8")
        payload["output_path"] = str(output_path)
        payload["output_ref"] = _proof_ref(base, output_path)
        if _is_relative_to(output_path, base):
            rel = output_path.relative_to(base).as_posix()
            payload["sha256"] = write_artifact_hash(base, rel)
            append_event(base, "team_agents_proof_report.written", run_id=args.run_id, status=payload["status"], refs=[rel, payload["proof_ref"]])
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_team_agents_proof_report_markdown(payload), end="")
    return 0 if payload["status"] == "pass" else 1


def _team_agents_prompt_payload(*, base: Path, run: dict[str, Any], round_id: str, seat: dict[str, Any]) -> dict[str, Any]:
    seat_id = str(seat.get("seat_id") or "claude_team")
    team_cfg = seat.get("team_agents") if isinstance(seat.get("team_agents"), dict) else {}
    role_specs = team_role_specs(team_cfg)
    roles = [role["name"] for role in role_specs]
    required_messages = int(team_cfg.get("required_direct_message_count") or 6)
    run_id = str(run["run_id"])
    team_name = f"providers-{round_id.lower()}-{run_id}"
    answer_rel = f"answers/round-{round_id}/{seat_id}.md"
    status_rel = f"logs/round-{round_id}/{seat_id}.status.json"
    proof_rel = f"logs/round-{round_id}/{seat_id}.proof.json"
    prompt_rel = f"prompts/round-{round_id}/{seat_id}.team-agents-prompt.md"
    bullet_rels = [f"logs/round-{round_id}/{role['artifact_label']}.bullet.txt" for role in role_specs]
    prompt_markdown = _team_agents_prompt_markdown(
        run=run,
        round_id=round_id,
        seat_id=seat_id,
        team_name=team_name,
        role_specs=role_specs,
        required_messages=required_messages,
        base=base,
        answer_rel=answer_rel,
        status_rel=status_rel,
        proof_rel=proof_rel,
        bullet_rels=bullet_rels,
    )
    return {
        "schema": "kdh.providers-discuss.team-agents-prompt.v1",
        "run_id": run_id,
        "round_id": round_id,
        "seat_id": seat_id,
        "team_name": team_name,
        "trigger_mode": "prompt_only",
        "roles": roles,
        "agent_profile_roles": [
            {
                "role": role["name"],
                "agent_profile_id": role["agent_profile"]["profile_id"],
            }
            for role in role_specs
            if isinstance(role.get("agent_profile"), dict)
        ],
        "required_direct_message_count": required_messages,
        "prompt_path": prompt_rel,
        "answer_path": answer_rel,
        "status_path": status_rel,
        "proof_path": proof_rel,
        "bullet_paths": bullet_rels,
        "completion_marker": "KDH_CLAUDE_DONE",
        "prompt_markdown": prompt_markdown,
    }


def _run_output_path(base: Path, output: Path) -> Path:
    return output if output.is_absolute() else base / output


def _team_agents_prompt_markdown(
    *,
    run: dict[str, Any],
    round_id: str,
    seat_id: str,
    team_name: str,
    role_specs: list[dict[str, Any]],
    required_messages: int,
    base: Path,
    answer_rel: str,
    status_rel: str,
    proof_rel: str,
    bullet_rels: list[str],
) -> str:
    roles = [role["name"] for role in role_specs]
    role_lines = "\n".join(f"- `{role}` must write `{base / rel}`" for role, rel in zip(roles, bullet_rels))
    profile_sections = []
    for role in role_specs:
        profile = role.get("agent_profile")
        if isinstance(profile, dict):
            profile_sections.append(render_agent_profile_contract(profile, assigned_to=f"team_role:{role['name']}"))
    profile_contracts = "\n".join(profile_sections).rstrip()
    if not profile_contracts:
        profile_contracts = "No agent profiles were assigned to individual Team Agents roles."
    status_template = {
        "schema": TEAM_AGENTS_STATUS_SCHEMA,
        "trigger_mode": "prompt_only",
        "verdict": "admitted",
        "team_name": team_name,
        "team_create_used": True,
        "task_create_count": len(roles),
        "agent_calls_with_team_name": len(roles),
        "direct_teammate_messages_required": required_messages,
        "direct_teammate_messages_observed": required_messages,
        "ordinary_agent_delegation_only": False,
        "summary_only_delegation": False,
        "blocked_reason": "",
    }
    return """# KDH Team Agents Prompt-Only Contract

Use this prompt in Claude Code for a providers-discuss Team Agents seat. This command only prepares the contract; it does not launch Claude, install hooks, or mutate provider settings.

## Run Contract

- run_id: `{run_id}`
- round_id: `{round_id}`
- seat_id: `{seat_id}`
- team_name: `{team_name}`
- trigger_mode: `prompt_only`
- run_root: `{run_root}`
- answer_path: `{answer_path}`
- status_path: `{status_path}`
- expected_proof_path: `{proof_path}`
- completion_marker: `KDH_CLAUDE_DONE`

## Mandatory Team Protocol

1. Use `TeamCreate` for team `{team_name}`.
2. Use `TaskCreate` for these roles: {roles}.
3. Launch each teammate with `Agent` scoped to team `{team_name}`.
4. Use `SendMessage` for at least {required_messages} teammate-to-teammate messages that include run_id `{run_id}`.
5. Each teammate must write a bullet artifact:
{role_lines}
6. The lead must write the final answer to `{answer_path_abs}`.
7. The lead must write status JSON to `{status_path_abs}` using this shape:

```json
{status_template}
```

8. Do not answer directly until the answer, status, and bullet artifacts are written.
9. Do not impose a character or word limit. Preserve concrete evidence, paths, commands, counts, failure causes, and route-back details.
10. End by printing `KDH_CLAUDE_DONE`.

## Agent Profile Contracts

{profile_contracts}
""".format(
        run_id=run["run_id"],
        round_id=round_id,
        seat_id=seat_id,
        team_name=team_name,
        run_root=base,
        answer_path=answer_rel,
        status_path=status_rel,
        proof_path=proof_rel,
        roles=", ".join(roles),
        required_messages=required_messages,
        role_lines=role_lines,
        profile_contracts=profile_contracts,
        answer_path_abs=base / answer_rel,
        status_path_abs=base / status_rel,
        status_template=json.dumps(status_template, ensure_ascii=False, indent=2, sort_keys=True),
    )


def _team_agents_proof_report_payload(*, base: Path, run_id: str, proof: dict[str, Any], proof_path: Path) -> dict[str, Any]:
    result = validate_team_agents_proof(proof, base)
    status = result["status"]
    return {
        "schema": "kdh.providers-discuss.team-agents-proof-report.v1",
        "run_id": run_id,
        "status": status,
        "evidence_verdict": "valid_real_team_agents_evidence" if status == "pass" else "not_valid_team_agents_evidence",
        "proof_path": str(proof_path),
        "proof_ref": _proof_ref(base, proof_path),
        "trigger_mode": str(proof.get("trigger_mode") or "legacy_unspecified"),
        "team_name": str(proof.get("team_name") or proof.get("team_session_id") or ""),
        "team_create_used": proof.get("team_create_used") is True,
        "task_create_count": int(proof.get("task_create_count", 0) or 0),
        "required_task_count": int(proof.get("required_task_count", 0) or 0),
        "agent_calls_with_team_name": int(proof.get("agent_calls_with_team_name", 0) or 0),
        "required_team_scoped_agent_calls": int(proof.get("required_team_scoped_agent_calls", 0) or 0),
        "direct_teammate_messages_observed": int(proof.get("direct_teammate_messages_observed", 0) or 0),
        "direct_teammate_messages_required": int(proof.get("direct_teammate_messages_required", 0) or 0),
        "ordinary_agent_delegation_only": proof.get("ordinary_agent_delegation_only") is True,
        "summary_only_delegation": proof.get("summary_only_delegation") is True,
        "checks": result["checks"],
        "blockers": result["blockers"],
    }


def _team_agents_proof_report_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Team Agents Proof Report",
        "",
        f"- schema: `{payload['schema']}`",
        f"- status: `{payload['status']}`",
        f"- evidence_verdict: `{payload['evidence_verdict']}`",
        f"- run_id: `{payload['run_id']}`",
        f"- proof_ref: `{payload['proof_ref']}`",
        f"- trigger_mode: `{payload['trigger_mode']}`",
        f"- team_name: `{payload['team_name']}`",
        f"- team_create_used: `{payload['team_create_used']}`",
        f"- task_create_count: `{payload['task_create_count']}` / `{payload['required_task_count']}`",
        f"- agent_calls_with_team_name: `{payload['agent_calls_with_team_name']}` / `{payload['required_team_scoped_agent_calls']}`",
        f"- direct_messages: `{payload['direct_teammate_messages_observed']}` / `{payload['direct_teammate_messages_required']}`",
        f"- ordinary_agent_delegation_only: `{payload['ordinary_agent_delegation_only']}`",
        f"- summary_only_delegation: `{payload['summary_only_delegation']}`",
        "",
        "## Checks",
        "",
    ]
    for check in payload.get("checks", []):
        lines.append(f"- `{check.get('status', '')}` {check.get('name', '')}: {check.get('note', '')}")
    if payload.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        for blocker in payload["blockers"]:
            lines.append(f"- `{blocker.get('check', '')}`: {blocker.get('reason', '')}")
    return "\n".join(lines).rstrip() + "\n"


def cmd_resume(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    if run.get("state") == "cancelled":
        raise ValueError("cancelled run cannot resume; route-back: start a new run")
    hint = _next_action_for_state(run)
    run["last_resume_hint"] = hint
    save_run(base, run)
    append_event(base, "run.resume_checked", run_id=args.run_id, state=run.get("state"), next_action=hint)
    print(f"resume: {hint}")
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    if args.max_steps < 1:
        raise ValueError("--max-steps must be positive")
    base = must_run_root(args.root, args.run_id)
    cli_overrides = parse_cli_path_overrides(args.cli_path)
    actions: list[dict[str, Any]] = []
    stop_reason = ""
    exit_code = 0

    for _ in range(args.max_steps):
        run = load_run(base)
        state = str(run.get("state") or "")
        current_round = str(run.get("current_round") or _first_round_id(run))
        if state == "finished":
            stop_reason = "finished"
            break
        if state in {"cancelled", "failed"}:
            stop_reason = f"run_{state}"
            exit_code = 1
            break
        if state in {"created", "preflight_ready"}:
            rc = _advance_call(cmd_preflight, argparse.Namespace(root=args.root, run_id=args.run_id), quiet=args.json)
            actions.append({"action": "preflight", "status": "pass" if rc == 0 else "fail"})
            if rc != 0:
                stop_reason = "preflight_failed"
                exit_code = rc
                break
            continue
        if state in {"preflight_passed", "next_round_ready"}:
            spec = round_spec(run, current_round)
            if args.round_mode == "dry-run":
                rc = _advance_call(lambda _ns: run_round_dry(base, run, spec), argparse.Namespace(), quiet=args.json)
            else:
                rc = _advance_call(lambda _ns: run_round_live_dispatch(base, run, spec, cli_overrides), argparse.Namespace(), quiet=args.json)
            actions.append({"action": "run-round", "round_id": current_round, "mode": args.round_mode, "status": "pass" if rc == 0 else "fail"})
            if rc != 0:
                stop_reason = "run_round_failed"
                exit_code = rc
                break
            continue
        if state == "round_prompt_ready":
            stop_reason = "provider_answers_needed"
            exit_code = 2
            break
        if state == "round_outputs_collected":
            claim_map = base / "claims" / f"round-{current_round}-claim-map.json"
            if not claim_map.exists():
                _write_auto_claim_map(base=base, run=run, round_id=current_round)
            terminal = next_round_id(run, current_round) == ""
            rc = _advance_call(cmd_gate, argparse.Namespace(root=args.root, run_id=args.run_id, round=current_round, terminal=terminal), quiet=args.json)
            actions.append({"action": "gate", "round_id": current_round, "terminal": terminal, "status": "pass" if rc == 0 else "fail"})
            if rc != 0:
                stop_reason = "gate_failed"
                exit_code = rc
                break
            continue
        if state == "round_gated":
            gate_path = base / "gates" / f"round-{current_round}-gate.md"
            if not gate_path.exists():
                stop_reason = f"gate_missing:{gate_path.relative_to(base).as_posix()}"
                exit_code = 2
                break
            gate_payload = _read_gate_payload(gate_path)
            verdict = str(gate_payload.get("verdict") or "")
            if verdict == "proceed_to_next_round":
                rc = _advance_call(cmd_orchestrate, argparse.Namespace(root=args.root, run_id=args.run_id, after_round=current_round), quiet=args.json)
                actions.append({"action": "orchestrate", "after_round": current_round, "status": "pass" if rc == 0 else "fail"})
                if rc != 0:
                    stop_reason = "orchestrate_failed"
                    exit_code = rc
                    break
                continue
            if verdict in terminal_verdicts():
                _write_auto_result(base=base, run=run, final_round=current_round)
                rc = _advance_call(cmd_finalize, argparse.Namespace(root=args.root, run_id=args.run_id), quiet=args.json)
                actions.append({"action": "finalize", "status": "pass" if rc == 0 else "fail"})
                if rc != 0:
                    stop_reason = "finalize_failed"
                    exit_code = rc
                    break
                continue
            stop_reason = f"gate_verdict:{verdict or 'unknown'}"
            exit_code = 1
            break
        if state == "finalizing":
            _write_auto_result(base=base, run=run, final_round=current_round)
            rc = _advance_call(cmd_finalize, argparse.Namespace(root=args.root, run_id=args.run_id), quiet=args.json)
            actions.append({"action": "finalize", "status": "pass" if rc == 0 else "fail"})
            if rc != 0:
                stop_reason = "finalize_failed"
                exit_code = rc
                break
            continue
        stop_reason = f"unsupported_state:{state}"
        exit_code = 2
        break
    else:
        stop_reason = "max_steps_reached"
        exit_code = 2

    run = load_run(base)
    payload = {
        "schema": "kdh.providers-discuss.advance.v1",
        "run_id": args.run_id,
        "status": "pass" if exit_code == 0 else "blocked",
        "state": run.get("state"),
        "current_round": run.get("current_round"),
        "round_mode": args.round_mode,
        "actions": actions,
        "stop_reason": stop_reason,
        "next_action": _next_action_for_state(run),
        "run_root": str(base),
    }
    append_event(base, "run.advance_checked", run_id=args.run_id, status=payload["status"], stop_reason=stop_reason, refs=["run.json"])
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"advance: {payload['status']}")
        print(f"state: {payload['state']}")
        print(f"current_round: {payload['current_round']}")
        print(f"stop_reason: {stop_reason}")
        print(f"next_action: {payload['next_action']}")
    return exit_code


def _advance_call(func: Any, namespace: argparse.Namespace, *, quiet: bool) -> int:
    if not quiet:
        return int(func(namespace))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return int(func(namespace))


def _write_auto_claim_map(*, base: Path, run: dict[str, Any], round_id: str) -> None:
    claim_map_rel = f"claims/round-{round_id}-claim-map.json"
    claim_map_path = base / claim_map_rel
    if claim_map_path.exists():
        return
    claims: list[dict[str, Any]] = []
    answer_texts: dict[str, str] = {}
    for index, seat in enumerate(provider_seats(base), start=1):
        seat_id = str(seat.get("seat_id") or f"seat-{index}")
        status_rel = f"logs/round-{round_id}/{seat_id}.status.json"
        answer_rel = f"answers/round-{round_id}/{seat_id}.md"
        status_path = base / status_rel
        answer_path = base / answer_rel
        if not status_path.exists() or not answer_path.exists():
            continue
        status = read_json(status_path)
        if status.get("status") != "completed":
            continue
        try:
            answer_texts[answer_rel] = answer_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            answer_texts[answer_rel] = ""
        claims.append(
            {
                "claim_id": f"CLM-{round_id}-{len(claims) + 1:03d}",
                "claim": f"{seat_id} produced a completed provider answer for {round_id}.",
                "claim_type": "provider_output",
                "status": "supported",
                "load_bearing": False,
                "support": [answer_rel, status_rel],
            }
        )
    claims.extend(_semantic_claims_from_answers(base=base, run=run, round_id=round_id, answer_texts=answer_texts, start_index=len(claims) + 1))
    payload = {
        "schema": CLAIM_MAP_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "claims": claims,
        "generated_by": "providers-discuss advance",
        "generation_mode": "semantic_draft_from_provider_answers" if any(claim.get("claim_type") != "provider_output" for claim in claims) else "provider_output_receipts",
    }
    write_json(claim_map_path, payload)
    write_artifact_hash(base, claim_map_rel)
    append_event(base, "claim_map.auto_written", run_id=run["run_id"], round_id=round_id, refs=[claim_map_rel], claim_count=len(claims))


def _semantic_claims_from_answers(
    *,
    base: Path,
    run: dict[str, Any],
    round_id: str,
    answer_texts: dict[str, str],
    start_index: int,
) -> list[dict[str, Any]]:
    corpus = "\n".join([str(run.get("objective", "")), *answer_texts.values()])
    corpus_lower = corpus.lower()
    claims: list[dict[str, Any]] = []
    index = start_index

    def add(
        claim_type: str,
        claim: str,
        *,
        status: str = "supported",
        load_bearing: bool = True,
        keywords: tuple[str, ...] = (),
        support_extra: list[str] | None = None,
        counterevidence: list[str] | None = None,
        owner_next_action: str = "",
    ) -> None:
        nonlocal index
        support = _supporting_answer_refs(answer_texts, keywords)
        if support_extra:
            support.extend(item for item in support_extra if item not in support)
        claims.append(
            {
                "claim_id": f"CLM-{round_id}-{index:03d}",
                "claim": claim,
                "claim_type": claim_type,
                "status": status,
                "load_bearing": load_bearing,
                "support": support,
                "counterevidence": counterevidence or [],
                "owner_next_action": owner_next_action,
            }
        )
        index += 1

    input_support: list[str] = []
    for rel in ("inputs/input-pack.md", "config/source-index.json", "config/providers-discuss.config.json"):
        if (base / rel).exists():
            input_support.append(rel)

    if _has_all(corpus_lower, ("file-backed",)) or _has_all(corpus_lower, ("local-first",)):
        add(
            "product_identity",
            "The package should be framed as a local-first, file-backed provider discussion runner.",
            keywords=("local-first", "file-backed", "runner"),
            support_extra=input_support,
            owner_next_action="Preserve this identity claim in the next prompt and final README.",
        )
    if _has_any(corpus_lower, ("2026-06-15", "june 15, 2026", "6월 15일", "15 de junio de 2026")) and _has_any(corpus_lower, ("claude -p", "agent sdk")):
        add(
            "policy_claim",
            "The README policy motivation should be the 2026-06-15 Claude Agent SDK / claude -p credit split.",
            keywords=("claude -p", "agent sdk", "2026-06-15"),
            support_extra=input_support,
            owner_next_action="Keep the policy date and source explicit; do not rewrite this as a billing workaround.",
        )
    if _has_any(corpus_lower, ("billing bypass", "결제 우회", "policy workaround", "free claude automation")):
        add(
            "non_goal_or_safety_boundary",
            "The package must not be described as a billing bypass, policy workaround, or free Claude automation path.",
            keywords=("billing bypass", "policy workaround", "free claude automation"),
            support_extra=input_support,
            owner_next_action="Challenge any provider wording that weakens this safety boundary.",
        )
    if _has_any(corpus_lower, ("claude_k", "claude team agents", "claude_k_team_agents")):
        add(
            "adapter_maturity",
            "The README must keep plain claude_k separate from claude_k_team_agents and preserve conservative maturity claims.",
            keywords=("claude_k", "claude_k_team_agents", "team agents"),
            support_extra=input_support,
            owner_next_action="Carry this into every later round and every localized section.",
        )
    if _has_any(corpus_lower, ("manual import", "manual fallback")):
        add(
            "adapter_maturity",
            "Manual import should be described as a fallback/import path, not as a provider choice.",
            keywords=("manual import", "fallback"),
            support_extra=input_support,
            owner_next_action="Reject provider drafts that list manual import as a provider seat.",
        )
    if _has_any(corpus_lower, ("runner-owned", "proof", "status", "hash", "claim map", "orchestrator")):
        add(
            "artifact_contract",
            "Provider answers must stay separate from runner-owned proof, status, event, hash, gate, claim, and orchestrator artifacts.",
            keywords=("runner-owned", "proof", "status", "claim map"),
            support_extra=input_support,
            owner_next_action="Require final output to preserve the artifact ownership boundary.",
        )
    if _has_any(corpus_lower, ("oauth", "cookie", "browser-state", "provider-home", "credential")):
        add(
            "credential_safety",
            "The README should state that the runner does not collect OAuth tokens, cookies, browser state, provider-home raw config, or credential file bodies.",
            keywords=("oauth", "cookie", "provider-home", "credential"),
            support_extra=input_support,
            owner_next_action="Keep this safety claim in all final README languages.",
        )
    language_hits = _language_hits(corpus_lower)
    if len(language_hits) >= 5:
        add(
            "localization_requirement",
            "The final README must preserve load-bearing claims across English, Korean, Chinese, Japanese, and Spanish.",
            keywords=(),
            support_extra=sorted(set(_all_answer_refs(answer_texts))),
            owner_next_action="Use this as a multilingual acceptance checklist, not as optional summary text.",
        )

    if _round_mode(run, round_id) == "challenge" or _has_any(corpus_lower, ("challenge", "risk", "unsupported", "overclaim", "safer wording")):
        challenge_support = _supporting_answer_refs(answer_texts, ("challenge", "risk", "unsupported", "overclaim", "safer"))
        if challenge_support:
            add(
                "round_challenge",
                "This round raised challenge material that the next round must resolve instead of replacing with another independent draft.",
                status="contested",
                load_bearing=False,
                keywords=("challenge", "risk", "unsupported", "overclaim", "safer"),
                support_extra=challenge_support,
                owner_next_action="Promote the challenged items into the next prompt delta and final acceptance checklist.",
            )
    if _round_mode(run, round_id) == "decide":
        add(
            "decision_contract",
            "The final round should produce a decision plus an acceptance checklist, with unresolved items routed back explicitly.",
            keywords=("acceptance", "checklist", "decision", "route-back"),
            support_extra=sorted(set(_all_answer_refs(answer_texts))),
            owner_next_action="Record final answer refs and any final implementation artifacts in result.json.",
        )
    return claims


def _round_mode(run: dict[str, Any], round_id: str) -> str:
    for item in run.get("rounds", []):
        if item.get("round_id") == round_id:
            return str(item.get("mode") or "")
    return ""


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle.lower() in text for needle in needles)


def _has_all(text: str, needles: tuple[str, ...]) -> bool:
    return all(needle.lower() in text for needle in needles)


def _all_answer_refs(answer_texts: dict[str, str]) -> list[str]:
    return [rel for rel, text in answer_texts.items() if text.strip()]


def _supporting_answer_refs(answer_texts: dict[str, str], keywords: tuple[str, ...]) -> list[str]:
    if not keywords:
        return _all_answer_refs(answer_texts)
    refs: list[str] = []
    lowered = tuple(keyword.lower() for keyword in keywords)
    for rel, text in answer_texts.items():
        text_lower = text.lower()
        if any(keyword in text_lower for keyword in lowered):
            refs.append(rel)
    return refs


def _language_hits(text: str) -> set[str]:
    hits: set[str] = set()
    markers = {
        "english": ("english", "## english"),
        "korean": ("korean", "한국어"),
        "chinese": ("chinese", "中文"),
        "japanese": ("japanese", "日本語"),
        "spanish": ("spanish", "español", "espanol"),
    }
    for language, candidates in markers.items():
        if any(candidate in text for candidate in candidates):
            hits.add(language)
    return hits


def _write_auto_result(*, base: Path, run: dict[str, Any], final_round: str) -> None:
    result_path = base / "result.json"
    _write_final_artifacts_from_answers(base=base, run=run, final_round=final_round)
    answer_refs: list[dict[str, Any]] = []
    for seat in provider_seats(base):
        seat_id = str(seat.get("seat_id") or "")
        answer_rel = f"answers/round-{final_round}/{seat_id}.md"
        status_rel = f"logs/round-{final_round}/{seat_id}.status.json"
        if (base / answer_rel).exists():
            answer_refs.append(
                {
                    "seat_id": seat_id,
                    "provider": seat.get("provider", ""),
                    "transport": seat.get("transport", ""),
                    "answer_path": answer_rel,
                    "status_path": status_rel if (base / status_rel).exists() else "",
                }
            )
    deliverable_gate = _deliverable_gate_payload(base=base, run=run, final_round=final_round)
    payload = {
        "schema": "kdh.providers-discuss.result.v1",
        "result_version": 2,
        "run_id": run["run_id"],
        "status": "completed",
        "objective": run.get("objective", ""),
        "final_round": final_round,
        "deliverable_profile": normalize_deliverable_profile(run.get("deliverable_profile")),
        "answer_refs": answer_refs,
        "final_artifacts": _detect_final_artifacts(base, run),
        "deliverable_gate": deliverable_gate,
        "acceptance_checklist": _final_acceptance_checklist(base, final_round),
        "summary": "Auto-generated completion result from final-round provider answer artifacts.",
        "generated_by": "providers-discuss advance",
    }
    write_json(result_path, payload)
    write_artifact_hash(base, "result.json")
    append_event(base, "result.auto_written", run_id=run["run_id"], round_id=final_round, refs=["result.json"], answer_count=len(answer_refs))


def _detect_final_artifacts(base: Path, run: dict[str, Any]) -> list[dict[str, Any]]:
    objective = str(run.get("objective") or "").lower()
    profile = normalize_deliverable_profile(run.get("deliverable_profile"))
    artifacts: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for configured in profile.get("final_artifacts", []):
        rel = str(configured.get("path") or "")
        try:
            path = safe_artifact_path(base, rel)
        except ValueError:
            continue
        if path in seen or not path.exists():
            continue
        seen.add(path)
        metadata = _artifact_metadata(path=path, base=base, artifact_type=profile.get("id", "deliverable"), profile=profile)
        metadata["configured"] = True
        artifacts.append(metadata)
    if "readme" not in objective and str(profile.get("id") or "") != "readme_or_docs":
        return artifacts
    for root in (base, base.parent, base.parent.parent):
        readme = (root / "README.md").resolve()
        if readme in seen or not readme.exists():
            continue
        seen.add(readme)
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        artifacts.append(_artifact_metadata(path=readme, base=base, artifact_type="readme", profile=profile, text=text))
    return artifacts


def _write_final_artifacts_from_answers(*, base: Path, run: dict[str, Any], final_round: str) -> list[dict[str, Any]]:
    profile = normalize_deliverable_profile(run.get("deliverable_profile"))
    if not profile.get("final_artifacts"):
        return []
    allowed_paths = {str(item.get("path") or "") for item in profile.get("final_artifacts", [])}
    written: list[dict[str, Any]] = []
    for seat in provider_seats(base):
        seat_id = str(seat.get("seat_id") or "")
        answer_rel = f"answers/round-{final_round}/{seat_id}.md"
        answer_path = base / answer_rel
        if not answer_path.exists():
            continue
        text = answer_path.read_text(encoding="utf-8", errors="replace")
        for block in extract_final_artifact_blocks(text, source_ref=answer_rel):
            rel = str(block.get("path") or "")
            if rel not in allowed_paths:
                continue
            if block.get("profile") and str(block["profile"]) != str(profile.get("id")):
                continue
            target = safe_artifact_path(base, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(block.get("content") or ""), encoding="utf-8")
            digest = write_artifact_hash(base, rel)
            record = {
                "path": rel,
                "source_ref": answer_rel,
                "sha256": digest,
            }
            written.append(record)
            append_event(base, "final_artifact.extracted", run_id=run["run_id"], round_id=final_round, refs=[rel, answer_rel], seat_id=seat_id)
    return written


def _deliverable_gate_payload(*, base: Path, run: dict[str, Any], final_round: str) -> dict[str, Any]:
    profile = normalize_deliverable_profile(run.get("deliverable_profile"))
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    if str(profile.get("id") or "") == "discussion_summary":
        return {
            "status": "skipped",
            "profile_id": profile.get("id"),
            "checks": checks,
            "blockers": blockers,
        }
    for configured in profile.get("final_artifacts", []):
        rel = str(configured.get("path") or "")
        required = configured.get("required") is not False
        try:
            path = safe_artifact_path(base, rel)
        except ValueError as exc:
            checks.append({"name": f"final_artifact_path_{rel}", "status": "fail", "refs": [rel], "note": str(exc)})
            blockers.append({"check": "final_artifact_path", "path": rel, "reason": str(exc)})
            continue
        exists = path.exists()
        checks.append({"name": f"final_artifact_exists_{rel}", "status": "pass" if exists else "fail", "refs": [rel]})
        if required and not exists:
            blockers.append({"check": "final_artifact_exists", "path": rel, "reason": "required final artifact missing"})
            continue
        if not exists:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if required and not text.strip():
            checks.append({"name": f"final_artifact_nonempty_{rel}", "status": "fail", "refs": [rel]})
            blockers.append({"check": "final_artifact_nonempty", "path": rel, "reason": "required final artifact is empty"})
        else:
            checks.append({"name": f"final_artifact_nonempty_{rel}", "status": "pass", "refs": [rel]})
        presence = section_presence(text, list(profile.get("required_sections") or []))
        for section, status in presence.items():
            checks.append({"name": f"required_section_{section}", "status": "pass" if status == "present" else "fail", "refs": [rel]})
            if status != "present":
                blockers.append({"check": "required_section_present", "path": rel, "section": section, "reason": "required section missing"})
        blockers.extend(_profile_quality_blockers(profile=profile, text=text, rel=rel, checks=checks))
    return {
        "status": "pass" if not blockers else "fail",
        "profile_id": profile.get("id"),
        "checks": checks,
        "blockers": blockers,
    }


def _profile_quality_blockers(*, profile: dict[str, Any], text: str, rel: str, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    gates = set(profile.get("quality_gates") or [])
    if "verification_is_executable" in gates:
        ok = bool(re.search(r"```(?:bash|sh|shell)?\n[^`]*(?:pytest|unittest|git diff --check|providers-discuss|python3? -m|npm test|go test|cargo test)", text, re.IGNORECASE))
        checks.append({"name": "verification_is_executable", "status": "pass" if ok else "fail", "refs": [rel]})
        if not ok:
            blockers.append({"check": "verification_is_executable", "path": rel, "reason": "Verification Plan lacks an executable command block"})
    if "acceptance_criteria_are_testable" in gates:
        ok = has_markdown_section(text, "Acceptance Criteria") and bool(re.search(r"(^|\n)\s*(-|\d+\.)\s+.*(pass|fail|verify|test|must|should|완료|검증)", text, re.IGNORECASE))
        checks.append({"name": "acceptance_criteria_are_testable", "status": "pass" if ok else "fail", "refs": [rel]})
        if not ok:
            blockers.append({"check": "acceptance_criteria_are_testable", "path": rel, "reason": "Acceptance Criteria is missing or not checkable"})
    if "open_questions_are_explicit" in gates:
        ok = has_markdown_section(text, "Open Questions / Deferred Items") or has_markdown_section(text, "Open Questions")
        checks.append({"name": "open_questions_are_explicit", "status": "pass" if ok else "fail", "refs": [rel]})
        if not ok:
            blockers.append({"check": "open_questions_are_explicit", "path": rel, "reason": "Open questions/deferred items section missing"})
    if "policy_boundary_present" in gates:
        lowered = text.lower()
        ok = "billing bypass" in lowered or "policy" in lowered or "safety" in lowered or "claude -p" in lowered
        checks.append({"name": "policy_boundary_present", "status": "pass" if ok else "fail", "refs": [rel]})
        if not ok:
            blockers.append({"check": "policy_boundary_present", "path": rel, "reason": "policy/safety boundary is missing"})
    return blockers


def _artifact_metadata(*, path: Path, base: Path, artifact_type: str, profile: dict[str, Any], text: str | None = None) -> dict[str, Any]:
    text = text if text is not None else path.read_text(encoding="utf-8", errors="replace")
    metadata: dict[str, Any] = {
        "path": _display_path(path, base),
        "artifact_type": artifact_type,
        "sha256": sha256_file(path),
        "line_count": len(text.splitlines()),
        "required_sections": section_presence(text, list(profile.get("required_sections") or [])),
    }
    if path.name.lower() == "readme.md" or artifact_type == "readme":
        metadata["language_sections"] = _readme_language_sections(text)
        metadata["policy_markers"] = {
            "claude_p": "claude -p" in text,
            "agent_sdk": "Agent SDK" in text,
            "date_2026_06_15": "2026-06-15" in text or "June 15, 2026" in text,
            "billing_bypass": "billing bypass" in text.lower(),
            "claude_k_team_agents": "claude_k_team_agents" in text,
        }
    return metadata


def _display_path(path: Path, base: Path) -> str:
    for root in (base, base.parent, base.parent.parent):
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return str(path)


def _readme_language_sections(text: str) -> list[str]:
    section_map = {
        "English": r"^##\s+English\b",
        "Korean": r"^##\s+(한국어|Korean)\b",
        "Chinese": r"^##\s+(中文|Chinese)\b",
        "Japanese": r"^##\s+(日本語|Japanese)\b",
        "Spanish": r"^##\s+(Español|Spanish|Espanol)\b",
    }
    found: list[str] = []
    for name, pattern in section_map.items():
        if re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE):
            found.append(name)
    return found


def _final_acceptance_checklist(base: Path, final_round: str) -> list[dict[str, Any]]:
    claim_map_path = base / "claims" / f"round-{final_round}-claim-map.json"
    if not claim_map_path.exists():
        return []
    claim_map = read_json(claim_map_path)
    checklist = []
    for claim in claim_map.get("claims", []):
        if claim.get("claim_type") == "provider_output":
            continue
        checklist.append(
            {
                "claim_id": claim.get("claim_id", ""),
                "claim_type": claim.get("claim_type", ""),
                "status": claim.get("status", ""),
                "load_bearing": claim.get("load_bearing") is True,
                "claim": claim.get("claim", ""),
            }
        )
    return checklist


def cmd_cancel(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    if run.get("state") == "finished":
        raise ValueError("finished run cannot be cancelled")
    if run.get("state") == "cancelled":
        raise ValueError("run is already cancelled")
    run["state"] = "cancelled"
    run["cancellation_reason"] = args.reason
    save_run(base, run)
    append_event(base, "run.cancelled", run_id=args.run_id, reason=args.reason)
    print("cancelled")
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    base = must_run_root(args.root, args.run_id)
    run = load_run(base)
    ensure_not_terminal(run, "finalize")
    gate_path, gate_payload = find_terminal_gate(base)
    final_round = str(gate_payload.get("round_id") or run.get("current_round") or "")
    if not final_round:
        raise ValueError("terminal gate round missing; route-back: rerun terminal gate")
    _write_auto_result(base=base, run=run, final_round=final_round)
    result_payload = read_json(base / "result.json")
    deliverable_gate = result_payload.get("deliverable_gate") if isinstance(result_payload.get("deliverable_gate"), dict) else {}
    if deliverable_gate.get("status") == "fail":
        raise ValueError("deliverable gate failed; route-back: fix final artifact before finalize")
    run["state"] = "finished"
    run["final_gate_path"] = str(gate_path.relative_to(base))
    run["result_path"] = "result.json"
    save_run(base, run)
    write_artifact_hash(base, "result.json")
    append_event(base, "run.finalized", run_id=args.run_id, gate=run["final_gate_path"], verdict=gate_payload.get("verdict"), refs=["result.json", run["final_gate_path"]])
    print("finalized")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    return handle_hook(
        event=args.event,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        root=args.root,
        run_id=args.run_id,
        round_id=args.round,
        seat_id=args.seat,
        trigger_mode=args.trigger_mode,
        trigger_regex=args.trigger_regex,
        roles=parse_roles(args.roles),
    )


def cmd_hook_dispatch(args: argparse.Namespace) -> int:
    return handle_dispatch(
        event=args.event,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        root=args.root,
        trigger_mode=args.trigger_mode,
        roles=parse_roles(args.roles),
        default_seat=args.seat,
    )


def cmd_trust_workspace(args: argparse.Namespace) -> int:
    result = (
        repair_workspace_trust(claude_json=args.claude_json, workspace=args.workspace)
        if args.repair
        else inspect_workspace_trust(claude_json=args.claude_json, workspace=args.workspace)
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"workspace: {result['workspace']}")
        print(f"status: {result['status']}")
        if result.get("changed"):
            print(f"backup: {result['backup_path']}")
    return 0 if result["status"] == "trusted" else 1


def cmd_permissions(args: argparse.Namespace) -> int:
    result = repair_permissions(settings_json=args.settings_json) if args.repair else inspect_permissions(settings_json=args.settings_json)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"settings_json: {result['settings_json']}")
        print(f"status: {result['status']}")
        print(f"permissions.defaultMode: {result.get('permissions_defaultMode')}")
        print(f"skipAutoPermissionPrompt: {result.get('skipAutoPermissionPrompt')}")
        if result.get("changed"):
            print(f"backup: {result['backup_path']}")
    return 0 if result["status"] == "auto" else 1


def cmd_hook_config(args: argparse.Namespace) -> int:
    if args.repair and args.remove:
        raise ValueError("hook-config accepts only one of --repair or --remove")
    kwargs = hook_config_kwargs(args)
    if args.remove:
        result = remove_hook_config(**kwargs)
    elif args.repair:
        result = repair_hook_config(**kwargs)
    else:
        result = inspect_hook_config(**kwargs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"settings_json: {result['settings_json']}")
        print(f"status: {result['status']}")
        print(f"configured_events: {', '.join(result['configured_events']) or 'none'}")
        print(f"missing_events: {', '.join(result['missing_events']) or 'none'}")
        if result.get("removed_events"):
            print(f"removed_events: {', '.join(result['removed_events'])}")
        if result.get("changed"):
            print(f"backup: {result['backup_path']}")
    if args.remove:
        return 0
    return 0 if result["status"] == "configured" else 1


def cmd_runtime_preflight(args: argparse.Namespace) -> int:
    hook_kwargs = hook_config_kwargs(args)
    settings_json = hook_kwargs.pop("settings_json")
    result = inspect_runtime_preflight(
        claude_json=args.claude_json,
        settings_json=settings_json,
        workspace=args.workspace,
        repair=args.repair,
        install_hook=args.install_hook,
        **hook_kwargs,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"runtime-preflight: {result['status']}")
        print(f"workspace_trust: {result['workspace_trust']['status']}")
        print(f"permissions: {result['permissions']['status']}")
        print(f"hook_config: {result['hook_config']['status']}")
        print(f"next_action: {result.get('next_action', '')}")
        if result["blockers"]:
            print("blockers:")
            for blocker in result["blockers"]:
                print(f"- {blocker['check']}: {blocker['reason']} next={blocker.get('next_action', '')}")
    return 0 if result["status"] == "pass" else 1


def hook_config_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "settings_json": args.settings_json,
        "harness_root": args.harness_root,
        "root": args.root,
        "run_id": args.run_id,
        "round_id": args.round,
        "seat_id": args.seat,
        "trigger_mode": args.trigger_mode,
        "trigger_regex": args.trigger_regex,
        "roles": args.roles,
    }


def validate_claim_map(path: Path) -> dict[str, Any]:
    checks = []
    blockers = []
    basis = []
    if not path.exists():
        return {
            "checks": [{"check_id": "CLM-001", "name": "claim_map_exists", "status": "fail", "refs": [str(path)]}],
            "blockers": [{"check": "claim_map_exists", "reason": "claim-map missing"}],
            "basis": [],
            "unsupported_load_bearing_claims": 0,
            "semantic_claim_count": 0,
            "load_bearing_claim_count": 0,
        }
    data = read_json(path)
    if data.get("schema") != CLAIM_MAP_SCHEMA:
        blockers.append({"check": "claim_map_schema", "reason": f"unexpected schema: {data.get('schema')}"})
        _check(checks, "claim_map_schema", "fail", [str(path)])
    else:
        _check(checks, "claim_map_schema", "pass", [str(path)])
    unsupported = 0
    semantic_count = 0
    load_bearing_count = 0
    for claim in data.get("claims", []):
        claim_id = claim.get("claim_id", "")
        if claim_id:
            basis.append(claim_id)
        if claim.get("claim_type") != "provider_output":
            semantic_count += 1
        if claim.get("load_bearing") is True:
            load_bearing_count += 1
        status = claim.get("status")
        if status not in ALLOWED_CLAIM_STATUSES:
            blockers.append({"check": "claim_status", "claim_id": claim_id, "reason": f"invalid status: {status}"})
        support = claim.get("support", [])
        if claim.get("load_bearing") is True and status == "unsupported":
            unsupported += 1
        if claim.get("load_bearing") is True and status == "supported" and not support:
            unsupported += 1
            blockers.append({"check": "claim_support", "claim_id": claim_id, "reason": "supported load-bearing claim lacks support"})
    _check(checks, "unsupported_load_bearing_claims_zero", "pass" if unsupported == 0 else "fail", [str(path)])
    _check(checks, "semantic_claims_present", "pass" if semantic_count > 0 else "fail", [str(path)], f"semantic={semantic_count}")
    _check(checks, "load_bearing_claims_present", "pass" if load_bearing_count > 0 else "fail", [str(path)], f"load_bearing={load_bearing_count}")
    return {
        "checks": checks,
        "blockers": blockers,
        "basis": basis,
        "unsupported_load_bearing_claims": unsupported,
        "semantic_claim_count": semantic_count,
        "load_bearing_claim_count": load_bearing_count,
    }


def find_provider_seat(base: Path, seat_id: str) -> dict[str, Any]:
    for seat in provider_seats(base):
        if seat.get("seat_id") == seat_id:
            return seat
    raise ValueError(f"unknown provider seat: {seat_id}")


def parse_answer_args(items: list[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"invalid --answer, expected seat_id=/path: {item}")
        seat, path = item.split("=", 1)
        parsed[seat] = Path(path)
    return parsed


def _resolve_live_cli(*, seat: dict[str, Any], cli_overrides: dict[str, Path], default_name: str) -> Path | None:
    keys = [
        str(seat.get("seat_id") or ""),
        str(seat.get("transport") or ""),
        str(seat.get("provider") or ""),
        default_name,
    ]
    for key in keys:
        if key and key in cli_overrides:
            return cli_overrides[key]
    resolved = shutil.which(default_name)
    return Path(resolved) if resolved else None


def ensure_round_allowed(run: dict[str, Any]) -> None:
    if run.get("state") == "cancelled":
        raise ValueError("cancelled run cannot dispatch or import provider outputs")
    ensure_not_terminal(run, "run a round")


def ensure_not_terminal(run: dict[str, Any], action: str) -> None:
    if run.get("state") == "finished":
        raise ValueError(f"finished run cannot {action}")
    if run.get("state") == "cancelled":
        raise ValueError(f"cancelled run cannot {action}")


def find_terminal_gate(base: Path) -> tuple[Path, dict[str, Any]]:
    for path in sorted((base / "gates").glob("round-*-gate.md"), reverse=True):
        payload = _read_gate_payload(path)
        if payload.get("verdict") in terminal_verdicts():
            return path, payload
    raise ValueError("terminal gate missing; route-back: run gate --terminal before finalize")


def terminal_verdicts() -> set[str]:
    return {"proceed_to_implementation", "proceed_to_final"}


def _read_gate_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"gate payload missing: {path}")
    return json.loads(text[start : end + 1])


def must_run_root(root: Path, run_id: str) -> Path:
    base = run_root(root, run_id)
    if not base.exists():
        raise ValueError(f"run missing: {base}")
    return base


def _first_round_id(run: dict[str, Any]) -> str:
    rounds = run.get("rounds")
    if isinstance(rounds, list) and rounds:
        return str(rounds[0].get("round_id") or "R1")
    return "R1"


def verify_recorded_artifact_hashes(base: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    manifest = base / "hashes" / "artifacts.sha256.json"
    if not manifest.exists():
        _check(checks, "artifact_hash_manifest_exists", "pass", ["hashes"])
        return checks, blockers
    data = read_json(manifest)
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        _check(checks, "artifact_hash_manifest_parseable", "fail", ["hashes/artifacts.sha256.json"])
        blockers.append({"check": "artifact_hash_manifest_parseable", "reason": "artifacts must be an object"})
        return checks, blockers
    mutable_refs = {"run.json", "verify.json", "summary.md"}
    mismatch_count = 0
    missing_count = 0
    checked_count = 0
    for rel, expected in sorted(artifacts.items()):
        rel_text = str(rel)
        if rel_text in mutable_refs or rel_text.startswith("hashes/"):
            continue
        path = base / rel_text
        if not path.exists():
            missing_count += 1
            blockers.append({"check": "artifact_hash_missing", "reason": "hashed artifact missing", "ref": rel_text})
            continue
        checked_count += 1
        actual = sha256_file(path)
        if actual != str(expected):
            mismatch_count += 1
            blockers.append({"check": "artifact_hash_mismatch", "reason": "artifact changed after runner hash", "ref": rel_text})
    status = "pass" if missing_count == 0 and mismatch_count == 0 else "fail"
    note = f"checked={checked_count} missing={missing_count} mismatched={mismatch_count}"
    _check(checks, "artifact_hashes_match", status, ["hashes/artifacts.sha256.json"], note)
    return checks, blockers


def _check(checks: list[dict[str, Any]], name: str, status: str, refs: list[str], note: str = "") -> None:
    checks.append(
        {
            "check_id": f"VR-{len(checks) + 1:03d}",
            "name": name,
            "status": status,
            "refs": refs,
            **({"note": note} if note else {}),
        }
    )


def _preflight_markdown(run: dict[str, Any], provider_config: dict[str, Any], checks: list[dict[str, Any]], issues: list[dict[str, Any]]) -> str:
    lines = [
        "# kdh-providers-discuss Preflight",
        "",
        f"run_id: `{run['run_id']}`",
        f"preset: `{run['preset']}`",
        "",
        "## Claude Policy",
        "",
        "- `claude -p` product dependency: forbidden",
        "- Claude live transport: `claude -k` spawn/work/kill",
        "- live provider calls during preflight: no",
        "",
        "## Provider Seats",
        "",
    ]
    for seat in provider_config.get("seats", []):
        lines.append(f"- `{seat['seat_id']}` transport `{seat['transport']}`")
    lines.extend(["", "## Checks", ""])
    for check in checks:
        lines.append(f"- {check['status']}: {check['name']}")
    if issues:
        lines.extend(["", "## Blockers", ""])
        for issue in issues:
            lines.append(f"- {issue}")
    return "\n".join(lines) + "\n"


def _next_action_for_gate(run: dict[str, Any], round_id: str, verdict: str) -> str:
    if verdict == "proceed_to_next_round":
        nxt = next_round_id(run, round_id)
        return f"run orchestrator for {round_id} and prepare {nxt}" if nxt else "run final gate"
    if verdict == "proceed_to_implementation":
        return "start scoped implementation after CEO approval"
    return "fix blockers and return to the indicated stage"


def _next_action_for_state(run: dict[str, Any]) -> str:
    state = run.get("state")
    current_round = run.get("current_round", "")
    if state == "created":
        return "run preflight"
    if state == "preflight_passed":
        return f"run round {current_round} dry-run or manual-import"
    if state == "round_prompt_ready":
        return f"collect and import provider answers for {current_round}"
    if state == "round_outputs_collected":
        return f"write claims/round-{current_round}-claim-map.json then run gate"
    if state == "round_running":
        return f"wait for live-dispatch providers in {current_round}"
    if state == "round_gated":
        return f"run orchestrate after {current_round} or finalize after a terminal gate"
    if state == "transport_smoke_completed":
        return "run verify-proof --kind transport for the smoke proof"
    if state == "transport_smoke_failed":
        return "inspect smoke proof/status/transcript and route back before live promotion"
    if state == "next_round_ready":
        return f"run round {current_round}"
    if state == "finalizing":
        return "run finalize; it will refresh final artifacts and result.json"
    if state == "finished":
        return "run finished"
    if state == "cancelled":
        return "run cancelled; start a new run if needed"
    if state == "failed":
        return "inspect verify.json and route back to the failed gate"
    if state == "interrupted":
        return run.get("resume_hint") or f"inspect latest event and resume from {current_round}"
    return "inspect run.json and events.jsonl"


def _gate_markdown(round_id: str, payload: dict[str, Any]) -> str:
    if payload["verdict"] not in ALLOWED_GATE_VERDICTS:
        raise ValueError(f"invalid gate verdict: {payload['verdict']}")
    return "# Round {round_id} Gate\n\n```json kdh-gate\n{payload}\n```\n".format(
        round_id=round_id,
        payload=json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
    )


def _orchestrator_review(base: Path, run: dict[str, Any], after: str, next_round: str, carried: list[dict[str, Any]], gate_path: Path) -> str:
    profile = normalize_deliverable_profile(run.get("deliverable_profile"))
    profile_lines = _deliverable_orchestrator_lines(base=base, run=run, profile=profile)
    lines = [
        f"# Round {after} Orchestrator Review",
        "",
        "## Prior Gate",
        "",
        f"- gate: `{gate_path.name}`",
        "",
        "## Claims To Carry Forward",
        "",
        "| claim_id | status | load_bearing | why carry |",
        "|---|---|---:|---|",
    ]
    for claim in carried:
        reason = str(claim.get("owner_next_action") or "unresolved or load-bearing").replace("|", "\\|")
        lines.append(f"| `{claim.get('claim_id', '')}` | `{claim.get('status', '')}` | {claim.get('load_bearing') is True} | {reason} |")
    if not carried:
        lines.append("| none | none | false | no unresolved claims |")
    lines.extend(["", "## Required Next-Round Focus", ""])
    if carried:
        for claim in carried:
            lines.append(f"- `{claim.get('claim_id', '')}` {claim.get('claim', '')}")
            support = claim.get("support") if isinstance(claim.get("support"), list) else []
            if support:
                lines.append(f"  support: {', '.join(str(item) for item in support[:4])}")
            action = str(claim.get("owner_next_action") or "").strip()
            if action:
                lines.append(f"  next_action: {action}")
    else:
        lines.append("- none")
    if profile_lines:
        lines.extend(["", "## Deliverable Profile Pressure", "", *profile_lines])
    lines.extend(
        [
            "",
            "## Next Round",
            "",
            f"- next_round: `{next_round or 'terminal'}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _prompt_delta(base: Path, run: dict[str, Any], after: str, next_round: str, carried: list[dict[str, Any]]) -> str:
    profile = normalize_deliverable_profile(run.get("deliverable_profile"))
    profile_lines = _deliverable_orchestrator_lines(base=base, run=run, profile=profile)
    lines = [
        f"# Prompt Delta After {after}",
        "",
        "## Delta Summary",
        "",
        "Carry unresolved, contested, deferred, and load-bearing claims into the next prompt.",
        "",
        "## Carried Claims",
        "",
    ]
    if carried:
        for claim in carried:
            lines.append(f"- `{claim.get('claim_id', '')}` status `{claim.get('status', '')}`: {claim.get('claim', '')}")
            support = claim.get("support") if isinstance(claim.get("support"), list) else []
            if support:
                lines.append(f"  - support: {', '.join(str(item) for item in support[:4])}")
            action = str(claim.get("owner_next_action") or "").strip()
            if action:
                lines.append(f"  - required_follow_up: {action}")
    else:
        lines.append("- none")
    if profile_lines:
        lines.extend(
            [
                "",
                "## Deliverable Profile Requirements",
                "",
                *profile_lines,
                "",
                "Provider instruction:",
                "- Fill missing or weak deliverable sections before adding new optional ideas.",
                "- Preserve accepted/rejected/deferred decisions explicitly.",
                "- Final rounds must emit a `KDH_FINAL_ARTIFACT` block when the profile has final artifacts.",
            ]
        )
    lines.extend(
        [
            "",
            "## Next-Round Contract",
            "",
            "- Resolve or preserve every carried claim explicitly.",
            "- Do not replace prior-round critique with another independent draft.",
            "- Cite the prior answer path, source id, or artifact path for each accepted or rejected claim.",
            "",
            "## Target",
            "",
            f"- next_round: `{next_round or 'terminal'}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _deliverable_orchestrator_lines(*, base: Path, run: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    if str(profile.get("id") or "") == "discussion_summary":
        return []
    total_rounds = len(run.get("rounds") or [])
    current_round = str(run.get("current_round") or "")
    gate = _deliverable_gate_payload(base=base, run=run, final_round=current_round)
    missing_sections = [
        blocker.get("section", "")
        for blocker in gate.get("blockers", [])
        if blocker.get("check") == "required_section_present" and blocker.get("section")
    ]
    lines = [
        f"- profile_id: `{profile.get('id', '')}`",
        f"- profile_title: `{profile.get('title', '')}`",
        f"- convergence_start_round: `R{convergence_start_round(total_rounds=total_rounds or 1, profile=profile)}`",
        "- final_artifacts: " + ", ".join(f"`{item.get('path', '')}`" for item in profile.get("final_artifacts", [])),
    ]
    if missing_sections:
        lines.append("- missing_required_sections: " + ", ".join(f"`{section}`" for section in missing_sections))
    else:
        required = profile.get("required_sections") or []
        lines.append("- required_sections: " + (", ".join(f"`{section}`" for section in required) if required else "none"))
    if gate.get("status") == "fail":
        lines.append("- deliverable_gate_status: `fail_or_not_ready`")
    else:
        lines.append(f"- deliverable_gate_status: `{gate.get('status', 'unknown')}`")
    return lines
