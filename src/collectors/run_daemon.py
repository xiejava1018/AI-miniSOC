#!/usr/bin/env python3
"""
采集器守护进程管理脚本
提供生产级可靠性：自动重启、健康检查、日志轮转、优雅关闭
"""

import os
import sys
import signal
import subprocess
import time
import logging
from pathlib import Path
from datetime import datetime
from threading import Thread

# 配置
SCRIPT_DIR = Path(__file__).parent
LOG_FILE = "/tmp/collector-daemon.log"
PID_FILE = Path("/tmp/collector-daemon.pid")
CHECK_INTERVAL = 60  # 健康检查间隔（秒）
MAX_RESTART_DELAY = 30  # 最大重启延迟（秒）
MAX_CONSECUTIVE_FAILURES = 3  # 最大连续失败次数

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 采集器配置
COLLECTORS = {
    "tplink": {
        "script": SCRIPT_DIR / "tplink" / "run_collector.py",
        "log": "/tmp/tplink-collector.log",
        "env": {"ROUTER_PASSWORD": "mnbvvbnm123qaz"},  # 从 .env 加载
    },
    "wazuh": {
        "script": SCRIPT_DIR / "wazuh" / "run_collector.py",
        "log": "/tmp/wazuh-collector.log",
        "env": {},
    },
}


class CollectorProcess:
    """单个采集器进程管理"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.script = config["script"]
        self.log_file = config["log"]
        self.env = config.get("env", {})
        self.process = None
        self.start_time = None
        self.failure_count = 0
        self.running = False

    def start(self):
        """启动采集器"""
        if self.process and self.process.poll() is None:
            logger.info(f"[{self.name}] 进程已在运行")
            return True

        env = os.environ.copy()
        env.update(self.env)

        try:
            # 启动进程
            self.process = subprocess.Popen(
                [sys.executable, str(self.script)],
                env=env,
                stdout=open(self.log_file, "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self.start_time = time.time()
            self.running = True
            logger.info(f"[{self.name}] 启动成功, PID={self.process.pid}")
            return True
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False

    def stop(self, timeout=10):
        """停止采集器"""
        if not self.process:
            return

        try:
            # 发送 SIGTERM
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # 强制杀死
                self.process.kill()
                self.process.wait()
            logger.info(f"[{self.name}] 已停止")
        except Exception as e:
            logger.error(f"[{self.name}] 停止失败: {e}")
        finally:
            self.process = None
            self.running = False

    def is_alive(self) -> bool:
        """检查进程是否存活"""
        if not self.process:
            return False
        return self.process.poll() is None

    def check_health(self) -> bool:
        """健康检查 - 检查日志是否有新数据"""
        if not self.is_alive():
            return False

        try:
            # 检查日志文件最近修改时间
            mtime = os.path.getmtime(self.log_file)
            age = time.time() - mtime
            # 如果日志超过 10 分钟没更新，认为可能卡住了
            if age > 600:
                logger.warning(f"[{self.name}] 日志超过 {age/60:.0f} 分钟未更新")
                return False
            return True
        except Exception as e:
            logger.error(f"[{self.name}] 健康检查失败: {e}")
            return False


class CollectorDaemon:
    """采集器守护进程"""

    def __init__(self):
        self.collectors = {name: CollectorProcess(name, config)
                      for name, config in COLLECTORS.items()}
        self.running = False
        self.health_check_thread = None

    def signal_handler(self, signum, frame):
        """信号处理"""
        logger.info(f"收到信号 {signum}, 准备关闭...")
        self.running = False
        for collector in self.collectors.values():
            collector.stop()

    def start_all(self):
        """启动所有采集器"""
        for name, collector in self.collectors.items():
            collector.start()
            time.sleep(2)  # 避免同时启动

    def stop_all(self):
        """停止所有采集器"""
        for collector in self.collectors.values():
            collector.stop()

    def health_check_loop(self):
        """健康检查循环"""
        while self.running:
            time.sleep(CHECK_INTERVAL)
            if not self.running:
                break

            for name, collector in self.collectors.items():
                if not collector.is_alive():
                    logger.warning(f"[{name}] 进程已退出, 尝试重启...")
                    collector.failure_count += 1

                    if collector.failure_count >= MAX_CONSECUTIVE_FAILURES:
                        logger.error(f"[{name}] 连续 {MAX_CONSECUTIVE_FAILURES} 次失败, 停止重启")
                        continue

                    # 指数退避
                    delay = min(MAX_RESTART_DELAY, 2 ** collector.failure_count)
                    time.sleep(delay)
                    collector.start()
                elif not collector.check_health():
                    logger.warning(f"[{name}] 健康检查失败, 重启...")
                    collector.stop()
                    time.sleep(5)
                    collector.start()

    def run(self):
        """运行守护进程"""
        # 注册信号处理
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        self.running = True

        # 写入 PID 文件
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

        logger.info("=" * 60)
        logger.info("采集器守护进程启动")
        logger.info(f"  监控: {list(self.collectors.keys())}")
        logger.info(f"  健康检查: 每 {CHECK_INTERVAL} 秒")
        logger.info(f"  PID: {os.getpid()}")
        logger.info("=" * 60)

        # 启动所有采集器
        self.start_all()

        # 启动健康检查线程
        self.health_check_thread = Thread(target=self.health_check_loop, daemon=True)
        self.health_check_thread.start()

        # 主循环 - 等待信号
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("守护进程退出...")
            self.stop_all()
            # 删除 PID 文件
            if PID_FILE.exists():
                PID_FILE.unlink()


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="采集器守护进程")
    parser.add_argument("command", choices=["start", "stop", "restart", "status"],
                     help="命令")
    parser.add_argument("--name", help="指定采集器名称")

    args = parser.parse_args()

    daemon = CollectorDaemon()

    if args.command == "start":
        # 检查是否已运行
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                os.kill(pid, 0)
                print(f"守护进程已在运行, PID={pid}")
                sys.exit(1)
            except (FileNotFoundError, ProcessLookupError, ValueError):
                PID_FILE.unlink()

        daemon.run()

    elif args.command == "stop":
        if not PID_FILE.exists():
            print("守护进程未运行")
            sys.exit(1)

        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"已发送停止信号, PID={pid}")
            time.sleep(3)
            print("守护进程已停止")
        except Exception as e:
            print(f"停止失败: {e}")
            sys.exit(1)

    elif args.command == "restart":
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                print(f"已发送停止信号, PID={pid}")
                time.sleep(3)
            except (FileNotFoundError, ProcessLookupError, ValueError):
                pass

        time.sleep(2)
        daemon.run()

    elif args.command == "status":
        if not PID_FILE.exists():
            print("守护进程未运行")
            sys.exit(1)

        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            print(f"守护进程运行中, PID={pid}")
        except (FileNotFoundError, ProcessLookupError, ValueError):
            print("守护进程未运行（PID文件残留）")
            sys.exit(1)


if __name__ == "__main__":
    main()