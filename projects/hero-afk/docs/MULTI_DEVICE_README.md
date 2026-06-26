# 多设备并行任务执行功能

##  功能概述

本功能实现了**在多个模拟器上同时运行相同的自动化任务**，支持真正的并行操作。

### ✨ 核心特性

- ✅ **真正并行**：每个设备的任务在独立线程中运行，互不干扰
- ✅ **统一控制**：一键启动/停止所有设备上的相同任务
- ✅ **灵活调度**：支持选择性控制（只在部分设备上启动）
- ✅ **状态追踪**：实时查询每个设备的任务状态
- ✅ **资源隔离**：每个设备有独立的 TaskManager，避免冲突
- ✅ **自动重连**：第二次打开脚本自动连接上次使用的设备
- ✅ **设备去重**：网易模拟器多端口自动去重，只显示真实设备数

---

## 🚀 快速开始

### 方式 1：使用 GUI（推荐）

1. **启动脚本**
   ```bash
   python projects/hero-afk/main.py
   ```

2. **连接设备**
   - 工具 → 设备管理 → 扫描设备
   - 选择设备 → 连接（首次连接会验证）

3. **配置任务**
   - 主窗口会自动显示"设备与任务"面板
   - 为每个设备选择要运行的任务（如"实时多模板自动点击"）

4. **批量启动**
   - 点击"全部启动"按钮
   - 两个模拟器将同时开始执行任务

5. **监控与控制**
   - 实时查看各设备任务状态
   - 可随时暂停/恢复/停止

### 方式 2：使用命令行示例

```bash
python examples/multi_device_parallel_demo.py
```

此脚本会在 `localhost:5555` 和 `localhost:5557` 两个设备上同时运行自动点击任务。

---

## 📁 文件结构

```
game_scripts/
├── game_platform/
│   ├── task/
│   │   ├── base_task.py                    # 任务基类
│   │   ├── task_manager.py                 # 单设备任务管理器
│   │   ├── device_task_registry.py         # ⭐ 多设备任务注册表（新增）
│   │   ├── __init__.py                     # 导出接口
│   │   ├── examples_multi_device.py        # API 使用示例
│   │   └── MULTI_DEVICE_GUIDE.md           # 完整文档
│   │
│   ── gui/
│       ├── main_window.py                  # 主窗口（已集成多设备面板）
│       ├── device_manager.py               # 设备管理器
│       ├── multi_device_task_panel.py      # ⭐ 多设备任务控制面板（新增）
│       ── settings_dialog.py              # 设置对话框
│
├── projects/hero-afk/
│   └── hero_afk/tasks/
│       └── realtime_multi_template_click_task.py  # 已适配多设备
│
└── examples/
    └── multi_device_parallel_demo.py       # ⭐ 完整演示脚本（新增）
```

---

## 🔑 核心 API

### DeviceTaskRegistry

```python
from game_platform.task import DeviceTaskRegistry

registry = DeviceTaskRegistry()

# 1. 为设备注册任务
registry.register_task_for_device("localhost:5555", task_instance)

# 2. 批量启动任务
results = registry.start_task_on_devices("任务名称")
# 返回: {"localhost:5555": True, "localhost:5557": True}

# 3. 批量停止任务
registry.stop_all_tasks_on_all_devices()

# 4. 查询状态
statuses = registry.get_task_status_across_devices("任务名称")
# 返回: {"localhost:5555": TaskStatus.RUNNING, ...}
```

### MultiDeviceTaskPanel（GUI）

```python
from game_platform.gui.multi_device_task_panel import MultiDeviceTaskPanel

panel = MultiDeviceTaskPanel(device_manager=dm)
panel.refresh_device_list()  # 刷新设备列表
```

---

## 🎯 使用场景

### 场景 1：双开游戏刷副本

```python
# 在两个模拟器上同时运行自动战斗
registry.start_task_on_devices("自动战斗")
```

### 场景 2：不同设备执行不同任务

```python
# 设备 A 运行自动收集
registry.start_task_on_devices("自动收集", ["localhost:5555"])

# 设备 B 运行自动战斗
registry.start_task_on_devices("自动战斗", ["localhost:5557"])
```

### 场景 3：动态调整任务分配

