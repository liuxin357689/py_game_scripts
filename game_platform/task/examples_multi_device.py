"""
多设备并行任务执行示例

演示如何在多个模拟器上同时运行相同的任务。
"""

import sys
import os

# 动态计算 game_scripts 路径（本文件在 game_platform/task/ 下）
_GAME_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _GAME_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _GAME_SCRIPTS_DIR)

from game_platform.task import BaseTask, DeviceTaskRegistry
from game_platform.adb.device import ADBDevice
import logging
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


class DemoTask(BaseTask):
    """演示任务：在设备上循环打印消息"""
    
    def __init__(self, device_name: str = "未知"):
        super().__init__(name=f"DemoTask-{device_name}")
        self._device_name = device_name
    
    def setup(self):
        logger.info(f"[{self._device_name}] 任务初始化")
    
    def execute(self):
        counter = 0
        while not self.is_stopped:
            counter += 1
            logger.info(f"[{self._device_name}] 第 {counter} 次循环")
            self.sleep(2)  # 每 2 秒一次
    
    def teardown(self):
        logger.info(f"[{self._device_name}] 任务清理")


def example_1_basic_usage():
    """示例 1：基本用法 - 在两个设备上启动同一任务"""
    print("\n" + "=" * 80)
    print("示例 1：基本用法 - 在两个设备上启动同一任务")
    print("=" * 80)
    
    # 1. 创建设备任务注册表
    registry = DeviceTaskRegistry()
    
    # 2. 为每个设备注册任务
    devices = ["localhost:5555", "localhost:5557"]
    
    for addr in devices:
        task = DemoTask(device_name=addr)
        registry.register_task_for_device(addr, task)
        logger.info(f"已为设备 {addr} 注册任务")
    
    # 3. 在所有设备上启动任务
    logger.info("正在所有设备上启动任务...")
    results = registry.start_task_on_devices("DemoTask-localhost:5555")
    
    for addr, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        logger.info(f"{addr}: {status}")
    
    # 4. 等待一段时间观察
    logger.info("任务运行中，等待 10 秒...")
    time.sleep(10)
    
    # 5. 停止所有设备上的任务
    logger.info("正在停止所有设备上的任务...")
    registry.stop_all_tasks_on_all_devices()
    
    logger.info("示例 1 完成")


def example_2_selective_control():
    """示例 2：选择性控制 - 在不同设备上执行不同操作"""
    print("\n" + "=" * 80)
    print("示例 2：选择性控制 - 在不同设备上执行不同操作")
    print("=" * 80)
    
    registry = DeviceTaskRegistry()
    
    # 注册任务到两个设备
    task1 = DemoTask(device_name="设备A")
    task2 = DemoTask(device_name="设备B")
    
    registry.register_task_for_device("localhost:5555", task1)
    registry.register_task_for_device("localhost:5557", task2)
    
    # 只在设备 A 上启动
    logger.info("仅在设备 A (5555) 上启动任务...")
    registry.start_task_on_devices("DemoTask-设备A", ["localhost:5555"])
    
    time.sleep(5)
    
    # 暂停设备 A，启动设备 B
    logger.info("暂停设备 A，启动设备 B...")
    registry.pause_task_on_devices("DemoTask-设备A", ["localhost:5555"])
    registry.start_task_on_devices("DemoTask-设备B", ["localhost:5557"])
    
    time.sleep(5)
    
    # 恢复设备 A，停止设备 B
    logger.info("恢复设备 A，停止设备 B...")
    registry.resume_task_on_devices("DemoTask-设备A", ["localhost:5555"])
    registry.stop_task_on_devices("DemoTask-设备B", ["localhost:5557"])
    
    time.sleep(5)
    
    # 清理
    registry.stop_all_tasks_on_all_devices()
    logger.info("示例 2 完成")


def example_3_query_status():
    """示例 3：状态查询 - 查看任务在各设备上的状态"""
    print("\n" + "=" * 80)
    print("示例 3：状态查询 - 查看任务在各设备上的状态")
    print("=" * 80)
    
    registry = DeviceTaskRegistry()
    
    # 注册并启动
    task = DemoTask(device_name="测试设备")
    registry.register_task_for_device("localhost:5555", task)
    registry.start_task_on_devices("DemoTask-测试设备")
    
    # 查询状态
    time.sleep(3)
    statuses = registry.get_task_status_across_devices("DemoTask-测试设备")
    
    logger.info("当前任务状态:")
    for addr, status in statuses.items():
        logger.info(f"  {addr}: {status.value}")
    
    # 列出设备
    devices = registry.list_devices_for_task("DemoTask-测试设备")
    logger.info(f"运行此任务的设备: {devices}")
    
    # 清理
    registry.stop_all_tasks_on_all_devices()
    logger.info("示例 3 完成")


if __name__ == "__main__":
    print("多设备并行任务执行示例")
    print("请选择要运行的示例:")
    print("  1. 基本用法 - 在两个设备上启动同一任务")
    print("  2. 选择性控制 - 在不同设备上执行不同操作")
    print("  3. 状态查询 - 查看任务在各设备上的状态")
    print("  0. 运行所有示例")
    
    choice = input("\n请输入选项 (0-3): ").strip()
    
    try:
        if choice == "1":
            example_1_basic_usage()
        elif choice == "2":
            example_2_selective_control()
        elif choice == "3":
            example_3_query_status()
        elif choice == "0":
            example_1_basic_usage()
            time.sleep(2)
            example_2_selective_control()
            time.sleep(2)
            example_3_query_status()
        else:
            print("无效选项")
    except KeyboardInterrupt:
        logger.info("\n用户中断")
    except Exception as e:
        logger.error(f"执行异常: {e}", exc_info=True)
    
    print("\n示例运行结束")
