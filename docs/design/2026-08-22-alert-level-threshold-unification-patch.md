# 告警分级阈值统一 — 补丁工单（v1.0）

> 文档版本: v1.0
> 创建日期: 2026-08-22
> 状态: Draft（交 pi agent 评审后执行）
> 背景: 2026-08-22 独立验证 pi agent 对 `ai_analysis.py` 分级阈值不统一的修复，
>       确认其核心修复正确，但漏掉了 1 处仍在生产使用的老阈值路径（R1 真 bug）+ 3 处收尾项（R2/R3/R4）。
>       本工单是「分级阈值统一」的收尾补丁，旨在让全项目**真正只有一个口径**。

---

## 0. 修订说明（本工单立场）

- 2026-08-22 pi agent 已新建 `app/core/alert_levels.py` 作为**唯一真相源**（`LEVEL_CRITICAL=13 / LEVEL_HIGH=10 / LEVEL_MEDIUM=7 / LEVEL_LOW=4`），并改造了 `ai_analysis.py`(3 处)、`asset_summary.py`、`alert_query.py`。
- **本工单不重复那部分**，只补 pi agent 漏掉的 4 处，并把"映射函数"也下沉到中央模块，彻底消灭散落 if/elif。
- 设计原则（沿用 P4 缺口工单）：**禁止裸魔法数比较**；所有 level→severity / level→priority 的映射走中央模块的纯函数；旧 import 不受影响。

---

## 1. 现状与残留（独立验证结论）

| 编号 | 位置 | 当前值 | 与权威 13/10/7/4 的关系 | 严重度 |
|------|------|--------|------------------------|--------|
| **R1** | `app/services/alert_incident_service.py:27-39` `_level_to_severity` | **12/9/6** | 直接冲突：level12→标 critical(应 high)、level9→high(应 medium)、level6→medium(应 low) | 🔴 真 bug（生产路径） |
| **R2** | `app/services/ai_analysis.py:532-537` `_heuristic_verdict` | 13/10 双档 → **P1/P2/P3** | P 级比 severity 链（`_PRIORITY_TO_SEVERITY`）**全程低一格**：level7-9 判 P3(→low) 而非 P2(→medium) | 🟡 软残留（off-by-one 未消） |
| **R3** | `app/services/query_templates.py:41-44` | 私有 `_LEVEL_CRITICAL=13`… | 值碰巧对，但**重复定义**违反单一真相源 | 🟢 小项 |
| **R4** | `app/api/webhooks.py:110` `if payload.rule_level < 12` | 裸 `12` | 通知阈值，属 `SEVERE_LEVEL=12` 决策，未命名、未引用中央模块 | 🟢 待拍板/小项 |

**权威口径**（全项目必须一致）：
```
level >= 13          → critical  → P0
level >= 10 (10-12)  → high      → P1
level >= 7  (7-9)    → medium    → P2
level >= 4  (4-6)    → low       → P3
level <  4           → 噪音（不计入分级计数）
```

---

## 2. 目标

1. 新告警 → 事件 severity（`_level_to_severity`）与权威口径一致（修 R1）。
2. 降级研判 P 级（`_heuristic_verdict`）与 severity 链对齐（修 R2），消除跨页不一致。
3. 全项目只保留 `app/core/alert_levels.py` 一处常量 + 两个纯函数（`level_to_severity` / `level_to_priority`），其余调用点 import 复用（修 R3，顺带收口 R1/R2/R4）。
4. 通知触发阈值显式命名 `SEVERE_LEVEL=12`，与 `LEVEL_HIGH=10` 区分（修 R4）。
5. 补单测，防止回退。

---

## 3. 详细设计

### 3.1 中央模块补强 `app/core/alert_levels.py`

在现有常量之后，新增两个纯函数 + `SEVERE_LEVEL` 常量（不破坏既有 import）：

