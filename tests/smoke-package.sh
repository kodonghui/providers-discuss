#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

pkg="${tmp}/providers-discuss"
mkdir -p "${pkg}"
tar -C "${root}" --exclude='__pycache__' --exclude='*.pyc' -cf - . | tar -C "${pkg}" -xf -
cmd="${pkg}/bin/providers-discuss"

"${cmd}" --help >/dev/null
"${cmd}" -help >/dev/null
"${cmd}" hook-config --help >/dev/null
"${cmd}" runtime-preflight --help >/dev/null
"${cmd}" team-agents-prompt --help >/dev/null
"${cmd}" team-agents-proof-report --help >/dev/null
"${cmd}" advance --help >/dev/null
"${cmd}" smoke-gemini-headless --help >/dev/null
"${cmd}" agent-profiles --help >/dev/null
"${cmd}" model-refresh --help >/dev/null

install_home="${tmp}/install-home"
"${pkg}/install.sh" --prefix "${install_home}/.local" --codex-home "${install_home}/.codex" --dry-run >/dev/null
"${pkg}/install.sh" --prefix "${install_home}/.local" --codex-home "${install_home}/.codex" >/dev/null
"${install_home}/.local/bin/providers-discuss" --help >/dev/null
"${install_home}/.local/bin/providers-discuss" -help >/dev/null
test -f "${install_home}/.codex/skills/kdh-providers-discuss/SKILL.md"
test ! -e "${install_home}/.codex/skills/providers-discuss"
grep -q "name: kdh-providers-discuss" "${install_home}/.codex/skills/kdh-providers-discuss/SKILL.md"

"${pkg}/install.sh" --prefix "${install_home}/.local" --codex-home "${install_home}/.codex" --with-public-alias >/dev/null
test -f "${install_home}/.codex/skills/providers-discuss/SKILL.md"
grep -q "name: providers-discuss" "${install_home}/.codex/skills/providers-discuss/SKILL.md"
grep -q "model-refresh --provider gemini" "${pkg}/skills/kdh-providers-discuss/SKILL.md"
grep -q "run-shape gate" "${pkg}/skills/kdh-providers-discuss/SKILL.md"
grep -q "deliverable profile" "${pkg}/skills/kdh-providers-discuss/SKILL.md"
grep -q "Do not call provider CLIs directly" "${pkg}/skills/providers-discuss/SKILL.md"
grep -q "hardcode a specific Gemini version" "${pkg}/skills/providers-discuss/SKILL.md"
grep -q "KDH_FINAL_ARTIFACT" "${pkg}/README.md"
grep -q "Default Run Shape" "${pkg}/README.md"
grep -q "gpt-5.5" "${pkg}/README.md"
grep -q "xhigh" "${pkg}/README.md"
grep -q "claude-opus-4-8" "${pkg}/README.md"
grep -q "Ideation Catalyst" "${pkg}/README.md"
grep -q "기본 실행 형태" "${pkg}/README.md"

"${pkg}/install.sh" --prefix "${install_home}/.local" --codex-home "${install_home}/.codex" --uninstall >/dev/null
test ! -e "${install_home}/.local/bin/providers-discuss"
test ! -e "${install_home}/.codex/skills/providers-discuss"
test ! -e "${install_home}/.codex/skills/kdh-providers-discuss"

