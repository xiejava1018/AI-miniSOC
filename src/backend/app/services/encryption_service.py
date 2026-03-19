"""
加密服务
用于敏感配置数据的加密和解密
"""

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet

from app.core.config import settings


class EncryptionService:
    """
    加密服务类

    使用Fernet对称加密（AES-128-CBC + HMAC）保护敏感配置数据

    用法：
        service = EncryptionService()

        # 加密
        encrypted = service.encrypt("sensitive_password")

        # 解密
        decrypted = service.decrypt(encrypted)
    """

    def __init__(self):
        """
        初始化加密服务

        从配置中读取加密密钥，如果不存在则生成新密钥
        """
        self._fernet: Optional[Fernet] = None
        self._init_cipher()

    def _init_cipher(self):
        """
        初始化Fernet加密器

        优先级：
        1. 使用配置中的 ENCRYPTION_KEY
        2. 如果不存在，从 SECRET_KEY 派生
        3. 如果都失败，生成临时密钥（仅用于开发）
        """
        try:
            # 尝试使用配置的加密密钥
            encryption_key = settings.ENCRYPTION_KEY

            if encryption_key:
                # 验证密钥格式（Fernet需要32字节base64编码）
                if not self._is_valid_fernet_key(encryption_key):
                    # 如果不是有效格式，尝试派生
                    encryption_key = self._derive_key_from_secret(encryption_key)
                self._fernet = Fernet(encryption_key)
            else:
                # 从SECRET_KEY派生
                secret_key = settings.SECRET_KEY
                derived_key = self._derive_key_from_secret(secret_key)
                self._fernet = Fernet(derived_key)

        except Exception as e:
            # 如果所有方法都失败，生成临时密钥
            import warnings
            warnings.warn(
                f"Failed to initialize encryption with configured keys: {e}. "
                "Using temporary key (DO NOT USE IN PRODUCTION)"
            )
            temp_key = Fernet.generate_key()
            self._fernet = Fernet(temp_key)

    def _is_valid_fernet_key(self, key: str) -> bool:
        """
        检查密钥是否为有效的Fernet密钥

        Args:
            key: 待检查的密钥

        Returns:
            bool: 是否有效
        """
        try:
            # Fernet密钥是32字节的base64编码
            decoded = base64.urlsafe_b64decode(key.encode())
            return len(decoded) == 32
        except Exception:
            return False

    def _derive_key_from_secret(self, secret: str) -> str:
        """
        从密钥派生Fernet密钥

        Args:
            secret: 原始密钥字符串

        Returns:
            str: Base64编码的Fernet密钥
        """
        # 使用SHA256哈希生成32字节密钥
        key_bytes = hashlib.sha256(secret.encode()).digest()
        # Base64 URL安全编码
        return base64.urlsafe_b64encode(key_bytes).decode()

    def encrypt(self, data: str) -> str:
        """
        加密数据

        Args:
            data: 明文字符串

        Returns:
            str: 加密后的字符串（Base64编码）

        Raises:
            ValueError: 加密失败
        """
        if not data:
            raise ValueError("Cannot encrypt empty data")

        try:
            # Fernet加密返回bytes
            encrypted_bytes = self._fernet.encrypt(data.encode())
            # 转为字符串存储
            return encrypted_bytes.decode()
        except Exception as e:
            raise ValueError(f"Encryption failed: {str(e)}")

    def decrypt(self, encrypted_data: str) -> str:
        """
        解密数据

        Args:
            encrypted_data: 加密的字符串（Base64编码）

        Returns:
            str: 解密后的明文字符串

        Raises:
            ValueError: 解密失败
        """
        if not encrypted_data:
            raise ValueError("Cannot decrypt empty data")

        try:
            # 将字符串转为bytes
            encrypted_bytes = encrypted_data.encode()
            # Fernet解密
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            # 转为字符串返回
            return decrypted_bytes.decode()
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")

    def generate_key(self) -> str:
        """
        生成新的Fernet密钥

        用于初始化系统配置时生成加密密钥

        Returns:
            str: Base64编码的Fernet密钥

        Example:
            key = EncryptionService().generate_key()
            print(f"Generated key: {key}")
            # 将此密钥添加到 .env 文件
            # ENCRYPTION_KEY={key}
        """
        return Fernet.generate_key().decode()

    def is_encrypted(self, data: str) -> bool:
        """
        检查数据是否已加密

        Args:
            data: 待检查的数据

        Returns:
            bool: 是否为加密数据
        """
        if not data:
            return False

        try:
            # 尝试解密，如果成功则认为是加密数据
            self.decrypt(data)
            return True
        except Exception:
            return False

    def encrypt_if_needed(self, data: str, force: bool = False) -> str:
        """
        按需加密数据

        如果数据已加密且不强制重新加密，则直接返回

        Args:
            data: 待加密的数据
            force: 是否强制重新加密

        Returns:
            str: 加密后的数据
        """
        if not force and self.is_encrypted(data):
            return data
        return self.encrypt(data)

    def decrypt_if_needed(self, data: str) -> str:
        """
        按需解密数据

        如果数据未加密，则直接返回原数据

        Args:
            data: 待解密的数据

        Returns:
            str: 解密后的数据或原数据
        """
        try:
            return self.decrypt(data)
        except Exception:
            # 如果解密失败，假设是明文，直接返回
            return data


# 创建全局加密服务实例
encryption_service = EncryptionService()
