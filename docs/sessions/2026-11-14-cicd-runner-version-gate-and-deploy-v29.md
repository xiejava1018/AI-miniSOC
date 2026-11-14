# 2026-11-14 CI/CD 恢复：runner 版本门禁 + 自更新失败根治 + deploy.sh v2.9

> 事故：11-11 起所有 CD run `cancelled`（jobs total_count=0，GitHub 压根不创建 job），
> runner 侧无任何报错只有 "Listening for Jobs"。§4.16 记的「runner 自更新卡死」
> 本次查明完整根因并根治。

## 症状组合 = runner 版本过旧（先查这个）

```
GitHub 侧：CD run cancelled + jobs total_count=0（job 从未创建）
runner 侧：进程活着、Session created、"Listening for Jobs"、无报错
runner log：大量 "Runner update failed: ... failed after 3 download attempts"
```

GitHub 对过旧 runner 版本**静默拒派 job**。本次 2.336.0 < 要求的 2.338.2。
**升级到 2.338.2 后，积压的 2 个 CD job 立即派发且全部 Succeeded**——
反证与 label / environment 门禁无关。

## 诊断纠错：102 → GitHub「断网」是误判

之前结论「102 完全连不上 GitHub」是**探测命令超时太短**造成的：

| 探测 | 误判原因 | 实际 |
|---|---|---|
| `curl https://github.com` timeout 25 | TLS 握手慢 | **200，6.9s**（TLS1.3）/13.9s（TLS1.2） |
| `git fetch` | — | **1.45s 成功** |

网络真相分层：
- github.com 主站 / API：正常但 TLS 慢（6–14s）
- **GitHub Releases CDN（objects.githubusercontent.com）：仅 ~8KB/s** ← runner 自更新失败的根因
- 解法：`ghfast.top` 代理可达 **1MB/s**（`https://ghfast.top/https://github.com/...` 直拼）

**教训：给 curl 至少 30–60s 超时再下「断网」结论；大文件下载先测代理镜像。**

## runner 升级操作手册（102）

sudoers 只放行 aisoc-backend 的 systemctl，**管不了 runner 服务**；unit 无 `Restart=`。
完整流程：

```bash
# 1. Mac 下载（走 ghfast.top 代理，218MB ~4min；tar -tzf 校验完整性 + sha256 两端比对）
curl -sSL -o runner.tar.gz "https://ghfast.top/https://github.com/actions/runner/releases/download/v<VER>/actions-runner-linux-x64-<VER>.tar.gz"
scp runner.tar.gz xiejava@192.168.0.102:/tmp/

# 2. 102 上：备份状态文件 + 原地解压（状态文件 .runner/.credentials/_work/_diag 不在包内，安全）
cd ~/actions-runner
cp .runner .credentials .credentials_rsaparams /tmp/runner-state-backup/
tar -xzf /tmp/runner.tar.gz -C ~/actions-runner
./bin/Runner.Listener --version   # 确认新版本

# 3. 重启进程链（无法 systemctl，kill 后 nohup 拉起）
pkill -INT -f "Runner.Listener run"; sleep 2
pkill -INT -f "RunnerService.js";   sleep 2
pkill -INT -f "runsvc.sh";          sleep 3
nohup ./runsvc.sh > /tmp/runner-svc.log 2>&1 &
```

systemd unit 仍 enabled——**机器重启后自动拉起**（用的就是已 patch 的 RunnerService.js）。

## 禁自更新

`bin/RunnerService.js` 硬编码 listener 参数（不透传 runsvc.sh 的参数），直接 patch：

```js
["run", "--startuptype", "service", "--disableupdate"]   // 加 --disableupdate
```

注意：启动时会打一行 `Unrecognized command-line input arguments for command run:
'disableupdate'` 警告（2.338.2 的 run 子命令 help 又列出了该 flag）——
**警告无害，listener 正常带参运行，且重启后 diag log 0 次自更新尝试**。

禁的理由：自更新走 Releases CDN（8KB/s）必失败；失败循环还会在下次版本门禁时
重演本次事故。未来要升级就走上面的代理下载手册。

## deploy.sh v2.9（commit d325cfe，同一事故窗口的两个部署痛点）

1. **fetch 策略 0**：目标 commit 本地已存在（`git cat-file -t` 可解析，长/短 SHA 均可）
   → 跳过全部 fetch。断网时原来要白等 90+120+300s=8 分半，实测 98s→0s。
2. **健康检查窗口**：5×2s=10s → 20×3s=60s（`HEALTH_MAX_RETRY`/`HEALTH_RETRY_INTERVAL`
   可调）。后端冷启动 ~30s（§4.10），10s 窗口必然误报失败→无谓回滚（实测发生过）。
   失败原因汇总到最后统一报（HEALTH_LAST_ERR），不逐轮刷屏。

**注意**：deploy.sh 的改动要**下一次部署**才生效（本次跑的还是旧脚本）。

## 验证（2026-11-14）

- runner 2.338.2 + `--disableupdate`，diag log 0 次自更新尝试
- 积压 2 个 CD job 连续执行：`completed with result: Succeeded` ×2
- GitHub 侧 `CD - Deploy to Production → completed/success`
- 102 HEAD 自动部署到 d325cfe4c（含 deploy.sh v2.9），backend/nginx 200

## 遗留

- sudoers 未放行 `systemctl ... actions.runner.*`（手动重启只能 kill+nohup；
  当前实例日志在 /tmp/runner-svc.log 不进 journalctl）
- CD run pending 超时无告警（job 积压 3 天无人知晓）
- 未来 runner 升级：走本文档手册，别等自更新
