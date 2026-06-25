# 多设备并行任务执行指南

## 概述

本功能支持**同时在多个模拟器上运行相同的自动化任务**，实现真正的并行操作。

### 核心组件

1. **DeviceTaskRegistry**: 多设备任务注册表，管理设备与任务的映射关系
2. **TaskManager**: 每个设备对应一个独立的 TaskManager 实例
3. **BaseTask**: 任务基类，所有具体任务必须继承此类

---

## 快速开始

### 示例 1：在两个设备上同时启动自动点击任务

```python
from game_platform.task import DeviceTaskRegistry
from hero_afk.tasks.realtime_multi_template_click_task import RealTimeMultiTemplateClickTask

# 1. 创建设备任务注册表
registry = DeviceTaskRegistry()

# 2. 为每个设备创建任务实例并注册
template_folder = "D:/game_scripts/projects/hero-afk/hero_afk/templates"

for port in [5555, 5557]:
    device_addr = f"localhost:{port}"
    
    # 创建任务（传入 device_address 用于标识）
    task = RealTimeMultiTemplateClickTask(
        template_folder=template_folder,
        device_manager=None,  # 单设备模式可传 None
        host="localhost",
        port=port,
        threshold=0.7,
        scan_interval=0.1,
        click_all_matches=False,
        device_address=device_addr  # 关键：记录设备地址
    )
    
    # 注册到 registry
    registry.register_task_for_device(device_addr, task)

# 3. 在所有设备上启动同一任务
results = registry.start_task_on_devices("实时多模板自动点击")

for addr, success in results.items():
    print(f"{addr}: {'✅ 成功' if success else '❌ 失败'}")

# 4. 等待任务运行...
import time
time.sleep(60)

# 5. 停止所有设备上的任务
registry.stop_all_tasks_on_all_devices()
```

### 示例 2：使用 DeviceManager 集成（推荐）

```python
from game_platform.gui.device_manager import DeviceManager
from game_platform.task import DeviceTaskRegistry
from hero_afk.tasks.realtime_multi_template_click_task import RealTimeMultiTemplateClickTask

# 1. 连接设备
dm = DeviceManager()
device1 = dm.connect_and_verify("localhost", 5555, parent_widget=None)
device2 = dm.connect_and_verify("localhost", 5557, parent_widget=None)

if not device1 or not device2:
    raise Exception("设备连接失败")

# 2. 设置活跃设备为 device1（任务会从活跃设备获取 ADBDevice）
dm.set_active("localhost:5555")

# 3. 创建 registry
registry = DeviceTaskRegistry()

template_folder = "D:/game_scripts/projects/hero-afk/hero_afk/templates"

# 4. 为每个设备注册任务
for addr in ["localhost:5555", "localhost:5557"]:
    # 临时切换活跃设备以获取正确的 ADBDevice
    dm.set_active(addr)
    
    task = RealTimeMultiTemplateClickTask(
        template_folder=template_folder,
        device_manager=dm,  # 传入 DeviceManager，任务会自动获取活跃设备
        threshold=0.7,
        scan_interval=0.1,
        click_all_matches=False,
        device_address=addr
    )
    
    registry.register_task_for_device(addr, task)

# 5. 批量启动
results = registry.start_task_on_devices("实时多模板自动点击")

# 6. 监控状态
statuses = registry.get_task_status_across_devices("实时多模板自动点击")
for addr, status in statuses.items():
    print(f"{addr}: {status.value}")

# 7. 停止
registry.stop_all_tasks_on_all_devices()
```

---

## API 参考

### DeviceTaskRegistry

#### 注册任务

```python
def register_task_for_device(
    device_address: str, 
    task: BaseTask, 
    config: dict = None
):
    """为指定设备注册任务
    
    Args:
        device_address: 设备地址（如 "localhost:5555"）
        task: 任务实例
        config: 任务配置（可选）
    """
```

#### 批量启动任务

```python
def start_task_on_devices(
    task_name: str, 
    device_addresses: List[str] = None
) -> Dict[str, bool]:
    """在多个设备上启动同一任务
    
    Args:
        task_name: 任务名称
        device_addresses: 目标设备列表，None 表示在所有已注册该任务的设备上启动
        
    Returns:
        字典 {device_address: success}，记录每个设备的启动结果
    """
```

#### 批量停止任务

```python
def stop_task_on_devices(
    task_name: str, 
    device_addresses: List[str] = None
) -> Dict[str, bool]:
    """在多个设备上停止同一任务"""
```

#### 批量暂停/恢复

```python
def pause_task_on_devices(task_name: str, device_addresses: List[str] = None) -> Dict[str, bool]
def resume_task_on_devices(task_name: str, device_addresses: List[str] = None) -> Dict[str, bool]
```

