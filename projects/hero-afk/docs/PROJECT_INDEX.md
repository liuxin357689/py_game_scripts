# Game Scripts Platform - 工程索引

> 版本: 0.1.0 | 生成时间: 2026-06-13 | Python >= 3.10

---

## 1. 项目概述

本项目是一个**安卓模拟器游戏脚本自动化平台**，基于 Python 构建，提供从设备连接、图像识别到任务调度的完整链路。核心设计思路是"平台 + 项目"两层架构：`game_platform` 提供通用基础能力，`projects/` 下的各项目继承平台能力实现具体游戏脚本。

**技术栈**: PyQt6 (GUI) + adb-shell (设备控制) + OpenCV (图像识别) + 多线程 (并行任务)

---

## 2. 目录结构

```
D:\game_scripts/
├── game_platform/              # 通用平台层（所有项目共享）
│   ├── adb/                    #   ADB 设备控制模块
│   │   ├── device.py           #     ADBDevice - 设备连接与操作
│   │   └── scanner.py          #     scan_emulators - 模拟器扫描与发现
│   ├── ocr/                    #   图像识别模块
│   │   └── recognizer.py       #     Recognizer - 模板匹配与颜色检测
│   ├── task/                   #   任务引擎模块
│   │   ├── base_task.py        #     BaseTask - 任务基类与生命周期
│   │   ├── task_manager.py     #     TaskManager - 单设备任务管理
│   │   ├── device_task_registry.py  #  DeviceTaskRegistry - 多设备任务注册表
│   │   ├── task_runner.py      #     TaskRunner - 任务执行器（骨架）
│   │   ├── examples_multi_device.py # 多设备 API 使用示例
│   │   └── MULTI_DEVICE_GUIDE.md    # 多设备功能完整文档
│   ├── gui/                    #   PyQt6 GUI 框架
│   │   ├── main_window.py      #     MainWindow - 主窗口基类
│   │   ├── device_manager.py   #     DeviceManager + DeviceManagerDialog
│   │   ├── control_panel.py    #     ControlPanel - 脚本控制面板基类
│   │   ├── multi_device_task_panel.py # MultiDeviceTaskPanel - 多设备任务面板
│   │   ├── log_viewer.py       #     LogViewer / MultiDeviceLogViewer
│   │   ├── settings_dialog.py  #     SettingsDialog - 设备设置对话框
│   │   ├── device_config.py    #     DeviceConfigManager - 设备配置持久化
│   │   ├── verification_dialog.py    # VerificationDialog - 设备验证对话框
│   │   ├── batch_verification_dialog.py # BatchVerificationDialog - 批量验证
│   │   └── task_config.py      #     TaskConfig - 任务配置面板基类
│   ├── tests/                  #   平台单元测试
│   │   ├── test_adb.py
│   │   ├── test_config.py
│   │   ├── test_gui.py
│   │   └── test_task.py
│   ├── config.py               #   Config - 全局配置管理（骨架）
│   ├── logger.py               #   get_logger - 日志模块
│   ├── __init__.py             #   包入口，版本号
│   └── pyproject.toml          #   平台包元数据与依赖声明
│
├── projects/                   # 项目层（各游戏的具体实现）
│   └── hero-afk/               #   Hero AFK（英雄挂机）项目
│       ├── main.py             #     程序入口
│       ├── config.yaml         #     项目配置文件
│       ├── build.spec          #     PyInstaller 打包配置
│       ├── pyproject.toml      #     项目包元数据
│       ├── hero_afk/
│       │   ├── gui/
│       │   │   └── app_window.py  #   HeroAfkWindow - 项目主窗口
│       │   ├── tasks/
│       │   │   ├── realtime_multi_template_click_task.py  # 实时多模板点击任务
│       │   │   ├── auto_battle.py     # 自动战斗（骨架）
│       │   │   └── auto_collect.py    # 自动领取（骨架）
│       │   └── templates/      #     模板图片资源（PNG/JPG）
│       └── tests/
│           └── test_tasks.py
│
├── examples/                   # 独立示例脚本
│   └── multi_device_parallel_demo.py  # 多设备并行执行演示
│
├── docker/                     # Docker 开发环境
│   ├── docker-compose.dev.yml
│   └── Dockerfile.dev
│
├── platform-tools/             # Android ADB 工具（Windows 二进制）
│   └── platform-tools/
│       ├── adb.exe
│       └── ...
│
├── requirements.txt            # 全局依赖（Docker/开发用）
├── requirements_en.txt         # 英文版依赖说明
├── MULTI_DEVICE_README.md      # 多设备功能说明文档
└── .gitignore
```

