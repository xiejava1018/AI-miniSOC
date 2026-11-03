name: 🐛 缺陷报告 / 踩坑分享
description: 报告 bug，或分享你部署过程中踩的坑（坑也是贡献）
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        报 bug 请提供**可复现的最小步骤**——"它坏了"无法修，"做 A → 做 B → 出现 C"可以修。
        如果是部署中踩的坑且已有 workaround，欢迎改投「部署求助」并在描述中写明解法——**坑也是贡献**。

  - type: textarea
    id: repro
    attributes:
      label: 复现步骤（最小可复现）
      placeholder: |
        1. 进入 XX 页面 / 执行 XX 命令
        2. 填入 XX 参数
        3. 点击 XX
        4. 出现 XX 错误
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: 期望行为 vs 实际行为
    validations:
      required: true

  - type: dropdown
    id: severity
    attributes:
      label: 影响程度
      options:
        - 功能不可用（有 workaround）
        - 功能不可用（无 workaround）
        - 数据错误（展示/统计不对）
        - 仅展示问题
    validations:
      required: true

  - type: textarea
    id: env-log
    attributes:
      label: 环境信息 + 相关日志（脱敏后）
      placeholder: |
        - 版本/commit：git log -1 或页面底部版本号
        - 关键日志（journalctl / 部署日志 / 浏览器 console）

  - type: checkboxes
    id: checklist
    attributes:
      label: 确认项
      options:
        - label: 提供了可复现的最小步骤
        - label: 已脱敏（无真实 IP / 密码 / API Key）
        - label: 安全漏洞已改走 SECURITY.md 流程（如适用）
