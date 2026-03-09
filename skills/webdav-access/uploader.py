#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-miniSOC WebDAV文件上传器
提供高级文件上传功能和批量操作
"""

import os
import sys
import subprocess
import tempfile
from typing import Tuple, List, Optional
from pathlib import Path


class WebDAVUploader:
    """
    WebDAV文件上传器

    支持多种上传方式：
    - 使用requests库上传
    - 使用curl命令上传（更快，支持断点续传）
    - 批量上传
    - 进度显示
    """

    def __init__(
        self,
        url: str = "https://fnos.ishareread.com:5006/aisoc_sharedoc",
        username: str = "xiejava",
        password: str = ""
    ):
        """
        初始化上传器

        Args:
            url: WebDAV服务器URL
            username: 用户名
            password: 密码
        """
        self.url = url.rstrip("/")
        self.username = username
        self.password = password

        # 尝试从配置文件加载
        if not password:
            self._load_config()

    def _load_config(self):
        """从配置文件加载凭证"""
        try:
            config_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "config.json"
            )
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                config_data = config.get("config", {})
                self.url = config_data.get("server", self.url)
                self.username = config_data.get("username", self.username)
                self.password = config_data.get("password", self.password)
        except Exception:
            pass

    def upload_with_curl(
        self,
        local_path: str,
        remote_path: str,
        timeout: int = 300
    ) -> Tuple[bool, str]:
        """
        使用curl命令上传文件（推荐）

        Args:
            local_path: 本地文件路径
            remote_path: 远程文件路径
            timeout: 超时时间（秒）

        Returns:
            (成功标志, 消息)
        """
        try:
            if not os.path.exists(local_path):
                return False, f"本地文件不存在: {local_path}"

            if not os.path.isfile(local_path):
                return False, f"{local_path} 不是有效的文件"

            # 构建远程URL
            remote_url = f"{self.url}/{remote_path.lstrip('/')}"

            # 使用curl命令上传
            command = [
                "curl",
                "-T", local_path,
                "-u", f"{self.username}:{self.password}",
                "--connect-timeout", "10",
                "--max-time", str(timeout),
                "--insecure",
                "-s",  # 静默模式
                "-o", "/dev/null",  # 输出到/dev/null
                "-w", "%{http_code}",  # 只输出HTTP状态码
                remote_url
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout + 10
            )

            status_code = result.stdout.strip()

            if status_code in ["201", "204"]:
                file_size = os.path.getsize(local_path)
                size_mb = file_size / (1024 * 1024)
                return True, f"上传成功 (大小: {size_mb:.2f} MB)"
            elif status_code == "404":
                return False, "远程目录不存在"
            elif status_code == "401":
                return False, "认证失败，请检查用户名和密码"
            elif status_code == "403":
                return False, "权限不足"
            else:
                return False, f"上传失败，HTTP状态码: {status_code}"

        except subprocess.TimeoutExpired:
            return False, "上传超时"
        except FileNotFoundError:
            return False, "curl命令未找到，请安装curl"
        except Exception as e:
            return False, f"上传失败: {str(e)}"

    def upload_with_requests(
        self,
        local_path: str,
        remote_path: str,
        timeout: int = 300
    ) -> Tuple[bool, str]:
        """
        使用requests库上传文件

        Args:
            local_path: 本地文件路径
            remote_path: 远程文件路径
            timeout: 超时时间（秒）

        Returns:
            (成功标志, 消息)
        """
        try:
            import requests

            if not os.path.exists(local_path):
                return False, f"本地文件不存在: {local_path}"

            target_url = f"{self.url}/{remote_path.lstrip('/')}"

            with open(local_path, 'rb') as f:
                response = requests.put(
                    target_url,
                    data=f,
                    auth=(self.username, self.password),
                    timeout=timeout,
                    verify=False
                )

                if response.status_code in [201, 204]:
                    file_size = os.path.getsize(local_path)
                    size_mb = file_size / (1024 * 1024)
                    return True, f"上传成功 (大小: {size_mb:.2f} MB)"
                else:
                    return False, f"上传失败，HTTP状态码: {response.status_code}"

        except ImportError:
            return False, "requests库未安装"
        except Exception as e:
            return False, f"上传失败: {str(e)}"

    def batch_upload(
        self,
        files: List[Tuple[str, str]],
        method: str = "curl"
    ) -> List[Tuple[str, bool, str]]:
        """
        批量上传文件

        Args:
            files: 文件列表 [(local_path, remote_path), ...]
            method: 上传方法 ("curl" 或 "requests")

        Returns:
            [(remote_path, 成功标志, 消息), ...]
        """
        results = []

        for local_path, remote_path in files:
            if method == "curl":
                success, message = self.upload_with_curl(local_path, remote_path)
            else:
                success, message = self.upload_with_requests(local_path, remote_path)

            results.append((remote_path, success, message))

        return results

    def upload_directory(
        self,
        local_dir: str,
        remote_dir: str,
        pattern: str = "*",
        method: str = "curl"
    ) -> Tuple[int, int, List[str]]:
        """
        上传整个目录

        Args:
            local_dir: 本地目录路径
            remote_dir: 远程目录路径
            pattern: 文件匹配模式
            method: 上传方法

        Returns:
            (成功数, 失败数, 错误消息列表)
        """
        import glob

        success_count = 0
        fail_count = 0
        errors = []

        # 递归查找所有文件
        local_path = Path(local_dir)
        files = list(local_path.rglob(pattern))

        for file_path in files:
            if file_path.is_file():
                # 计算相对路径
                relative_path = file_path.relative_to(local_path)
                remote_path = f"{remote_dir.rstrip('/')}/{relative_path}"

                if method == "curl":
                    success, message = self.upload_with_curl(
                        str(file_path),
                        remote_path
                    )
                else:
                    success, message = self.upload_with_requests(
                        str(file_path),
                        remote_path
                    )

                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    errors.append(f"{file_path}: {message}")

        return success_count, fail_count, errors

    def test_connection(self) -> Tuple[bool, str]:
        """
        测试WebDAV连接

        Returns:
            (成功标志, 消息)
        """
        try:
            # 创建临时测试文件
            test_file = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
            test_file.write(b"AI-miniSOC WebDAV connection test")
            test_file.close()

            test_path = f".connection_test_{os.getpid()}.txt"

            # 尝试上传
            success, message = self.upload_with_curl(test_file.name, test_path)

            if success:
                # 上传成功，删除测试文件
                self._delete_file(test_path)
                os.unlink(test_file.name)
                return True, "连接测试成功"
            else:
                os.unlink(test_file.name)
                return False, f"连接测试失败: {message}"

        except Exception as e:
            return False, f"连接测试异常: {str(e)}"

    def _delete_file(self, remote_path: str) -> bool:
        """删除远程文件（内部使用）"""
        try:
            command = [
                "curl",
                "-X", "DELETE",
                "-u", f"{self.username}:{self.password}",
                "--insecure",
                "-s",
                f"{self.url}/{remote_path.lstrip('/')}"
            ]
            subprocess.run(command, capture_output=True, timeout=10)
            return True
        except Exception:
            return False


def main():
    """命令行测试入口"""
    import argparse

    parser = argparse.ArgumentParser(description="AI-miniSOC WebDAV上传器")
    parser.add_argument("local_path", help="本地文件路径")
    parser.add_argument("remote_path", help="远程文件路径")
    parser.add_argument("--method", choices=["curl", "requests"],
                       default="curl", help="上传方法")
    parser.add_argument("--test", action="store_true",
                       help="测试连接")

    args = parser.parse_args()

    uploader = WebDAVUploader()

    if args.test:
        print("🧪 测试WebDAV连接...")
        success, message = uploader.test_connection()
        if success:
            print(f"✅ {message}")
        else:
            print(f"❌ {message}")
        return

    print(f"📤 上传文件: {args.local_path}")
    print(f"   目标: {args.remote_path}")
    print(f"   方法: {args.method}")
    print()

    if args.method == "curl":
        success, message = uploader.upload_with_curl(
            args.local_path,
            args.remote_path
        )
    else:
        success, message = uploader.upload_with_requests(
            args.local_path,
            args.remote_path
        )

    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")


if __name__ == "__main__":
    main()