---

## 3. 模块详解

### 3.1 ADB 设备控制 (`game_platform/adb/`)

负责与安卓模拟器/设备的所有交互。

**`device.py` - ADBDevice 类**

| 方法 | 说明 |
|------|------|
| `connect()` | TCP 模式连接 ADB 设备，使用 RSA 密钥认证 |
| `disconnect()` | 断开 ADB 连接 |
| `is_connected()` | 通过轻量 shell 命令验证连接状态 |
| `tap(x, y)` | 模拟屏幕点击 |
| `swipe(x1, y1, x2, y2, duration)` | 模拟屏幕滑动 |
| `key_event(keycode)` | 发送按键事件（HOME=3, BACK=4） |
| `screenshot(save_path)` | 截取屏幕，返回 PNG 字节流 |
| `tap_human_like(x, y, jitter, delay_min, delay_max)` | 模拟人类点击：随机偏移 + 随机延时 |
| `find_and_tap(template_path, threshold, ...)` | 截图 -> 模板匹配 -> 人类点击（含调试标注） |
| `find_and_tap_region(template_path, region_ratio, ...)` | 裁剪区域后模板匹配，提升速度 |

**`scanner.py` - 模拟器扫描**

| 函数/类 | 说明 |
|---------|------|
| `EmulatorInfo` | 数据类，存储模拟器信息（host/port/model/brand/resolution/android_version 等） |
| `scan_emulators(host, adb_server_port, extra_ports, timeout)` | 扫描本地所有安卓模拟器（ADB Server 查询 + 端口探测 + 去重） |
| `_query_adb_server()` | 通过 ADB Server 协议 (port 5037) 查询已知设备 |
| `_probe_port()` | 单端口探测：TCP 连接 -> ADB 连接 -> 获取设备属性 |
| `_probe_ports(host, ports, max_workers)` | 并发多端口探测（ThreadPoolExecutor，默认 20 线程） |
| `_deduplicate_emulators()` | 同一模拟器的多端口去重（按 model+brand+resolution 分组） |
| `_generate_device_name()` | 根据品牌/型号生成友好名称（识别雷电/夜神/MuMu/逍遥/蓝叠） |

支持的模拟器端口：标准 5555-5587、雷电、夜神 (62001/62025/62050)、MuMu (7555/16384+)、逍遥 (21503+)、蓝叠。

---

### 3.2 图像识别 (`game_platform/ocr/`)

**`recognizer.py` - Recognizer 类**

| 方法 | 说明 |
|------|------|
| `find_template(screenshot, template_path, threshold, region)` | 彩色模板匹配，返回 (x, y, w, h) 或 None |
| `find_all_templates(screenshot, template_path, threshold, overlap_threshold)` | 查找所有匹配位置，带去重 |
| `find_template_grayscale(screen_gray, template_path, threshold)` | 灰度模板匹配（更快，适合 UI 按钮） |
| `detect_color(screenshot, x, y)` | 检测指定坐标 RGB 颜色 |
| `recognize_text(screenshot, region)` | OCR 文字识别（TODO，待集成引擎） |
| `_load_image(image_data)` | 统一图片加载（bytes/ndarray/文件路径） |
| `_load_template(template_path)` | 带 TTL 缓存的彩色模板加载（默认 30 分钟过期） |
| `_load_grayscale_template(template_path)` | 带 TTL 缓存的灰度模板加载，专供灰度匹配使用 |
| `clear_cache()` | 手动清除所有模板缓存（彩色 + 灰度两套独立缓存） |

核心算法：`cv2.matchTemplate` + `TM_CCOEFF_NORMED`，支持区域限制和灰度加速。内部维护彩色 `_templates_cache` 和灰度 `_grayscale_templates_cache` 两套独立缓存。

