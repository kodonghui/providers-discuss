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
"${cmd}" hook-config --help >/dev/null
"${cmd}" runtime-preflight --help >/dev/null
"${cmd}" team-agents-prompt --help >/dev/null
"${cmd}" team-agents-proof-report --help >/dev/null
"${cmd}" agent-profiles --help >/dev/null

install_home="${tmp}/install-home"
"${pkg}/install.sh" --prefix "${install_home}/.local" --codex-home "${install_home}/.codex" --dry-run >/dev/null
"${pkg}/install.sh" --prefix "${install_home}/.local" --codex-home "${install_home}/.codex" >/dev/null
"${install_home}/.local/bin/providers-discuss" --help >/dev/null
test -f "${install_home}/.codex/skills/providers-discuss/SKILL.md"
"${pkg}/install.sh" --prefix "${install_home}/.local" --codex-home "${install_home}/.codex" --uninstall >/dev/null
test ! -e "${install_home}/.local/bin/providers-discuss"
test ! -e "${install_home}/.codex/skills/providers-discuss"

for config in "${pkg}"/examples/*.config.json; do
  "${cmd}" validate-config "${config}" --json >/dev/null
done

profile_report="$("${cmd}" agent-profiles \
  --config "${pkg}/examples/profile-balanced-kdh.config.json" \
  --seat human_reviewer)"
python3 - "${profile_report}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["status"] == "pass"
assert payload["profile_count"] >= 6
text = json.dumps(payload, ensure_ascii=False)
assert "source_profile_ids" not in text
assert "source_repo_paths" not in text
assert "/home/opc/kdh-harness" not in text
assert any(item["id"] == "kdh-technical-writer" for item in payload["profiles"])
PY
"${cmd}" agent-profiles \
  --config "${pkg}/examples/profile-balanced-kdh.config.json" \
  --transport manual \
  --markdown >/dev/null

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
                    "load_bearing": False,
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
