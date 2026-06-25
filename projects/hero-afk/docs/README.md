# Hero AFK

英雄挂机自动化脚本 — 基于 ADB + 像素颜色检测的轻量游戏自动化工具。

## 功能特性

- **实时模板点击**：灰度图像匹配 + 多线程并行扫描，自动识别并点击目标按钮
- **自动领取奖励**（开发中）：基于固定坐标 + 像素颜色检测，覆盖签到、邮件、任务、活动等模块
- **多设备支持**：同时管理多台安卓模拟器，每台设备独立日志和任务管理
- **PyQt6 图形界面**：可视化的任务控制面板和设备日志查看器
- **YAML 配置驱动**：所有坐标、颜色值、任务参数均通过配置文件管理，无需修改代码

## 技术架构

```
AutoCollectRewardsTask(BaseTask)
├── PixelChecker          # 像素颜色检测器（ADB 截图 + RGB 采样）
├── ScreenPilot           # 坐标驱动的屏幕导航器
└── RewardModule          # 可插拔的奖励收集模块
    ├── SignInModule      #   每日签到
    ├── MailModule        #   邮件领取
    ├── TaskRewardModule  #   任务奖励
    ├── ActivityModule    #   活动奖励
    ├── EquipUpgradeModule#   装备升级
    ├── SkillUpgradeModule#   技能升级
    └── DungeonModule     #   副本挑战
```

核心设计思路：游戏核心逻辑走 TCP 二进制协议（端口 10012），无法通过 HTTPS API 回放实现自动化。因此采用 UI 层自动化方案 — 通过 ADB 截图 + 像素颜色比对判断界面状态，固定坐标点击执行操作。相比模板匹配 + OCR，该方案速度更快（像素检测 <1ms）、配置更简单、维护成本更低。

## 项目结构

```
hero-afk/
├── main.py                     # 应用入口
├── config.yaml                 # 项目配置
├── pyproject.toml              # 构建配置
├── build.spec                  # PyInstaller 打包配置
├── hero_afk/                   # 主包
│   ├── core/                   # 核心自动化引擎
│   │   ├── pixel_checker.py    #   像素颜色检测器
│   │   ├── screen_pilot.py     #   屏幕导航器
│   │   └── reward_module.py    #   奖励模块基类
│   ├── tasks/                  # 任务实现
│   │   ├── auto_collect.py     #   自动领奖任务
│   │   ├── auto_battle.py      #   自动战斗任务
│   │   └── realtime_multi_...  #   实时模板点击任务
│   ├── gui/                    # PyQt6 界面
│   │   └── app_window.py       #   主窗口
│   └── templates/              # 模板图片资源
├── config/                     # 坐标配置文件
│   └── rewards_1920x1080.yaml  #   1920x1080 分辨率坐标
├── tools/                      # 开发工具
│   └── coord_picker.py         #   坐标采集工具
├── tests/                      # 测试套件
└── docs/                       # 设计文档
```

## 环境要求

- Python >= 3.10
- ADB（Android Debug Bridge）已安装且在 PATH 中
- 安卓模拟器（推荐 MuMu 12）或已 root 的安卓设备
- [game-scripts-platform](https://github.com/USER/game-scripts-platform) 平台包

## 安装

```bash
# 克隆项目
git clone https://github.com/USER/hero-afk.git
cd hero-afk

# 安装依赖（开发模式）
pip install -e ".[dev]"
```

## 使用方法

### 启动应用

```bash
python main.py
```

启动后在 GUI 中连接模拟器设备，选择任务并启动。

### 配置 ADB 连接

编辑 `config.yaml`，设置模拟器的 ADB 地址：

```yaml
adb:
  host: "localhost"
  port: 5555          # MuMu 默认端口
  auto_connect: true
```

常用模拟器 ADB 端口：MuMu 12 默认 `16384`，雷电 `5555`，夜神 `62001`。

### 自动领奖配置

在 `config.yaml` 中启用并配置自动领奖模块：

```yaml
tasks:
  auto_collect:
    enabled: true
    resolution: [1920, 1080]     # 模拟器分辨率
    color_tolerance: 30          # 颜色容差
    modules:
      sign_in: true
      mail: true
      task_reward: true
      activity: true
```

坐标配置在 `config/rewards_<分辨率>.yaml` 中，使用坐标采集工具生成。

## 开发

### 运行测试

```bash
pytest
```

### 坐标采集

使用内置的坐标采集工具从游戏截图中采样坐标和颜色值：

```bash
python -m tools.coord_picker screenshot.png
```

点击截图任意位置即可输出坐标和 RGB 值，方便快速编写配置文件。

### 打包发布

```bash
pyinstaller build.spec
```

生成的可执行文件位于 `dist/HeroAFK.exe`。

## 开发路线

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | PixelChecker + 坐标采集工具 | 进行中 |
| P2 | ScreenPilot 导航框架 | 计划中 |
| P3 | SignInModule（签到，跑通流程） | 计划中 |
| P4 | MailModule + TaskRewardModule | 计划中 |
| P5 | Activity + Equip + Skill + Dungeon | 计划中 |
| P6 | 循环模式 + 容错 + GUI 集成 | 计划中 |

## 许可证

本项目基于 [MIT License](../LICENSE) 开源。

## 免责声明

本项目仅供学习交流使用。使用本工具产生的一切后果由使用者自行承担。请遵守相关游戏的服务条款。
