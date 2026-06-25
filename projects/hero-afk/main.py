"""
Hero AFK - 程序入口

启动流程:
    1. 加载项目配置（config.yaml）
    2. 初始化日志
    3. 注册 Hero AFK 专属任务
    4. 启动 PyQt6 应用
    5. 显示 HeroAfkWindow 主窗口
"""

import sys

# 动态设置平台路径（替代硬编码 sys.path.insert）
from hero_afk._paths import setup_platform_path
setup_platform_path()

from PyQt6.QtWidgets import QApplication
from hero_afk.gui.app_window import HeroAfkWindow


def main():
    """Hero AFK 应用主入口"""
    # 创建 QApplication
    app = QApplication(sys.argv)
    
    # 设置应用样式（可选）
    app.setStyle('Fusion')
    
    # 创建并显示主窗口
    window = HeroAfkWindow()
    window.show()
    
    # 进入事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
