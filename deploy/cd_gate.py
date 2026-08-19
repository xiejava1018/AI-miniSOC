#!/usr/bin/env python3
"""CD 门禁：确认目标 commit 的两个 CI 都成功才部署（顺带去重双触发）。

背景（cicd.md §12.13）：deploy-prod.yml 的 workflow_run 监听 CI - Backend 与
CI - Frontend，一次 push 两个 CI 各触发一次 CD。本脚本按 head_sha 查询两个
CI 的最终状态：

- 两个都 completed + success → GITHUB_OUTPUT 写 deploy=yes（执行部署）
- 任一尚未完成（另一个 CI 还在跑）→ deploy=no（跳过本次，由后完成的那个
  CI 触发的 CD 来部署 —— 天然去重，且保证部署时 CI 全过）
- 任一 conclusion 为 failure/cancelled → 退出码 1（阻断，job 失败）

环境变量：TARGET_SHA（目标 commit 全长 sha）、GH_TOKEN（github.token）
"""
import json
import os
import sys
import urllib.request

REPO = "xiejava1018/AI-miniSOC"
REQUIRED = ["CI - Backend", "CI - Frontend"]


def build_opener():
    """优先 certifi CA（Mac 本地自带 python 缺根证书时也能跑）"""
    try:
        import certifi
        import ssl
        ctx = ssl.create_default_context(cafile=certifi.where())
        return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    except Exception:
        return urllib.request.build_opener()


def main() -> int:
    sha = os.environ.get("TARGET_SHA", "")
    token = os.environ.get("GH_TOKEN", "")  # 可选：公开仓库匿名可读，token 仅提升限流
    if not sha:
        print("::error::missing TARGET_SHA")
        return 2

    url = f"https://api.github.com/repos/{REPO}/actions/runs?head_sha={sha}&per_page=100"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with build_opener().open(req, timeout=30) as resp:
        runs = {w["name"]: w for w in json.load(resp).get("workflow_runs", [])}

    summary = {}
    for name in REQUIRED:
        w = runs.get(name)
        summary[name] = f"{w['status']}/{w['conclusion']}" if w else "missing"
    print("CI 状态: " + ", ".join(f"{k}={v}" for k, v in summary.items()))

    for name in REQUIRED:
        if runs.get(name) is None:
            print(f"::error::{name} 的 run 不存在（该 sha 从未跑过此 CI？）")
            return 1

    out_path = os.environ.get("GITHUB_OUTPUT", "/dev/null")
    with open(out_path, "a") as out:
        for name in REQUIRED:
            if runs[name]["status"] != "completed":
                print(f"DEPLOY=no（{name} 尚未完成；跳过本次触发，由后完成的 CI 触发部署）")
                out.write("deploy=no\n")
                return 0
        for name in REQUIRED:
            if runs[name]["conclusion"] != "success":
                print(f"::error::{name} conclusion={runs[name]['conclusion']}，阻断部署")
                return 1
        print("DEPLOY=yes（两个 CI 均 success）")
        out.write("deploy=yes\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())