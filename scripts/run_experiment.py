#!/usr/bin/env python3
"""Run experiments/*.yaml against the deployed gateway.

  python3 scripts/run_experiment.py experiments/noisy_neighbor.yaml --policy slo-aware --smoke
  python3 scripts/run_experiment.py experiments/noisy_neighbor.yaml --all-policies --deploy
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOADGEN = ROOT / "loadgen"
sys.path.insert(0, str(LOADGEN))
sys.path.insert(0, str(ROOT / "analysis"))

try:
    from scenario import load_scenario  # noqa: E402
    from metrics import load_events, summarize  # noqa: E402
except ModuleNotFoundError as exc:
    missing = exc.name or "a dependency"
    venv_py = ROOT / ".venv" / "bin" / "python"
    hint = (
        f"{venv_py} {Path(__file__).relative_to(ROOT)} ..."
        if venv_py.exists()
        else "python3 -m venv .venv && .venv/bin/pip install -r loadgen/requirements.txt"
    )
    sys.exit(f"Missing {missing}. Use the project venv:\n  {hint}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("yaml_path", type=Path)
    parser.add_argument("--policy", help="Single admission policy")
    parser.add_argument("--all-policies", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="10 tenants, short duration")
    parser.add_argument("--skip-deploy", action="store_true", help="Do not terraform-apply policy/run_id")
    parser.add_argument("--deploy", action="store_true", help="terraform apply admission_policy + run_id")
    parser.add_argument("--load-pct", type=float)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--adaptive-alpha", type=float, default=None)
    parser.add_argument("--adaptive-beta", type=float, default=None)
    parser.add_argument("--adaptive-window-s", type=float, default=None)
    args = parser.parse_args()

    scenario = load_scenario(args.yaml_path, smoke=args.smoke, load_pct=args.load_pct)
    policies = scenario["policies"] if args.all_policies else [args.policy or scenario["policies"][0]]
    reps = args.repetitions or (1 if args.smoke else scenario["repetitions"])
    load_pcts = [args.load_pct]
    if not args.smoke and args.load_pct is None:
        load_pcts = scenario["load_pcts"]

    gateway = _tf_output("api_endpoint")
    role = json.loads(subprocess.check_output(
        ["terraform", f"-chdir={ROOT / 'terraform/envs/dev'}", "output", "-json", "sample_role_arns"],
        text=True,
    ))["app-002"]
    bucket = _tf_output("results_bucket")
    adaptive_vars = {
        "adaptive_alpha": args.adaptive_alpha,
        "adaptive_beta": args.adaptive_beta,
        "adaptive_window_s": args.adaptive_window_s,
    }

    for policy in policies:
        for load_pct in load_pcts:
            if load_pct is not None:
                scenario = load_scenario(args.yaml_path, smoke=args.smoke, load_pct=load_pct)
            for rep in range(1, reps + 1):
                run_id = _run_id(scenario, policy, rep, load_pct, adaptive_vars)
                scenario["run_id"] = run_id
                print(f"==> {run_id} tenants={len(scenario['profiles'])} duration={scenario['duration_s']}s")
                if args.deploy and not args.skip_deploy:
                    _deploy(policy, run_id, adaptive_vars)
                _locust(scenario, gateway, role)
                _fetch_results(bucket, run_id)
                _summarize(scenario, run_id)


def _run_id(
    scenario: dict,
    policy: str,
    rep: int,
    load_pct: float | None,
    adaptive_vars: dict[str, float | None] | None = None,
) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    pct = f"-{int(load_pct)}pct" if load_pct is not None else ""
    tag = ""
    if adaptive_vars:
        a, b, w = adaptive_vars.get("adaptive_alpha"), adaptive_vars.get("adaptive_beta"), adaptive_vars.get("adaptive_window_s")
        parts = []
        if a is not None:
            parts.append(f"a{a:g}")
        if b is not None:
            parts.append(f"b{b:g}")
        if w is not None:
            parts.append(f"w{int(w) if float(w).is_integer() else w}")
        if parts:
            tag = "-" + "-".join(parts)
    return f"{scenario['name']}-{policy}{pct}{tag}-r{rep}-{stamp}"


def _tf_output(name: str) -> str:
    return subprocess.check_output(
        ["terraform", f"-chdir={ROOT / 'terraform/envs/dev'}", "output", "-raw", name],
        text=True,
    ).strip()


def _deploy(policy: str, run_id: str, adaptive_vars: dict[str, float | None] | None = None) -> None:
    tf = ROOT / "terraform/envs/dev"
    cmd = [
        "terraform",
        f"-chdir={tf}",
        "apply",
        "-input=false",
        "-auto-approve",
        f"-var=admission_policy={policy}",
        f"-var=run_id={run_id}",
    ]
    adaptive_vars = adaptive_vars or {}
    if adaptive_vars.get("adaptive_alpha") is not None:
        cmd.append(f"-var=adaptive_alpha={adaptive_vars['adaptive_alpha']}")
    if adaptive_vars.get("adaptive_beta") is not None:
        cmd.append(f"-var=adaptive_beta={adaptive_vars['adaptive_beta']}")
    if adaptive_vars.get("adaptive_window_s") is not None:
        cmd.append(f"-var=adaptive_window_s={adaptive_vars['adaptive_window_s']}")
    subprocess.check_call(cmd)
    subprocess.check_call(
        [
            "aws",
            "ecs",
            "wait",
            "services-stable",
            "--cluster",
            "bedrock-platform-dev-llm",
            "--services",
            "llm-gateway",
            "--region",
            "us-east-1",
        ]
    )


def _locust(scenario: dict, gateway: str, role: str) -> None:
    exp_file = ROOT / "analysis" / "out" / f"{scenario['run_id']}.json"
    exp_file.parent.mkdir(parents=True, exist_ok=True)
    exp_file.write_text(json.dumps(scenario), encoding="utf-8")
    users = len(scenario["profiles"])
    env = os.environ.copy()
    env.update(
        {
            "GATEWAY_URL": gateway,
            "LOADGEN_ROLE_ARN": role,
            "EXPERIMENT_FILE": str(exp_file),
            "RUN_ID": scenario["run_id"],
            "AWS_REGION": "us-east-1",
        }
    )
    rc = subprocess.call(
        [
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(LOADGEN / "locustfile.py"),
            "--headless",
            "--host",
            gateway,
            "--users",
            str(users),
            "--spawn-rate",
            str(min(users, 20)),
            "--run-time",
            f"{scenario['duration_s']}s",
            "--only-summary",
        ],
        env=env,
        cwd=str(LOADGEN),
    )
    if rc != 0:
        print(f"locust exited {rc}; still fetching gateway events from S3", file=sys.stderr)


def _fetch_results(bucket: str, run_id: str) -> Path:
    dest = ROOT / "analysis" / "out" / run_id
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.call(
        ["aws", "s3", "sync", f"s3://{bucket}/results/{run_id}", str(dest), "--region", "us-east-1", "--only-show-errors"]
    )
    return dest


def _summarize(scenario: dict, run_id: str) -> None:
    dest = ROOT / "analysis" / "out" / run_id
    events = load_events(dest)
    exclude = {scenario["victim"]} if scenario.get("exclude_victim") and scenario.get("victim") else None
    summary = summarize(events, exclude_tenants=exclude)
    out = dest / "summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