```python
# 通知/处置阈值：level >= SEVERE_LEVEL 视为"严重"，触发站内通知 + WS 推送。
# 注意：SEVERE_LEVEL(12) 与 LEVEL_HIGH(10) 是**两个不同语义**——前者是"是否值得打扰人"，
# 后者是"风险等级 high"。二者不可混用，故独立命名。
SEVERE_LEVEL = 12


def level_to_severity(level) -> str:
    """Wazuh rule.level(1-15) → 事件 severity(critical/high/medium/low)。

    权威口径：>=13 critical / >=10 high / >=7 medium / 其余 low（<4 为噪音但不在此降级）。
    无效输入（None / 非数字）回退 'low'，调用方不应因此崩溃。
    """
    try:
        lv = int(level)
    except (TypeError, ValueError):
        return "low"
    if lv >= LEVEL_CRITICAL:
        return "critical"
    if lv >= LEVEL_HIGH:
        return "high"
    if lv >= LEVEL_MEDIUM:
        return "medium"
    return "low"


def level_to_priority(level) -> str:
    """Wazuh rule.level → AI 研判优先级 P0-P3，对齐 `_PRIORITY_TO_SEVERITY`。"""
    return {
        "critical": "P0",
        "high": "P1",
        "medium": "P2",
        "low": "P3",
    }[level_to_severity(level)]
```

> 设计说明：`level_to_severity` 是 `_level_to_severity` 的权威化版本；`level_to_priority`
> 把"level → P 级"的映射显式化，供 `_heuristic_verdict` 复用，确保降级路径与 LLM 路径结论一致。

### 3.2 R1 — `alert_incident_service._level_to_severity` 改委托

`app/services/alert_incident_service.py:27-39` 整段替换为委托中央模块：

```python
# AI 优先级 P0-P3 → 事件 severity（与 ai_analysis 研判对齐）
_PRIORITY_TO_SEVERITY = {"P0": "critical", "P1": "high", "P2": "medium", "P3": "low"}

# 2026-08-22 统一：此前硬写 12/9/6，与权威 13/10/7/4 冲突。
# 现委托 app.core.alert_levels.level_to_severity，禁止再写裸数字。
from app.core.alert_levels import level_to_severity as _level_to_severity  # noqa: E402,F401
```

> 注意：保留 `_level_to_severity` 这个名字（函数签名不变），`alert_incident_service.py:119`
> 与 `:239` 的调用点**无需改动**。仅语义从 12/9/6 变为 13/10/7/4。
> 影响范围：仅**新建事件**的 severity 字段（历史事件不受影响）。

### 3.3 R2 — `ai_analysis._heuristic_verdict` P 级对齐

`app/services/ai_analysis.py:525-547` 中：

- 顶部 import 区（:7 附近）追加 `from app.core.alert_levels import level_to_priority`
- `:529-537` 的 if/elif 三行改为一行：

```python
        # 阈值与 P 级对齐权威口径（13/10/7/4 → P0/P1/P2/P3），
        # 此前 12/8 → P1/P2/P3 导致 level7-9 被判 P3(→low) 而非 P2(→medium)。
        priority = level_to_priority(level_max)
```

- `:544` 的 `suggest_incident = priority == "P1"` 需同步复核。建议改为
  `suggest_incident = priority in ("P0", "P1")`（critical/high 簇建议建事件），
  以匹配新产生的 P0。若产品希望"仅 critical 才建议建单"，则用 `== "P0"`。
  **此点需评审时拍板**（见 §4 WO-3 验收）。

### 3.4 R3 — `query_templates.py` 私有常量改 import

`app/services/query_templates.py:41-44` 删除私有 `_LEVEL_*` 定义，改为：

```python
# 阈值统一引用中央模块（2026-08-22），本模块不再持有任何口径副本。
from app.core.alert_levels import LEVEL_CRITICAL, LEVEL_HIGH, LEVEL_MEDIUM, LEVEL_LOW  # noqa: F401
```

> 若该模块后续确有分桶需求，调用 `level_to_severity()` 而非比较裸常量。

### 3.5 R4 — `webhooks.py` 通知阈值命名

`app/api/webhooks.py:106`（docstring）与 `:110`（逻辑）的 `12` 改为 `SEVERE_LEVEL`：

```python
from app.core.alert_levels import SEVERE_LEVEL  # 顶部 import 区

    """严重告警 webhook：level >= SEVERE_LEVEL(12) 时触发站内通知 + WS 推送 ..."""
    if payload.rule_level < SEVERE_LEVEL:
        return WebhookResponse(success=True, message="alert level below threshold, ignored")
```

