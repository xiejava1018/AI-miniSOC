"""域名分类体系 + 时段定义（从 POC scripts/behavior_profile_collect.py 迁入）

设计要点（POC 已验证）：
- 三大层：ACT（主动行为）/ SYS（系统背景）/ AD（广告追踪），
  NTP/DNS/系统更新/广告追踪是机器行为，不纳入人的兴趣统计。
- 分类优先级 _CAT_ORDER 越靠前越优先（避免 "apple.com" 吃掉 "weatherkit.apple.com"）。
- 学习教育类（§9.7.5 补充）：让"学生党"标签可触发。
"""

import re
from dataclasses import dataclass
from typing import Optional

# ─────────────────────────────────────────────────────────────
# 时段定义（7 段）
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TimeBlock:
    lo: int
    hi: int
    name: str
    label: str
    color: str


TIME_BLOCKS = [
    TimeBlock(0, 6, "深夜", "00-06", "#4c6ef5"),
    TimeBlock(6, 9, "早晨", "06-09", "#22b8cf"),
    TimeBlock(9, 12, "上午", "09-12", "#51cf66"),
    TimeBlock(12, 14, "午间", "12-14", "#fcc419"),
    TimeBlock(14, 18, "下午", "14-18", "#ff922b"),
    TimeBlock(18, 21, "傍晚", "18-21", "#ff6b6b"),
    TimeBlock(21, 24, "夜间", "21-24", "#845ef7"),
]

BLOCK_ORDER = [b.name for b in TIME_BLOCKS]


def block_of(hour: int) -> TimeBlock:
    for b in TIME_BLOCKS:
        if b.lo <= hour < b.hi:
            return b
    return TIME_BLOCKS[-1]


# ─────────────────────────────────────────────────────────────
# 分类体系（layer: ACT/SYS/AD；kw 为子串匹配关键词）
# ─────────────────────────────────────────────────────────────

