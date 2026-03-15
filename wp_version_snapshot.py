import json
import os
import sys
import datetime
from pathlib import Path

import paramiko

BASE_DIR = Path(__file__).resolve().parent
VERSIONS_DIR = BASE_DIR / "versions"


def get_env(name: str, default=None, required: bool = False):
    value = os.getenv(name, default)
    if required and not value:
        print(f"環境変数 {name} が設定されていません。", file=sys.stderr)
        sys.exit(1)
    return value


def ssh_run(client: paramiko.SSHClient, cmd: str) -> tuple[str, str, int]:
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    exit_status = stdout.channel.recv_exit_status()
    return out, err, exit_status


def main():
    host = get_env("SSH_HOST", required=True)
    user = get_env("SSH_USER", required=True)
    password = get_env("SSH_PASS", required=True)
    wp_path = get_env("WP_PATH", "/var/www/chotto.news")
    port = int(get_env("SSH_PORT", "22"))

    VERSIONS_DIR.mkdir(exist_ok=True)

    print(f"Connecting to {host}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(hostname=host, username=user, password=password, port=port)
        print("Connection successful.\n")

        snapshot: dict = {
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
            "host": host,
            "wp_path": wp_path,
            "wp_cli": {},
        }

        # WP-CLI info
        out, err, code = ssh_run(client, f"cd {wp_path} && wp --info --format=json")
        snapshot["wp_cli"]["info"] = {
            "stdout": out,
            "stderr": err,
            "exit_code": code,
        }

        # Core version
        out, err, code = ssh_run(
            client, f"cd {wp_path} && wp core version --extra --format=json"
        )
        snapshot["wp_cli"]["core"] = {
            "stdout": out,
            "stderr": err,
            "exit_code": code,
        }

        # Plugins
        out, err, code = ssh_run(
            client, f"cd {wp_path} && wp plugin list --format=json"
        )
        plugins_json = None
        try:
            plugins_json = json.loads(out) if out else None
        except Exception:
            plugins_json = None

        snapshot["wp_cli"]["plugins"] = {
            "stdout": out,
            "stderr": err,
            "exit_code": code,
            "parsed": plugins_json,
        }

        # Themes（将来のために）
        out, err, code = ssh_run(
            client, f"cd {wp_path} && wp theme list --format=json"
        )
        themes_json = None
        try:
            themes_json = json.loads(out) if out else None
        except Exception:
            themes_json = None

        snapshot["wp_cli"]["themes"] = {
            "stdout": out,
            "stderr": err,
            "exit_code": code,
            "parsed": themes_json,
        }

        # ファイルに保存
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = VERSIONS_DIR / f"wp_snapshot_{ts}.json"
        latest_path = VERSIONS_DIR / "latest.json"

        with snapshot_path.open("w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

        with latest_path.open("w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

        print(f"✅ スナップショットを保存しました: {snapshot_path.name}")
        print(f"✅ 最新スナップショット: {latest_path.name}")

    except Exception as e:
        print(f"Connection or command failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()

