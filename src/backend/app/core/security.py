"""
核心安全模块
提供密码哈希、配置加密解密、密码强度验证等功能
"""

from passlib.context import CryptContext
from cryptography.fernet import Fernet
import re

from app.core.config import settings


# 密码哈希上下文（bcrypt算法，work factor 12）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Fernet加密器（用于敏感配置加密）
# 使用环境变量中的ENCRYPTION_KEY，如果不存在则使用SECRET_KEY
try:
    _encryption_key = settings.ENCRYPTION_KEY
    if not _encryption_key:
        # 如果没有单独的加密密钥，使用SECRET_KEY派生
        # Fernet需要32字节的base64编码密钥
        import base64
        import hashlib
        key_bytes = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        _encryption_key = base64.urlsafe_b64encode(key_bytes).decode()
    _fernet = Fernet(_encryption_key)
except Exception as e:
    # 如果密钥配置有问题，创建一个临时的（仅用于开发）
    import warnings
    warnings.warn(f"Encryption key configuration error: {e}. Using temporary key.")
    _fernet = Fernet(Fernet.generate_key())


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码

    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码

    Returns:
        bool: 密码是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    对密码进行哈希

    Args:
        password: 明文密码

    Returns:
        str: 哈希后的密码（bcrypt，work factor 12）
    """
    return pwd_context.hash(password)


def encrypt_config(value: str) -> str:
    """
    加密敏感配置值

    Args:
        value: 明文配置值

    Returns:
        str: 加密后的配置值（base64编码）

    Raises:
        Exception: 加密失败时抛出异常
    """
    try:
        # Fernet加密返回bytes，转为字符串存储
        encrypted = _fernet.encrypt(value.encode())
        return encrypted.decode()
    except Exception as e:
        raise ValueError(f"配置加密失败: {str(e)}")


def decrypt_config(encrypted_value: str) -> str:
    """
    解密配置值

    Args:
        encrypted_value: 加密的配置值

    Returns:
        str: 解密后的明文配置值

    Raises:
        Exception: 解密失败时抛出异常
    """
    try:
        # 将字符串转为bytes，然后解密
        decrypted = _fernet.decrypt(encrypted_value.encode())
        return decrypted.decode()
    except Exception as e:
        raise ValueError(f"配置解密失败: {str(e)}")


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    验证密码强度

    密码要求：
    - 最小长度8个字符
    - 包含大写字母
    - 包含小写字母
    - 包含数字
    - 包含特殊字符

    Args:
        password: 待验证的密码

    Returns:
        tuple[bool, str]: (是否通过验证, 错误消息)
    """
    if len(password) < 8:
        return False, "密码长度至少为8个字符"

    if not re.search(r'[A-Z]', password):
        return False, "密码必须包含至少一个大写字母"

    if not re.search(r'[a-z]', password):
        return False, "密码必须包含至少一个小写字母"

    if not re.search(r'\d', password):
        return False, "密码必须包含至少一个数字"

    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', password):
        return False, "密码必须包含至少一个特殊字符"

    return True, ""


def is_strong_password(password: str) -> bool:
    """
    快速检查密码是否满足强度要求

    Args:
        password: 待验证的密码

    Returns:
        bool: 密码是否足够强
    """
    is_valid, _ = validate_password_strength(password)
    return is_valid


# Alias for consistency (spec uses 'hash_password' name)
hash_password = get_password_hash
