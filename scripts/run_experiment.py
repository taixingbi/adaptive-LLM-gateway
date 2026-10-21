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
from urllib.parse import urlparse

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session

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
    parser.add_argument("--rep-start", type=int, default=1)
    parser.add_argument("--adaptive-alpha", type=float, default=None)
    parser.add_argument("--adaptive-beta", type=float, default=None)
    parser.add_argument("--adaptive-window-s", type=float, default=None)
    parser.add_argument("--platform-tpm-budget", type=int, default=None)
    parser.add_argument("--reset-adaptive", action="store_true", help="POST /v1/admin/reset-adaptive after deploy")
    parser.add_argument("--no-reset-adaptive", action="store_true")
    parser.add_argument("--background-concurrency", type=int, default=None)
    args = parser.parse_args()

    scenario = load_scenario(args.yaml_path, smoke=args.smoke, load_pct=args.load_pct)
    policies = scenario["policies"] if args.all_policies else [args.policy or scenario["policies"][0]]
    reps = args.repetitions or (1 if args.smoke else scenario["repetitions"])
    load_pcts = [args.load_pct]
    if not args.smoke and args.load_pct is None:
        load_pcts = scenario["load_pcts"]

    gateway = _tf_output("api_endpoint")
    role = json.loads(
        subprocess.check_output(
            ["terraform", f"-chdir={ROOT / 'terraform/envs/dev'}", "output", "-json", "sample_role_arns"],
            text=True,
        )
    )["app-002"]
    bucket = _tf_output("results_bucket")
    adaptive_vars = {
        "adaptive_alpha": args.adaptive_alpha,
        "adaptive_beta": args.adaptive_beta,
        "adaptive_window_s": args.adaptive_window_s,
    }
    budget = args.platform_tpm_budget
    if budget is None and scenario.get("platform_tpm_budget") is not None:
        budget = int(scenario["platform_tpm_budget"])

    last_deploy = None
    for policy in policies:
        for load_pct in load_pcts:
            if load_pct is not None:
                scenario = load_scenario(args.yaml_path, smoke=args.smoke, load_pct=load_pct)
            for rep in range(args.rep_start, args.rep_start + reps):
                run_id = _run_id(scenario, policy, rep, load_pct, adaptive_vars, budget)
                scenario["run_id"] = run_id
                print(f"==> {run_id} tenants={len(scenario['profiles'])} duration={scenario['duration_s']}s", flush=True)
                deploy_key = (policy, budget, args.adaptive_alpha, args.adaptive_beta, args.adaptive_window_s)
                if args.deploy and not args.skip_deploy and deploy_key != last_deploy:
                    _deploy(policy, run_id, adaptive_vars, budget)
                    last_deploy = deploy_key
                do_reset = args.reset_adaptive or (
                    policy == "adaptive-slo" and not args.no_reset_adaptive
                )
                if do_reset:
                    expected = int(budget if budget is not None else 100000)
                    _reset_adaptive(gateway, role, expected)
                dest = ROOT / "analysis" / "out" / run_id
                dest.mkdir(parents=True, exist_ok=True)
                bg = _start_background(scenario, dest, args.background_concurrency)
                try:
                    _locust(scenario, gateway, role)
                finally:
                    _stop_background(bg)
                _fetch_results(bucket, run_id)
                _summarize(scenario, run_id)


def _run_id(
    scenario: dict,
    policy: str,
    rep: int,
    load_pct: float | None,
    adaptive_vars: dict[str, float | None] | None = None,
    budget: int | None = None,
) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    pct = f"-{int(load_pct)}pct" if load_pct is not None else ""
    tag = ""
    if adaptive_vars:
        a, b, w = (
            adaptive_vars.get("adaptive_alpha"),
            adaptive_vars.get("adaptive_beta"),
            adaptive_vars.get("adaptive_window_s"),
        )
        parts = []
        if a is not None:
            parts.append(f"a{a:g}")
        if b is not None:
            parts.append(f"b{b:g}")
        if w is not None:
            parts.append(f"w{int(w) if float(w).is_integer() else w}")
        if parts:
            tag = "-" + "-".join(parts)
    return f"{scenario['name']}-{policy}{pct}{tag}{_budget_tag(budget)}-r{rep}-{stamp}"


