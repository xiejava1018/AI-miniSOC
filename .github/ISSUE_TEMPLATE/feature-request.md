name: 💡 功能建议 / 路线图讨论
description: 建议新功能，或对 Phase 5 路线图发表看法
labels: ["enhancement"]
body:
  - type: markdown
    attributes:
      value: |
        提建议前请看 [路线图](https://github.com/xiejava1018/AI-miniSOC#路线图)——Phase 5（集群化/多租户/插件市场等）已列入待启动清单。
        本项目的取舍原则：**不为想象中的需求增加今天的复杂度**——说清楚你的真实场景比说功能名更有说服力。

  - type: textarea
    id: problem
    attributes:
      label: 你要解决的真实问题（场景优先，不是功能名）
      placeholder: |
        ❌ "希望支持多租户"
        ✅ "我有两个子公司，部门 A 的运维不应该看到部门 B 的资产，目前 XX 页面做不到隔离"
    validations:
      required: true

  - type: textarea
    id: current
    attributes:
      label: 现有功能为什么覆盖不了
      placeholder: 说明你尝试过的现有功能（如权限矩阵 viewer 角色、data_health 等）及差距

  - type: textarea
    id: scale
    attributes:
      label: 你的规模
      placeholder: |
        - 资产数量：如 75 台 / 500 台
        - 用户数：如 1 人 / 5 人
        - 日告警量级：如 2 万条
    validations:
      required: true

  - type: dropdown
    id: willing
    attributes:
      label: 你愿意参与吗？
      options:
        - 愿意测试验证（Phase 5 功能落地前帮我实测）
        - 愿意贡献代码（提 PR）
        - 仅提供场景，不参与开发
    validations:
      required: true

  - type: checkboxes
    id: checklist
    attributes:
      label: 确认项
      options:
        - label: 已检查路线图，此功能不在 Phase 1-4 已交付清单中
        - label: 已说明真实场景（而非仅功能名）