```python
# 暂停设备 A，启动设备 B
registry.pause_task_on_devices("自动战斗", ["localhost:5555"])
registry.start_task_on_devices("自动战斗", ["localhost:5557"])
```

---

## ⚙️ 技术细节

### 架构设计

```
┌─────────────────────────────────────────┐
│         MainWindow (GUI)                │
│  ┌───────────────────────────────────┐  │
│  │  MultiDeviceTaskPanel             │  │
│  │  ┌─────────────┬───────────────┐  │  │
│  │  │ localhost:5555 │ 任务选择     │  │  │
│  │  │ localhost:5557 │ 任务选择     │  │  │
│  │  ─────────────┴───────────────┘  │  │
│  └───────────────────────────────────┘  │
─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│       DeviceTaskRegistry                │
│  ┌──────────────┐  ┌──────────────┐     │
│  │ TaskManager  │  │ TaskManager  │     │
│  │ (5555)       │  │ (5557)       │     │
│  │  ├─ Task A   │  │  ├─ Task A   │     │
│  │  ─ Thread 1 │  │  └─ Thread 2 │     │
│  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│         DeviceManager                   │
│  ├─ ADBDevice (5555)                    │
│  └─ ADBDevice (5557)                    │
└─────────────────────────────────────────┘
```

### 线程模型

- 每个任务在独立线程中运行（`BaseTask._thread`）
- `DeviceTaskRegistry` 内部使用线程安全的字典和集合
- GUI 更新通过 PyQt6 信号槽机制在主线程中执行

### 资源管理

- 任务停止时自动调用 `teardown()` 清理资源
- 如果任务自己创建了 ADBDevice（`_owns_device=True`），会在 teardown 时断开连接
- 如果使用 DeviceManager 提供的设备（`_owns_device=False`），不会断开连接

---

##  常见问题

### Q1: 为什么扫描出 5 个设备但只开了 2 台模拟器？

**A**: 网易模拟器会为同一台实例分配多个 ADB 端口（主端口 + 备用端口）。已通过 `_deduplicate_emulators()` 自动去重，只保留主端口。

### Q2: 任务启动后立即失败怎么办？

**A**: 检查以下几点：
1. 模拟器是否已完全启动（等待 Android 系统加载完成）
2. 模板文件夹路径是否正确
3. 模板图片是否存在且格式正确（PNG/JPG）
4. 查看日志输出中的具体错误信息

### Q3: 如何在代码中动态添加新任务类型？

**A**: 
1. 继承 `BaseTask` 实现新任务类
2. 在 `MultiDeviceTaskPanel._available_tasks` 中添加任务名称
3. 在 `_on_start_all()` 中根据任务名称创建对应实例

### Q4: 多设备运行时性能如何优化？

**A**: 
- 减少扫描间隔（`scan_interval`）会增加 CPU 占用
- 建议使用灰度匹配 + 多线程并行（已默认启用）
- 大量设备同时运行时，注意系统资源占用

---

## 📖 相关文档

- [MULTI_DEVICE_GUIDE.md](../../../game_platform/task/MULTI_DEVICE_GUIDE.md) - 完整 API 文档
- [examples_multi_device.py](../../../game_platform/task/examples_multi_device.py) - API 使用示例
- [multi_device_parallel_demo.py](examples/multi_device_parallel_demo.py) - 完整演示脚本

---

##  下一步计划

- [ ] 添加任务配置持久化（保存每个设备的任务选择）
- [ ] 实现任务执行进度条和日志输出
- [ ] 添加任务优先级调度（避免资源竞争）
- [ ] 支持热重载任务配置（无需重启）
- [ ] 添加性能监控面板（CPU/内存占用）

---

## 📝 更新日志

### v0.2.0 (2026-06-12)
- ✨ 新增多设备并行任务执行功能
- ✨ 新增 DeviceTaskRegistry 多设备任务注册表
-  新增 MultiDeviceTaskPanel GUI 控制面板
- ✨ 新增自动重连上次设备功能
- ✨ 新增网易模拟器多端口去重功能
- 🐛 修复 QFrame 枚举语法（PyQt6 兼容）
- 🐛 修复中文引号导致的 SyntaxError

---

**最后更新**: 2026-06-12  
**作者**: Game Scripts Team
