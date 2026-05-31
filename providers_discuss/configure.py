from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from .artifacts import DEFAULT_PROVIDER_TIMEOUT_SECONDS, DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT, write_json
from .agent_profiles import DEFAULT_AGENT_PROFILE_PRESET, load_agent_profiles, profile_compatibility
from .public_config import example_public_config, validate_public_config


CONFIGURE_SCHEMA = "providers-discuss.configure.v1"

SUPPORTED_INTAKE_LANGUAGES = ("English", "Korean", "Chinese", "Japanese", "Spanish")
SUPPORTED_BRAINSTORMING_MODES = ("none", "light", "deep")
INTAKE_PROVIDER_FAMILIES = ("gpt/codex", "claude", "claude team agents", "gemini")

OFFICIAL_MODEL_SOURCES_BY_FAMILY = {
    "gpt/codex": [
        "https://platform.openai.com/docs/models",
        "local CLI: codex debug models, codex /model, or codex --help",
    ],
    "claude": [
        "https://platform.claude.com/docs/en/about-claude/models/overview",
        "https://platform.claude.com/docs/en/about-claude/models/model-ids",
        "local CLI: claude --help and Claude Code model picker",
    ],
    "claude team agents": [
        "https://platform.claude.com/docs/en/about-claude/models/overview",
        "https://platform.claude.com/docs/en/about-claude/models/model-ids",
        "local CLI: claude --help and Claude Code model picker",
    ],
    "gemini": [
        "https://ai.google.dev/gemini-api/docs/models",
        "https://ai.google.dev/api/models",
        "local dynamic refresh: providers-discuss model-refresh --provider gemini --json",
        "https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/model.md",
        "local CLI: gemini /model, gemini --help, or gemini --model help when available",
    ],
}

ROUND_MODE_SEQUENCE = ("explore", "challenge", "synthesize", "verify", "decide")
ROUND_TITLE_BY_MODE = {
    "explore": "Independent proposals and risk candidates",
    "challenge": "Challenge unsupported claims and hidden assumptions",
    "synthesize": "Synthesize architecture and contract candidates",
    "verify": "Failure simulation and recovery requirements",
    "decide": "Decision contract and implementation gate",
}

DEFAULT_PROVIDER_TRANSPORT = {
    "openai": "codex_exec_file",
    "anthropic": "claude_k",
    "google": "gemini_cli",
    "manual": "manual",
    "other": "manual",
}

DEFAULT_PROVIDER_MODEL = {
    "openai": "gpt-5.5",
    "anthropic": "opus",
    "google": "auto",
    "manual": "manual",
    "other": "custom",
}

DEFAULT_PROVIDER_REASONING = {
    "openai": "high",
    "anthropic": "max",
    "google": "default",
    "manual": "manual",
    "other": "default",
}


