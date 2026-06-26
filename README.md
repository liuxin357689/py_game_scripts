# Hero AFK

> **免责声明**：本项目仅供学习交流使用，不可用于任何商业或盈利目的。使用本工具产生的一切后果由使用者自行承担，与项目作者无关。请遵守相关游戏的服务条款。

英雄没有闪挂机自动化脚本 — 基于 ADB + 图像识别的游戏辅助工具，支持模拟器自动操作、任务状态机、实时日志监控。

---

## 一、game_platform 是什么

`game_platform`（游戏脚本通用平台）是本项目的共享基础设施库，为所有游戏自动化项目提供通用的底层能力。

### 包含的功能模块

| 模块 | 功能 |
|------|------|
| `adb` | ADB 设备连接与控制：连接/断开、截图、点击、滑动、按键事件 |
| `gui` | PyQt6 GUI 基类：主窗口、控制面板、设备管理器、日志查看器、设备配置对话框、验证对话框 |
| `screenshot` | 截图管理：全图/区域截图、自动保存、时间戳命名 |
| `task` | 任务引擎：帧任务基类（FrameTask）、截图服务（ScreenshotService）、优先级仲裁、动作执行 |
| `ocr` | 图像识别：模板匹配（彩色/灰度）、OCR 文字识别（PaddleOCR）、颜色检测 |

### 架构设计

```
截图服务（ScreenshotService）
    │
    ├── 管理 ADB 设备连接
    ├── 截图线程循环：截图 → 推送给所有激活的 FrameTask
    ├── 收集动作请求 → 按优先级仲裁
    └── 执行动作 + 人类行为模拟延迟

FrameTask（帧任务，抽象基类）
    │
    ├── setup() / teardown() — 生命周期
    ├── on_frame(screen) — 每帧分析，返回 Action 或 None
    ├── annotate_detection(screen, action) — 标注检测结果（用于测试模式）
    └── is_active / priority — 激活状态和优先级
```

各游戏项目（如 hero_afk）只需实现具体的 FrameTask 子类，不需要关心设备连接和截图细节。

---

## 二、已完成的功能

### 2.1 Hero AFK 游戏任务

| 任务 | 功能 | 技术 |
|------|------|------|
| **自动关闭通知** | 检测黄色感叹号通知并自动关闭 | 坐标 + 像素点 |
| **暗能秘境** | 自动刷秘境关卡，检测战斗结果（胜/负统一流程），连续检测新关卡 | 模板匹配 + 像素点 + 状态机 |
| **自动替换装备** | 全图扫描红色「替换」按钮并点击 | 模板匹配 |
| **混沌牧场** | 自动刷牧场关卡，检测战斗结果并关闭结算 | 模板匹配 + 坐标像素点 + 状态机 |
| **自动领取活动奖励** | 扫描活动列表中带角标的图标，进入详情页领取，返回后重新扫描直到全部领完 | 模板匹配 + 角标检测（NMS去重）+ 状态机 |

### 2.2 公共组件

- **BattleResultDetector** — 战斗结果检测器（胜/负模板匹配），所有战斗任务共用
- **测试模式对话框** — 手动截取画面推送任务，标注检测结果并保存截图
- **多日志选项卡** — 实时显示运行日志，支持多设备日志分离

### 2.3 game_platform 通用组件

- **设备扫描器** — 自动探测常见模拟器端口段（MuMu、雷电、夜神、逍遥、蓝叠等）
- **设备管理器** — 多设备连接管理、验证流程、黑名单、配置持久化
- **OCR 识别器** — 模板匹配 + PaddleOCR 文字识别
- **截图管理器** — ADB 截图、自动保存到用户目录

---

## 三、技术栈

### 核心依赖

| 技术 | 用途 |
|------|------|
| **Python >= 3.10** | 运行环境 |
| **PyQt6 >= 6.4.0** | GUI 图形界面 |
| **opencv-python >= 4.8.0** | 图像处理、模板匹配 |
| **numpy >= 1.24.0** | 数值计算 |
| **adb-shell == 0.4.4** | ADB 设备控制 |
| **Pillow >= 10.0.0** | 图像读取 |
| **PyYAML >= 6.0** | 配置文件 |
| **paddlepaddle >= 2.6** | OCR 引擎（CPU 模式） |
| **paddleocr >= 2.8** | OCR 文字识别 |

### 开发工具

| 工具 | 用途 |
|------|------|
| **pytest >= 7.4.0** | 单元测试 |
| **pyinstaller >= 6.0.0** | 打包成 exe |
| **ruff >= 0.1.0** | 代码检查 |
| **black >= 23.0.0** | 代码格式化 |

---

## 四、项目结构

```
game_scripts/
├── game_platform/              # 通用平台库
│   ├── adb/                   # ADB 设备控制
│   │   ├── device.py          #   ADBDevice 连接类
│   │   └── scanner.py         #   模拟器端口扫描
│   ├── gui/                   # PyQt6 GUI 基类
│   │   ├── main_window.py     #   主窗口基类
│   │   ├── control_panel.py    #   任务控制面板
│   │   ├── device_manager.py   #   设备管理
│   │   ├── log_viewer.py      #   日志查看器
│   │   └── *.py               #   各种对话框
│   ├── screenshot/            # 截图管理
│   ├── task/                  # 任务引擎
│   │   ├── frame_task.py      #   帧任务基类
│   │   ├── screenshot_service.py # 截图服务核心
│   │   └── *.py
│   └── ocr/                   # 图像识别
│       └── recognizer.py      #   模板匹配 + OCR
│
└── projects/
    └── hero-afk/             # Hero AFK 游戏自动化
        ├── main.py            #   程序入口
        ├── hero_afk/
        │   ├── gui/
        │   │   ├── app_window.py       #   主窗口
        │   │   └── test_mode_dialog.py #   测试模式
        │   ├── tasks/                   # 具体任务实现
        │   │   ├── auto_close_notify.py     # 自动关闭通知
        │   │   ├── auto_dark_realm.py       # 暗能秘境
        │   │   ├── auto_replace_equipment.py # 自动替换装备
        │   │   ├── auto_chaos_ranch.py      # 混沌牧场
        │   │   └── auto_activity_reward.py  # 活动奖励
        │   └── core/                # 核心工具
        │       ├── battle_detector.py    # 战斗结果检测
        │       ├── pixel_checker.py      # 像素检测
        │       ├── screen_pilot.py       # 屏幕导航
        │       └── *.py
        └── tests/                  # 测试套件
```

---

## 五、快速开始

### 环境要求

- Python >= 3.10
- ADB（Android Debug Bridge）已安装且在 PATH 中
- 安卓模拟器（推荐 MuMu 12）或已 root 的安卓设备

常用模拟器 ADB 端口：MuMu 12 默认 `16384`，雷电 `5555`，夜神 `62001`。

### 安装依赖

```bash
cd D:\game_scripts
pip install -r requirements.txt
```

### 启动应用

```bash
cd projects\hero-afk
python main.py
```

启动后在 GUI 中连接模拟器设备，选择任务并启动。

### 运行测试

```bash
cd projects\hero-afk
pytest
```

---

## 六、许可证

本项目基于 [MIT License](projects/hero-afk/LICENSE) 开源。