---

### 3.3 任务引擎 (`game_platform/task/`)

**`base_task.py` - BaseTask 抽象基类**

任务生命周期: `setup() -> execute() -> teardown()`

| 方法/属性 | 说明 |
|-----------|------|
| `setup()` [抽象] | 任务初始化，加载资源 |
| `execute()` [抽象] | 任务主逻辑，子类实现 |
| `teardown()` [抽象] | 任务清理，释放资源 |
| `start()` | 在后台 daemon 线程中运行 setup->execute->teardown |
| `stop()` | 设置停止标志，唤醒暂停线程 |
| `pause()` / `resume()` | 通过 Event 暂停/恢复任务 |
| `sleep(seconds)` | 可中断睡眠，响应暂停和停止请求 |
| `is_stopped` | 停止标志属性 |
| `get_status()` | 线程安全获取 TaskStatus 枚举 |

TaskStatus 枚举: `IDLE | RUNNING | PAUSED | STOPPED | ERROR`

**`task_manager.py` - TaskManager 类**

| 方法 | 说明 |
|------|------|
| `register(task, config)` | 注册任务实例 |
| `unregister(task_name)` | 注销任务（运行中会自动停止） |
| `start_task(task_name)` | 启动指定任务 |
| `stop_task(task_name)` / `pause_task` / `resume_task` | 控制指定任务 |
| `stop_all()` | 停止所有运行中任务 |
| `enable_task` / `disable_task` | 启用/禁用任务 |
| `get_task_status(task_name)` | 查询任务状态 |

**`device_task_registry.py` - DeviceTaskRegistry 类**

| 方法 | 说明 |
|------|------|
| `get_or_create(device_address)` | 获取或创建设备对应的 TaskManager |
| `register_task_for_device(device_address, task, config)` | 为设备注册任务 |
| `unregister_task_for_device(device_address, task_name)` | 从指定设备注销任务 |
| `start_task_on_devices(task_name, device_addresses)` | 批量启动任务，返回 {addr: bool} |
| `stop_task_on_devices(task_name, device_addresses)` | 批量停止任务 |
| `pause_task_on_devices` / `resume_task_on_devices` | 批量暂停/恢复 |
| `get_task_status_across_devices(task_name)` | 跨设备查询任务状态 |
| `stop_all_tasks_on_device(device_address)` | 停止某设备上的所有任务 |
| `stop_all_tasks_on_all_devices()` | 全局停止所有设备的所有任务 |
| `remove_device(device_address)` | 移除设备及其所有任务 |
| `list_devices_for_task(task_name)` | 列出运行某任务的所有设备 |
| `list_tasks_for_device(device_address)` | 列出某设备上的所有任务 |
| `all_devices` / `all_task_names` | 属性查询 |

**`task_runner.py` - TaskRunner 类** (骨架，待实现)

---

### 3.4 GUI 框架 (`game_platform/gui/`)

所有 GUI 组件基于 PyQt6 构建，使用信号槽机制实现线程安全通信。

| 文件 | 核心类 | 说明 |
|------|--------|------|
| `main_window.py` | `MainWindow(QMainWindow)` | 主窗口基类：菜单栏、工具栏、状态栏、设备名称信号、自动连接上次设备、多设备面板集成 |
| `device_manager.py` | `DeviceManager(QObject)` | 设备连接管理器：多设备连接、活跃设备切换、黑名单、验证缓存。发射 `device_connected`/`device_disconnected`/`active_device_changed` 信号 |
| `device_manager.py` | `DeviceManagerDialog(QDialog)` | 设备管理 UI：扫描设备、连接/断开、选择活跃设备、验证流程 |
| `control_panel.py` | `ControlPanel(QWidget)` | 脚本控制面板基类：启动/停止/暂停、任务进度、快速操作 |
| `multi_device_task_panel.py` | `MultiDeviceTaskPanel(QWidget)` | 多设备任务控制面板：设备列表、任务分配、批量启停、实时状态 |
| `log_viewer.py` | `LogHandler(logging.Handler)` | 自定义日志处理器，转发日志到 Qt 信号 |
| `log_viewer.py` | `LogViewer` / `MultiDeviceLogViewer` | 实时日志查看器：搜索、导出、多设备标签页 |
| `settings_dialog.py` | `SettingsDialog(QDialog)` | 设备设置：黑名单管理、验证缓存、导入导出 |
| `device_config.py` | `DeviceConfigManager` | 设备配置持久化：`~/.game_scripts/device_config.json`，线程安全读写、自动备份 |
| `device_config.py` | `VerifiedDeviceInfo` | 已验证设备信息数据类 |
| `verification_dialog.py` | `VerificationDialog` | 单设备验证对话框 |
| `batch_verification_dialog.py` | `BatchVerificationDialog` | 批量设备验证对话框 |
| `task_config.py` | `TaskConfig` | 任务配置面板基类 |

