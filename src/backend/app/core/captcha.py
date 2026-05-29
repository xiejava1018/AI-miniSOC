"""
验证码模块

提供图形验证码生成和验证功能。
使用内存存储（带过期时间），生产环境建议替换为Redis。
"""

import base64
import io
import random
import string
import time
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


# 内存验证码存储: {key: (code, expire_timestamp)}
_captcha_store: dict[str, Tuple[str, float]] = {}
CAPTCHA_EXPIRE_SECONDS = 300  # 5分钟过期
CAPTCHA_LENGTH = 4


def _generate_code(length: int = CAPTCHA_LENGTH) -> str:
    """生成随机验证码"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def _generate_image(code: str, width: int = 120, height: int = 40) -> Image.Image:
    """生成验证码图片"""
    # 创建图片
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 尝试使用等宽字体
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Courier New.ttf", 28)
    except Exception:
        font = ImageFont.load_default()

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
        x = i * char_width + random.randint(5, 10)
        y = random.randint(2, 8)
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
    if not key or not code:
        return False

    stored = _captcha_store.pop(key, None)
    if not stored:
        return False

    stored_code, expire = stored
    if time.time() > expire:
        return False

    return stored_code == code.upper().strip()


def _cleanup_expired():
    """清理过期验证码"""
    now = time.time()
    expired_keys = [k for k, (_, exp) in _captcha_store.items() if now > exp]
    for k in expired_keys:
        del _captcha_store[k]
