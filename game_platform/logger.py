"""
日志模块

职责:
    - 统一日志格式和输出
    - 支持文件日志和控制台日志
    - 提供不同级别的日志记录（DEBUG, INFO, WARNING, ERROR）
"""

import logging


def get_logger(name: str = "game-scripts") -> logging.Logger:
    """获取日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        配置好的 Logger 实例
    """
    # TODO: 配置日志格式、输出目标
    logger = logging.getLogger(name)
    return logger
