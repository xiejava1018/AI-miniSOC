name: 🚀 部署求助
description: 部署/运行中遇到问题，请求帮助
labels: ["question", "deployment"]
body:
  - type: markdown
    attributes:
      value: |
        提问前请先检查：
        1. 是否已按 [02 篇部署指南](https://xiejava.ishareread.com/posts/xxx-deploy/)（或 README 安装章节）操作
        2. [常见问题 FAQ](https://github.com/xiejava1018/AI-miniSOC/blob/master/README.md) 是否已覆盖
        3. 搜索 [已有 Issue](https://github.com/xiejava1018/AI-miniSOC/issues?q=is%3Aissue) 是否重复

        > ⚠️ 安全漏洞请勿在此披露，按 [SECURITY.md](https://github.com/xiejava1018/AI-miniSOC/blob/master/SECURITY.md) 私密上报

  - type: textarea
    id: env
    attributes:
      label: 环境信息
      description: 尽量完整，截图/日志可贴在下方
      placeholder: |
        - 硬件：如 8G 内存迷你主机 / 云服务器 2C4G
        - 操作系统：如 Ubuntu 22.04
        - 部署方式：按 README 手动 / docker / 其他
        - 出问题的组件：backend / frontend / wazuh / collector / AI 调用
    validations:
      required: true

  - type: textarea
    id: symptom
    attributes:
      label: 现象（做了什么、期望什么、实际看到什么）
      placeholder: |
        1. 我按 XX 步骤操作
        2. 期望出现 XX
        3. 实际出现 XX（贴关键报错日志，敏感信息请脱敏）
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: 相关日志（脱敏后）
      placeholder: |
        # 后端日志
        sudo journalctl -u aisoc-backend --no-pager -n 50
        # 或部署日志
        cat /tmp/aisoc-deploy.log

  - type: checkboxes
    id: checklist
    attributes:
      label: 确认项
      options:
        - label: 已搜索现有 Issue，无重复
        - label: 已脱敏（无真实 IP / 密码 / API Key）
        - label: 安全漏洞已改走 SECURITY.md 流程（如适用）
