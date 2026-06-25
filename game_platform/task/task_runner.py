"""
任务执行器

职责:
    - 在独立线程中运行任务
    - 管理任务线程的启停
    - 处理任务异常和状态回调
"""


class TaskRunner:
    """任务执行器，负责在后台线程中运行 BaseTask"""

    def __init__(self):
        """初始化任务执行器"""
        # TODO: 初始化线程池或线程管理
        pass

    def run(self, task):
        """在后台线程中执行任务

        Args:
            task: BaseTask 实例
        """
        # TODO: 启动线程，调用 task.start()
        pass

    def stop(self):
        """停止当前执行的任务"""
        # TODO: 调用 task.stop() 并等待线程结束
        pass

    def is_running(self) -> bool:
        """检查是否有任务正在运行

        Returns:
            是否正在运行
        """
        # TODO: 返回运行状态
        pass