---

### 3.5 配置与日志

| 文件 | 说明 |
|------|------|
| `config.py` | Config 类（骨架）：加载 config.yaml，支持嵌套键访问和热更新 |
| `logger.py` | `get_logger(name)` 工厂函数，返回配置好的 Logger 实例 |

---

### 3.6 Hero AFK 项目 (`projects/hero-afk/`)

| 文件 | 说明 |
|------|------|
| `main.py` | 入口：创建 QApplication -> HeroAfkWindow -> exec |
| `config.yaml` | 项目配置：ADB 连接、日志级别/文件、任务参数（auto_battle/auto_collect）、GUI 主题 |
| `hero_afk/gui/app_window.py` | `HeroAfkWindow(MainWindow)` - 继承平台主窗口，注册专属任务，集成控制面板+多设备日志查看器 |
| `hero_afk/tasks/realtime_multi_template_click_task.py` | `RealTimeMultiTemplateClickTask(BaseTask)` - 核心任务：单次截图+灰度并行匹配+人类模拟点击 |
| `hero_afk/tasks/auto_battle.py` | AutoBattle（骨架） |
| `hero_afk/tasks/auto_collect.py` | AutoCollect（骨架） |
| `hero_afk/templates/` | 模板图片资源目录（`#` 前缀文件自动排除） |
| `build.spec` | PyInstaller 打包配置 |

**RealTimeMultiTemplateClickTask 关键参数**:
- `template_folder`: 模板图片文件夹
- `threshold`: 匹配阈值（默认 0.7）
- `scan_interval`: 扫描间隔（默认 0.1 秒）
- `click_all_matches`: True=点击所有匹配 / False=只点第一个
- `device_manager`: 可选，传入后自动获取活跃设备
- 性能优化：单次截图 -> 灰度转换 -> ThreadPoolExecutor 并行匹配

---

### 3.7 其他

| 文件/目录 | 说明 |
|-----------|------|
| `examples/multi_device_parallel_demo.py` | 多设备并行执行的独立演示脚本 |
| `docker/` | Docker 开发环境（docker-compose + Dockerfile），用于 IDEA Docker Interpreter |
| `platform-tools/` | Android SDK Platform Tools（adb.exe 等 Windows 二进制） |
| `MULTI_DEVICE_README.md` | 多设备功能说明：架构设计、API 示例、FAQ |

---

## 4. 核心类关系

```
QApplication
  └─ MainWindow (gui/main_window.py)
       ├─ DeviceManager (gui/device_manager.py)
       │    ├─ ADBDevice (adb/device.py)         [多实例，每设备一个]
       │    ├─ DeviceConfigManager (gui/device_config.py)
       │    └─ 信号: device_connected / device_disconnected / active_device_changed
       │
       ├─ MultiDeviceTaskPanel (gui/multi_device_task_panel.py)
       │    └─ DeviceTaskRegistry (task/device_task_registry.py)
       │         └─ TaskManager × N (task/task_manager.py)    [每设备一个]
       │              └─ BaseTask 子类 (task/base_task.py)
       │                   ├─ setup() -> execute() -> teardown()
       │                   ├─ 使用 ADBDevice 操作设备
       │                   └─ 使用 Recognizer (ocr/recognizer.py) 匹配模板
       │
       ├─ ControlPanel (gui/control_panel.py)
       ├─ LogViewer / MultiDeviceLogViewer (gui/log_viewer.py)
       └─ DeviceManagerDialog / SettingsDialog / VerificationDialog

项目层:
  HeroAfkWindow(MainWindow)           [hero_afk/gui/app_window.py]
    └─ 注册 RealTimeMultiTemplateClickTask
         └─ 继承 BaseTask，使用 ADBDevice + Recognizer
```

