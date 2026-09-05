"""画像标签规则引擎（从 POC scripts/behavior_profile_collect.py 迁入）

- build_tags(): 规则判定，每项附 evidence。
- PERSONA_MAP(): 规则名 → 人设别名映射层（§9.7.4，与规则解耦、可独立调整）。
  当前样本未触发"学生党/购物狂"是事实（样本电商/学习占比 <1%），
  规则已随「学习教育」类预留（§9.7.5），覆盖到真实学生/购物设备即自动出现。

输入必须是 merge_days() 的滚动窗口聚合结果（7 天口径）。
"""

from typing import Dict, List

# 规则名 → 人设别名（展示层）。没有映射的规则直接显示规则名。
PERSONA_MAP: Dict[str, str] = {
    "夜猫子": "野猫子",
    "周末战士": "工作狂",
    "追剧党": "追剧狂",
    "典型打工人": "上班族",
    "下载机": "下载狂",
    "作息极规律": "规律党",
    "兴趣广泛": "杂食党",
    "书虫": "小说迷",
}


def persona_alias(name: str) -> str:
    return PERSONA_MAP.get(name, "")


def build_tags(s: dict) -> List[dict]:
    """画像标签规则引擎。返回 [{name, alias, desc, color, evidence}]"""
    tags: List[dict] = []

    def add(n, d, c, e):
        tags.append({"name": n, "alias": persona_alias(n), "desc": d, "color": c, "evidence": e})

    sh = s["cat_share"]
    total = s["total"]
    if not total:
        return tags

    # ── 时间节律类 ──
    if s["night_share"] >= 20:
        add("夜猫子", "深夜 00–06 点仍高度活跃", "#4c6ef5",
            f"深夜占比 {s['night_share']}%")
    elif s["night_share"] >= 10:
        add("轻度熬夜", "深夜有一定活动", "#748ffc",
            f"深夜占比 {s['night_share']}%")

    if s["morning_share"] >= 25:
        add("早起鸟", "清晨 06–09 点是主战场", "#22b8cf",
            f"早晨占比 {s['morning_share']}%")

    if s["workhours_share"] >= 60 and s["daily_avg"] >= 2000:
        add("工作狂", "工作时段高强度在线", "#1864ab",
            f"工作时段占比 {s['workhours_share']}%，日均 {s['daily_avg']:,} 次")

    if s["evening_share"] >= 30:
        add("夜间活跃型", "晚 19–24 点是主活跃期", "#845ef7",
            f"夜间占比 {s['evening_share']}%")

    if s["active_hours"] >= 150 and s["days"] >= 5:
        add("全天候在线", "几乎每个小时都有流量", "#0c8599",
            f"{s['active_hours']}/{s['days'] * 24} 小时有活动")
    elif 0 < s["active_hours"] <= s["days"] * 24 * 0.35 and s["days"] >= 5:
        add("间歇上线型", "只在部分时段出现", "#868e96",
            f"仅 {s['active_hours']} 个小时有活动")

    if s["top6_share"] >= 65:
        add("作息极规律", "活动高度集中在少数几小时", "#2f9e44",
            f"Top6 小时占 {s['top6_share']}%")
    elif s["top6_share"] <= 35:
        add("作息发散", "活动均匀铺开，无固定节律", "#f59f00",
            f"Top6 小时仅占 {s['top6_share']}%")

    weekdays = max(s["days"] - s["days"] // 7 * 2, 1)
    weekend_days = max(s["days"] // 7 * 2, 1)
    wd_per = s["workday"] / weekdays
    we_per = s["weekend"] / weekend_days if s["weekend"] > 0 else 0
    if we_per > wd_per * 1.25 and s["weekend"] > 0:
        add("周末战士", "周末比工作日更活跃", "#e8590c",
            f"周末日均 {int(we_per):,} vs 工作日 {int(wd_per):,}")
    elif wd_per > we_per * 1.5 and s["weekend"] > 0:
        add("典型打工人", "工作日显著高于周末", "#1971c2",
            f"工作日日均 {int(wd_per):,} vs 周末 {int(we_per):,}")

    # ── 兴趣类（只基于主动行为 ACT 层）──
    if sh.get("AI 工具", 0) >= 12:
        add("AI 重度用户", "AI 工具访问占比显著", "#7048e8",
            f"AI 类占主动行为 {sh['AI 工具']}%")
    elif sh.get("AI 工具", 0) >= 4:
        add("AI 尝鲜者", "有一定 AI 工具使用", "#9775fa",
            f"AI 类占 {sh['AI 工具']}%")

    if sh.get("开发技术", 0) >= 15:
        add("码农", "开发工具/云平台访问密集", "#1971c2",
            f"开发类占 {sh['开发技术']}%")

    # "学生党"（§9.7.5 预留）：学习教育类占比触发
    if sh.get("学习教育", 0) >= 12:
        add("学生党", "学习教育类访问密集", "#37b24d",
            f"学习类占主动行为 {sh['学习教育']}%")

    if sh.get("电商购物", 0) >= 12:
        add("剁手党", "电商/本地生活访问频繁", "#f76707",
            f"购物类占 {sh['电商购物']}%")
    elif sh.get("电商购物", 0) >= 5:
        add("理性消费者", "有一定购物浏览", "#fd7e14",
            f"购物类占 {sh['电商购物']}%")

    if sh.get("影音娱乐", 0) >= 25:
        add("追剧党", "短视频/长视频重度消费", "#e64980",
            f"影音类占 {sh['影音娱乐']}%")
    elif sh.get("影音娱乐", 0) >= 10:
        add("轻度刷视频", "有短视频消费习惯", "#f783ac",
            f"影音类占 {sh['影音娱乐']}%")

    if sh.get("小说阅读", 0) >= 12:
        add("书虫", "小说/阅读类访问突出", "#d6336c",
            f"阅读类占 {sh['小说阅读']}%")

    if sh.get("社交沟通", 0) >= 15:
        add("社交达人", "社交/即时通讯高频", "#20c997",
            f"社交类占 {sh['社交沟通']}%")

    if sh.get("游戏", 0) >= 15:
        add("游戏迷", "游戏相关流量占比高", "#ae3ec9",
            f"游戏类占 {sh['游戏']}%")

    if sh.get("下载传输", 0) >= 15:
        add("下载机", "P2P/网盘下载流量显著", "#5c7cfa",
            f"下载类占 {sh['下载传输']}%")

    # ── 设备/性质类 ──
    lv = s["layer_visit"]
    if total and lv.get("SYS", 0) / total >= 0.6:
        add("机器流量为主", "绝大部分是系统/协议心跳", "#868e96",
            f"系统背景占 {round(lv['SYS'] / total * 100)}%")
    if total and lv.get("AD", 0) / total >= 0.35:
        add("广告追踪密集", "大量流量来自 SDK 上报", "#adb5bd",
            f"广告追踪占 {round(lv['AD'] / total * 100)}%")
    if s["domain_count"] <= 60 and total >= 5000:
        add("行为极单一", "只访问极少数域名", "#495057",
            f"{s['domain_count']} 个域名 / {total:,} 次访问")
    if s["domain_count"] >= 400:
        add("兴趣广泛", "域名覆盖面很广", "#2f9e44",
            f"覆盖 {s['domain_count']} 个域名")

    return tags


def compute_confidence(total: int, truncated_windows: int, days_span: int = 1) -> int:
    """快照置信度 0-100：数据量 + 截断惩罚。

    - 数据量：total≥1000 满分起步，线性衰减到 0
    - 每个 truncated_window 扣 15（数据不完整的显式惩罚，§9.3）
    """
    if total <= 0:
        return 0
    vol = min(total / 1000, 1) * 100
    trunc_penalty = min(truncated_windows * 15, 50)
    span_bonus = min(days_span, 3) * 2  # 多日窗口略有加成
    return max(0, min(100, round(vol - trunc_penalty + span_bonus)))