> 文档注释（:6/:88）同步把 "level >= 12" 改为 "level >= SEVERE_LEVEL(12)"。

---

## 4. 可执行工单

### WO-1 中央模块补强
- **目标**：`app/core/alert_levels.py` 新增 `SEVERE_LEVEL=12` + `level_to_severity()` + `level_to_priority()`。
- **改动**：见 §3.1（纯函数，无副作用；不改动既有常量与 re-export）。
- **验收**：`py_compile` 通过；`from app.core.alert_levels import level_to_severity, level_to_priority, SEVERE_LEVEL` 可导入。
- **依赖**：无。
- **估时**：0.5h。

### WO-2 修 R1 `_level_to_severity`
- **目标**：告警→事件 severity 与权威口径一致。
- **改动**：`alert_incident_service.py:27-39` 替换为 `from app.core.alert_levels import level_to_severity as _level_to_severity`（§3.2）。`:119`/`:239` 调用点不动。
- **验收**：
  - `_level_to_severity(12) == "high"`（原 "critical"，**断言已不再是 critical**）
  - `_level_to_severity(9) == "medium"`、`_level_to_severity(6) == "low"`、`_level_to_severity(13) == "critical"`、`_level_to_severity(7) == "medium"`
  - 新建一条 level=12 的测试告警→事件，severity 落库为 `high`
- **依赖**：WO-1。
- **估时**：0.5h。

### WO-3 修 R2 `_heuristic_verdict` P 级
- **目标**：降级研判 P 级与 severity 链对齐。
- **改动**：`ai_analysis.py` 顶部加 `level_to_priority` import；`:529-537` 改 `priority = level_to_priority(level_max)`；`:544` `suggest_incident` 条件复核（§3.3）。
- **验收**：
  - `_heuristic_verdict({"level_max":13,...})["priority"] == "P0"`
  - `level_max=11 → "P1"`、`level_max=8 → "P2"`、`level_max=5 → "P3"`
  - 与 `_get_rule_level` 对同 level 的 severity 结论自洽（level13→critical↔P0）
- **依赖**：WO-1；`suggest_incident` 用 P0/P1 还是仅 P0 需评审拍板。
- **估时**：0.5h。

### WO-4 修 R3 `query_templates.py`
- **目标**：消除重复常量定义。
- **改动**：`query_templates.py:41-44` 删除私有 `_LEVEL_*`，改为 import 中央模块（§3.4）。
- **验收**：`py_compile` 通过；grep 确认该文件无 `>= 13`/`>= 10` 等裸阈值分桶。
- **依赖**：WO-1。
- **估时**：0.25h。

### WO-5 修 R4 `webhooks.py`
- **目标**：通知阈值显式命名，区分于 LEVEL_HIGH。
- **改动**：`webhooks.py` 顶部 import `SEVERE_LEVEL`；`:110` 与文档注释的 `12` 改为 `SEVERE_LEVEL`（§3.5）。
- **验收**：行为不变（阈值仍为 12）；`grep` 确认无裸 `12` 作为通知阈值；手动/单测模拟 `rule_level=12` 仍触发、`rule_level=11` 仍忽略。
- **依赖**：WO-1。
- **估时**：0.25h。

---

## 5. 验收总口径（"分级阈值统一"视为真正完成的签字条件）

1. 全项目**只存在一处**阈值真相：`app/core/alert_levels.py`。
2. `grep -rn ">= 12\|>= 9\|>= 8\|>= 6" app/` 在 level/severity 语义上下文中**零裸魔法数**（webhooks 用 `SEVERE_LEVEL` 命名常量不在此限）。
3. 单测覆盖：`level_to_severity` / `level_to_priority` 映射正确；`_level_to_severity`(12)≠critical；`_heuristic_verdict` level7-9→P2。
4. 端到端冒烟（接真实库）：构造 level=12 告警 → 事件页 severity=high（不再 critical）；构造 level=13 告警簇降级研判 → priority=P0。

---

## 6. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-08-22 | 初版。基于 2026-08-22 对 pi agent 修复的独立验证，收敛出 R1(真 bug)+R2/R3/R4(收尾) 四处补丁，含中央模块函数下沉设计与 5 张可执行工单。 |