---

## 5. 关键数据流

```
扫描设备:
  scan_emulators() -> ADB Server 查询 + 端口探测 -> EmulatorInfo 列表
  -> DeviceManager 管理连接 -> 验证 -> 持久化到 device_config.json

任务执行:
  用户选择任务 -> DeviceTaskRegistry.register_task_for_device()
  -> start_task_on_devices() -> TaskManager.start_task()
  -> BaseTask.start() -> daemon Thread 运行 setup->execute->teardown
  -> execute 循环: screenshot -> find_template_grayscale (并行) -> tap_human_like

GUI 通信:
  后台线程 --信号--> 主线程 UI 更新
  DeviceManager.pyqtSignal -> MainWindow 标题栏/状态栏更新
  LogHandler -> pyqtSignal -> LogViewer 实时显示
```

---

## 6. 依赖关系

**运行时核心**:
- `PyQt6 >= 6.4.0` — GUI 框架
- `adb-shell == 0.4.4` — ADB 协议通信（纯 Python 实现）
- `opencv-python >= 4.13.0` — 图像处理和模板匹配
- `numpy >= 1.24.0` — 数组运算
- `Pillow == 10.0.0` — 图像处理辅助
- `PyYAML == 6.0.1` — 配置文件解析
- `schedule == 1.2.0` — 定时任务调度
- `watchdog == 3.0.0` — 文件监控

**可选**:
- `flask == 3.0.0` + `flask-cors == 4.0.0` — Web 界面

**开发工具**:
- `pytest`, `pytest-cov`, `black`, `pylint`, `pyinstaller`

---

## 7. 入口点

| 入口 | 命令 | 说明 |
|------|------|------|
| Hero AFK 项目 | `python projects/hero-afk/main.py` | 启动 Hero AFK GUI 应用 |
| 多设备示例 | `python examples/multi_device_parallel_demo.py` | 命令行演示多设备并行 |
| 单元测试 | `pytest game_platform/tests/` | 运行平台测试 |
| Docker 开发 | `docker compose -f docker/docker-compose.dev.yml up -d` | 启动开发容器 |

---

## 8. 配置文件

| 文件 | 路径 | 用途 |
|------|------|------|
| 项目配置 | `projects/hero-afk/config.yaml` | ADB、日志、任务参数、GUI 主题 |
| 设备配置 | `~/.game_scripts/device_config.json` | 黑名单、已验证设备缓存、用户设置 |
| ADB 密钥 | `~/.game_scripts/adbkey` + `adbkey.pub` | ADB RSA 认证密钥对（自动生成） |
| 平台包配置 | `game_platform/pyproject.toml` | 平台元数据与依赖 |
| 项目包配置 | `projects/hero-afk/pyproject.toml` | 项目元数据 |
| 打包配置 | `projects/hero-afk/build.spec` | PyInstaller 打包参数 |

---

## 9. 模块成熟度

| 模块 | 状态 | 说明 |
|------|------|------|
| ADB 设备控制 | ✅ 已实现 | 连接、操作、扫描、去重均完整 |
| 图像识别 | ✅ 已实现 | 模板匹配、灰度加速、多目标匹配、缓存 |
| OCR 文字识别 | 🔲 骨架 | `recognize_text()` 待集成 OCR 引擎 |
| 任务引擎 | ✅ 已实现 | BaseTask + TaskManager + DeviceTaskRegistry |
| TaskRunner | 🔲 骨架 | 待实现，当前由 BaseTask 自带线程管理替代 |
| Config 配置 | 🔲 骨架 | 待实现 yaml 加载和热更新 |
| GUI 框架 | ✅ 已实现 | 主窗口、设备管理、多设备面板、日志、设置、验证 |
