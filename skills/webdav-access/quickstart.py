#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-miniSOC WebDAV技能快速开始示例
"""

import sys
import os

# 添加技能目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import WebDAVClient, handle_webdav_command


def print_section(title: str):
    """打印分隔符和标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def quick_start():
    """快速开始示例"""
    print_section("🚀 AI-miniSOC WebDAV技能快速开始")

    # 1. 检查配置
    print("📋 步骤1: 检查配置")
    print("-" * 60)
    client = WebDAVClient()
    print(f"✅ 服务器: {client.server}")
    print(f"✅ 用户名: {client.username}")
    print()

    # 2. 列出目录
    print("📁 步骤2: 列出NAS共享目录")
    print("-" * 60)
    result = handle_webdav_command("列出NAS共享目录内容")
    print(result)
    print()

    # 3. 显示使用示例
    print("💡 步骤3: 使用示例")
    print("-" * 60)
    examples = [
        ("列出目录", "列出NAS目录 reports/"),
        ("上传文件", "上传 /tmp/file.pdf 到NAS reports/"),
        ("下载文件", "下载NAS文件 reports/file.pdf 到 /tmp/"),
        ("删除文件", "删除NAS文件 reports/old.pdf"),
        ("创建目录", "在NAS上创建目录 reports/2026/"),
    ]

    for title, cmd in examples:
        print(f"\n{title}:")
        print(f"   命令: {cmd}")

    print()

    # 4. 创建测试目录
    print("🔧 步骤4: 创建测试目录")
    print("-" * 60)
    result = handle_webdav_command("在NAS上创建目录 aisoc-test/")
    print(result)
    print()

    # 5. 显示Python API示例
    print_section("🐍 Python API使用示例")

    print("""
# 示例1: 创建客户端
from skills.webdav_access.main import WebDAVClient
client = WebDAVClient()

# 示例2: 列出目录
contents = client.list_contents("reports/")
for item in contents:
    print(f"- {item}")

# 示例3: 上传文件
success, message = client.upload_file(
    "/tmp/report.pdf",
    "reports/2026/report.pdf"
)
if success:
    print(f"✅ {message}")

# 示例4: 下载文件
success, message = client.download_file(
    "reports/2026/report.pdf",
    "/tmp/downloaded.pdf"
)

# 示例5: 检查文件是否存在
if client.file_exists("reports/2026/report.pdf"):
    print("文件存在")
""")

    # 6. 显示集成示例
    print_section("🔗 与AI-miniSOC集成示例")

    print("""
# 在报告生成脚本中使用
from skills.webdav_access.main import WebDAVClient

def generate_and_upload_report():
    # 生成报告
    report_path = "/tmp/security_report.pdf"
    # ... 生成报告的代码 ...

    # 上传到NAS
    client = WebDAVClient()
    success, message = client.upload_file(
        report_path,
        "reports/daily/report.pdf"
    )

    return success

# 在日志查询脚本中使用
def archive_query_results(query, results):
    import json
    import tempfile

    # 保存查询结果
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(results, f)
        temp_file = f.name

    # 上传到NAS
    client = WebDAVClient()
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    client.upload_file(
        temp_file,
        f"loki-queries/query_{timestamp}.json"
    )

    # 清理临时文件
    os.unlink(temp_file)
""")

    print_section("✅ 准备完成！")

    print("""
🎉 恭喜！你的WebDAV技能已准备就绪。

📚 更多信息请查看:
   - 技能说明: skills/webdav-access/SKILL.md
   - 使用文档: skills/webdav-access/README.md
   - 配置文件: skills/webdav-access/config.json

🧪 测试技能:
   python skills/webdav-access/test.py
   python skills/webdav-access/test.py --full

⚙️  配置WebDAV服务器:
   编辑 skills/webdav-access/config.json
   设置你的NAS服务器地址、用户名和密码
""")


if __name__ == "__main__":
    try:
        quick_start()
    except KeyboardInterrupt:
        print("\n\n⚠️  示例被用户中断")
    except Exception as e:
        print(f"\n\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
