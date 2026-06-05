from __future__ import annotations

import argparse
import json
import sys

from .configure import (
    CONFIGURE_SCHEMA,
    configure_from_answers,
    configure_interactive,
    read_answers,
    validate_generated_config,
    write_config,
)
from .provider_auth import parse_cli_path_overrides, run_auth_preflight
from .public_config import example_public_config, read_public_config, validate_public_config


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
