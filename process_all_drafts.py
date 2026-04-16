import os
import glob
import time
import api_poster

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DRAFTS_DIR = os.path.join(BASE_DIR, "drafts")


def has_target_files() -> bool:
    """README_drafts.md 以外の .md / .txt が残っているか確認する。"""
    all_md_files = glob.glob(os.path.join(DRAFTS_DIR, "*.md")) + glob.glob(
        os.path.join(DRAFTS_DIR, "*.txt")
    )
    md_files = [
        f for f in all_md_files if os.path.basename(f).upper() != "README_DRAFTS.MD"
    ]
    return len(md_files) > 0


def main():
    """
    drafts フォルダ内のドラフトをすべて処理し終わるまで
    api_poster.main() を繰り返し実行するヘルパー。

    1回の api_poster.main() で1ファイルだけ処理し、成功後に processed へ移動する
    既存仕様を前提にしているため、api_poster.py 自体の挙動は変えない。
    """
    loop = 0
    while has_target_files():
        loop += 1
        print(f"\n==============================")
        print(f"  バッチ処理ループ #{loop}")
        print(f"==============================\n")

        result = api_poster.main()
        if result is False:
            print(" これ以上処理対象ファイルが存在しないため、バッチ処理を終了します。")
            break

        # 連続で叩きすぎないように軽く待つ（サーバー負荷対策）
        time.sleep(2)

    print("✅ drafts フォルダ内のドラフト処理が完了しました。")


if __name__ == "__main__":
    main()

