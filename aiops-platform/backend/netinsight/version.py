"""网络洞察 - Git 版本控制服务

为配置备份目录维护 Git 历史：
- 扫描/上传后自动提交变更
- 保留最近 N 个提交版本（默认 10）
- 提供按文件查询历史版本的能力
"""

import os
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


def _run_git(base_path: str, args: list, check: bool = False):
    """执行 git 命令"""
    try:
        result = subprocess.run(
            ["git", "-C", base_path] + args,
            capture_output=True,
            text=True,
            check=check,
        )
        return result
    except FileNotFoundError:
        raise RuntimeError("系统中未找到 git 命令，请确保容器/环境中已安装 git")


def ensure_repo(base_path: str) -> bool:
    """初始化 git 仓库（幂等）"""
    if not base_path or not os.path.isdir(base_path):
        return False
    git_dir = os.path.join(base_path, ".git")
    if os.path.isdir(git_dir):
        return True
    r = _run_git(base_path, ["init"], check=True)
    # 忽略 .git 自身
    gitignore = os.path.join(base_path, ".gitignore")
    if not os.path.exists(gitignore):
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write(".git\n")
        _run_git(base_path, ["add", ".gitignore"], check=False)
        _run_git(base_path, ["commit", "-m", "初始化版本仓库"], check=False)
    return r.returncode == 0


def commit_changes(base_path: str, message: str, keep: int = 10) -> Optional[str]:
    """提交当前变更，并保留最近 keep 个提交

    返回新提交 hash，失败返回 None
    """
    if not ensure_repo(base_path):
        return None

    # 配置 git 用户（避免 commit 因无用户配置失败）
    _run_git(base_path, ["config", "user.email", "aiops@local"], check=False)
    _run_git(base_path, ["config", "user.name", "AIOPS"], check=False)

    _run_git(base_path, ["add", "-A"], check=False)

    # 检查是否有变更需要提交
    status = _run_git(base_path, ["status", "--porcelain"])
    if not status.stdout.strip():
        return None

    r = _run_git(base_path, ["commit", "-m", message], check=True)
    if r.returncode != 0:
        return None

    # 获取新提交 hash
    head = _run_git(base_path, ["rev-parse", "HEAD"])
    new_hash = head.stdout.strip() if head.returncode == 0 else None

    # 清理旧版本，保留最近 keep 个
    _prune_old_commits(base_path, keep)

    return new_hash


def _prune_old_commits(base_path: str, keep: int):
    """保留最近 keep 个提交，删除更旧的提交"""
    try:
        count_res = _run_git(base_path, ["rev-list", "--count", "HEAD"])
        count = int(count_res.stdout.strip())
    except Exception:
        return

    if count <= keep:
        return

    try:
        # 列出提交：从 HEAD（最新）到最旧
        all_commits = _run_git(base_path, ["rev-list", "HEAD"]).stdout.strip().split("\n")
        # all_commits[keep] 是第 keep+1 个最新提交，从这里开始及更旧的全部删除
        first_to_drop = all_commits[keep].strip()
        parent = f"{first_to_drop}^"

        # 将 first_to_drop 之后的提交（即更新的 keep 个提交）重放到 first_to_drop 的父提交上
        r = _run_git(base_path, ["rebase", "--onto", parent, first_to_drop], check=True)
        if r.returncode == 0:
            print(f"[AIOPS] Git 版本已清理，保留最近 {keep} 个提交")
            return
    except Exception:
        pass

    # 兜底：如果 rebase 失败，使用 soft reset + 重新提交的方式合并旧版本
    try:
        excess = count - keep
        _run_git(base_path, ["reset", "--soft", f"HEAD~{excess}"], check=True)
        _run_git(base_path, ["commit", "-m", f"归档早期版本（保留最近 {keep} 个）"], check=True)
        print(f"[AIOPS] Git 版本已通过归档方式清理，保留最近 {keep} 个提交")
    except Exception as e:
        print(f"[AIOPS] Git 版本清理失败: {e}")


def list_file_versions(base_path: str, file_path: str, keep: int = 10) -> List[Dict]:
    """查询指定文件（相对路径）的最近 keep 个版本历史"""
    if not ensure_repo(base_path):
        return []

    # --follow 追踪重命名；-- <file> 限定文件
    fmt = "%H|%ci|%s"
    r = _run_git(base_path, ["log", "--follow", f"--pretty=format:{fmt}", "-n", str(keep), "--", file_path])
    if r.returncode != 0 or not r.stdout.strip():
        return []

    versions = []
    for line in r.stdout.strip().split("\n"):
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        commit_hash, commit_time, message = parts
        versions.append({
            "commit": commit_hash,
            "time": commit_time,
            "message": message,
        })
    return versions


def get_version_content(base_path: str, file_path: str, commit_hash: str) -> Optional[str]:
    """获取指定文件在指定提交中的内容"""
    if not ensure_repo(base_path):
        return None

    try:
        r = _run_git(base_path, ["show", f"{commit_hash}:{file_path}"])
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return None
