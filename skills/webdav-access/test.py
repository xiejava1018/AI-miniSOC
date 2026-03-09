#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-miniSOC WebDAV访问技能测试脚本
"""

import sys
import os

# 添加技能目录到Python路径
skill_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, skill_dir)

from main import WebDAVClient, handle_webdav_command
from uploader import WebDAVUploader


def test_basic_operations():
    """测试基本操作"""
    print("=" * 60)
    print("AI-miniSOC WebDAV访问技能测试")
    print("=" * 60)
    print()

    # 测试1: 初始化客户端
    print("🔧 测试1: 初始化WebDAV客户端")
    print("-" * 60)
    client = WebDAVClient()
    print(f"✅ 客户端初始化成功")
    print(f"   服务器: {client.server}")
    print(f"   用户名: {client.username}")
    print()

    # 测试2: 列出目录
    print("📁 测试2: 列出共享目录内容")
    print("-" * 60)
    contents = client.list_contents()
    if contents:
        print(f"✅ 找到 {len(contents)} 个项目:")
        for item in contents[:10]:  # 只显示前10个
            print(f"   - {item}")
        if len(contents) > 10:
            print(f"   ... 还有 {len(contents) - 10} 个项目")
    else:
        print("⚠️  目录为空或无法访问")
    print()

    # 测试3: 测试上传器
    print("📤 测试3: 测试WebDAV上传器")
    print("-" * 60)
    uploader = WebDAVUploader()
    success, message = uploader.test_connection()
    if success:
        print(f"✅ {message}")
    else:
        print(f"⚠️  {message}")
        print("   提示: 请检查 config.json 中的配置")
    print()

    # 测试4: 自然语言命令
    print("💬 测试4: 自然语言命令处理")
    print("-" * 60)
    test_commands = [
        "列出NAS共享目录内容",
        "列出NAS目录 reports/",
    ]

    for cmd in test_commands:
        print(f"命令: {cmd}")
        result = handle_webdav_command(cmd)
        print(f"结果: {result[:100]}...")
        print()

    print("=" * 60)
    print("✅ 测试完成")
    print("=" * 60)


def test_file_operations():
    """测试文件操作（需要有效的WebDAV配置）"""
    print()
    print("=" * 60)
    print("文件操作测试")
    print("=" * 60)
    print()

    import tempfile

    # 创建测试文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("AI-miniSOC WebDAV测试文件\n")
        f.write(f"测试时间: {__import__('datetime').datetime.now()}\n")
        test_file = f.name

    print(f"📝 创建测试文件: {test_file}")

    # 测试上传
    client = WebDAVClient()
    remote_path = "test/aisoc_test_file.txt"

    print(f"📤 上传到: {remote_path}")
    success, message = client.upload_file(test_file, remote_path)
    if success:
        print(f"✅ {message}")

        # 测试列出
        print(f"📁 列出测试目录:")
        contents = client.list_contents("test/")
        for item in contents:
            print(f"   - {item}")

        # 测试下载
        download_file = test_file + ".downloaded"
        print(f"📥 下载到: {download_file}")
        success, message = client.download_file(remote_path, download_file)
        if success:
            print(f"✅ {message}")

        # 清理
        os.unlink(download_file)

        # 测试删除
        print(f"🗑️  删除远程文件")
        success, message = client.delete_file(remote_path)
        if success:
            print(f"✅ {message}")

    else:
        print(f"❌ {message}")

    # 清理测试文件
    os.unlink(test_file)

    print()
    print("=" * 60)
    print("✅ 文件操作测试完成")
    print("=" * 60)


def main():
    """主测试函数"""
    import argparse

    parser = argparse.ArgumentParser(description="WebDAV技能测试")
    parser.add_argument("--full", action="store_true",
                       help="运行完整测试（包括文件操作）")

    args = parser.parse_args()

    try:
        test_basic_operations()

        if args.full:
            test_file_operations()

    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
