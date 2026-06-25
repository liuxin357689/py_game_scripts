"""
任务注册中心 — 统一管理所有任务的定义、配置和工厂方法

职责：
    1. 从 task_definitions.json 加载任务定义
    2. 提供任务信息查询接口（优先级、冷却、依赖等）
    3. 管理任务工厂方法（创建任务实例）
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

# 默认配置文件路径（hero_afk/config/task_definitions.json）
_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "config",
)
_DEFAULT_DEFINITIONS_PATH = os.path.join(_CONFIG_DIR, "task_definitions.json")


@dataclass
class TaskDefinition:
    """任务定义"""
    id: str                                    # 唯一标识
    name: str                                  # 显示名称
    priority: int                              # 优先级（值越小越高）
    cooldown: int                              # 冷却时间（秒）
    max_failures: int = 3                      # 最大连续失败次数
    dependencies: list[str] = field(default_factory=list)
    retry_policy: dict = field(default_factory=lambda: {
        "max_attempts": 3,
        "backoff_seconds": 30,
        "retry_on_error": True,
    })


class TaskRegistry:
    """任务注册中心"""

    def __init__(self, config_path: str | None = None):
        self._definitions: dict[str, TaskDefinition] = {}
        self._factories: dict[str, Callable] = {}
        self._config_path = config_path or _DEFAULT_DEFINITIONS_PATH

    # ---- 定义管理 ----

    def load_from_json(self, path: str | None = None):
        """从 JSON 文件加载任务定义

        Args:
            path: JSON 文件路径，默认使用 config/task_definitions.json
        """
        path = path or self._config_path
        path = os.path.normpath(path)

        if not os.path.exists(path):
            raise FileNotFoundError(f"任务定义文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for task_id, config in data.items():
            defn = TaskDefinition(
                id=task_id,
                name=config["name"],
                priority=config["priority"],
                cooldown=config["cooldown"],
                max_failures=config.get("max_failures", 3),
                dependencies=config.get("dependencies", []),
                retry_policy=config.get("retry_policy", {}),
            )
            self._definitions[task_id] = defn

        logger.info(
            f"[TaskRegistry] 从 {path} 加载了 "
            f"{len(self._definitions)} 个任务定义"
        )

    def register(self, definition: TaskDefinition | dict):
        """注册单个任务定义

        Args:
            definition: TaskDefinition 实例或 dict（自动转换）
        """
        if isinstance(definition, dict):
            task_id = definition["id"]
            defn = TaskDefinition(
                id=task_id,
                name=definition["name"],
                priority=definition["priority"],
                cooldown=definition["cooldown"],
                max_failures=definition.get("max_failures", 3),
                dependencies=definition.get("dependencies", []),
                retry_policy=definition.get("retry_policy", {}),
            )
        else:
            task_id = definition.id
            defn = definition
        self._definitions[task_id] = defn

    # ---- 信息查询 ----

    def get_definition(self, task_id: str) -> TaskDefinition:
        """获取任务定义

        Raises:
            KeyError: 任务未注册
        """
        if task_id not in self._definitions:
            raise KeyError(f"任务未注册: {task_id}")
        return self._definitions[task_id]

    def get_priority(self, task_id: str) -> int:
        """获取任务优先级"""
        return self._definitions.get(task_id, TaskDefinition(
            id=task_id, name=task_id, priority=50, cooldown=0
        )).priority

    def get_cooldown(self, task_id: str) -> int:
        """获取任务冷却时间（秒）"""
        return self._definitions.get(task_id, TaskDefinition(
            id=task_id, name=task_id, priority=50, cooldown=0
        )).cooldown

    def get_dependencies(self, task_id: str) -> list[str]:
        """获取任务依赖列表"""
        defn = self._definitions.get(task_id)
        return defn.dependencies if defn else []

    def get_retry_policy(self, task_id: str) -> dict:
        """获取任务重试策略"""
        defn = self._definitions.get(task_id)
        return defn.retry_policy if defn else {}

    def list_tasks(self) -> list[TaskDefinition]:
        """列出所有已注册的任务定义"""
        return list(self._definitions.values())

    # ---- 工厂管理 ----

    def register_factory(self, task_id: str, factory: Callable):
        """注册任务工厂方法

        Args:
            task_id: 任务标识
            factory: 无参可调用对象，返回 FrameTask 实例
        """
        self._factories[task_id] = factory
        logger.info(f"[TaskRegistry] 注册工厂: {task_id}")

    def create_task(self, task_id: str):
        """通过工厂创建任务实例

        Raises:
            KeyError: 工厂未注册
        """
        if task_id not in self._factories:
            raise KeyError(f"任务工厂未注册: {task_id}")
        return self._factories[task_id]()
