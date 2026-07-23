"""
数据持久化：把每天的交易记录自动同步到 GitHub 仓库
==================================================
Render 免费版文件系统是临时的，重启后非 Git 文件会丢。
此模块在每次录入操作后，自动把数据 commit + push 回 GitHub。

使用前提：
- 仓库已 clone 到服务器
- 配了 GitHub Token（环境变量 GH_TOKEN 或 GH_PAT）
- git config user.name / user.email 已设置

如果没配 Token，静默跳过（不影响 App 正常使用，只是重启后丢未同步的数据）。
"""
import os
import subprocess
import json
from pathlib import Path
from datetime import datetime

BASE = Path(".")
HISTORY_DIR = BASE / "data/history"


def sync_to_github():
    """把 data/history/ 下的文件 commit + push 到 GitHub"""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GH_PAT")
    if not token:
        return False, "未配 GH_TOKEN，跳过同步"

    # 检查是否在 git 仓库内
    if not (BASE / ".git").exists():
        return False, "非 git 仓库"

    try:
        # 检查有无改动
        r = subprocess.run(
            ["git", "status", "--porcelain", "data/history/"],
            capture_output=True, text=True, cwd=str(BASE), timeout=10
        )
        if not r.stdout.strip():
            return True, "无改动，跳过"

        # git add
        subprocess.run(["git", "add", "data/history/"], cwd=str(BASE), timeout=10)

        # git commit
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(
            ["git", "commit", "-m", f"数据同步 {ts}"],
            cwd=str(BASE), timeout=10,
            env={**os.environ, "GIT_AUTHOR_NAME": "stock-bot", "GIT_AUTHOR_EMAIL": "bot@local"}
        )

        # git push（用 token 替换 remote URL）
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=str(BASE), timeout=10
        )
        origin = r.stdout.strip()
        # 注入 token: https://<token>@github.com/user/repo.git
        if "github.com" in origin and "@" not in origin:
            origin_with_token = origin.replace("https://", f"https://{token}@")
            subprocess.run(
                ["git", "push", origin_with_token, "main"],
                cwd=str(BASE), timeout=30,
                capture_output=True, text=True
            )
        else:
            subprocess.run(["git", "push"], cwd=str(BASE), timeout=30, capture_output=True)

        return True, f"已同步 {ts}"
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    ok, msg = sync_to_github()
    print(f"{'✅' if ok else '⚠️'} {msg}")