for config in "${pkg}"/examples/*.config.json; do
  "${cmd}" validate-config "${config}" --json >/dev/null
done

"${cmd}" config-template --output "${tmp}/default-template.json" >/dev/null
python3 - "${tmp}/default-template.json" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
seats = [seat for seat in config["seats"] if seat.get("enabled", True) is not False]
assert [seat["seat_id"] for seat in seats] == ["gpt", "claude_team"]
assert seats[0]["provider"] == "openai"
assert seats[0]["transport"] == "codex_exec_file"
assert seats[0]["model"] == "gpt-5.5"
assert seats[0]["reasoning_effort"] == "xhigh"
assert seats[1]["provider"] == "anthropic"
assert seats[1]["transport"] == "claude_k_team_agents"
assert seats[1]["model"] == "claude-opus-4-8"
assert seats[1]["reasoning_effort"] == "max"
assert seats[1]["execution"]["permission_mode"] == "auto"
team_agents = seats[1]["team_agents"]
assert "team_agent_count" not in team_agents
assert "Ideation Catalyst" in team_agents["roles"]
PY

cat > "${tmp}/configure-answers.json" <<'EOF'
{
  "language": "Korean",
  "round_count": 2,
  "brainstorming_mode": "light",
  "objective": "Smoke configure intake fields.",
  "source_dirs": ["./inputs"],
  "seats": [
    {
      "seat_id": "gpt_xhigh",
      "provider": "openai",
      "transport": "codex_exec_file",
      "model": "gpt-5.5",
      "reasoning_effort": "xhigh",
      "role": "verify generated config",
      "required": true
    }
  ]
}
EOF
"${cmd}" configure \
  --answers-json "${tmp}/configure-answers.json" \
  --output "${tmp}/configured.json" \
  --json >/dev/null
python3 - "${tmp}/configured.json" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert config["language"]["conversation"] == "Korean"
assert config["brainstorming"]["mode"] == "light"
assert config["deliverable_profile"]["id"] == "development_contract"
assert config["seats"][0]["reasoning_effort"] == "xhigh"
PY
PYTHONPATH="${pkg}" python3 - <<'PY'
from providers_discuss.profiles import normalize_deliverable_profile, section_presence
from providers_discuss.provider_auth import login_hint_for_transport, login_url_action_for_transport

profile = normalize_deliverable_profile("development_contract")
assert profile["final_artifacts"][0]["path"] == "final/development-contract.md"
sections = section_presence("## Requirements Definition\n\nx\n", ["Requirements Definition", "Functional Spec"])
assert sections == {"Requirements Definition": "present", "Functional Spec": "missing"}

for transport in ("codex_exec_file", "claude_k", "claude_k_team_agents", "gemini_cli"):
    hint = login_hint_for_transport(transport).lower()
    action = login_url_action_for_transport(transport).lower()
    assert "login" in hint
    assert "url" in hint
    assert "url" in action
PY

fake_gemini="${tmp}/fake-gemini"
cat > "${fake_gemini}" <<'PY'
#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

prompt = sys.stdin.read()
argv = " ".join(sys.argv)
counter = os.environ.get("KDH_FAKE_GEMINI_COUNTER")
if counter:
    path = Path(counter)
    path.write_text(str((int(path.read_text() or "0") if path.exists() else 0) + 1), encoding="utf-8")
if os.environ.get("GEMINI_CLI_TRUST_WORKSPACE") != "true":
    print("untrusted directory: GEMINI_CLI_TRUST_WORKSPACE=true required", file=sys.stderr)
    raise SystemExit(23)
if "GEMINI_AUTH_OK" in argv:
    print(json.dumps({"response": "GEMINI_AUTH_OK"}))
    raise SystemExit(0)

response = "# Fake Gemini answer\n\n"
response += "package smoke headless response\n"
response += f"prompt_bytes={len(prompt.encode('utf-8'))}\n"
response += "KDH_GEMINI_DONE\n"
print(json.dumps({"response": response, "stats": {"models": {"gemini-test": {"tokens": {"total": 1}}}}}))
PY
chmod +x "${fake_gemini}"

fake_claude="${tmp}/fake-claude"
cat > "${fake_claude}" <<'PY'
#!/usr/bin/env python3
import json
import os
import select
import sys
from pathlib import Path

cwd = Path.cwd()
stdin_chunks = []
for _ in range(20):
    readable, _, _ = select.select([sys.stdin], [], [], 0.05)
    if not readable:
        continue
    data = os.read(sys.stdin.fileno(), 4096)
    if not data:
        break
    stdin_chunks.append(data.decode("utf-8", errors="replace"))
    if "Write the required artifacts before final response" in "".join(stdin_chunks):
        break
runtime = {
    "argv": sys.argv,
    "stdin": "".join(stdin_chunks),
    "env": {
        "KDH_PROVIDER_DISCUSS_CLAUDE_MODEL": os.environ.get("KDH_PROVIDER_DISCUSS_CLAUDE_MODEL", ""),
        "KDH_PROVIDER_DISCUSS_CLAUDE_EFFORT": os.environ.get("KDH_PROVIDER_DISCUSS_CLAUDE_EFFORT", ""),
        "KDH_PROVIDER_DISCUSS_CLAUDE_PERMISSION_MODE": os.environ.get("KDH_PROVIDER_DISCUSS_CLAUDE_PERMISSION_MODE", ""),
    },
}
(cwd / "fake-claude-runtime.json").write_text(json.dumps(runtime, indent=2, sort_keys=True), encoding="utf-8")
counter = os.environ.get("KDH_FAKE_CLAUDE_COUNTER")
if counter:
    path = Path(counter)
    path.write_text(str((int(path.read_text() or "0") if path.exists() else 0) + 1), encoding="utf-8")

answer = Path(os.environ["KDH_PROVIDER_DISCUSS_ANSWER_PATH"])
status = Path(os.environ["KDH_PROVIDER_DISCUSS_STATUS_PATH"])
marker = os.environ["KDH_PROVIDER_DISCUSS_COMPLETION_MARKER"]
run_root = Path(os.environ["KDH_PROVIDER_DISCUSS_RUN_ROOT"])
run_id = run_root.name
team_name = os.environ.get("KDH_PROVIDER_DISCUSS_TEAM_NAME", f"providers-r1-{run_id}")
answer.parent.mkdir(parents=True, exist_ok=True)
status.parent.mkdir(parents=True, exist_ok=True)
answer.write_text(f"# fake claude team answer\n\nrun_id={run_id}\nteam={team_name}\n\n{marker}\n", encoding="utf-8")
status.write_text(
    json.dumps(
        {
            "schema": "kdh.providers-discuss.claude-team-agents-status.v1",
            "run_id": run_id,
            "round_id": "R1",
            "seat_id": "claude_team_shape",
            "team_name": team_name,
            "trigger_mode": "prompt_only",
            "verdict": "admitted",
            "timed_out": False,
            "team_create_used": True,
            "task_create_count": 4,
            "agent_calls_with_team_name": 4,
            "direct_teammate_messages_required": 6,
            "direct_teammate_messages_observed": 6,
            "ordinary_agent_delegation_only": False,
            "summary_only_delegation": False,
            "blocked_reason": "",
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
home = Path.home()
project = home / ".claude" / "projects"
project.mkdir(parents=True, exist_ok=True)
events = [
    ("TeamCreate", {"team_name": team_name}),
    ("TaskCreate", {"team_name": team_name, "task": "ideation-catalyst"}),
    ("TaskCreate", {"team_name": team_name, "task": "readme-writer"}),
    ("TaskCreate", {"team_name": team_name, "task": "maturity-auditor"}),
    ("TaskCreate", {"team_name": team_name, "task": "boundary-reviewer"}),
    ("Agent", {"team_name": team_name, "role": "ideation-catalyst"}),
    ("Agent", {"team_name": team_name, "role": "readme-writer"}),
    ("Agent", {"team_name": team_name, "role": "maturity-auditor"}),
    ("Agent", {"team_name": team_name, "role": "boundary-reviewer"}),
]
events.extend(("SendMessage", {"team_name": team_name, "token": token}) for token in ("RW->MA", "MA->BR", "BR->RW", "RW->BR", "MA->RW", "BR->MA"))
with (project / "fake-team.jsonl").open("w", encoding="utf-8") as fh:
    for name, payload in events:
        fh.write(json.dumps({"message": {"content": [{"type": "tool_use", "name": name, "input": payload}]}}) + "\n")
(home / ".claude" / "teams" / team_name).mkdir(parents=True, exist_ok=True)
(home / ".claude" / "teams" / team_name / "state.json").write_text(json.dumps({"team_name": team_name}) + "\n", encoding="utf-8")
for name, payload in events:
    print(f"{name} team_name={payload.get('team_name')}")
if os.environ.get("KDH_FAKE_CLAUDE_ARTIFACT_ONLY") == "1":
    import time
    time.sleep(10)
else:
    print(marker)
PY
chmod +x "${fake_claude}"

fake_codex="${tmp}/fake-codex"
cat > "${fake_codex}" <<'PY'
#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

prompt = sys.stdin.read()
counter = os.environ.get("KDH_FAKE_CODEX_COUNTER")
if counter:
    path = Path(counter)
    path.write_text(str((int(path.read_text() or "0") if path.exists() else 0) + 1), encoding="utf-8")
output = None
for index, item in enumerate(sys.argv):
    if item in {"-o", "--output-last-message"} and index + 1 < len(sys.argv):
        output = Path(sys.argv[index + 1])
if output is None:
    raise SystemExit("missing -o/--output-last-message")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    "# Fake Codex answer\n\n"
    + f"argv={json.dumps(sys.argv)}\n"
    + f"prompt_bytes={len(prompt.encode('utf-8'))}\n"
    + "KDH_CODEX_DONE\n",
    encoding="utf-8",
)
print("fake codex completed")
PY
chmod +x "${fake_codex}"

cat > "${tmp}/gemini-live.config.json" <<'EOF'
{
  "schema": "providers-discuss.public-config.v1",
  "objective": "Smoke Gemini headless dispatch.",
  "rounds": [
    {"round_id": "R1", "mode": "decide", "title": "Gemini smoke decision"}
  ],
  "seats": [
    {
      "seat_id": "gemini_required",
      "provider": "google",
      "transport": "gemini_cli",
      "model": "gemini-test",
      "reasoning_effort": "default",
      "role": "required Gemini headless reviewer",
      "required": true,
      "timeout_seconds": 5
    }
  ]
}
EOF
cat > "${tmp}/mixed-live.config.json" <<'EOF'
{
  "schema": "providers-discuss.public-config.v1",
  "objective": "Smoke mixed live dispatch partial behavior.",
  "rounds": [
    {"round_id": "R1", "mode": "decide", "title": "Mixed live dispatch"}
  ],
  "seats": [
    {
      "seat_id": "codex_required",
      "provider": "openai",
      "transport": "codex_exec_file",
      "model": "gpt-5.5",
      "reasoning_effort": "medium",
      "role": "required structural reviewer",
      "required": true,
      "timeout_seconds": 5,
      "execution": {
        "answer_path_required": true,
        "completion_marker": "KDH_CODEX_DONE",
        "read_only_sandbox_forbidden": true,
        "sandbox": "workspace-write",
        "stdout_capture_fallback": true
      }
    },
    {
      "seat_id": "claude_team_required",
      "provider": "anthropic",
      "transport": "claude_k_team_agents",
      "model": "sonnet",
      "reasoning_effort": "medium",
      "role": "required Claude Team Agents reviewer",
      "required": true,
      "timeout_seconds": 5,
      "execution": {
        "model": "sonnet",
        "effort": "medium",
        "permission_mode": "auto"
      },
      "team_agents": {
        "enabled": true,
        "required_direct_message_count": 6,
        "roles": [
          {"name": "Ideation Catalyst"},
          {"name": "readme-writer"},
          {"name": "maturity-auditor"},
          {"name": "boundary-reviewer"}
        ]
      }
    },
    {
      "seat_id": "gemini_required",
      "provider": "google",
      "transport": "gemini_cli",
      "model": "gemini-test",
      "reasoning_effort": "default",
      "role": "required Gemini headless reviewer",
      "required": true,
      "timeout_seconds": 5
    }
  ]
}
EOF
cat > "${tmp}/full-live.config.json" <<'EOF'
{
  "schema": "providers-discuss.public-config.v1",
  "objective": "Run a three-round, three-seat fake live dispatch proof.",
  "rounds": [
    {"round_id": "R1", "mode": "explore", "title": "Explore README framing"},
    {"round_id": "R2", "mode": "challenge", "title": "Challenge maturity and billing claims"},
    {"round_id": "R3", "mode": "decide", "title": "Decide README contract"}
  ],
  "seats": [
    {
      "seat_id": "codex_required",
      "provider": "openai",
      "transport": "codex_exec_file",
      "model": "gpt-5.5",
      "reasoning_effort": "medium",
      "role": "required Codex reviewer",
      "required": true,
      "timeout_seconds": 5,
      "execution": {
        "answer_path_required": true,
        "completion_marker": "KDH_CODEX_DONE",
        "read_only_sandbox_forbidden": true,
        "sandbox": "workspace-write",
        "stdout_capture_fallback": true
      }
    },
    {
      "seat_id": "claude_team_required",
      "provider": "anthropic",
      "transport": "claude_k_team_agents",
      "model": "sonnet",
      "reasoning_effort": "medium",
      "role": "required Claude Team Agents reviewer",
      "required": true,
      "timeout_seconds": 5,
      "execution": {
        "model": "sonnet",
        "effort": "medium",
        "permission_mode": "auto"
      },
      "team_agents": {
        "enabled": true,
        "required_direct_message_count": 6,
        "roles": [
          {"name": "Ideation Catalyst"},
          {"name": "readme-writer"},
          {"name": "maturity-auditor"},
          {"name": "boundary-reviewer"}
        ]
      }
    },
    {
      "seat_id": "gemini_required",
      "provider": "google",
      "transport": "gemini_cli",
      "model": "gemini-test",
      "reasoning_effort": "default",
      "role": "required Gemini reviewer",
      "required": true,
      "timeout_seconds": 5
    }
  ]
}
EOF
cat > "${tmp}/claude-shape.config.json" <<'EOF'
{
  "schema": "providers-discuss.public-config.v1",
  "objective": "Smoke Claude run-shape binding.",
  "rounds": [
    {"round_id": "R1", "mode": "decide", "title": "Claude shape binding"}
  ],
  "seats": [
    {
      "seat_id": "claude_team_shape",
      "provider": "anthropic",
      "transport": "claude_k_team_agents",
      "model": "sonnet",
      "reasoning_effort": "medium",
      "role": "shape-bound Team Agents reviewer",
      "required": true,
      "timeout_seconds": 5,
      "execution": {
        "model": "sonnet",
        "effort": "medium",
        "permission_mode": "auto"
      },
      "team_agents": {
        "enabled": true,
        "required_direct_message_count": 6,
        "roles": [
          {"name": "Ideation Catalyst"},
          {"name": "readme-writer"},
          {"name": "maturity-auditor"},
          {"name": "boundary-reviewer"}
        ]
      }
    }
  ]
}
EOF
"${cmd}" auth-preflight "${tmp}/gemini-live.config.json" \
  --report-dir "${tmp}/gemini-auth" \
  --cli-path "gemini_cli=${fake_gemini}" \
  --json > "${tmp}/gemini-auth.json"
python3 - "${tmp}/gemini-auth.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["status"] == "pass"
assert payload["seats"][0]["probe"] == "gemini_headless_probe"
assert payload["seats"][0]["status"] == "installed_logged_in"
PY

profile_report="$("${cmd}" agent-profiles \
  --config "${pkg}/examples/profile-balanced-kdh.config.json" \
  --seat human_reviewer)"
python3 - "${profile_report}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["status"] == "pass"
assert payload["profile_count"] == 15
text = json.dumps(payload, ensure_ascii=False)
assert "source_profile_ids" not in text
assert "source_repo_paths" not in text
assert "/home/opc/kdh-harness" not in text
assert any(item["id"] == "kdh-technical-writer" for item in payload["profiles"])
assert any(item["id"] == "kdh-security-reviewer" for item in payload["profiles"])
PY
"${cmd}" agent-profiles \
  --config "${pkg}/examples/profile-balanced-kdh.config.json" \
  --transport manual \
  --markdown >/dev/null
gemini_profile_report="$("${cmd}" agent-profiles \
  --config "${pkg}/examples/profile-balanced-kdh.config.json" \
  --transport gemini_cli)"
python3 - "${gemini_profile_report}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
compatible = [item["id"] for item in payload["profiles"] if item["compatibility"]["compatible"] is True]
assert payload["profile_count"] == 15
assert len(compatible) == 15
PY
PYTHONPATH="${pkg}" python3 - <<'PY'
from pathlib import Path
from providers_discuss.configure import _default_agent_catalog_paths

paths = [Path(path).resolve() for path in _default_agent_catalog_paths()]
assert paths
assert paths[0].exists()
assert paths[0].name == "kdh-profile-catalog.json", paths
PY

work="${tmp}/work"
mkdir -p "${work}/inputs" "${work}/answers"
printf '# Source\n\nKeep decisions tied to artifacts.\n' > "${work}/inputs/source.md"

"${cmd}" build-input-pack \
  --config "${pkg}/examples/minimal-manual.config.json" \
  --source-dir "${work}/inputs" \
  --output-dir "${work}/input-pack" >/dev/null

run_id="$("${cmd}" init \
  --config "${pkg}/examples/minimal-manual.config.json" \
  --root "${work}/runs" \
  --run-id smoke-manual)"

"${cmd}" preflight "${run_id}" --root "${work}/runs" >/dev/null
"${cmd}" run-round "${run_id}" --root "${work}/runs" --round R1 --mode dry-run >/dev/null

printf '# Manual answer\n\nManual evidence is preserved as an answer artifact.\n' > "${work}/answers/human.md"
"${cmd}" run-round "${run_id}" \
  --root "${work}/runs" \
  --round R1 \
  --mode manual-import \
  --answer "human_reviewer=${work}/answers/human.md" >/dev/null

python3 - "${work}/runs/${run_id}" <<'PY'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
(run / "claims").mkdir(exist_ok=True)
(run / "claims" / "round-R1-claim-map.json").write_text(
    json.dumps(
        {
            "schema": "kdh.providers-discuss.claim-map.v1",
            "run_id": run.name,
            "round_id": "R1",
            "claims": [
                {
                    "claim_id": "CLM-R1-001",
                    "claim": "Manual smoke preserved the answer artifact.",
                    "claim_type": "decision",
                    "status": "supported",
                    "load_bearing": True,
                    "support": ["answers/round-R1/human_reviewer.md"],
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

"${cmd}" gate "${run_id}" --root "${work}/runs" --round R1 >/dev/null
"${cmd}" orchestrate "${run_id}" --root "${work}/runs" --after-round R1 >/dev/null
"${cmd}" verify "${run_id}" --root "${work}/runs" >/dev/null
set +e
"${cmd}" advance "${run_id}" --root "${work}/runs" --round-mode dry-run --json > "${work}/advance.json"
advance_rc=$?
set -e
test "${advance_rc}" -eq 2
python3 - "${work}/advance.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["status"] == "blocked"
assert payload["state"] == "round_prompt_ready"
assert payload["current_round"] == "R2"
assert payload["stop_reason"] == "provider_answers_needed"
assert payload["actions"][0]["action"] == "run-round"
PY

gemini_run="$("${cmd}" init \
  --config "${tmp}/gemini-live.config.json" \
  --root "${work}/runs" \
  --run-id smoke-gemini)"
"${cmd}" preflight "${gemini_run}" --root "${work}/runs" >/dev/null
"${cmd}" smoke-gemini-headless "${gemini_run}" \
  --root "${work}/runs" \
  --round R1 \
  --seat gemini_required \
  --gemini-bin "${fake_gemini}" \
  --timeout-seconds 5 \
  --json >/dev/null
"${cmd}" verify-proof "${gemini_run}" \
  --root "${work}/runs" \
  --kind transport \
  --proof logs/round-R1/gemini_required.proof.json >/dev/null
"${cmd}" run-round "${gemini_run}" \
  --root "${work}/runs" \
  --round R1 \
  --mode live-dispatch \
  --cli-path "gemini_cli=${fake_gemini}" >/dev/null
"${cmd}" verify "${gemini_run}" --root "${work}/runs" >/dev/null
grep -q "KDH_GEMINI_DONE" "${work}/runs/${gemini_run}/answers/round-R1/gemini_required.md"

mixed_run="$("${cmd}" init \
  --config "${tmp}/mixed-live.config.json" \
  --root "${work}/runs" \
  --run-id smoke-mixed)"
"${cmd}" preflight "${mixed_run}" --root "${work}/runs" >/dev/null
set +e
HOME="${tmp}/fake-claude-home-mixed" "${cmd}" run-round "${mixed_run}" \
  --root "${work}/runs" \
  --round R1 \
  --mode live-dispatch \
  --cli-path "codex=${fake_codex}" \
  --cli-path "claude=${fake_claude}" \
  --cli-path "gemini_cli=${fake_gemini}" > "${work}/mixed-live.out" 2> "${work}/mixed-live.err"
mixed_rc=$?
set -e
test "${mixed_rc}" -eq 0
grep -q "live dispatch completed" "${work}/mixed-live.out"
grep -q "KDH_CODEX_DONE" "${work}/runs/${mixed_run}/answers/round-R1/codex_required.md"
grep -q "KDH_CLAUDE_DONE" "${work}/runs/${mixed_run}/answers/round-R1/claude_team_required.md"
grep -q "KDH_GEMINI_DONE" "${work}/runs/${mixed_run}/answers/round-R1/gemini_required.md"
python3 - "${work}/runs/${mixed_run}/run.json" <<'PY'
import json
import sys
from pathlib import Path

run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert run["state"] == "round_outputs_collected"
assert run["current_round"] == "R1"
PY
python3 - "${work}/runs/${mixed_run}" <<'PY'
import json
import sys
from pathlib import Path

run_root = Path(sys.argv[1])
run_path = run_root / "run.json"
run = json.loads(run_path.read_text(encoding="utf-8"))
run["state"] = "failed"
run["current_round"] = "R1"
run_path.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
status_path = run_root / "logs/round-R1/claude_team_required.status.json"
status = json.loads(status_path.read_text(encoding="utf-8"))
status["status"] = "failed"
status["verdict"] = "failed"
status["blocked_reason"] = "simulated_retry"
status["failure_classification"] = "simulated_retry"
status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
HOME="${tmp}/fake-claude-home-mixed-retry" \
KDH_FAKE_CODEX_COUNTER="${work}/codex-retry-count" \
KDH_FAKE_CLAUDE_COUNTER="${work}/claude-retry-count" \
KDH_FAKE_GEMINI_COUNTER="${work}/gemini-retry-count" \
"${cmd}" run-round "${mixed_run}" \
  --root "${work}/runs" \
  --round R1 \
  --mode live-dispatch \
  --cli-path "codex=${fake_codex}" \
  --cli-path "claude=${fake_claude}" \
  --cli-path "gemini_cli=${fake_gemini}" > "${work}/mixed-live-retry.out"
python3 - "${work}" "${work}/runs/${mixed_run}/events.jsonl" <<'PY'
import json
import sys
from pathlib import Path

work = Path(sys.argv[1])
events_path = Path(sys.argv[2])
def count(name: str) -> int:
    path = work / name
    return int(path.read_text(encoding="utf-8")) if path.exists() else 0
assert count("codex-retry-count") == 0
assert count("gemini-retry-count") == 0
assert count("claude-retry-count") == 1
events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
assert any(event.get("type") == "provider.reused" and event.get("actor") == "codex_required" for event in events)
assert any(event.get("type") == "provider.reused" and event.get("actor") == "gemini_required" for event in events)
summary = (events_path.parent / "summary.md").read_text(encoding="utf-8")
assert summary.count("- round_id: `R1`\n- seat_id: `claude_team_required`") == 1
PY

full_run="$("${cmd}" init \
  --config "${tmp}/full-live.config.json" \
  --root "${work}/runs" \
  --run-id smoke-full-live)"
"${cmd}" preflight "${full_run}" --root "${work}/runs" >/dev/null
HOME="${tmp}/fake-claude-home-full" "${cmd}" advance "${full_run}" \
  --root "${work}/runs" \
  --round-mode live-dispatch \
  --cli-path "codex=${fake_codex}" \
  --cli-path "claude=${fake_claude}" \
  --cli-path "gemini_cli=${fake_gemini}" \
  --max-steps 30 \
  --json > "${work}/full-live-advance.json"
python3 - "${work}/runs/${full_run}" "${work}/full-live-advance.json" <<'PY'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert payload["status"] == "pass"
assert payload["state"] == "finished"
run_rounds = [item for item in payload["actions"] if item["action"] == "run-round"]
assert [item["round_id"] for item in run_rounds] == ["R1", "R2", "R3"]
assert (run / "result.json").exists()
for round_id in ("R1", "R2", "R3"):
    assert (run / "claims" / f"round-{round_id}-claim-map.json").exists()
    for seat in ("codex_required", "claude_team_required", "gemini_required"):
        assert (run / "answers" / f"round-{round_id}" / f"{seat}.md").exists()
PY
"${cmd}" verify "${full_run}" --root "${work}/runs" >/dev/null

claude_shape_run="$("${cmd}" init \
  --config "${tmp}/claude-shape.config.json" \
  --root "${work}/runs" \
  --run-id smoke-claude-shape)"
"${cmd}" preflight "${claude_shape_run}" --root "${work}/runs" >/dev/null
HOME="${tmp}/fake-claude-home" "${cmd}" smoke-claude-team-agents "${claude_shape_run}" \
  --root "${work}/runs" \
  --round R1 \
  --seat claude_team_shape \
  --claude-bin "${fake_claude}" \
  --experimental-agent-teams \
  --json > "${work}/claude-shape.json"
python3 - "${work}/runs/${claude_shape_run}" "${work}/claude-shape.json" <<'PY'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert payload["status"] == "pass"
assert payload["proof_path"] == "logs/round-R1/claude_team_shape.team-agents-smoke.proof.json"
runtime = json.loads((run / "fake-claude-runtime.json").read_text(encoding="utf-8"))
argv = runtime["argv"]
assert argv[argv.index("--model") + 1] == "sonnet"
assert argv[argv.index("--effort") + 1] == "medium"
assert argv[argv.index("--permission-mode") + 1] == "auto"
argv_text = "\n".join(argv)
assert "# KDH Claude-K Team Agents Live Smoke Contract" not in argv_text
assert "claude_team_shape.live-team-agents-smoke.md" not in argv_text
assert "claude_team_shape.live-team-agents-smoke.md" in runtime["stdin"]
assert "Read and execute the instructions in this prompt file exactly" in runtime["stdin"]
assert runtime["env"]["KDH_PROVIDER_DISCUSS_CLAUDE_MODEL"] == "sonnet"
assert runtime["env"]["KDH_PROVIDER_DISCUSS_CLAUDE_EFFORT"] == "medium"
proof = json.loads((run / payload["proof_path"]).read_text(encoding="utf-8"))
assert proof["runtime"]["model"]["effective"] == "sonnet"
assert proof["runtime"]["effort"]["effective"] == "medium"
assert proof["runtime"]["timeout_seconds"]["effective"] == 5
assert proof["runtime"]["timeout_seconds"]["overridden"] is False
assert proof["required_teammates"] == ["Ideation Catalyst", "readme-writer", "maturity-auditor", "boundary-reviewer"]
prompt = (run / "prompts" / "round-R1" / "claude_team_shape.live-team-agents-smoke.md").read_text(encoding="utf-8")
assert "Ideation Catalyst, readme-writer, maturity-auditor, and boundary-reviewer" in prompt
assert "source-reader, skeptic, and recorder" not in prompt
assert "substantive provider result" not in prompt
assert "substantive answer section" not in prompt
assert '"task_create_count": 4' in prompt
assert '"agent_calls_with_team_name": 4' in prompt
PY
if HOME="${tmp}/fake-claude-home-override" "${cmd}" smoke-claude-team-agents "${claude_shape_run}" \
  --root "${work}/runs" \
  --round R1 \
  --seat claude_team_shape \
  --claude-bin "${fake_claude}" \
  --timeout-seconds 4 \
  --experimental-agent-teams \
  --json >/dev/null 2>"${work}/claude-override.err"; then
  echo "timeout override without reason unexpectedly passed" >&2
  exit 1
fi
grep -q "override requires --override-reason" "${work}/claude-override.err"

claude_artifact_run="$("${cmd}" init \
  --config "${tmp}/claude-shape.config.json" \
  --root "${work}/runs" \
  --run-id smoke-claude-artifact-completion)"
"${cmd}" preflight "${claude_artifact_run}" --root "${work}/runs" >/dev/null
HOME="${tmp}/fake-claude-home-artifact" KDH_FAKE_CLAUDE_ARTIFACT_ONLY=1 "${cmd}" smoke-claude-team-agents "${claude_artifact_run}" \
  --root "${work}/runs" \
  --round R1 \
  --seat claude_team_shape \
  --claude-bin "${fake_claude}" \
  --timeout-seconds 10 \
  --override-reason "package smoke artifact completion cleanup" \
  --experimental-agent-teams \
  --json > "${work}/claude-artifact-completion.json"
python3 - "${work}/runs/${claude_artifact_run}" "${work}/claude-artifact-completion.json" <<'PY'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert payload["status"] == "pass"
proof = json.loads((run / payload["proof_path"]).read_text(encoding="utf-8"))
assert proof["cleanup_after_completion"] is True
PY

profile_run="$("${cmd}" init \
  --config "${pkg}/examples/profile-balanced-kdh.config.json" \
  --root "${work}/runs" \
  --run-id smoke-profiles)"
"${cmd}" preflight "${profile_run}" --root "${work}/runs" >/dev/null
"${cmd}" run-round "${profile_run}" --root "${work}/runs" --round R1 --mode dry-run >/dev/null
grep -q "Agent Profile Contract" "${work}/runs/${profile_run}/prompts/round-R1/human_reviewer.prompt.md"
grep -q "profile_id: \`kdh-technical-writer\`" "${work}/runs/${profile_run}/prompts/round-R1/human_reviewer.prompt.md"
team_profile_json="$("${cmd}" team-agents-prompt "${profile_run}" --root "${work}/runs" --round R1 --seat claude_team --json)"
team_profile_prompt="$(python3 - "${team_profile_json}" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["prompt_path"])
PY
)"
grep -q "Agent Profile Contracts" "${work}/runs/${profile_run}/${team_profile_prompt}"
grep -q "profile_id: \`kdh-ideation-catalyst\`" "${work}/runs/${profile_run}/${team_profile_prompt}"

team_run="$("${cmd}" init \
  --config "${pkg}/examples/claude-team-agents.config.json" \
  --root "${work}/runs" \
  --run-id smoke-team)"
"${cmd}" preflight "${team_run}" --root "${work}/runs" >/dev/null
"${cmd}" team-agents-prompt "${team_run}" --root "${work}/runs" --round R1 --seat claude_team --json >/dev/null

python3 - "${work}/runs/${team_run}" <<'PY'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
logs = run / "logs" / "round-R1"
logs.mkdir(parents=True, exist_ok=True)
(logs / "summary-only.proof.json").write_text(
    json.dumps(
        {
            "schema": "kdh.providers-discuss.team-agents-proof.v1",
            "trigger_mode": "prompt_only",
            "team_create_used": False,
            "team_name": "summary-only",
            "required_task_count": 3,
            "task_create_count": 0,
            "required_team_scoped_agent_calls": 3,
            "agent_calls_with_team_name": 0,
            "direct_teammate_messages_required": 6,
            "direct_teammate_messages_observed": 0,
            "ordinary_agent_delegation_only": True,
            "summary_only_delegation": True,
            "artifacts": {},
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

if "${cmd}" team-agents-proof-report "${team_run}" \
  --root "${work}/runs" \
  --proof "logs/round-R1/summary-only.proof.json" \
  --json >/dev/null; then
  echo "summary-only proof unexpectedly passed" >&2
  exit 1
fi

echo "providers-discuss package smoke: pass"