def _budget_tag(budget: int | None) -> str:
    if budget is None:
        return ""
    if budget >= 1_000_000 and budget % 1_000_000 == 0:
        return f"-c{budget // 1_000_000}M"
    if budget >= 1000 and budget % 1000 == 0:
        return f"-c{budget // 1000}k"
    return f"-c{budget}"


def _tf_output(name: str) -> str:
    return subprocess.check_output(
        ["terraform", f"-chdir={ROOT / 'terraform/envs/dev'}", "output", "-raw", name],
        text=True,
    ).strip()


def _deploy(
    policy: str,
    run_id: str,
    adaptive_vars: dict[str, float | None] | None = None,
    budget: int | None = None,
) -> None:
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
    if budget is not None:
        cmd.append(f"-var=platform_tpm_budget={budget}")
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


def _reset_adaptive(gateway: str, role: str, expected: int) -> None:
    url = f"{gateway.rstrip('/')}/v1/admin/reset-adaptive"
    payload = _signed_json("POST", url, role, body="{}")
    capacity = int(payload.get("adaptive_capacity") or -1)
    print(f"reset-adaptive capacity={capacity} action={payload.get('adaptive_last_action')}")
    if capacity != expected:
        raise SystemExit(f"reset-adaptive returned Ĉ={capacity}, expected {expected}")
    health = _signed_json("GET", f"{gateway.rstrip('/')}/health", role)
    health_cap = int(health.get("adaptive_capacity") or -1)
    if health_cap != expected:
        raise SystemExit(f"/health adaptive_capacity={health_cap}, expected {expected}")
    print(f"health adaptive_capacity={health_cap} policy={health.get('policy')}")


def _signed_json(method: str, url: str, role: str, body: str | None = None) -> dict:
    session = boto3.Session(region_name="us-east-1")
    assumed = session.client("sts").assume_role(RoleArn=role, RoleSessionName="exp-admin")["Credentials"]
    frozen = boto3.Session(
        aws_access_key_id=assumed["AccessKeyId"],
        aws_secret_access_key=assumed["SecretAccessKey"],
        aws_session_token=assumed["SessionToken"],
        region_name="us-east-1",
    ).get_credentials().get_frozen_credentials()
    headers = {"Content-Type": "application/json"}
    request = AWSRequest(method=method, url=url, data=body if body is not None else "", headers=headers)
    SigV4Auth(frozen, "execute-api", "us-east-1").add_auth(request)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SystemExit(f"refusing non-http URL {url}")
    response = URLLib3Session().send(request.prepare())
    text = response.text
    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError:
        payload = {"raw": text}
    if response.status_code >= 400:
        raise SystemExit(f"{method} {url} -> {response.status_code}: {text[:400]}")
    return payload


def _start_background(scenario: dict, dest: Path, concurrency_override: int | None):
    spec = scenario.get("background")
    if not spec:
        return None
    out = dest / "background.jsonl"
    if out.exists():
        out.unlink()
    concurrency = int(concurrency_override if concurrency_override is not None else spec.get("concurrency") or 8)
    cmd = [
        sys.executable,
        str(LOADGEN / "bedrock_background.py"),
        "--concurrency",
        str(concurrency),
        "--start-s",
        str(spec.get("start_s") or 0),
        "--end-s",
        str(spec.get("end_s") or scenario["duration_s"]),
        "--run-s",
        str(scenario["duration_s"]),
        "--model",
        str(spec.get("model") or "us.amazon.nova-micro-v1:0"),
        "--prompt-class",
        str(spec.get("prompt_class") or "long"),
        "--max-tokens",
        str(spec.get("max_tokens") or 256),
        "--out",
        str(out),
    ]
    print("background:", " ".join(cmd))
    return subprocess.Popen(cmd, cwd=str(LOADGEN))


def _stop_background(proc) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=45)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    if proc.returncode not in (0, None, -15):
        print(f"background exited {proc.returncode}", file=sys.stderr)


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
