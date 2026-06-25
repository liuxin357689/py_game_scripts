"""
任务配置面板基类

职责:
    - 任务参数配置（UI 表单）
    - 任务选择和启用/禁用
    - 配置导入/导出
    - 配置持久化

各项目通过继承来定制自己的任务配置面板
"""


class TaskConfig:
    """任务配置面板基类，提供可视化的任务参数配置界面"""

    def __init__(self, parent=None):
        """初始化任务配置面板

        Args:
            parent: 父窗口
        """
        # TODO: 创建任务列表（复选框）
        # TODO: 创建参数配置表单
        # TODO: 添加导入/导出按钮
        # TODO: 绑定配置变更事件
        pass

    def load_config(self, config: dict):
        """从配置字典加载任务参数到 UI

        Args:
            config: 配置字典
        """
        # TODO: 将配置值填充到表单控件
        pass

    def save_config(self) -> dict:
        """从 UI 收集配置并保存

        Returns:
            配置字典
        """
        # TODO: 从表单控件读取值，组装为配置字典
        pass

    def export_config(self, file_path: str):
        """导出配置到文件

        Args:
            file_path: 导出文件路径
        """
        # TODO: 将配置写入 YAML 文件
        pass

    def import_config(self, file_path: str):
        """从文件导入配置

        Args:
            file_path: 配置文件路径
        """
        # TODO: 读取 YAML 文件并加载到 UI
        pass
