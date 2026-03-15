import os
import paramiko
import sys

# 環境変数から接続情報を取得
host = os.getenv("SSH_HOST", "104.156.239.43")
user = os.getenv("SSH_USER", "u9_chotto_uapw")
password = os.getenv("SSH_PASS")
path = os.getenv("WP_PATH", "/var/www/chotto.news")
port = int(os.getenv("SSH_PORT", "22"))

if not password:
    print("環境変数 SSH_PASS が設定されていません。", file=sys.stderr)
    sys.exit(1)

try:
    print(f"Connecting to {host}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=user, password=password, port=port)
    print("Connection successful!\n")
    
    print("Checking wp-cli presence and server path...")
    commands = [
        f"cd {path} && pwd",
        f"cd {path} && wp --info",
        f"cd {path} && wp core version",
        f"cd {path} && wp plugin list"
    ]
    
    for cmd in commands:
        print(f"--- Running: {cmd} ---")
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        if out:
            print(out)
        if err:
            print(f"STDERR: {err}")
        print()
        
except Exception as e:
    print(f"Connection failed: {e}")
    sys.exit(1)
finally:
    client.close()