#### 查询状态

```python
def get_task_status_across_devices(task_name: str) -> Dict[str, TaskStatus]:
    """查询任务在所有设备上的状态
    
    Returns:
        字典 {device_address: TaskStatus}
    """
```

#### 列出设备/任务

```python
def list_devices_for_task(task_name: str) -> List[str]:
    """列出运行某任务的所有设备"""

def list_tasks_for_device(device_address: str) -> List[str]:
    """列出某设备上的所有任务"""
```

#### 全局控制

```python
def stop_all_tasks_on_device(device_address: str):
    """停止某设备上的所有任务"""

def stop_all_tasks_on_all_devices():
    """停止所有设备上的所有任务"""
```

---

## GUI 集成

### MultiDeviceTaskPanel

`game_platform.gui.multi_device_task_panel.MultiDeviceTaskPanel` 提供了完整的 GUI 控制面板：

```python
from game_platform.gui.multi_device_task_panel import MultiDeviceTaskPanel
from game_platform.gui.device_manager import DeviceManager

# 创建设备管理器
dm = DeviceManager()

# 创建多设备任务面板
panel = MultiDeviceTaskPanel(device_manager=dm)

# 添加到主窗口布局
main_layout.addWidget(panel)

# 刷新设备列表（从 DeviceManager 获取已连接设备）
panel.refresh_device_list()
```

**面板功能：**
-  显示所有已连接设备列表
-  为每个设备选择要运行的任务
- ▶️ 批量启动/停止/暂停/恢复按钮
- 📊 实时显示各设备任务状态

---

## 注意事项

### 1. 任务命名规范

每个任务实例的 `name` 属性应该唯一标识任务类型，例如：
- `"实时多模板自动点击"`
- `"自动战斗"`
- `"自动收集"`

相同类型的任务在不同设备上应使用相同的名称，这样 `DeviceTaskRegistry` 才能正确识别和批量控制。

### 2. 设备地址格式

设备地址统一使用 `"host:port"` 格式，例如：
- `"localhost:5555"`
- `"localhost:5557"`
- `"192.168.1.100:5555"`

### 3. 线程安全

- 每个设备的任务在独立线程中运行
- `DeviceTaskRegistry` 内部使用线程安全的字典和集合
- GUI 更新应在主线程中进行（通过信号槽机制）

### 4. 资源管理

- 任务停止时会自动调用 `teardown()` 清理资源
- 如果任务自己创建了 ADBDevice（`_owns_device=True`），会在 teardown 时断开连接
- 如果使用 DeviceManager 提供的设备（`_owns_device=False`），不会断开连接

### 5. 性能考虑

- 建议在任务中使用 `self.sleep()` 而非 `time.sleep()`，以响应暂停/停止请求
- 多线程并行匹配模板时，线程数建议不超过 CPU 核心数
- 大量设备同时运行时，注意系统资源占用

---

## 常见问题

### Q1: 如何在不同设备上运行不同的任务？

```python
registry = DeviceTaskRegistry()

# 设备 A 运行任务 X
task_x = MyTaskX()
registry.register_task_for_device("localhost:5555", task_x)

# 设备 B 运行任务 Y
task_y = MyTaskY()
registry.register_task_for_device("localhost:5557", task_y)

# 分别启动
registry.start_task_on_devices("MyTaskX", ["localhost:5555"])
registry.start_task_on_devices("MyTaskY", ["localhost:5557"])
```

### Q2: 如何暂停某个设备上的任务？

```python
# 暂停单个设备
registry.pause_task_on_devices("实时多模板自动点击", ["localhost:5555"])

# 暂停所有设备
registry.pause_task_on_devices("实时多模板自动点击")
```

### Q3: 如何查看某个设备上有哪些任务在运行？

```python
tasks = registry.list_tasks_for_device("localhost:5555")
print(f"设备 localhost:5555 上的任务: {tasks}")

# 查看任务状态
for task_name in tasks:
    status = registry.get_task_status_across_devices(task_name)
    print(f"  {task_name}: {status.get('localhost:5555')}")
```

### Q4: 网易模拟器多端口问题如何处理？

扫描时已通过 `_deduplicate_emulators()` 去重，只保留主端口。确保：
1. 使用去重后的设备地址（通常是标准端口段 5555-5587）
2. 不要在同一个模拟器的多个端口上同时运行任务

---

## 下一步

- [ ] 在 `MainWindow` 中集成 `MultiDeviceTaskPanel`
- [ ] 添加任务配置持久化（保存每个设备的任务选择）
- [ ] 实现任务执行进度条和日志输出
- [ ] 添加任务优先级调度（避免资源竞争）
