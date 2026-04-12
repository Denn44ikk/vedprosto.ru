from __future__ import annotations

import argparse
import json
import posixpath
import shlex
import tarfile
from pathlib import Path
from typing import Any

import paramiko


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "server.config.local.json"
REMOTE_STACK_DIR = SCRIPT_DIR / "remote" / "ui_stack"
BUILD_DIR = SCRIPT_DIR / "build"

APP_BUNDLE_ITEMS = {
    "backend/app": PROJECT_ROOT / "app",
    "frontend": PROJECT_ROOT.parent / "frontend",
    "requirements.txt": PROJECT_ROOT.parent / "requirements.txt",
}
OPTIONAL_APP_BUNDLE_ITEMS = {
    "backend/runtime/tg/its/tg_config.json": PROJECT_ROOT / "runtime" / "tg" / "its" / "tg_config.json",
    "backend/runtime/tg/sessions/tg_its.session": PROJECT_ROOT / "runtime" / "tg" / "sessions" / "tg_its.session",
    "backend/runtime/tg/sessions/tg_its.session-journal": PROJECT_ROOT / "runtime" / "tg" / "sessions" / "tg_its.session-journal",
    "backend/runtime/tg/sessions/tg_its.session-wal": PROJECT_ROOT / "runtime" / "tg" / "sessions" / "tg_its.session-wal",
    "backend/runtime/tg/sessions/tg_its.session-shm": PROJECT_ROOT / "runtime" / "tg" / "sessions" / "tg_its.session-shm",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_path: str) -> None:
    parts = [part for part in remote_path.split("/") if part]
    current = "/"
    for part in parts:
        current = posixpath.join(current, part)
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def upload_tree(sftp: paramiko.SFTPClient, local_dir: Path, remote_dir: str) -> None:
    ensure_remote_dir(sftp, remote_dir)
    for item in local_dir.rglob("*"):
        if "__pycache__" in item.parts:
            continue
        if item.is_file() and item.suffix == ".pyc":
            continue
        relative = item.relative_to(local_dir).as_posix()
        target = posixpath.join(remote_dir, relative)
        if item.is_dir():
            ensure_remote_dir(sftp, target)
            continue
        ensure_remote_dir(sftp, posixpath.dirname(target))
        sftp.put(str(item), target)


def upload_file(sftp: paramiko.SFTPClient, local_path: Path, remote_path: str) -> None:
    ensure_remote_dir(sftp, posixpath.dirname(remote_path))
    sftp.put(str(local_path), remote_path)


def write_remote_text(sftp: paramiko.SFTPClient, remote_path: str, text: str) -> None:
    ensure_remote_dir(sftp, posixpath.dirname(remote_path))
    with sftp.file(remote_path, "w") as handle:
        handle.write(text)


def run_remote(ssh: paramiko.SSHClient, command: str) -> str:
    print(f"[remote] {command}")
    stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="ignore").strip()
    err = stderr.read().decode("utf-8", errors="ignore").strip()
    if out:
        print(out)
    if err:
        print(err)
    if exit_code != 0:
        raise RuntimeError(f"Remote command failed with exit code {exit_code}: {command}")
    return out


def render_remote_env(config: dict[str, Any]) -> str:
    server = config["server"]
    app = config["app"]
    env = dict(config["env"])
    env["APP_DOMAIN"] = server["domain"]
    env["PUBLIC_SCHEME"] = app["public_scheme"]
    env["PUBLIC_HOST"] = app["public_host"]
    env["PUBLIC_PORT"] = str(app["public_port"])
    env["APP_SITE_ADDRESS"] = app.get("site_address") or (
        app["public_host"] if app["public_scheme"] == "https" else f":{app.get('caddy_http_port', 80)}"
    )
    env["BACKEND_PORT"] = str(app["backend_port"])
    env["CADDY_HTTP_PORT"] = str(app["caddy_http_port"])
    env["CADDY_HTTPS_PORT"] = str(app["caddy_https_port"])
    lines = [render_env_line(key, value) for key, value in env.items()]
    return "\n".join(lines) + "\n"


def render_env_line(key: str, value: Any) -> str:
    normalized = "" if value is None else str(value)
    escaped = normalized.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}="{escaped}"'


def render_caddyfile(config: dict[str, Any]) -> str:
    server = config["server"]
    app = config["app"]
    deploy_cfg = config["deploy"]
    backend_port = str(app["backend_port"])
    public_host = app["public_host"]
    domain = server["domain"]
    enable_https = bool(deploy_cfg.get("enable_https", False))
    site_blocks = [
        f"http://{server['host']} {{",
        "    encode zstd gzip",
        f"    reverse_proxy 127.0.0.1:{backend_port}",
        "}",
        "",
    ]
    if domain and domain != server["host"]:
        domain_address = f"{domain}, www.{domain}" if enable_https else f"http://{domain}, http://www.{domain}"
        site_blocks.extend(
            [
                f"{domain_address} {{",
                "    encode zstd gzip",
                f"    reverse_proxy 127.0.0.1:{backend_port}",
                "}",
                "",
            ]
        )
    if public_host not in {server["host"], domain, f"www.{domain}"}:
        site_blocks.extend(
            [
                f"{public_host} {{",
                "    encode zstd gzip",
                f"    reverse_proxy 127.0.0.1:{backend_port}",
                "}",
                "",
            ]
        )
    return "\n".join(site_blocks)


