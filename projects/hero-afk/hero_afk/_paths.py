"""
路径工具模块

解决开发环境下 game_platform 包的路径发现问题。
通过 __file__ 动态计算路径，不依赖任何硬编码绝对路径。

用法:
    # 在需要使用 game_platform 的模块顶部，import 此模块即可
    from hero_afk._paths import setup_platform_path
    setup_platform_path()

    # 获取项目内资源路径
    from hero_afk._paths import get_templates_dir, get_config_path
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

# ---- 路径常量（基于 __file__ 动态计算） ----

# 本文件位置: hero_afk/_paths.py
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))          # hero_afk/
_PROJECT_DIR = os.path.dirname(_PACKAGE_DIR)                       # projects/hero-afk/
_PROJECTS_DIR = os.path.dirname(_PROJECT_DIR)                      # projects/
_GAME_SCRIPTS_DIR = os.path.dirname(_PROJECTS_DIR)                 # game_scripts/


def setup_platform_path():
    """将 game_scripts 目录加入 sys.path（如果 game_platform 尚未可导入）

    查找优先级:
        1. game_platform 已安装（pip install -e .）→ 无需处理
        2. 环境变量 GAME_SCRIPTS_HOME → 使用指定路径
        3. 通过 __file__ 相对计算 → 自动定位
    """
    # 已可导入，直接跳过
    if _is_importable("game_platform"):
        return

    # 环境变量覆盖
    env_path = os.environ.get("GAME_SCRIPTS_HOME")
    if env_path and os.path.isdir(env_path):
        _add_path(env_path)
        if _is_importable("game_platform"):
            return

    # __file__ 相对计算
    if os.path.isdir(os.path.join(_GAME_SCRIPTS_DIR, "game_platform")):
        _add_path(_GAME_SCRIPTS_DIR)
        if _is_importable("game_platform"):
            return

    logger.warning(
        "无法定位 game_platform 包。请通过以下任一方式解决:\n"
        "  1. pip install -e <game_platform路径>\n"
        "  2. 设置环境变量 GAME_SCRIPTS_HOME=<game_scripts目录>"
    )


def get_templates_dir() -> str:
    """获取模板图片目录的绝对路径"""
    return os.path.join(_PACKAGE_DIR, "templates")


def get_config_path(filename: str = "config.yaml") -> str:
    """获取项目配置文件的绝对路径

    Args:
        filename: 配置文件名
    """
    return os.path.join(_PROJECT_DIR, filename)


def get_project_dir() -> str:
    """获取项目根目录的绝对路径"""
    return _PROJECT_DIR


# ---- 内部工具 ----

def _add_path(path: str):
    """安全添加路径到 sys.path"""
    if path not in sys.path:
        sys.path.insert(0, path)
        logger.debug(f"已添加平台路径: {path}")


def _is_importable(module_name: str) -> bool:
    """检查模块是否可导入"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False
