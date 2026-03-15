#!/usr/bin/env python3
"""
サーバーリソース診断スクリプト
WEBサイトの重さの原因（アクセス増 vs リソース不足）を切り分ける
"""
import os
import sys

# .env 読み込み
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(BASE_DIR, ".env")
if os.path.isfile(_env_path):
    with open(_env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if v.startswith('"') and v.endswith('"') or v.startswith("'") and v.endswith("'"):
                    v = v[1:-1]
                if k and k not in os.environ:
                    os.environ[k] = v

host = os.getenv("SSH_HOST", "104.156.239.43")
user = os.getenv("SSH_USER", "u9_chotto_uapw")
password = os.getenv("SSH_PASS")
path = os.getenv("WP_PATH", "/var/www/chotto.news")
port = int(os.getenv("SSH_PORT", "22"))

if not password:
    print("❌ 環境変数 SSH_PASS が設定されていません。.env に SSH_PASS=xxx を追加してください。", file=sys.stderr)
    sys.exit(1)

try:
    import paramiko
except ImportError:
    print("❌ paramiko がインストールされていません。pip install paramiko を実行してください。", file=sys.stderr)
    sys.exit(1)


def run_ssh(cmd: str) -> tuple[str, str]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=user, password=password, port=port)
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    client.close()
    return out, err


def main():
    print("=" * 60)
    print("🔍 サーバーリソース診断 (chotto.news)")
    print("=" * 60)

    # 1. 負荷・CPU・メモリ
    print("\n📊 【1】システム負荷・リソース")
    print("-" * 40)
    out, err = run_ssh("uptime && free -h && echo '---' && cat /proc/cpuinfo | grep processor | wc -l")
    if out:
        lines = out.split("\n")
        for line in lines:
            if "load average" in line:
                load = line.split("load average:")[-1].strip()
                print(f"  負荷平均: {load}")
                la = [float(x.strip()) for x in load.split(",")]
                if len(la) >= 1 and la[0] > 4:
                    print("  ⚠️  負荷が高めです（CPU/IO待ちの可能性）")
            elif line.startswith("Mem:"):
                parts = line.split()
                if len(parts) >= 7:
                    print(f"  メモリ: 使用 {parts[2]} / 合計 {parts[1]} (利用可能 {parts[6]})")
            elif line.strip().isdigit():
                ncpu = int(line.strip())
                print(f"  CPUコア数: {ncpu}")
    if err:
        print(f"  STDERR: {err}")

    # 2. プロセス別リソース消費
    print("\n📊 【2】リソース消費トップ10（メモリ）")
    print("-" * 40)
    out, err = run_ssh("ps aux --sort=-%mem | head -11")
    if out:
        print(out)
    if err:
        print(err)

    # 3. ディスク使用量
    print("\n📊 【3】ディスク使用量")
    print("-" * 40)
    out, err = run_ssh("df -h / /var/www 2>/dev/null || df -h /")
    if out:
        print(out)
    if err:
        print(err)

    # 4. PHP-FPM / Apache / Nginx の状態
    print("\n📊 【4】Webサーバー・PHPプロセス")
    print("-" * 40)
    out, err = run_ssh(
        "ps aux | grep -E 'php-fpm|apache|nginx|httpd' | grep -v grep | head -20"
    )
    if out:
        lines = out.strip().split("\n")
        print(f"  プロセス数: {len(lines)}")
        for line in lines[:5]:
            print(f"    {line[:100]}...")
    else:
        print("  （該当プロセスなし）")
    if err:
        print(err)

    # 5. MySQL の状態（存在すれば）
    print("\n📊 【5】MySQL 状態")
    print("-" * 40)
    out, err = run_ssh("ps aux | grep -E 'mysql|mariadb' | grep -v grep")
    if out:
        print(f"  MySQL/MariaDB プロセス: 稼働中")
    else:
        print("  MySQL/MariaDB: 未検出")
    if err:
        print(err)

    # 6. アクセスログの直近ヒット数（概算）
    print("\n📊 【6】直近アクセス傾向（概算）")
    print("-" * 40)
    out, err = run_ssh(
        "tail -5000 /var/log/nginx/access.log 2>/dev/null | wc -l || "
        "tail -5000 /var/log/apache2/access.log 2>/dev/null | wc -l || "
        "echo '0'"
    )
    if out and out.strip().isdigit():
        n = int(out.strip())
        print(f"  直近5000行のログ件数: {n} 件")
    out2, _ = run_ssh(
        "tail -1 /var/log/nginx/access.log 2>/dev/null || tail -1 /var/log/apache2/access.log 2>/dev/null || echo ''"
    )
    if out2:
        print(f"  最新ログ例: {out2[:80]}...")

    # 7. WordPress キャッシュ・プラグイン
    print("\n📊 【7】WordPress キャッシュ・重いプラグイン")
    print("-" * 40)
    out, err = run_ssh(f"cd {path} && wp plugin list --status=active 2>/dev/null | head -30")
    if out:
        print(out)
    else:
        print("  wp-cli で取得できませんでした")
    if err and "Error" in err:
        print(f"  Note: {err[:200]}")

    print("\n" + "=" * 60)
    print("💡 診断の目安")
    print("  - 負荷平均が CPUコア数より大きい → CPU/IO 不足の可能性")
    print("  - メモリ使用率が90%超 → メモリ不足の可能性")
    print("  - php-fpm プロセスが多数 → アクセス増 or 1リクエストあたりの処理が重い")
    print("  - キャッシュプラグイン未使用 → ページ生成の都度DB問い合わせで重くなりやすい")
    print("=" * 60)


if __name__ == "__main__":
    main()