def bootstrap_remote_host(ssh: paramiko.SSHClient, *, install_docker: bool) -> None:
    run_remote(ssh, "mkdir -p /opt")
    if not install_docker:
        return
    command = (
        "bash -lc "
        + shlex.quote(
            "set -euo pipefail; "
            "if ! command -v docker >/dev/null 2>&1; then "
            "(curl --connect-timeout 20 --max-time 120 -fsSL https://get.docker.com | sh) || "
            "(apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2); "
            "fi; "
            "systemctl enable docker || true; "
            "systemctl start docker || true"
        )
    )
    run_remote(ssh, command)


def upload_remote_stack(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    upload_tree(sftp, REMOTE_STACK_DIR, remote_dir)


def upload_app_bundle(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    archive_path = build_app_bundle_archive()
    remote_build_dir = posixpath.join(remote_dir, "build")
    remote_archive_path = posixpath.join(remote_build_dir, archive_path.name)
    ensure_remote_dir(sftp, remote_build_dir)
    upload_file(sftp, archive_path, remote_archive_path)


def build_app_bundle_archive() -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = BUILD_DIR / "agent_ui_bundle.tar.gz"
    if archive_path.exists():
        archive_path.unlink()

    def should_include(path: Path) -> bool:
        if "__pycache__" in path.parts:
            return False
        if path.is_file() and path.suffix == ".pyc":
            return False
        return True

    with tarfile.open(archive_path, "w:gz") as archive:
        bundle_items = dict(APP_BUNDLE_ITEMS)
        bundle_items.update(
            {
                remote_rel: local_path
                for remote_rel, local_path in OPTIONAL_APP_BUNDLE_ITEMS.items()
                if local_path.exists()
            }
        )
        for remote_rel, local_path in bundle_items.items():
            arc_root = Path("agent_ui") / Path(remote_rel)
            if local_path.is_dir():
                for item in local_path.rglob("*"):
                    if not should_include(item):
                        continue
                    archive.add(item, arcname=arc_root / item.relative_to(local_path))
            else:
                archive.add(local_path, arcname=arc_root)
    return archive_path


def extract_remote_app_bundle(ssh: paramiko.SSHClient, remote_dir: str) -> None:
    for remote_rel, local_path in APP_BUNDLE_ITEMS.items():
        target = posixpath.join(remote_dir, "agent_ui", remote_rel.replace("\\", "/"))
        run_remote(ssh, f"rm -rf {shlex.quote(target)}")
    archive_path = posixpath.join(remote_dir, "build", "agent_ui_bundle.tar.gz")
    run_remote(ssh, f"tar -xzf {shlex.quote(archive_path)} -C {shlex.quote(remote_dir)}")


def install_or_update_caddy(ssh: paramiko.SSHClient, config: dict[str, Any]) -> None:
    install_command = (
        "set -euo pipefail; "
        "if ! command -v caddy >/dev/null 2>&1; then "
        "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y caddy; "
        "fi; "
        "systemctl enable caddy"
    )
    run_remote(ssh, f"bash -lc {shlex.quote(install_command)}")
    caddyfile = render_caddyfile(config).replace("\\", "\\\\").replace("$", "\\$").replace("`", "\\`")
    run_remote(ssh, f"cat > /etc/caddy/Caddyfile <<'EOF'\n{caddyfile}EOF")
    run_remote(ssh, "caddy validate --config /etc/caddy/Caddyfile")
    run_remote(ssh, "systemctl reload caddy || systemctl restart caddy")
    run_remote(ssh, "systemctl status caddy --no-pager --lines=30")


def deploy_host_systemd(ssh: paramiko.SSHClient, config: dict[str, Any], remote_dir: str) -> None:
    app_dir = posixpath.join(remote_dir, "agent_ui")
    service_name = "tnved-ui"
    service_file = f"/etc/systemd/system/{service_name}.service"
    use_caddy = bool(config.get("deploy", {}).get("install_caddy", False))
    port = str(config.get("app", {}).get("backend_port" if use_caddy else "caddy_http_port", 80))
    host = "127.0.0.1" if use_caddy else "0.0.0.0"
    run_remote(
        ssh,
        "bash -lc "
        + shlex.quote(
            f"cd {shlex.quote(remote_dir)} && "
            "if command -v docker >/dev/null 2>&1; then docker compose down --remove-orphans || true; fi"
        ),
    )
    install_command = (
        f"cd {shlex.quote(app_dir)} && "
        "apt-get update && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip && "
        "python3 -m venv .venv && "
        ".venv/bin/pip install --upgrade pip && "
        ".venv/bin/pip install -r requirements.txt"
    )
    run_remote(ssh, f"bash -lc {shlex.quote(install_command)}")

    service_unit = "\n".join(
        [
            "[Unit]",
            "Description=TNVED Agent UI",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={app_dir}",
            f"EnvironmentFile={remote_dir}/.env",
            f"Environment=APP_HOST={host}",
            f"Environment=APP_PORT={port}",
            f"ExecStart={app_dir}/.venv/bin/uvicorn backend.app.main:app --host {host} --port {port}",
            "Restart=always",
            "RestartSec=5",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    encoded = service_unit.replace("\\", "\\\\").replace("$", "\\$").replace("`", "\\`")
    run_remote(ssh, f"cat > {shlex.quote(service_file)} <<'EOF'\n{encoded}EOF")
    run_remote(ssh, "systemctl daemon-reload")
    run_remote(ssh, f"systemctl enable --now {service_name}")
    run_remote(ssh, f"systemctl restart {service_name}")
    run_remote(ssh, f"systemctl status {service_name} --no-pager --lines=20")
    if use_caddy:
        install_or_update_caddy(ssh, config)


def verify_local_inputs() -> None:
    missing = [str(path) for path in APP_BUNDLE_ITEMS.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing local deploy inputs: {', '.join(missing)}")


def deploy(config_path: Path, *, skip_upload: bool = False, skip_build: bool = False) -> None:
    verify_local_inputs()
    config = load_json(config_path)
    server = config["server"]
    deploy_cfg = config["deploy"]
    remote_dir = deploy_cfg["remote_dir"]

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[ssh] Connecting to {server['ssh_user']}@{server['host']}:{server.get('ssh_port', 22)}")
    ssh.connect(
        hostname=server["host"],
        port=int(server.get("ssh_port", 22)),
        username=server["ssh_user"],
        password=server["ssh_password"],
        timeout=30,
    )
    try:
        bootstrap_remote_host(ssh, install_docker=bool(deploy_cfg.get("install_docker", True)))
        run_remote(ssh, f"mkdir -p {shlex.quote(remote_dir)}")
        run_remote(ssh, f"mkdir -p {shlex.quote(posixpath.join(remote_dir, 'data/runtime'))}")
        with ssh.open_sftp() as sftp:
            if not skip_upload:
                upload_remote_stack(sftp, remote_dir)
                upload_app_bundle(sftp, remote_dir)
            write_remote_text(sftp, posixpath.join(remote_dir, ".env"), render_remote_env(config))
        if not skip_upload:
            extract_remote_app_bundle(ssh, remote_dir)
        if not skip_build:
            if deploy_cfg.get("runtime") == "systemd":
                deploy_host_systemd(ssh, config, remote_dir)
            else:
                compose_up = (
                    f"cd {remote_dir} && "
                    f"COMPOSE_PROJECT_NAME={shlex.quote(deploy_cfg.get('compose_project_name', 'tnved-ui'))} "
                    "docker compose up -d --build --remove-orphans"
                )
                try:
                    run_remote(ssh, f"bash -lc {shlex.quote(compose_up)}")
                    compose_ps = (
                        f"cd {remote_dir} && "
                        f"COMPOSE_PROJECT_NAME={shlex.quote(deploy_cfg.get('compose_project_name', 'tnved-ui'))} "
                        "docker compose ps"
                    )
                    run_remote(ssh, f"bash -lc {shlex.quote(compose_ps)}")
                except Exception:
                    print("[fallback] Docker build failed. Falling back to host systemd deployment.")
                    deploy_host_systemd(ssh, config, remote_dir)
        health_url = deploy_cfg.get("healthcheck_url", "http://127.0.0.1/api/health")
        health_check = (
            "python3 - <<'PY'\n"
            "import json, time, urllib.request\n"
            f"url = {health_url!r}\n"
            "last_error = None\n"
            "for attempt in range(1, 31):\n"
            "    try:\n"
            "        with urllib.request.urlopen(url, timeout=5) as response:\n"
            "            payload = json.load(response)\n"
            "        print(payload)\n"
            "        break\n"
            "    except Exception as exc:\n"
            "        last_error = exc\n"
            "        time.sleep(1)\n"
            "else:\n"
            "    raise SystemExit(f'Healthcheck failed after 30 attempts: {last_error}')\n"
            "PY"
        )
        run_remote(ssh, f"bash -lc {shlex.quote(health_check)}")
    finally:
        ssh.close()

    print("[done] UI deploy finished successfully.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy backend+frontend UI stack to remote server.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to server.config.local.json")
    parser.add_argument("--skip-upload", action="store_true", help="Do not upload files, only refresh remote env and run compose")
    parser.add_argument("--skip-build", action="store_true", help="Do not rebuild containers after upload")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    deploy(config_path, skip_upload=args.skip_upload, skip_build=args.skip_build)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
