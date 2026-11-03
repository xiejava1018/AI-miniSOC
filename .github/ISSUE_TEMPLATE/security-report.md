name: 🔒 安全漏洞上报
description: 安全漏洞请使用此模板私密上报，勿在公开 Issue 披露
labels: ["security"]
body:
  - type: markdown
    attributes:
      value: |
        **请勿在公开 Issue 中披露安全漏洞细节。**
        本模板为私密模板内容仅供参考——如你的 Issue 会被公开，请改走 [SECURITY.md](https://github.com/xiejava1018/AI-miniSOC/blob/master/SECURITY.md) 中的私密渠道（邮件）。

  - type: textarea
    id: vuln
    attributes:
      label: 漏洞描述（影响面 + 复现条件概述）
    validations:
      required: true

  - type: dropdown
    id: severity
    attributes:
      label: 你评估的严重度
      options:
        - S0 — 可直接未授权访问/篡改数据
        - S1 — 结构性缺陷，特定条件下可越权
        - S2 — 规范问题（信息泄露/配置不当）
    validations:
      required: true

  - type: textarea
    id: contact
    attributes:
      label: 联系方式（方便跟进与致谢）
