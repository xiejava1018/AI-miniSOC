"""
核心安全模块单元测试
"""

import pytest

from app.core.security import (
    verify_password,
    get_password_hash,
    generate_random_password,
    validate_password_strength,
    is_strong_password
)


class TestPasswordHashing:
    """密码哈希测试类"""

    def test_hash_password(self):
        """测试密码哈希"""
        password = "TestPassword123!"
        hashed = get_password_hash(password)

        assert hashed != password
        assert isinstance(hashed, str)
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_verify_password_correct(self):
        """测试验证正确的密码"""
        password = "TestPassword123!"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """测试验证错误的密码"""
        password = "TestPassword123!"
        wrong_password = "WrongPassword123!"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False


class TestPasswordValidation:
    """密码验证测试类"""

    def test_strong_password(self):
        """测试强密码验证"""
        password = "StrongPass123!"
        is_valid, message = validate_password_strength(password)

        assert is_valid
        assert message == ""

    def test_weak_password_too_short(self):
        """测试密码太短"""
        password = "Short1!"
        is_valid, message = validate_password_strength(password)

        assert not is_valid
        assert "长度" in message

    def test_weak_password_no_uppercase(self):
        """测试密码没有大写字母"""
        password = "lowercase123!"
        is_valid, message = validate_password_strength(password)

        assert not is_valid
        assert "大写" in message

    def test_weak_password_no_lowercase(self):
        """测试密码没有小写字母"""
        password = "UPPERCASE123!"
        is_valid, message = validate_password_strength(password)

        assert not is_valid
        assert "小写" in message

    def test_weak_password_no_digit(self):
        """测试密码没有数字"""
        password = "NoDigits!"
        is_valid, message = validate_password_strength(password)

        assert not is_valid
        assert "数字" in message

    def test_weak_password_no_special(self):
        """测试密码没有特殊字符"""
        password = "NoSpecial123"
        is_valid, message = validate_password_strength(password)

        assert not is_valid
        assert "特殊字符" in message

    def test_is_strong_password_helper(self):
        """测试is_strong_password辅助函数"""
        assert is_strong_password("StrongPass123!") is True
        assert is_strong_password("weak") is False


class TestGenerateRandomPassword:
    """随机密码生成测试类"""

    def test_generate_random_password_default_length(self):
        """测试生成默认长度密码"""
        password = generate_random_password()

        assert len(password) == 12
        assert any(c.isupper() for c in password)
        assert any(c.islower() for c in password)
        assert any(c.isdigit() for c in password)

    def test_generate_random_password_custom_length(self):
        """测试生成自定义长度密码"""
        password = generate_random_password(length=20)

        assert len(password) == 20

    def test_generate_random_password_uniqueness(self):
        """测试生成的密码是唯一的"""
        passwords = [generate_random_password() for _ in range(100)]

        assert len(set(passwords)) > 90  # 至少90%是唯一的
