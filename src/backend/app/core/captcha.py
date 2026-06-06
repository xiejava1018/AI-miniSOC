"""
验证码模块

提供图形验证码生成和验证功能。
使用内存存储（带过期时间），生产环境建议替换为Redis。
"""

import base64
import io
import os
import platform
import random
import string
import time
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


# 内存验证码存储: {key: (code, expire_timestamp)}
_captcha_store: dict[str, Tuple[str, float]] = {}
CAPTCHA_EXPIRE_SECONDS = 300  # 5分钟过期
CAPTCHA_LENGTH = 4
CAPTCHA_FONT_SIZE = 36  # 跨平台统一字号（之前 macOS 28 偏小, Windows/Linux fallback 10 更小）


def _candidate_font_paths() -> list[str]:
    """
    跨平台常见等宽字体路径，按优先级排序。

    历史: 之前硬编码 /System/Library/Fonts/Supplemental/Courier New.ttf,
    只在 macOS 命中 (28px); Windows/Linux 走 ImageFont.load_default() (10px),
    导致验证码字看起来比 macOS 小很多。
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        return [
            "/System/Library/Fonts/Supplemental/Courier New.ttf",
            "/System/Library/Fonts/Courier New.ttf",
            "/Library/Fonts/Courier New.ttf",
            "/System/Library/Fonts/Menlo.ttc",
            "/System/Library/Fonts/Monaco.ttf",
        ]
    if system == "Windows":
        return [
            "C:/Windows/Fonts/consola.ttf",       # Consolas (等宽)
            "C:/Windows/Fonts/cour.ttf",          # Courier New
            "C:/Windows/Fonts/courier.ttf",       # Courier New (alt)
            "C:/Windows/Fonts/lucon.ttf",         # Lucida Console
            "C:/Windows/Fonts/arial.ttf",         # Arial (非等宽 fallback)
        ]
    # Linux (Debian/Ubuntu/RHEL/Arch 主流包)
    return [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    ]


def _load_font(size: int = CAPTCHA_FONT_SIZE) -> ImageFont.ImageFont:
    """
    加载跨平台字体：按候选路径依次尝试，失败则用 load_default 兜底。

    兜底字号也按目标 size 给 Pillow 默认字体升档位（10/12/15/20/26 ...）
    虽然不能完美对齐 truetype，但至少不会像之前那样永远是 10px。
    """
    for path in _candidate_font_paths():
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # Pillow load_default 不支持 size 参数; 用 bitmap font 加 anchor 对齐居中
    return ImageFont.load_default()


def _generate_code(length: int = CAPTCHA_LENGTH) -> str:
    """生成随机验证码"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def _generate_image(code: str, width: int = 150, height: int = 50) -> Image.Image:
    """生成验证码图片"""
    # 创建图片
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    font = _load_font(CAPTCHA_FONT_SIZE)

    # 添加干扰线
    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=1)

    # 添加噪点
    for _ in range(100):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(random.randint(150, 255), random.randint(150, 255), random.randint(150, 255)))

    # 绘制文字
    char_width = width // len(code)
    for i, char in enumerate(code):
        x = i * char_width + random.randint(8, 14)
        y = random.randint(4, 10)
        color = (random.randint(30, 120), random.randint(30, 120), random.randint(30, 120))
        draw.text((x, y), char, font=font, fill=color)

    return img


def create_captcha() -> Tuple[str, str]:
    """
    创建验证码

    Returns:
        (captcha_key, base64_image)
    """
    code = _generate_code()
    key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))

    img = _generate_image(code)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    # 存储验证码
    _captcha_store[key] = (code.upper(), time.time() + CAPTCHA_EXPIRE_SECONDS)
    
    print(f"[Captcha] 创建验证码: key={key}, code={code.upper()}")
    print(f"[Captcha] 当前验证码存储: {_captcha_store.keys()}")

    # 清理过期验证码
    _cleanup_expired()

    return key, f"data:image/png;base64,{img_base64}"


def verify_captcha(key: str, code: str) -> bool:
    """
    验证验证码

    Args:
        key: 验证码key
        code: 用户输入的验证码

    Returns:
        是否验证通过
    """
    print(f"[Captcha] 验证请求: key={key}, code={code}")
    print(f"[Captcha] 当前验证码存储: {_captcha_store.keys()}")
    
    if not key or not code:
        print(f"[Captcha] 失败: 缺少key或code")
        return False

    # 不使用pop()，这样验证失败后验证码还可以再次尝试
    stored = _captcha_store.get(key)
    if not stored:
        print(f"[Captcha] 失败: key不存在")
        return False

    stored_code, expire = stored
    print(f"[Captcha] 存储的code: {stored_code}, expire: {expire}, 当前时间: {time.time()}")
    
    if time.time() > expire:
        print(f"[Captcha] 失败: 已过期")
        # 过期了就删除
        _captcha_store.pop(key, None)
        return False

    result = stored_code == code.upper().strip()
    print(f"[Captcha] 验证结果: {result} (存储: {stored_code}, 输入: {code.upper().strip()})")
    
    # 只有验证成功才删除验证码
    if result:
        _captcha_store.pop(key, None)
        print(f"[Captcha] 验证成功，已删除验证码")
    
    return result


def _cleanup_expired():
    """清理过期验证码"""
    now = time.time()
    expired_keys = [k for k, (_, exp) in _captcha_store.items() if now > exp]
    for k in expired_keys:
        del _captcha_store[k]
