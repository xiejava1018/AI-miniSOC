"""
行为画像采集器（Behavior Profile Collector）
============================================
从 Loki 采集指定 IP 的上网行为原始日志，产出「行为画像」所需的全部维度：

  1. 小时级活跃序列（7 天 × 24 小时）
  2. 域名 × 小时矩阵（正则下推提取域名，避免拉全量原始日志）
  3. 时段分布（7 个时段 / 工作日 vs 周末）
  4. 域名分类（主动行为 vs 系统背景 vs 广告追踪）
  5. 画像标签（规则引擎打分）

设计要点
--------
* **Loki 读取上限**：单次 query_range 超过 100 MiB 会被拒绝，故按 24h 分块。
* **域名提取下推**：用 `| regexp "网址:(?P<dom>[^ :]+)"` 把域名做成 label，
  再用 `sum by (dom) (count_over_time(...))` 让 Loki 侧完成聚合，
  避免把数十万行原始日志拉回本地（实测单日查询 0.2s）。
* **行为分层**：NTP / DNS / 系统更新 / 广告追踪是机器行为，不能算作人的兴趣，
  分类时单独归入「系统背景」「广告追踪」，画像标签只基于「主动行为」计算。

用法
----
    python scripts/behavior_profile_collect.py                      # 默认目标集
    python scripts/behavior_profile_collect.py 192.168.0.8 --days 7
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter, defaultdict

import httpx

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

try:
    from app.core.config import settings

    LOKI = settings.LOKI_API_URL.rstrip("/")
except Exception:  # pragma: no cover
    LOKI = os.getenv("LOKI_URL", "http://192.168.0.30:3100").rstrip("/")

TZ = dt.timezone(dt.timedelta(hours=8))
NS = 1_000_000_000

DEFAULT_TARGETS = [
    "192.168.0.8",  # xiejava 的开发机（Mac Mini）
    "192.168.0.100",  # 另一台 Mac 工作站
    "192.168.0.17",  # NAS / 下载机
    "192.168.0.25",  # 手机用户（小说 + 短视频）
    "192.168.0.27",  # 手机用户（购物 + 社交）
    "192.168.0.30",  # 服务器（Wazuh / Loki / Grafana）
    "192.168.0.42",  # DNS / 网络设备
    "192.168.0.102",  # xiejava 的服务器
]

# ─────────────────────────────────────────────────────────────
# 时段定义
# ─────────────────────────────────────────────────────────────
TIME_BLOCKS = [
    (0, 6, "深夜", "00-06", "#4c6ef5"),
    (6, 9, "早晨", "06-09", "#22b8cf"),
    (9, 12, "上午", "09-12", "#51cf66"),
    (12, 14, "午间", "12-14", "#fcc419"),
    (14, 18, "下午", "14-18", "#ff922b"),
    (18, 21, "傍晚", "18-21", "#ff6b6b"),
    (21, 24, "夜间", "21-24", "#845ef7"),
]


def block_of(hour: int) -> dict:
    for lo, hi, name, label, color in TIME_BLOCKS:
        if lo <= hour < hi:
            return {"name": name, "label": label, "color": color}
    return TIME_BLOCKS[-1]


# ─────────────────────────────────────────────────────────────
# 域名分类体系
#   三大层：ACT（主动行为）/ SYS（系统背景）/ AD（广告追踪）
#   ACT 内部再分兴趣类别，用于「访问习惯」与「画像标签」
# ─────────────────────────────────────────────────────────────
CATEGORIES = {
    "AI 工具": {
        "layer": "ACT",
        "color": "#7048e8",
        "icon": "✦",
        "kw": [
            "copilot", "chatgpt", "openai", "claude", "anthropic", "bigmodel",
            "open.bigmodel", "glm", "minimaxi", "minimax", "deepseek", "kimi",
            "moonshot", "doubao", "z.ai", "gemini", "huggingface", "volcengineapi",
            "tgalileo", "galileo", "ark.cn", "lingxi", "tencent-ai", "qianfan",
            "baichuan", "01.ai", "siliconflow", "multica", "api.multica",
        ],
    },
    "开发技术": {
        "layer": "ACT",
        "color": "#1971c2",
        "icon": "⌘",
        "kw": [
            "vscode", "visualstudio", "github", "gitlab", "gitee", "npmjs",
            "pypi", "docker", "stackoverflow", "csdn", "juejin", "cnblogs",
            "jetbrains", "gradle", "maven", "aliyun", "tencent-cloud",
            "myqcloud", "log.aliyuncs", "xtrace", "sentry", "grafana",
            "kubernetes", "jenkins", "vercel", "netlify", "cloudflare",
            "workbuddy", "api.", "sdk", "developer",
        ],
    },
    "工作办公": {
        "layer": "ACT",
        "color": "#0c8599",
        "icon": "▤",
        "kw": [
            "wps.cn", "wpscdn", "docs.qq", "doc.weixin", "feishu", "lark",
            "dingtalk", "office", "outlook", "sharepoint", "teams", "zoom",
            "docs.gtimg", "docs2.gtimg", "drive.wps", "mail.163",
            "woodcattle", "dashi.163", "tencent-doc", "notion", "yuque",
            "shimo", "processon", "xmind",
        ],
    },
    "影音娱乐": {
        "layer": "ACT",
        "color": "#e64980",
        "icon": "▶",
        "kw": [
            "douyin", "zijieapi", "byteimg", "douyinpic", "bilibili",
            "hdslb", "iqiyi", "youku", "v.qq", "qqlive", "youtube",
            "netflix", "mgtv", "hitv", "kugou", "qqmusic", "kuwo",
            "spotify", "webcast", "live.", "mcdn", "vod", "video",
            "qznovelvod", "readingvideo",
        ],
    },
    "小说阅读": {
        "layer": "ACT",
        "color": "#d6336c",
        "icon": "❏",
        "kw": [
            "novel", "qnovel", "fqnovel", "fqnovelpic", "ishareread",
            "zhangyue", "qqread", "weread", "duokan", "chuangshi",
            "read.", "book.", "zongheng", "qidian",
        ],
    },
    "电商购物": {
        "layer": "ACT",
        "color": "#f76707",
        "icon": "🛒",
        "kw": [
            "taobao", "tmall", "jd.com", "360buy", "pinduoduo", "yangkeduo",
            "meituan", "s3plus.meituan", "ele.me", "suning", "kaola",
            "xiaohongshu", "ecombdapi", "goofish", "闲鱼", "alipay",
            "tmall.com", "alicdn", "taobaocdn", "dianping", "amazon",
        ],
    },
    "社交沟通": {
        "layer": "ACT",
        "color": "#20c997",
        "icon": "◍",
        "kw": [
            "weixin", "wechat", "dns.weixin", "tencent-cloud.net",
            "apd-pcdnwx", "weibo", "momo", "douban", "zhihu", "tieba",
            "xigua", "qq.com", "im.", "chat.", "message",
        ],
    },
    "游戏": {
        "layer": "ACT",
        "color": "#ae3ec9",
        "icon": "◈",
        "kw": [
            "nie.netease", "netease", "163.com", "miHoYo", "hoyoverse",
            "genshin", "steam", "epicgames", "pubg", "lol.qq", "game.",
            "games.", "tgp", "wegame", "battle", "garena",
        ],
    },
    "新闻资讯": {
        "layer": "ACT",
        "color": "#868e96",
        "icon": "▦",
        "kw": [
            "news", "sina", "sohu", "toutiao", "thepaper", "people.com.cn",
            "xinhua", "cctv", "ithome", "cnbeta", "36kr", "huxiu",
            "infoq", "cisa.gov",
        ],
    },
    "下载传输": {
        "layer": "ACT",
        "color": "#5c7cfa",
        "icon": "⇩",
        "kw": [
            "xunlei", "sandai", "thunder", "pcdn", "bt.", "torrent",
            "pan.", "baiduPan", "aliyundrive", "quark.cn", "fnnas",
            "fnos.", "dlandroid", "rcv.sandai",
        ],
    },
    "移动设备": {
        "layer": "ACT",
        "color": "#4c6ef5",
        "icon": "▢",
        "kw": [
            "miui", "xiaomi", "mi.com", "oppo", "vivo", "huawei", "honor",
            "oneplus", "realme", "meizu", "samsung", "apple.com",
            "icloud", "aaplimg", "mzstatic", "apple-cloudkit",
        ],
    },
    # ── 非主动行为层 ──
    "系统背景": {
        "layer": "SYS",
        "color": "#adb5bd",
        "icon": "⚙",
        "kw": [
            "ntp", "pool.ntp", "time.", "time.apple", "time.g.aaplimg",
            "dns.google", "doh.pub", "alidns", "dns.weixin.qq.com.cn",
            "in-addr.arpa", "update.", "ocsp", "ocsp2", "apple.com",
            "weatherkit", "stun", "telemetry", "metrics", "crash",
            "crashlytics", "sentry.io", "ubuntu", "snapcraft",
            "launchpad", "archive.", "apt.", "msftconnecttest",
            "connectivity", "captive", "whoami.akamai", "ipw.cn",
        ],
    },
    "广告追踪": {
        "layer": "AD",
        "color": "#ced4da",
        "icon": "◌",
        "kw": [
            "tracking", "adashx", "gdt", "gdtimg", "ugdtimg", "adsmind",
            "ads3", "ads.", "ad.", "px.", "analytics", "countly",
            "sensor", "beacon", "log.", "stat", "monitor", "report.",
            "sdktt", "comfylink", "shuc-other", "metok", "get.sogou",
            "bsync", "gecko", "apd-", "pgdt",
        ],
    },
}

# 分类优先级：越靠前越优先匹配（避免 "apple.com" 吃掉 "weatherkit.apple.com"）
_CAT_ORDER = [
    "AI 工具", "开发技术", "工作办公", "小说阅读", "影音娱乐",
    "电商购物", "社交沟通", "游戏", "新闻资讯", "下载传输",
    "移动设备", "广告追踪", "系统背景",
]

_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def classify(domain: str) -> tuple[str, dict]:
    """把域名归入一个类别，返回 (类别名, 类别定义)。"""
    d = (domain or "").lower().strip()
    if not d:
        return "其他", {"layer": "ACT", "color": "#adb5bd", "icon": "·"}
    if _IP_RE.match(d):
        return "IP 直连", {"layer": "ACT", "color": "#495057", "icon": "#"}
    for cat in _CAT_ORDER:
        for kw in CATEGORIES[cat]["kw"]:
            if kw in d:
                return cat, CATEGORIES[cat]
    return "其他", {"layer": "ACT", "color": "#adb5bd", "icon": "·"}


# ─────────────────────────────────────────────────────────────
# Loki 查询
# ─────────────────────────────────────────────────────────────
def _ns(d: dt.datetime) -> str:
    return str(int(d.timestamp() * NS))


def loki_query_range(query: str, start: dt.datetime, end: dt.datetime,
                     step: str = "1h", timeout: float = 300.0):
    with httpx.Client(timeout=timeout) as c:
        r = c.get(f"{LOKI}/loki/api/v1/query_range", params={
            "query": query, "start": _ns(start), "end": _ns(end), "step": step})
        if r.status_code != 200:
            raise RuntimeError(f"Loki {r.status_code}: {r.text[:200]}")
        return r.json()["data"]["result"]


def loki_raw(ip: str, start: dt.datetime, end: dt.datetime, limit: int = 10000):
    """拉取某时间窗内的原始日志行，返回 [(ts_ns, line), ...]。"""
    with httpx.Client(timeout=120.0) as c:
        r = c.get(f"{LOKI}/loki/api/v1/query_range", params={
            "query": f'{{ip="{ip}"}}',
            "start": _ns(start), "end": _ns(end),
            "limit": str(limit), "direction": "forward"})
        if r.status_code != 200:
            raise RuntimeError(f"Loki {r.status_code}: {r.text[:200]}")
        out = []
        for x in r.json()["data"]["result"]:
            out.extend((int(ts), line) for ts, line in x.get("values", []))
        return out


MIN_WINDOW = dt.timedelta(minutes=15)


def pull_window(ip, start, end, limit=10000, stats=None):
    """递归自适应分块：单次查询撞到 limit 就把窗口劈成两半再拉。

    为什么要自己数而不用 count_over_time：
    实测 Loki 的 `sum(count_over_time({ip}[1h]))` 在 step=1h 下存在
    **窗口标签错位**（真实 20 点的数据被标到 21 点）与**边界重复计数**
    （凭空多出一个 11 点尖峰）。行为画像对时段极其敏感，一个小时的偏移
    足以把"夜猫子"误判成"早起鸟"，故一律以原始日志时间戳为准。
    """
    rows = loki_raw(ip, start, end, limit)
    if stats is not None:
        stats[0] += 1
    if len(rows) >= limit and (end - start) > MIN_WINDOW:
        mid = start + (end - start) / 2
        return (pull_window(ip, start, mid, limit, stats)
                + pull_window(ip, mid, end, limit, stats))
    if len(rows) >= limit and stats is not None:
        stats[1] += 1  # 已切到最小窗口仍然饱和 → 该窗口被截断
    return rows


# 日志行: {"body":"<13>Sep 05 10:09:51 TL-R479GP-AC behavior_ctl: ...
#          上网行为:a:IPGROUP_ANY a:1.2.3.4 网站分组:所有网站 网址:host:port 。"}
RE_DOM = re.compile(r"网址:([^\s:：]+)")


def fetch_events(ip: str, days: int, now: dt.datetime):
    """拉取指定 IP 全部原始上网行为事件，返回 [(本地datetime, 域名), ...]。"""
    events = []
    stats = [0, 0]  # [请求数, 截断窗口数]
    end = now
    remaining = days * 24
    while remaining > 0:
        chunk = min(6, remaining)
        start = end - dt.timedelta(hours=chunk)
        for ts, line in pull_window(ip, start, end, stats=stats):
            m = RE_DOM.search(line)
            if not m:
                continue
            d = dt.datetime.fromtimestamp(ts / 1e9, TZ)
            events.append((d, m.group(1).lower()))
        end = start
        remaining -= chunk
    return events, stats


def build_from_events(events: list, days: int):
    """把原始事件汇总成画像统计（替代被弃用的 fetch_hourly/fetch_domain_hour）。"""
    if not events:
        return None
    hourly: dict[int, int] = {}
    matrix: dict[str, dict[int, int]] = defaultdict(dict)
    for d, dom in events:
        key = int(d.replace(minute=0, second=0, microsecond=0).timestamp())
        hourly[key] = hourly.get(key, 0) + 1
        matrix[dom][key] = matrix[dom].get(key, 0) + 1
    return hourly, matrix


# ─────────────────────────────────────────────────────────────
# 聚合与画像
# ─────────────────────────────────────────────────────────────
def build_stats(hourly: dict[int, int], matrix: dict[str, dict[int, int]]):
    """把小时序列 + 域名矩阵汇总成画像统计。"""
    total = sum(hourly.values())
    if total == 0:
        return None

    # 24 小时分布
    by_hour = [0] * 24
    # 星期 × 小时
    wd_hour = [[0] * 24 for _ in range(7)]
    # 时段分布
    by_block = {b[2]: 0 for b in TIME_BLOCKS}
    # 工作日 vs 周末
    workday = weekend = 0
    # 每日
    by_day: dict[str, int] = defaultdict(int)

    for ts, n in hourly.items():
        d = dt.datetime.fromtimestamp(ts, TZ)
        by_hour[d.hour] += n
        wd_hour[d.weekday()][d.hour] += n
        blk = block_of(d.hour)
        by_block[blk["name"]] += n
        if d.weekday() < 5:
            workday += n
        else:
            weekend += n
        by_day[d.strftime("%m-%d")] += n

    # 域名层面：总访问量 + 分类 + 分类×时段
    dom_total = {d: sum(h.values()) for d, h in matrix.items()}

    # 分类统计（按访问量）
    cat_visit = Counter()
    cat_domain = Counter()
    cat_by_block: dict[str, Counter] = defaultdict(Counter)
    dom_cat = {}
    for dom, tot in dom_total.items():
        cat, _ = classify(dom)
        dom_cat[dom] = cat
        cat_visit[cat] += tot
        cat_domain[cat] += 1
        for ts, n in matrix[dom].items():
            h = dt.datetime.fromtimestamp(ts, TZ).hour
            cat_by_block[block_of(h)["name"]][cat] += n

    layer_visit = Counter()
    for cat, v in cat_visit.items():
        layer_visit[CATEGORIES.get(cat, {}).get("layer", "ACT")] += v

    act_total = layer_visit["ACT"]
    cat_share = {c: (v / act_total * 100 if act_total else 0)
                 for c, v in cat_visit.items()
                 if CATEGORIES.get(c, {}).get("layer", "ACT") == "ACT"}

    active_hours = len([1 for v in hourly.values() if v > 0])
    peak_hour = max(range(24), key=lambda h: by_hour[h]) if total else 0
    top6_share = sum(sorted(by_hour, reverse=True)[:6]) / total * 100 if total else 0

    night = sum(by_hour[h] for h in range(0, 6)) / total * 100 if total else 0
    morning = sum(by_hour[h] for h in range(6, 9)) / total * 100 if total else 0
    workhrs = sum(by_hour[h] for h in range(9, 19)) / total * 100 if total else 0
    evening = sum(by_hour[h] for h in range(19, 24)) / total * 100 if total else 0

    return {
        "total": total,
        "days": len(by_day),
        "daily_avg": round(total / max(len(by_day), 1)),
        "by_hour": by_hour,
        "wd_hour": wd_hour,
        "by_block": by_block,
        "by_day": dict(sorted(by_day.items())),
        "workday": workday,
        "weekend": weekend,
        "workday_share": round(workday / total * 100, 1) if total else 0,
        "domain_count": len(dom_total),
        "top_domains": [
            {"domain": d, "visits": v, "category": dom_cat.get(d, "其他"),
             "share": round(v / total * 100, 2)}
            for d, v in sorted(dom_total.items(), key=lambda t: -t[1])[:30]
        ],
        "cat_visit": dict(cat_visit.most_common()),
        "cat_domain": dict(cat_domain.most_common()),
        "cat_share": {k: round(v, 1) for k, v in
                      sorted(cat_share.items(), key=lambda t: -t[1])},
        "cat_by_block": {b: dict(c) for b, c in cat_by_block.items()},
        "layer_visit": dict(layer_visit),
        "act_total": act_total,
        "active_hours": active_hours,
        "peak_hour": peak_hour,
        "top6_share": round(top6_share, 1),
        "night_share": round(night, 1),
        "morning_share": round(morning, 1),
        "workhours_share": round(workhrs, 1),
        "evening_share": round(evening, 1),
    }


def build_tags(s: dict) -> list[dict]:
    """画像标签规则引擎。返回 [{name, desc, color, evidence}]"""
    tags = []
    add = lambda n, d, c, e: tags.append(
        {"name": n, "desc": d, "color": c, "evidence": e})

    sh = s["cat_share"]
    bh = s["by_hour"]
    total = s["total"]

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
    elif s["active_hours"] <= s["days"] * 24 * 0.35 and s["days"] >= 5:
        add("间歇上线型", "只在部分时段出现", "#868e96",
            f"仅 {s['active_hours']} 个小时有活动")

    if s["top6_share"] >= 65:
        add("作息极规律", "活动高度集中在少数几小时", "#2f9e44",
            f"Top6 小时占 {s['top6_share']}%")
    elif s["top6_share"] <= 35:
        add("作息发散", "活动均匀铺开，无固定节律", "#f59f00",
            f"Top6 小时仅占 {s['top6_share']}%")

    wd_per = s["workday"] / max(s["days"] - s["days"] // 7 * 2, 1)
    we_per = s["weekend"] / max(s["days"] // 7 * 2, 1) if s["days"] >= 7 else 0
    if we_per > wd_per * 1.25 and s["weekend"] > 0:
        add("周末战士", "周末比工作日更活跃", "#e8590c",
            f"周末日均 {int(we_per):,} vs 工作日 {int(wd_per):,}")
    elif wd_per > we_per * 1.5 and s["weekend"] > 0:
        add("典型打工人", "工作日显著高于周末", "#1971c2",
            f"工作日日均 {int(wd_per):,} vs 周末 {int(we_per):,}")

    # ── 兴趣类（只基于主动行为 ACT 层）──
    def top_cat(n=3):
        return [c for c in list(sh.items())[:n]]

    if sh.get("AI 工具", 0) >= 12:
        add("AI 重度用户", "AI 工具访问占比显著", "#7048e8",
            f"AI 类占主动行为 {sh['AI 工具']}%")
    elif sh.get("AI 工具", 0) >= 4:
        add("AI 尝鲜者", "有一定 AI 工具使用", "#9775fa",
            f"AI 类占 {sh['AI 工具']}%")

    if sh.get("开发技术", 0) >= 15:
        add("码农", "开发工具/云平台访问密集", "#1971c2",
            f"开发类占 {sh['开发技术']}%")

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


def asset_info(ips: list[str]) -> dict:
    """从资产表取设备身份信息（取不到就返回空）。"""
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        rows = db.execute(text("""
            select asset_ip, name, asset_type, criticality, owner,
                   os_name, mac_address, business_unit
            from soc_assets where asset_ip = any(:ips)
        """), {"ips": ips}).fetchall()
        db.close()
        return {r[0]: dict(zip(
            ["ip", "name", "asset_type", "criticality", "owner",
             "os_name", "mac_address", "business_unit"], r)) for r in rows}
    except Exception as e:
        print(f"  (资产信息不可用: {str(e)[:80]})")
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ips", nargs="*", default=DEFAULT_TARGETS)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default="scripts/behavior_profile_data.json")
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    print(f"Loki: {LOKI}   窗口: 最近 {args.days} 天   目标: {len(args.ips)} 个 IP\n")

    assets = asset_info(args.ips)
    targets = []
    for ip in args.ips:
        print(f"[{ip}] 采集中…")
        events, st = fetch_events(ip, args.days, now)
        if not events:
            print("    × 无数据，跳过")
            continue
        built = build_from_events(events, args.days)
        if not built:
            continue
        hourly, matrix = built
        total = sum(hourly.values())
        stats = build_stats(hourly, matrix)
        if not stats:
            continue
        stats["truncated_windows"] = st[1]
        stats["loki_requests"] = st[0]
        tags = build_tags(stats)
        a = assets.get(ip, {})
        targets.append({
            "ip": ip,
            "asset": a,
            "stats": stats,
            "tags": tags,
        })
        trunc = f" ⚠{st[1]}窗口截断" if st[1] else ""
        print(f"    ✓ {total:>9,} 次访问 | {stats['domain_count']:>4} 域名 | "
              f"峰值 {stats['peak_hour']:>2} 点 | {st[0]} 次查询{trunc}")
        print(f"      标签: {', '.join(t['name'] for t in tags) or '（无）'}")

    payload = {
        "generated_at": dt.datetime.now(TZ).isoformat(),
        "loki": LOKI,
        "days": args.days,
        "time_blocks": [{"name": b[2], "label": b[3], "color": b[4]} for b in TIME_BLOCKS],
        "categories": {k: {kk: vv for kk, vv in v.items() if kk != "kw"}
                       for k, v in CATEGORIES.items()},
        "targets": targets,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}  ({len(targets)} 个主体)")


if __name__ == "__main__":
    main()
