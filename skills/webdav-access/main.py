#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-miniSOC WebDAV访问技能 - main.py
"""

import os
import sys
import re
import json
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from typing import Tuple, List, Optional

# 从配置文件读取WebDAV服务器配置
def load_config():
    """加载配置文件"""
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get("config", {})
    except Exception as e:
        print(f"[警告] 无法加载配置文件: {e}")
        return {}

config = load_config()
WEBDAV_SERVER = config.get("server", "https://example.com/webdav")
WEBDAV_USER = config.get("username", "your_username")
WEBDAV_PASS = config.get("password", "your_password")


class WebDAVClient:
    """WebDAV客户端类"""

    def __init__(self, server: str = None, username: str = None, password: str = None):
        """
        初始化WebDAV客户端

        Args:
            server: WebDAV服务器地址（可选，默认使用配置文件）
            username: 用户名（可选，默认使用配置文件）
            password: 密码（可选，默认使用配置文件）
        """
        self.server = server or WEBDAV_SERVER
        self.username = username or WEBDAV_USER
        self.password = password or WEBDAV_PASS

        # 验证配置
        if self.server == "https://example.com/webdav":
            print("[警告] 使用默认配置，请修改 config.json 设置你的WebDAV服务器信息")

    def list_contents(self, remote_path: str = "") -> List[str]:
        """
        列出目录内容

        Args:
            remote_path: 远程目录路径（相对路径）

        Returns:
            文件和目录列表
        """
        try:
            # 确保server URL以斜杠结尾，然后拼接路径
            base_url = self.server if self.server.endswith('/') else self.server + '/'
            target_url = base_url + remote_path.lstrip('/')
            headers = {"Depth": "1"}

            response = requests.request(
                "PROPFIND",
                target_url,
                headers=headers,
                auth=(self.username, self.password),
                timeout=10,
                verify=False
            )

            if response.status_code == 207:
                root = ET.fromstring(response.text)
                contents = []

                for response_elem in root.findall("{DAV:}response"):
                    href = response_elem.find("{DAV:}href")
                    if href is not None and href.text:
                        item = href.text
                        # 过滤掉当前目录和父目录
                        if item and item not in ["/", target_url]:
                            relative_path = item.replace(self.server, "").lstrip('/')
                            if relative_path and relative_path != remote_path:
                                contents.append(relative_path)

                return sorted(contents)
            elif response.status_code == 404:
                return []
            else:
                print(f"[错误] 列出目录失败，HTTP状态码: {response.status_code}")
                return []

        except requests.exceptions.Timeout:
            print("[错误] 连接超时")
            return []
        except requests.exceptions.ConnectionError:
            print("[错误] 无法连接到WebDAV服务器")
            return []
        except Exception as e:
            print(f"[错误] 列出目录时发生异常: {e}")
            return []

    def upload_file(self, local_path: str, remote_path: str) -> Tuple[bool, str]:
        """
        上传文件

        Args:
            local_path: 本地文件路径
            remote_path: 远程文件路径

        Returns:
            (成功标志, 消息)
        """
        try:
            if not os.path.exists(local_path):
                return False, "文件不存在"

            if not os.path.isfile(local_path):
                return False, f"{local_path} 不是有效的文件"

            # 确保server URL以斜杠结尾，然后拼接路径
            base_url = self.server if self.server.endswith('/') else self.server + '/'
            target_url = base_url + remote_path.lstrip('/')

            with open(local_path, 'rb') as f:
                response = requests.put(
                    target_url,
                    data=f,
                    auth=(self.username, self.password),
                    timeout=60,
                    verify=False
                )

                if response.status_code in [201, 204]:
                    return True, "文件上传成功"
                else:
                    return False, f"服务器响应错误: HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            return False, "上传超时"
        except requests.exceptions.ConnectionError:
            return False, "无法连接到WebDAV服务器"
        except Exception as e:
            return False, f"上传失败: {str(e)}"

    def download_file(self, remote_path: str, local_path: str) -> Tuple[bool, str]:
        """
        下载文件

        Args:
            remote_path: 远程文件路径
            local_path: 本地保存路径

        Returns:
            (成功标志, 消息)
        """
        try:
            # 确保server URL以斜杠结尾，然后拼接路径
            base_url = self.server if self.server.endswith('/') else self.server + '/'
            target_url = base_url + remote_path.lstrip('/')

            response = requests.get(
                target_url,
                auth=(self.username, self.password),
                timeout=60,
                verify=False,
                stream=True
            )

            if response.status_code == 200:
                local_dir = os.path.dirname(local_path)
                if local_dir and not os.path.exists(local_dir):
                    os.makedirs(local_dir, exist_ok=True)

                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                file_size = os.path.getsize(local_path)
                return True, f"文件下载成功 (大小: {file_size} 字节)"
            elif response.status_code == 404:
                return False, "文件不存在"
            else:
                return False, f"服务器响应错误: HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            return False, "下载超时"
        except requests.exceptions.ConnectionError:
            return False, "无法连接到WebDAV服务器"
        except Exception as e:
            return False, f"下载失败: {str(e)}"

    def delete_file(self, remote_path: str) -> Tuple[bool, str]:
        """
        删除文件

        Args:
            remote_path: 远程文件路径

        Returns:
            (成功标志, 消息)
        """
        try:
            # 确保server URL以斜杠结尾，然后拼接路径
            base_url = self.server if self.server.endswith('/') else self.server + '/'
            target_url = base_url + remote_path.lstrip('/')

            response = requests.delete(
                target_url,
                auth=(self.username, self.password),
                timeout=10,
                verify=False
            )

            if response.status_code in [204, 200]:
                return True, "删除成功"
            elif response.status_code == 404:
                return False, "文件不存在"
            else:
                return False, f"服务器响应错误: HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            return False, "操作超时"
        except requests.exceptions.ConnectionError:
            return False, "无法连接到WebDAV服务器"
        except Exception as e:
            return False, f"删除失败: {str(e)}"

    def create_directory(self, remote_path: str) -> Tuple[bool, str]:
        """
        创建目录

        Args:
            remote_path: 远程目录路径

        Returns:
            (成功标志, 消息)
        """
        try:
            # 确保server URL以斜杠结尾，然后拼接路径
            base_url = self.server if self.server.endswith('/') else self.server + '/'
            target_url = base_url + remote_path.lstrip('/')

            response = requests.request(
                "MKCOL",
                target_url,
                auth=(self.username, self.password),
                timeout=10,
                verify=False
            )

            if response.status_code in [201, 204]:
                return True, "目录创建成功"
            elif response.status_code == 405:
                return False, "目录已存在"
            else:
                return False, f"服务器响应错误: HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            return False, "操作超时"
        except requests.exceptions.ConnectionError:
            return False, "无法连接到WebDAV服务器"
        except Exception as e:
            return False, f"创建目录失败: {str(e)}"

    def file_exists(self, remote_path: str) -> bool:
        """
        检查文件是否存在

        Args:
            remote_path: 远程文件路径

        Returns:
            文件是否存在
        """
        try:
            # 确保server URL以斜杠结尾，然后拼接路径
            base_url = self.server if self.server.endswith('/') else self.server + '/'
            target_url = base_url + remote_path.lstrip('/')

            response = requests.request(
                "PROPFIND",
                target_url,
                headers={"Depth": "0"},
                auth=(self.username, self.password),
                timeout=10,
                verify=False
            )

            return response.status_code in [200, 207]

        except Exception:
            return False


# 全局客户端实例
client = WebDAVClient()


def handle_webdav_command(command: str) -> str:
    """
    处理WebDAV命令（自然语言接口）

    Args:
        command: 自然语言命令

    Returns:
        操作结果
    """
    # 定义命令模式
    patterns = {
        # 列出目录
        r"列出NAS共享目录内容|列出NAS目录内容|列出NAS共享目录|列出共享目录内容":
            lambda cmd, m: handle_list(cmd, None),

        r"列出NAS目录\s+(.+)|列出NAS文件夹\s+(.+)":
            handle_list,

        # 上传文件
        r"上传\s+(.+)\s+到NAS\s+(.+)":
            handle_upload,

        # 下载文件
        r"下载NAS[文件项]*\s+(.+)\s+到\s+(.+)":
            handle_download,

        # 删除文件
        r"删除NAS[文件项]*\s+(.+)":
            handle_delete,

        # 创建目录
        r"(?:在NAS上创建|创建NAS)\s*(?:目录|文件夹)\s*(.+)|创建NAS文件夹\s*(.+)":
            handle_create_dir,
    }

    # 匹配命令
    for pattern, handler in patterns.items():
        match = re.search(pattern, command)
        if match:
            return handler(command, match)

    # 默认帮助信息
    if "NAS" in command or "WebDAV" in command or "webdav" in command.lower():
        return handle_help()

    return "❌ 无法识别的WebDAV命令。请使用：列出NAS目录、上传文件、下载NAS文件、删除NAS文件、创建NAS目录等操作。"


def handle_list(command: str, match: Optional[re.Match]) -> str:
    """处理列出目录操作"""
    if match:
        remote_path = "".join(filter(None, match.groups())).strip()
        if remote_path and remote_path != "None":
            contents = client.list_contents(remote_path)
            if contents:
                result = f"📁 NAS目录 '{remote_path}' 的内容：\n"
                for item in contents:
                    item_name = item.split('/')[-1]  # 只显示文件名
                    result += f"   - {item_name}\n"
                result += f"\n总计: {len(contents)} 项"
                return result
            else:
                return f"📂 NAS目录 '{remote_path}' 为空或无法访问"

    # 列出根目录
    contents = client.list_contents()
    if contents:
        result = "📁 NAS共享目录的内容：\n"
        for item in contents:
            item_name = item.split('/')[-1]
            result += f"   - {item_name}\n"
        result += f"\n总计: {len(contents)} 项"
        return result
    else:
        return "📂 NAS共享目录为空或无法访问"


def handle_upload(command: str, match: re.Match) -> str:
    """处理文件上传操作"""
    local_path = match.group(1).strip().strip('"\'')
    remote_path = match.group(2).strip().strip('"\'')

    # 检查本地文件
    if not os.path.exists(local_path):
        return f"❌ 本地文件不存在: {local_path}"

    # 如果远程路径是目录，则使用原文件名
    if remote_path.endswith('/') or '.' not in remote_path.split('/')[-1]:
        filename = os.path.basename(local_path)
        remote_path = f"{remote_path.rstrip('/')}/{filename}"

    success, message = client.upload_file(local_path, remote_path)

    if success:
        file_size = os.path.getsize(local_path)
        size_mb = file_size / (1024 * 1024)
        return f"✅ 文件上传成功\n" \
               f"   本地: {local_path}\n" \
               f"   远程: {remote_path}\n" \
               f"   大小: {size_mb:.2f} MB"
    else:
        return f"❌ 上传失败: {message}"


def handle_download(command: str, match: re.Match) -> str:
    """处理文件下载操作"""
    remote_path = match.group(1).strip().strip('"\'')
    local_path = match.group(2).strip().strip('"\'')

    # 如果本地路径是目录，则使用原文件名
    if local_path.endswith('/') or os.path.isdir(local_path):
        filename = os.path.basename(remote_path)
        local_path = f"{local_path.rstrip('/')}/{filename}"

    success, message = client.download_file(remote_path, local_path)

    if success:
        return f"✅ 文件下载成功\n" \
               f"   远程: {remote_path}\n" \
               f"   本地: {local_path}\n" \
               f"   {message}"
    else:
        return f"❌ 下载失败: {message}"


def handle_delete(command: str, match: re.Match) -> str:
    """处理文件删除操作"""
    remote_path = match.group(1).strip().strip('"\'')

    # 清理路径中的特殊词
    for word in ['文件', '目录', '文件夹']:
        remote_path = remote_path.replace(word, '')

    remote_path = remote_path.strip()

    success, message = client.delete_file(remote_path)

    if success:
        return f"✅ NAS文件删除成功\n   路径: {remote_path}"
    else:
        return f"❌ 删除失败: {message}"


def handle_create_dir(command: str, match: re.Match) -> str:
    """处理创建目录操作"""
    dir_path = "".join(filter(None, match.groups())).strip()

    if not dir_path:
        return "❌ 请指定要创建的目录名称"

    success, message = client.create_directory(dir_path)

    if success:
        return f"✅ NAS目录创建成功\n   路径: {dir_path}"
    else:
        return f"❌ 创建目录失败: {message}"


def handle_help() -> str:
    """显示帮助信息"""
    return (
        "📋 AI-miniSOC WebDAV访问技能使用说明：\n\n"
        "🔹 列出目录：\n"
        "   • 列出NAS共享目录内容\n"
        "   • 列出NAS目录 reports/\n\n"
        "🔹 上传文件：\n"
        "   • 上传 /tmp/file.pdf 到NAS reports/file.pdf\n"
        "   • 上传 /data/log.json 到NAS logs/\n\n"
        "🔹 下载文件：\n"
        "   • 下载NAS文件 reports/file.pdf 到 /tmp/\n"
        "   • 下载NAS logs/data.json 到 /var/aisoc/\n\n"
        "🔹 删除文件：\n"
        "   • 删除NAS文件 reports/old.pdf\n\n"
        "🔹 创建目录：\n"
        "   • 在NAS上创建目录 reports/2026/\n"
        "   • 创建NAS文件夹 threat-analysis/\n\n"
        "💡 提示：请先在 config.json 中配置你的WebDAV服务器信息"
    )


def main():
    """命令行入口"""
    if len(sys.argv) > 1:
        command = " ".join(sys.argv[1:])
        print(handle_webdav_command(command))
    else:
        print(handle_help())


if __name__ == "__main__":
    main()