CATEGORIES: dict[str, dict] = {
    "AI 工具": {
        "layer": "ACT", "color": "#7048e8", "icon": "✦",
        "kw": [
            "copilot", "chatgpt", "openai", "claude", "anthropic", "bigmodel",
            "open.bigmodel", "glm", "minimaxi", "minimax", "deepseek", "kimi",
            "moonshot", "doubao", "z.ai", "gemini", "huggingface", "volcengineapi",
            "tgalileo", "galileo", "ark.cn", "lingxi", "tencent-ai", "qianfan",
            "baichuan", "01.ai", "siliconflow", "multica", "api.multica",
        ],
    },
    "开发技术": {
        "layer": "ACT", "color": "#1971c2", "icon": "⌘",
        "kw": [
            "vscode", "visualstudio", "github", "gitlab", "gitee", "npmjs",
            "pypi", "docker", "stackoverflow", "csdn", "juejin", "cnblogs",
            "jetbrains", "gradle", "maven", "aliyuncs", "tencent-cloud",
            "myqcloud", "xtrace", "sentry", "grafana",
            "kubernetes", "jenkins", "vercel", "netlify", "cloudflare",
            "workbuddy", "api.", "sdk", "developer",
        ],
    },
    "工作办公": {
        "layer": "ACT", "color": "#0c8599", "icon": "▤",
        "kw": [
            "office", "microsoftonline", "dingtalk", "feishu", "larksuite",
            "notion", "yuhuati", "teambition", "wps", "kingsoft", "zoom",
            "tencentmeeting", "weixin-work", "work.weixin", "docs.qq",
            "shimo", "yiyizbms", "pan.baidu", "yunpan", "asana", "trello",
        ],
    },
    "学习教育": {
        "layer": "ACT", "color": "#37b24d", "icon": "✎",
        "kw": [
            "coursera", "edx", "udemy", "mooc", "icourse163", "xuetangx",
            "bilibili.education", "kaoyan", "chaoxing", "xueersi", "zxxk",
            "21cnjy", "jyeoo", "koolearn", "learnku", "runoob", "w3school",
            "edu.cn", "school", "academy", "tutorial",
        ],
    },
    "影音娱乐": {
        "layer": "ACT", "color": "#e64980", "icon": "▶",
        "kw": [
            "douyin", "tiktok", "bilibili", "iqiyi", "youku", "v.qq",
            "mgtv", "sohu.tv", "letv", "acfun", "ixigua", "kuaishou",
            "netflix", "youtube", "spotify", "music.163", "kugou", "kuwo",
            "qqmusic", "ximalaya", "qingting", "lrts", "emby", "jellyfin",
            "plex", "tvbox", "nvidia.dtv", "hitv", "tcl.com", "skyworth",
        ],
    },
    "小说阅读": {
        "layer": "ACT", "color": "#d6336c", "icon": "❏",
        "kw": [
            "qidian", "zongheng", "hongxiu", "jjwxc", "ciweimao", "fanqie",
            "changdunovel", "duokan", "areal.me", "69shu", "biquge",
            "ixdzs", "kunyuankan", "trxs", "shuku", "novel",
        ],
    },
    "电商购物": {
        "layer": "ACT", "color": "#f76707", "icon": "🛒",
        "kw": [
            "taobao", "tmall", "jd.com", "jd.hk", "pinduoduo", "yangkeduo",
            "suning", "gome", "vip.com", "wphuodong", "kaola", "dangdang",
            "xiaohongshu", "xhslink", "meituan", "dianping", "ele.me",
            "starbucks", "mcdonalds", "kfc", "luckin", "heytea",
        ],
    },
    "社交沟通": {
        "layer": "ACT", "color": "#20c997", "icon": "◍",
        "kw": [
            "weixin", "wechat", "qq.com", "tim.qq", "whatsapp", "telegram",
            "signal", "line.naver", "discord", "slack", "twitter", "x.com",
            "facebook", "instagram", "linkedin", "weibo", "zhihu", "tieba",
            "douban", "xiahei", "soulapp", "momo",
        ],
    },
    "游戏": {
        "layer": "ACT", "color": "#ae3ec9", "icon": "◈",
        "kw": [
            "steampowered", "epicgames", "battle.net", "riotgames", "tencentgames",
            "mihoyo", "hoyoverse", "yuanshen", "neteasegames", "unity", "unrealengine",
            "ea.com", "ubisoft", "rockstar", "minecraft", "mojang", "4399", "37.net",
        ],
    },
    "新闻资讯": {
        "layer": "ACT", "color": "#868e96", "icon": "▦",
        "kw": [
            "news", "toutiao", "chinanews", "thepaper", "caixin", "jiemian",
            "ifeng", "people.com", "xinhuanet", "cctv", "nbd.com", "cls.cn",
            "yicai", "21jingji", "ftchinese", "wsj", "reuters", "bbc", "cnn",
        ],
    },
    "下载传输": {
        "layer": "ACT", "color": "#5c7cfa", "icon": "⇩",
        "kw": [
            "thunder", "xunlei", "115.com", "123pan", "quark", "uc.cn",
            "aliyundrive", "alipan", "mega.nz", "mediafire", "utorrent",
            "transmission", "aria2", "qbittorrent", "openwrt.download",
        ],
    },
    "移动设备": {
        "layer": "ACT", "color": "#4c6ef5", "icon": "▢",
        "kw": [
            "xiaomi", "mi.com", "miwifi", "oppo", "heytap", "vivo", "honor",
            "huawei", "hicloud", "meizu", "oneplus", "coloros", "miui",
        ],
    },
    "广告追踪": {
        "layer": "AD", "color": "#ced4da", "icon": "◌",
        "kw": [
            "doubleclick", "googlesyndication", "googleadservices",
            "adnxs", "adsrvr", "criteo", "taboola", "outbrain", "appsflyer",
            "adjust.com", "umeng", "countly", "woodcattle", "applovin",
            "ironsrc", "vungle", "unityads", "tracking", "analytics",
        ],
    },
    "系统背景": {
        "layer": "SYS", "color": "#adb5bd", "icon": "⚙",
        "kw": [
            "ntp", "time.apple", "time.windows", "pool.ntp", "dns",
            "dnsmasq", "swscan", "mesu", "xp.apple", "updates.cdn",
            "windowsupdate", "update.microsoft", " ubuntu", "debian",
            "redhat", "centos", "mirrors.", "connect.rom",
            "systemupdate", "ota", "checkip", "ipify", "ip.sb",
            "connectivitycheck", "msftconnecttest", "gstatic",
            "captive.apple", "uuid", "metrics", "telemetry",
        ],
    },
}