def read_answers(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("answers JSON root must be an object")
    return data


def write_config(path: Path, config: dict[str, Any]) -> None:
    write_json(path, config)


def configure_from_answers(answers: dict[str, Any]) -> dict[str, Any]:
    config = example_public_config()
    config["language"] = {
        "conversation": _language_value(answers.get("language") or answers.get("conversation_language"), "English"),
        "supported": list(SUPPORTED_INTAKE_LANGUAGES),
    }
    config["objective"] = _str_value(answers.get("objective"), config["objective"])
    brainstorming = answers.get("brainstorming")
    if isinstance(brainstorming, dict):
        config["brainstorming"] = {
            "mode": _brainstorming_mode_value(brainstorming.get("mode"), "none"),
            "include_as_provider_input": _bool_value(brainstorming.get("include_as_provider_input"), True),
        }
    else:
        config["brainstorming"] = {
            "mode": _brainstorming_mode_value(answers.get("brainstorming_mode"), "none"),
            "include_as_provider_input": _bool_value(answers.get("brainstorming_include_as_provider_input"), True),
        }
    input_cfg = dict(config.get("input") or {})
    input_cfg["source_dirs"] = _list_value(answers.get("source_dirs"), input_cfg.get("source_dirs") or ["./inputs"])
    if "package_strategy" in answers:
        input_cfg["package_strategy"] = _str_value(answers.get("package_strategy"), input_cfg.get("package_strategy", ""))
    config["input"] = input_cfg
    if "agent_catalogs" in answers or "agent_catalog_paths" in answers:
        config["agent_catalogs"] = _catalogs_value(answers.get("agent_catalogs"), answers.get("agent_catalog_paths"))
    if "agent_profile_defaults" in answers:
        defaults = answers.get("agent_profile_defaults")
        if not isinstance(defaults, dict):
            raise ValueError("agent_profile_defaults must be an object")
        config["agent_profile_defaults"] = dict(defaults)
    elif "use_agent_profile_defaults" in answers or "agent_profile_preset" in answers:
        config["agent_profile_defaults"] = {
            "enabled": _bool_value(answers.get("use_agent_profile_defaults"), False),
            "preset": _str_value(answers.get("agent_profile_preset"), DEFAULT_AGENT_PROFILE_PRESET),
        }
    config["rounds"] = _rounds_from_answers(answers)
    config["seats"] = [_seat_from_answers(item, index) for index, item in enumerate(_seat_answers(answers), start=1)]
    return config


def configure_interactive(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> dict[str, Any]:
    defaults = example_public_config()
    answers: dict[str, Any] = {}
    answers["language"] = _ask_language(stdout, stdin)
    _write_setup_sequence(stdout)
    answers["round_count"], seats = _ask_run_shape_gate(stdout, stdin, defaults)
    if _ask_bool(stdout, stdin, "Use agent profiles", False):
        catalog_paths = _ask_list(stdout, stdin, "Agent catalog paths", _default_agent_catalog_paths())
        catalogs = _catalogs_value(None, catalog_paths)
        answers["agent_catalogs"] = catalogs
        _write_agent_profile_options(stdout, catalogs=catalogs, seats=seats)
        use_defaults = _ask_bool(stdout, stdin, f"Use {DEFAULT_AGENT_PROFILE_PRESET} defaults", True)
        answers["agent_profile_defaults"] = {"enabled": use_defaults, "preset": DEFAULT_AGENT_PROFILE_PRESET}
        if not use_defaults:
            _ask_profile_assignments(stdout, stdin, seats, catalogs)
    answers["seats"] = seats
    answers["objective"] = _ask(stdout, stdin, "Objective/topic", defaults["objective"])
    answers["brainstorming_mode"] = _ask_brainstorming_mode(stdout, stdin)
    answers["source_dirs"] = _ask_list(stdout, stdin, "Input/source dirs", defaults["input"]["source_dirs"])
    return configure_from_answers(answers)


def _write_setup_sequence(stdout: TextIO) -> None:
    stdout.write(
        "\nproviders-discuss setup will continue in this order:\n"
        "- run shape gate: round count, seat count, provider/model/effort per seat\n"
        "- provider login/auth check\n"
        "- agent profile or default for each seat\n"
        "- topic/objective\n"
        "- brainstorming mode\n"
        "- input data path or input pack\n\n"
    )


def _ask_language(stdout: TextIO, stdin: TextIO) -> str:
    stdout.write("English: Choose a language:\n- English\n- Korean\n- Chinese\n- Japanese\n- Spanish\n")
    stdout.write("Korean: 언어를 선택해주세요:\n- 영어\n- 한국어\n- 중국어\n- 일본어\n- 스페인어\n")
    stdout.write("Chinese: 请选择语言:\n- 英语\n- 韩语\n- 中文\n- 日语\n- 西班牙语\n")
    stdout.write("Japanese: 言語を選んでください:\n- 英語\n- 韓国語\n- 中国語\n- 日本語\n- スペイン語\n")
    stdout.write("Spanish: Elige un idioma:\n- inglés\n- coreano\n- chino\n- japonés\n- español\n")
    return _language_value(_ask(stdout, stdin, "Language", "English"), "English")


def _ask_run_shape_gate(stdout: TextIO, stdin: TextIO, defaults: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    stdout.write(
        "\nRun shape gate:\n"
        "- This single gate collects round count, seat count, provider type, model, and reasoning effort.\n"
        "- Round count can be any positive integer from 1 to N. Default is 3, but it is not a limit.\n"
        "- Seat count means how many independent provider voices you want.\n"
        "- Provider/model/effort choices are examples until auth and adapter capability checks pass.\n\n"
    )
    round_count = _ask_int(stdout, stdin, "Round count", len(defaults["rounds"]))
    seat_count = _ask_int(stdout, stdin, "Seat count", len([seat for seat in defaults["seats"] if seat.get("enabled", True) is not False]))
    seats: list[dict[str, Any]] = []
    default_seats = defaults["seats"]
    _write_provider_options(stdout)
    for index in range(seat_count):
        default = default_seats[index] if index < len(default_seats) else {}
        stdout.write(f"\nRun shape gate / Seat {index + 1}\n")
        seat: dict[str, Any] = {}
        seat["seat_id"] = _ask(stdout, stdin, "Seat id", default.get("seat_id") or f"seat_{index + 1}")
        default_family = _default_provider_family(default)
        family = _provider_family_value(_ask(stdout, stdin, "Provider type", default_family), default_family)
        family_defaults = _provider_family_defaults(family)
        seat["provider"] = family_defaults["provider"]
        seat["transport"] = family_defaults["transport"]
        _write_model_effort_refresh_gate(stdout, family)
        model_default = default.get("model") if family == default_family else family_defaults["model"]
        effort_default = default.get("reasoning_effort") if family == default_family else family_defaults["reasoning_effort"]
        seat["model"] = _ask(stdout, stdin, "Model", model_default or family_defaults["model"])
        seat["reasoning_effort"] = _ask(
            stdout,
            stdin,
            "Reasoning/effort",
            effort_default or family_defaults["reasoning_effort"],
        )
        seat["role"] = _ask(stdout, stdin, "Role", default.get("role") or "independent reviewer")
        seat["required"] = _ask_bool(stdout, stdin, "Required seat", bool(default.get("required", True)))
        seat["enabled"] = _ask_bool(stdout, stdin, "Enabled", bool(default.get("enabled", True)))
        if seat["transport"] == "claude_k_team_agents":
            team_default = default.get("team_agents") or {}
            seat["team_agents"] = {
                "enabled": True,
                "roles": _ask_list(stdout, stdin, "Team Agent roles", team_default.get("roles") or ["source-reader", "skeptic", "recorder"]),
                "required_direct_message_count": _ask_int(
                    stdout,
                    stdin,
                    "Required direct teammate messages",
                    int(team_default.get("required_direct_message_count", DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT)),
                ),
            }
        seats.append(seat)
    return round_count, seats


def _write_provider_options(stdout: TextIO) -> None:
    stdout.write(
        "\nProvider options:\n"
        "[gpt/codex]\n"
        "- One OpenAI/Codex CLI seat.\n"
        "- Good for analysis, code review, implementation planning, and file-output answers.\n\n"
        "[claude]\n"
        "- One normal Claude Code seat.\n"
        "- Good for architecture review, long-context reasoning, and design critique.\n\n"
        "[claude team agents]\n"
        "- One Claude Code seat that uses Claude Team Agents internally.\n"
        "- Claude coordinates its own teammates, they discuss the topic, and the Claude lead returns one final conclusion.\n\n"
        "[gemini]\n"
        "- One Gemini CLI seat.\n"
        "- Good for another independent provider perspective once installed and logged in.\n\n"
        "Examples:\n"
        "- Example 1: gpt/codex 1, claude 1, claude team agents 1, gemini 1\n"
        "- Example 2: gpt/codex 1, claude 1\n"
        "- Example 3: claude team agents 1, gemini 1\n\n"
    )


def _write_model_effort_refresh_gate(stdout: TextIO, family: str) -> None:
    stdout.write(
        "\n사용 가능한 model과 effort를 최신정보로 검색하겠습니다.\n"
        "Refresh rule:\n"
        "- Use the exact official sources below first; do not rely on search-result snippets.\n"
        "- Use local CLI discovery when available, because CLI accounts can expose a different model menu.\n"
        "- Do not invent version numbers or reuse old remembered names.\n"
        "- If the official sources cannot be opened, say refresh failed and ask for a model manually.\n"
        "- Show refreshed options only; do not recommend one.\n"
        "- Keep each provider section structured as bullets.\n\n"
        "Official/current sources to open before listing exact names:\n"
    )
    families = [family] if family in INTAKE_PROVIDER_FAMILIES else list(INTAKE_PROVIDER_FAMILIES)
    for item in families:
        stdout.write(f"{_provider_source_heading(item)}\n")
        for source in OFFICIAL_MODEL_SOURCES_BY_FAMILY.get(item, []):
            stdout.write(f"- {source}\n")
    stdout.write(
        "\n"
        "Output format after refresh:\n"
    )
    for item in families:
        stdout.write(_model_effort_format_example(item))
    if family == "gemini":
        stdout.write(
            "Gemini freshness check:\n"
            "- Run `providers-discuss model-refresh --provider gemini --json` or parse the opened official model page/API reference directly.\n"
            "- List the newest stable Flash model discovered from the official source before older Flash/Pro options.\n"
            "- Do not hardcode a specific Gemini version; official model pages can change faster than this package.\n\n"
        )


def _provider_source_heading(family: str) -> str:
    if family == "gpt/codex":
        return "[gpt/codex sources]"
    if family == "claude":
        return "[claude sources]"
    if family == "claude team agents":
        return "[claude team agents sources]"
    if family == "gemini":
        return "[gemini sources]"
    return f"[{family} sources]"


def _model_effort_format_example(family: str) -> str:
    if family == "gpt/codex":
        return (
            "[gpt/codex]\n"
            "- model: <refreshed GPT/Codex model 1>\n"
            "- model: <refreshed GPT/Codex model 2>\n"
            "- model: <refreshed GPT/Codex model 3>\n"
            "- effort: <refreshed effort 1>\n"
            "- effort: <refreshed effort 2>\n"
            "- effort: <refreshed effort 3>\n\n"
        )
    if family == "claude":
        return (
            "[claude]\n"
            "- model: <refreshed Claude Haiku-family option>\n"
            "- model: <refreshed Claude Sonnet-family option>\n"
            "- model: <refreshed Claude Opus-family option>\n"
            "- effort: <refreshed effort 1>\n"
            "- effort: <refreshed effort 2>\n"
            "- effort: <refreshed effort 3>\n\n"
        )
    if family == "claude team agents":
        return (
            "[claude team agents]\n"
            "- model: <refreshed Claude model for the lead seat>\n"
            "- effort: <refreshed Claude effort for the lead seat>\n"
            "- teammate roles: <role 1>\n"
            "- teammate roles: <role 2>\n"
            "- teammate roles: <role 3>\n\n"
        )
    if family == "gemini":
        return (
            "[gemini]\n"
            "- model: <refreshed Gemini model 1>\n"
            "- model: <refreshed Gemini model 2>\n"
            "- model: <refreshed Gemini model 3>\n"
            "- effort: <refreshed effort 1>\n"
            "- effort: <refreshed effort 2>\n"
            "- effort: <refreshed effort 3>\n\n"
        )
    return ""


def _write_agent_profile_options(stdout: TextIO, *, catalogs: list[dict[str, Any]], seats: list[dict[str, Any]]) -> None:
    stdout.write("Agent profile options:\n")
    stdout.write("- default: balanced-kdh preset.\n")
    try:
        profiles = load_agent_profiles(catalogs)
    except ValueError as exc:
        stdout.write(f"- catalog load failed: {exc}\n")
        stdout.write("- Enter an explicit catalog path or use default without per-profile assignment.\n")
        return
    stdout.write(f"- loaded_profiles: {len(profiles)}\n")
    for profile_id, profile in sorted(profiles.items()):
        description = str(profile.get("description") or "").strip()
        stdout.write(f"- {profile_id}: {description}\n")
    for seat in seats:
        transport = str(seat.get("transport") or "")
        compatible = _compatible_profile_ids(profiles, transport=transport)
        stdout.write(
            f"\nCompatible profiles for seat {seat.get('seat_id', '')} "
            f"({transport or 'unknown transport'}): {len(compatible)}\n"
        )
        for profile_id in compatible:
            stdout.write(f"- {profile_id}\n")


def _ask_brainstorming_mode(stdout: TextIO, stdin: TextIO) -> str:
    stdout.write("Brainstorming modes:\n- none\n- light\n- deep\n")
    return _brainstorming_mode_value(_ask(stdout, stdin, "Brainstorming mode", "none"), "none")


def _default_provider_family(default: dict[str, Any]) -> str:
    transport = str(default.get("transport") or "")
    provider = str(default.get("provider") or "")
    if transport == "codex_exec_file" or provider == "openai":
        return "gpt/codex"
    if transport == "claude_k_team_agents":
        return "claude team agents"
    if transport == "claude_k" or provider == "anthropic":
        return "claude"
    if transport == "gemini_cli" or provider == "google":
        return "gemini"
    return "gpt/codex"


def _provider_family_value(value: Any, default: str) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if not text:
        return default
    aliases = {
        "gpt": "gpt/codex",
        "openai": "gpt/codex",
        "codex": "gpt/codex",
        "gpt/codex": "gpt/codex",
        "gpt codex": "gpt/codex",
        "claude": "claude",
        "anthropic": "claude",
        "claude team": "claude team agents",
        "claude team agents": "claude team agents",
        "team agents": "claude team agents",
        "gemini": "gemini",
        "google": "gemini",
        "재미나이": "gemini",
        "지피티": "gpt/codex",
        "클로드": "claude",
        "클로드 팀에이전트": "claude team agents",
        "클로드 팀 에이전트": "claude team agents",
    }
    normalized = aliases.get(text)
    if normalized:
        return normalized
    raise ValueError(f"unsupported provider type for intake: {value}")


def _provider_family_defaults(family: str) -> dict[str, str]:
    if family == "gpt/codex":
        return {
            "provider": "openai",
            "transport": "codex_exec_file",
            "model": DEFAULT_PROVIDER_MODEL["openai"],
            "reasoning_effort": DEFAULT_PROVIDER_REASONING["openai"],
        }
    if family == "claude":
        return {
            "provider": "anthropic",
            "transport": "claude_k",
            "model": DEFAULT_PROVIDER_MODEL["anthropic"],
            "reasoning_effort": DEFAULT_PROVIDER_REASONING["anthropic"],
        }
    if family == "claude team agents":
        return {
            "provider": "anthropic",
            "transport": "claude_k_team_agents",
            "model": DEFAULT_PROVIDER_MODEL["anthropic"],
            "reasoning_effort": DEFAULT_PROVIDER_REASONING["anthropic"],
        }
    if family == "gemini":
        return {
            "provider": "google",
            "transport": "gemini_cli",
            "model": DEFAULT_PROVIDER_MODEL["google"],
            "reasoning_effort": DEFAULT_PROVIDER_REASONING["google"],
        }
    raise ValueError(f"unsupported provider family: {family}")


def _rounds_from_answers(answers: dict[str, Any]) -> list[dict[str, str]]:
    raw_rounds = answers.get("rounds")
    if isinstance(raw_rounds, list) and raw_rounds:
        rounds = []
        for index, item in enumerate(raw_rounds, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"round #{index} must be an object")
            mode = _str_value(item.get("mode"), _mode_for_index(index, len(raw_rounds)))
            rounds.append(
                {
                    "round_id": _str_value(item.get("round_id"), f"R{index}"),
                    "mode": mode,
                    "title": _str_value(item.get("title"), ROUND_TITLE_BY_MODE.get(mode, f"Round {index}")),
                }
            )
        return rounds
    count = int(answers.get("round_count") or 3)
    if count < 1:
        raise ValueError("round_count must be positive")
    rounds = []
    for index in range(1, count + 1):
        mode = _mode_for_index(index, count)
        rounds.append({"round_id": f"R{index}", "mode": mode, "title": ROUND_TITLE_BY_MODE.get(mode, f"Round {index}")})
    return rounds


def _mode_for_index(index: int, count: int) -> str:
    if count == 1:
        return "decide"
    if index == 1:
        return "explore"
    if index == count:
        return "decide"
    return ROUND_MODE_SEQUENCE[min(index - 1, len(ROUND_MODE_SEQUENCE) - 2)]


def _seat_answers(answers: dict[str, Any]) -> list[dict[str, Any]]:
    seats = answers.get("seats")
    if isinstance(seats, list) and seats:
        return [dict(item) for item in seats if isinstance(item, dict)]
    return [seat for seat in example_public_config()["seats"] if seat.get("enabled", True) is not False]


def _seat_from_answers(item: dict[str, Any], index: int) -> dict[str, Any]:
    provider = _str_value(item.get("provider"), "manual")
    transport = _str_value(item.get("transport"), DEFAULT_PROVIDER_TRANSPORT.get(provider, "manual"))
    seat: dict[str, Any] = {
        "seat_id": _str_value(item.get("seat_id"), f"seat_{index}"),
        "provider": provider,
        "transport": transport,
        "model": _str_value(item.get("model"), DEFAULT_PROVIDER_MODEL.get(provider, "custom")),
        "reasoning_effort": _str_value(item.get("reasoning_effort"), DEFAULT_PROVIDER_REASONING.get(provider, "default")),
        "role": _str_value(item.get("role"), "independent reviewer"),
        "required": _bool_value(item.get("required"), True),
        "enabled": _bool_value(item.get("enabled"), True),
        "timeout_seconds": int(item.get("timeout_seconds") or DEFAULT_PROVIDER_TIMEOUT_SECONDS),
    }
    execution = item.get("execution")
    if isinstance(execution, dict):
        seat["execution"] = dict(execution)
    if transport == "codex_exec_file":
        seat["execution"] = {
            **dict(seat.get("execution") or {}),
            "sandbox": (seat.get("execution") or {}).get("sandbox", "workspace-write"),
            "answer_path_required": (seat.get("execution") or {}).get("answer_path_required", True),
            "stdout_capture_fallback": (seat.get("execution") or {}).get("stdout_capture_fallback", True),
            "completion_marker": (seat.get("execution") or {}).get("completion_marker", "KDH_CODEX_DONE"),
            "read_only_sandbox_forbidden": (seat.get("execution") or {}).get("read_only_sandbox_forbidden", True),
        }
    agent_profile_id = _str_value(item.get("agent_profile_id"), "")
    if agent_profile_id:
        seat["agent_profile_id"] = agent_profile_id
    team_agents = item.get("team_agents")
    if isinstance(team_agents, dict) and _bool_value(team_agents.get("enabled"), False):
        seat["transport"] = "claude_k_team_agents"
        seat["team_agents"] = {
            "enabled": True,
            "roles": _team_roles_value(team_agents.get("roles") or team_agents.get("required_teammates"), ["source-reader", "skeptic", "recorder"]),
            "required_direct_message_count": int(team_agents.get("required_direct_message_count") or DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT),
        }
    return seat


def validate_generated_config(config: dict[str, Any], *, config_path: Path | None = None) -> dict[str, Any]:
    return validate_public_config(config, config_path=config_path)


def _ask(stdout: TextIO, stdin: TextIO, label: str, default: str) -> str:
    stdout.write(f"{label} [{default}]: ")
    stdout.flush()
    value = stdin.readline().strip()
    return value or str(default)


def _ask_list(stdout: TextIO, stdin: TextIO, label: str, default: list[str]) -> list[str]:
    value = _ask(stdout, stdin, label + " (comma-separated)", ",".join(default))
    return _list_value(value, default)


def _ask_int(stdout: TextIO, stdin: TextIO, label: str, default: int) -> int:
    value = _ask(stdout, stdin, label, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"{label} must be positive")
    return parsed


def _ask_bool(stdout: TextIO, stdin: TextIO, label: str, default: bool) -> bool:
    value = _ask(stdout, stdin, label + " (y/n)", "y" if default else "n")
    return _bool_value(value, default)


def _str_value(value: Any, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or str(default)


def _language_value(value: Any, default: str) -> str:
    aliases = {
        "en": "English",
        "english": "English",
        "영어": "English",
        "ko": "Korean",
        "kor": "Korean",
        "korean": "Korean",
        "한국어": "Korean",
        "zh": "Chinese",
        "cn": "Chinese",
        "chinese": "Chinese",
        "中文": "Chinese",
        "중국어": "Chinese",
        "ja": "Japanese",
        "jp": "Japanese",
        "japanese": "Japanese",
        "日本語": "Japanese",
        "일본어": "Japanese",
        "es": "Spanish",
        "spanish": "Spanish",
        "español": "Spanish",
        "스페인어": "Spanish",
    }
    text = str(value).strip() if value is not None else ""
    if not text:
        return default
    normalized = aliases.get(text.lower()) or aliases.get(text)
    if normalized:
        return normalized
    if text in SUPPORTED_INTAKE_LANGUAGES:
        return text
    raise ValueError(f"unsupported language: {value}")


def _brainstorming_mode_value(value: Any, default: str) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if not text:
        return default
    if text not in SUPPORTED_BRAINSTORMING_MODES:
        raise ValueError(f"unsupported brainstorming mode: {value}")
    return text


def _list_value(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    elif isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
    else:
        items = []
    return items or list(default)


def _catalogs_value(catalogs: Any, catalog_paths: Any) -> list[dict[str, Any]]:
    if isinstance(catalogs, list) and catalogs:
        result = []
        for index, item in enumerate(catalogs, start=1):
            if isinstance(item, dict):
                entry = dict(item)
            else:
                path = str(item).strip()
                if not path:
                    continue
                entry = {"path": path}
            entry.setdefault("id", Path(str(entry.get("path") or f"catalog-{index}")).stem or f"catalog-{index}")
            entry.setdefault("type", "explicit_agent_catalog")
            entry.setdefault("enabled", True)
            entry.setdefault("required", True)
            result.append(entry)
        return result
    paths = _list_value(catalog_paths, [])
    return [
        {
            "id": Path(path).stem or f"catalog-{index}",
            "type": "explicit_agent_catalog",
            "path": path,
            "enabled": True,
            "required": True,
        }
        for index, path in enumerate(paths, start=1)
    ]


def _team_roles_value(value: Any, default: list[str]) -> list[Any]:
    if isinstance(value, list):
        roles: list[Any] = []
        for item in value:
            if isinstance(item, dict):
                name = _str_value(item.get("name") or item.get("role"), "")
                profile_id = _str_value(item.get("agent_profile_id"), "")
                if name or profile_id:
                    role: dict[str, Any] = {}
                    if name:
                        role["name"] = name
                    if profile_id:
                        role["agent_profile_id"] = profile_id
                    roles.append(role)
            elif str(item).strip():
                roles.append(str(item).strip())
        return roles or list(default)
    return _list_value(value, default)


def _default_agent_catalog_paths() -> list[str]:
    package_root = Path(__file__).resolve().parents[1]
    candidates = [
        package_root / "examples" / "agents" / "kdh-profile-catalog.json",
        Path.cwd() / "closed-door-training" / "workspaces" / "kdh-agents" / "catalog" / "kdh-agents.json",
        package_root / "examples" / "agents" / "kdh-mini-catalog.json",
    ]
    for path in candidates:
        resolved = path.resolve()
        if resolved.exists():
            return [str(resolved)]
    return []


def _ask_profile_assignments(stdout: TextIO, stdin: TextIO, seats: list[dict[str, Any]], catalogs: list[dict[str, Any]]) -> None:
    profiles: dict[str, dict[str, Any]]
    try:
        profiles = load_agent_profiles(catalogs)
    except ValueError as exc:
        stdout.write(f"Could not load agent catalogs yet: {exc}\n")
        profiles = {}
    for seat in seats:
        transport = str(seat.get("transport") or "")
        compatible = _compatible_profile_ids(profiles, transport=transport)
        default_profile = compatible[0] if compatible else ""
        hint = f" compatible ({len(compatible)}): {', '.join(compatible)}" if compatible else " compatible (0): none"
        profile_id = _ask(stdout, stdin, f"Agent profile for seat {seat.get('seat_id', '')}{hint}", default_profile)
        if profile_id:
            seat["agent_profile_id"] = profile_id
        team_agents = seat.get("team_agents")
        if not isinstance(team_agents, dict):
            continue
        roles = _team_roles_value(team_agents.get("roles") or team_agents.get("required_teammates"), ["source-reader", "skeptic", "recorder"])
        updated_roles: list[Any] = []
        for role in roles:
            if isinstance(role, dict):
                name = _str_value(role.get("name") or role.get("role"), _str_value(role.get("agent_profile_id"), "role"))
                current = _str_value(role.get("agent_profile_id"), "")
            else:
                name = str(role).strip()
                current = ""
            role_profile_id = _ask(stdout, stdin, f"Agent profile for Team Agents role {name}{hint}", current)
            updated_roles.append({"name": name, **({"agent_profile_id": role_profile_id} if role_profile_id else {})})
        team_agents["roles"] = updated_roles


def _compatible_profile_ids(profiles: dict[str, dict[str, Any]], *, transport: str) -> list[str]:
    ids = []
    for profile_id, profile in sorted(profiles.items()):
        compatibility = profile_compatibility(profile, transport=transport)
        if compatibility.get("compatible") is not False:
            ids.append(profile_id)
    return ids


def _bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")