# 分类优先级：越靠前越优先匹配（避免 "apple.com" 吃掉 "weatherkit.apple.com"）
_CAT_ORDER = [
    "AI 工具", "开发技术", "工作办公", "学习教育", "小说阅读", "影音娱乐",
    "电商购物", "社交沟通", "游戏", "新闻资讯", "下载传输",
    "移动设备", "广告追踪", "系统背景",
]

_OTHER = {"layer": "ACT", "color": "#adb5bd", "icon": "·"}
_IP_DIRECT = {"layer": "ACT", "color": "#495057", "icon": "#"}

_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


# 9.7.3 可配置词典缓存：soc_system_config(category='behavior_profile', key='domain_categories')
# 值为 JSON：{"分类名": {"kw": [...], "layer": "ACT"}}, 运营可增删关键词/调优先级
# （dict 键序即优先级）。缓存 5 分钟，读失败回落代码内置词典。
_dict_override: dict | None = None
_dict_loaded_at: float = 0.0


def _load_dict_override() -> dict:
    """返回 {cat: [kw,...]} 的运营覆盖（空 dict = 无覆盖）。"""
    global _dict_override, _dict_loaded_at
    import time as _time
    now = _time.time()
    if _dict_override is not None and now - _dict_loaded_at < 300:
        return _dict_override
    override: dict = {}
    try:
        import json as _json
        from app.core.database import SessionLocal
        from app.models.system_config import SystemConfig
        db = SessionLocal()
        try:
            row = (db.query(SystemConfig)
                   .filter(SystemConfig.category == "behavior_profile",
                           SystemConfig.key == "domain_categories")
                   .first())
            if row and row.value:
                data = _json.loads(row.value)
                # 展开为 {cat: [kw...]}，保留运营给的键序
                for cat, spec in data.items():
                    kws = spec.get("kw", []) if isinstance(spec, dict) else spec
                    override[cat] = [str(k).lower() for k in kws]
        finally:
            db.close()
    except Exception:
        pass  # 静默回落内置词典
    _dict_override = override
    _dict_loaded_at = now
    return override


def invalidate_dict_cache() -> None:
    """词典更新后调用（运营改配置后生效，无需重启）。"""
    global _dict_override
    _dict_override = None


def classify(domain: str) -> tuple[str, dict]:
    """把域名归入一个类别，返回 (类别名, 类别定义)。"""
    d = (domain or "").lower().strip()
    if not d:
        return "其他", _OTHER
    if _IP_RE.match(d):
        return "IP 直连", _IP_DIRECT
    # 1) 运营覆盖词典优先（键序即优先级）
    override = _load_dict_override()
    if override:
        for cat, kws in override.items():
            for kw in kws:
                if kw and kw in d:
                    return cat, CATEGORIES.get(cat) or {
                        "layer": "ACT", "color": "#7048e8", "icon": "✦"}
    # 2) 内置词典
    for cat in _CAT_ORDER:
        for kw in CATEGORIES[cat]["kw"]:
            if kw in d:
                return cat, CATEGORIES[cat]
    return "其他", _OTHER


def category_layer(category: str) -> str:
    return CATEGORIES.get(category, {}).get("layer", "ACT")


def is_known_category(category: str) -> bool:
    return category in CATEGORIES


def lookup_category(category: str) -> Optional[dict]:
    return CATEGORIES.get(category)
