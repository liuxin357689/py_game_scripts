"""
模拟器扫描模块

职责:
    - 通过 ADB Server 协议查询已连接设备
    - 探测常见模拟器端口段
    - 返回本地所有可达的模拟器列表

扫描策略:
    1. 连接 ADB Server（默认 localhost:5037），发送 host:devices 获取已知设备
    2. 探测常见模拟器端口段（5555-5587 奇数、7555、16384+ 等）
    3. 对发现的端口尝试 TCP 连接验证
    4. 合并去重，返回完整模拟器列表
"""

import socket
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ADB Server 默认地址
ADB_SERVER_HOST = "localhost"
ADB_SERVER_PORT = 5037

# 常见模拟器 ADB 端口
# 参考: https://github.com/nicehash/NiceHashQuickMiner 等
COMMON_EMULATOR_PORTS = [
    # 标准 Android 模拟器端口段（5555, 5557, 5559, ... 奇数递增）
    *range(5555, 5588, 2),
    # 雷电模拟器 (LDPlayer)
    5555, 5557, 5559, 5561, 5563, 5565, 5567, 5569, 5571, 5573, 5575,
    # 夜神模拟器 (Nox)
    62001, 62025, 62050,
    # MuMu 模拟器
    7555, 16384, 16416, 16448, 16480, 16512,
    # 逍遥模拟器 (MEmu)
    21503, 21513, 21523,
    # 蓝叠 (BlueStacks)
    5555, 5556, 5575, 5576,
]


@dataclass
class EmulatorInfo:
    """模拟器信息"""
    host: str
    port: int
    status: str = "unknown"       # online / offline / unauthorized / unknown
    model: str = ""               # 设备型号（通过 shell 获取）
    brand: str = ""               # 设备品牌
    serial: str = ""              # 设备序列号
    is_emulator: bool = True      # 是否为模拟器（vs 真机）
    name: str = ""                # 用户友好的设备名称（如 "雷电模拟器 #1"）
    resolution: str = ""          # 屏幕分辨率
    android_version: str = ""     # Android 版本
    verified: bool = False        # 是否已验证（通过 ADB 连接并获取信息）

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def __eq__(self, other):
        if not isinstance(other, EmulatorInfo):
            return False
        return self.host == other.host and self.port == other.port

    def __hash__(self):
        return hash((self.host, self.port))


def _query_adb_server(host: str = ADB_SERVER_HOST, port: int = ADB_SERVER_PORT) -> List[EmulatorInfo]:
    """通过 ADB Server 协议查询已连接设备列表

    ADB 协议格式:
        1. 连接 ADB Server (port 5037)
        2. 发送: 4位十六进制长度 + 命令（如 "host:devices"）
        3. 读取: "OKAY" + 4位十六进制长度 + 数据

    Args:
        host: ADB Server 地址
        port: ADB Server 端口

    Returns:
        设备信息列表
    """
    devices = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((host, port))

        # 发送 host:devices 命令
        command = "host:devices"
        sock.sendall(f"{len(command):04x}{command}".encode())

        # 读取响应
        response = sock.recv(4)
        if response != b"OKAY":
            logger.warning(f"ADB Server 响应异常: {response}")
            sock.close()
            return devices

        # 读取数据长度
        length_hex = sock.recv(4)
        if len(length_hex) < 4:
            sock.close()
            return devices

        data_length = int(length_hex.decode(), 16)
        if data_length <= 0:
            sock.close()
            return devices

        # 读取设备列表数据
        data = b""
        while len(data) < data_length:
            chunk = sock.recv(data_length - len(data))
            if not chunk:
                break
            data += chunk

        sock.close()

        # 解析设备列表
        # 格式: "serial\tstatus\n" per line
        text = data.decode("utf-8", errors="ignore").strip()
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                serial = parts[0].strip()
                status = parts[1].strip()

                # 解析 host:port
                emu_host, emu_port = _parse_serial(serial)
                if emu_host and emu_port:
                    devices.append(EmulatorInfo(
                        host=emu_host,
                        port=emu_port,
                        status=status,
                        serial=serial,
                        is_emulator=_is_emulator_port(emu_port),
                    ))

        logger.info(f"ADB Server 查询到 {len(devices)} 个设备")

    except ConnectionRefusedError:
        logger.warning(f"无法连接 ADB Server {host}:{port}，请确认 ADB Server 已启动")
    except socket.timeout:
        logger.warning(f"连接 ADB Server 超时 {host}:{port}")
    except Exception as e:
        logger.error(f"查询 ADB Server 失败: {e}")

    return devices


def _parse_serial(serial: str) -> tuple:
    """解析设备序列号为 host:port

    Args:
        serial: 设备序列号，如 "localhost:5555" 或 "emulator-5554"

    Returns:
        (host, port) 元组，解析失败返回 (None, None)
    """
    # 格式: host:port
    if ":" in serial:
        parts = serial.rsplit(":", 1)
        try:
            return parts[0], int(parts[1])
        except (ValueError, IndexError):
            pass

    # 格式: emulator-5554 → port = 5554 + 1 = 5555
    if serial.startswith("emulator-"):
        try:
            console_port = int(serial.split("-")[1])
            return "localhost", console_port + 1
        except (ValueError, IndexError):
            pass

    return None, None


def _is_emulator_port(port: int) -> bool:
    """判断端口是否属于常见模拟器端口"""
    # 标准模拟器端口段 5555-5587（奇数）
    if 5555 <= port <= 5587 and port % 2 == 1:
        return True
    # 常见模拟器端口
    known_ports = {62001, 62025, 62050, 7555, 16384, 16416, 16448, 16480, 16512, 21503, 21513, 21523}
    return port in known_ports


def _is_emulator_by_props(model: str, brand: str, port: int) -> bool:
    """根据设备属性和端口判断是否为模拟器

    Args:
        model: 设备型号
        brand: 设备品牌
        port: ADB 端口

    Returns:
        是否为模拟器
    """
    model_lower = model.lower() if model else ""
    brand_lower = brand.lower() if brand else ""
    
    # 常见模拟器特征
    emulator_keywords = [
        "emulator", "sdk", "generic", "android_x86",
        "nox", "夜神", "ldplayer", "leidian", "雷电",
        "mumu", "网易", "memu", "逍遥", "bluestacks", "蓝叠"
    ]
    
    for kw in emulator_keywords:
        if kw in model_lower or kw in brand_lower:
            return True
    
    # 模拟器常用端口
    if _is_emulator_port(port):
        return True
    
    return False


def _generate_device_name(model: str, brand: str, port: int) -> str:
    """根据设备型号、品牌和端口生成用户友好的设备名称

    Args:
        model: 设备型号字符串
        brand: 设备品牌
        port: ADB 端口

    Returns:
        用户友好的设备名称
    """
    model_lower = model.lower() if model else ""
    brand_lower = brand.lower() if brand else ""
    
    # 优先根据品牌识别
    if any(kw in brand_lower for kw in ["nox", "夜神"]):
        return f"夜神模拟器 (端口{port})"
    elif any(kw in brand_lower for kw in ["leidian", "雷电"]):
        return f"雷电模拟器 (端口{port})"
    elif any(kw in brand_lower for kw in ["mumu", "netease", "网易"]):
        return f"MuMu模拟器 (端口{port})"
    elif any(kw in brand_lower for kw in ["memu", "逍遥"]):
        return f"逍遥模拟器 (端口{port})"
    elif any(kw in brand_lower for kw in ["bluestacks", "蓝叠"]):
        return f"蓝叠模拟器 (端口{port})"
    
    # 其次根据型号识别
    if any(kw in model_lower for kw in ["nox", "夜神"]):
        return f"夜神模拟器 (端口{port})"
    elif any(kw in model_lower for kw in ["ldplayer", "leidian", "雷电"]):
        return f"雷电模拟器 (端口{port})"
    elif any(kw in model_lower for kw in ["mumu", "网易"]):
        return f"MuMu模拟器 (端口{port})"
    elif any(kw in model_lower for kw in ["memu", "逍遥"]):
        return f"逍遥模拟器 (端口{port})"
    elif any(kw in model_lower for kw in ["bluestacks", "蓝叠"]):
        return f"蓝叠模拟器 (端口{port})"
    elif "emulator" in model_lower or "sdk" in model_lower:
        return f"Android模拟器 (端口{port})"
    elif brand and brand.lower() not in ["unknown", ""]:
        # 有品牌的真机
        return f"{brand} {model} (端口{port})"
    else:
        # 其他设备，使用型号
        return f"{model or '未知设备'} (端口{port})"


def _probe_port(host: str, port: int, timeout: float = 1.0) -> Optional[EmulatorInfo]:
    """探测单个端口并获取完整设备信息

    Args:
        host: 目标地址
        port: 目标端口
        timeout: 超时时间（秒）

    Returns:
        如果端口可达且是 ADB 设备，返回 EmulatorInfo；否则返回 None
    """
    try:
        # 先快速检查端口是否开放
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result != 0:
            return None  # 端口未开放
        
        # 尝试连接 ADB 并获取设备信息
        from game_platform.adb.device import ADBDevice
        device = ADBDevice(host, port)
        if not device.connect():
            return None  # ADB 连接失败
        
        try:
            info = EmulatorInfo(
                host=host,
                port=port,
                status="online",
                verified=True,
            )
            
            # 获取设备型号
            model = device._device.shell("getprop ro.product.model").strip()
            info.model = model if model else "未知设备"
            
            # 获取品牌
            brand = device._device.shell("getprop ro.product.brand").strip()
            info.brand = brand if brand else ""
            
            # 获取序列号
            serial = device._device.shell("getprop ro.serialno").strip()
            info.serial = serial if serial else ""
            
            # 获取 Android 版本
            version = device._device.shell("getprop ro.build.version.release").strip()
            info.android_version = version if version else ""
            
            # 获取分辨率
            wm_size = device._device.shell("wm size").strip()
            if wm_size and "Physical size:" in wm_size:
                info.resolution = wm_size.split("Physical size:")[1].strip()
            
            # 生成用户友好的名称
            info.name = _generate_device_name(info.model, info.brand, port)
            
            # 判断是否为模拟器
            info.is_emulator = _is_emulator_by_props(info.model, info.brand, port)
            
            logger.debug(f"发现设备: {info.name} [{info.model}]")
            return info
            
        except Exception as e:
            logger.debug(f"获取设备信息失败 {host}:{port}: {e}")
            return None
        finally:
            device.disconnect()
            
    except Exception:
        return None


def _probe_ports(host: str, ports: List[int], max_workers: int = 20) -> Dict[int, EmulatorInfo]:
    """并发探测多个端口并获取设备信息

    Args:
        host: 目标地址
        ports: 待探测的端口列表
        max_workers: 最大并发线程数

    Returns:
        字典 {port: EmulatorInfo}，只包含成功获取信息的设备
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_probe_port, host, port): port for port in ports}
        for future in as_completed(futures):
            port = futures[future]
            try:
                info = future.result()
                if info is not None and info.verified:
                    results[port] = info
                    logger.debug(f"发现设备: {info.name}")
            except Exception:
                pass
    return results


def scan_emulators(
    host: str = ADB_SERVER_HOST,
    adb_server_port: int = ADB_SERVER_PORT,
    extra_ports: Optional[List[int]] = None,
    timeout: float = 1.0,
) -> List[EmulatorInfo]:
    """扫描本地所有安卓模拟器

    扫描流程:
        1. 通过 ADB Server 查询已知设备
        2. 探测常见模拟器端口
        3. 合并去重

    Args:
        host: ADB Server 地址（通常为 localhost）
        adb_server_port: ADB Server 端口（通常为 5037）
        extra_ports: 额外需要探测的端口
        timeout: 端口探测超时（秒）

    Returns:
        发现的模拟器信息列表
    """
    logger.info(f"开始扫描本地模拟器 (ADB Server: {host}:{adb_server_port})...")

    discovered: dict = {}  # address -> EmulatorInfo

    # 1. 通过 ADB Server 查询
    server_devices = _query_adb_server(host, adb_server_port)
    for dev in server_devices:
        discovered[dev.address] = dev

    # 2. 探测常见端口
    all_ports = list(set(COMMON_EMULATOR_PORTS))
    if extra_ports:
        all_ports.extend(extra_ports)
    all_ports = sorted(set(all_ports))

    logger.info(f"正在探测 {len(all_ports)} 个常见模拟器端口...")
    port_models = _probe_ports(host, all_ports, max_workers=20)

    for port, info in port_models.items():
        address = f"{host}:{port}"
        if address not in discovered:
            discovered[address] = info
            logger.info(f"发现新设备: {info.name} [{info.model}]")

    result = list(discovered.values())
    logger.info(f"扫描完成，共发现 {len(result)} 个设备")

    # 3. 去重：同一台模拟器的多个端口只保留一个
    result = _deduplicate_emulators(result)
    logger.info(f"去重后剩余 {len(result)} 个设备")

    return result


def _deduplicate_emulators(devices: List[EmulatorInfo]) -> List[EmulatorInfo]:
    """对模拟器设备进行去重

    某些模拟器（如 MuMu、夜神）会为同一台实例分配多个 ADB 端口。
    通过设备型号+品牌+分辨率识别同一台模拟器，只保留主端口。

    Args:
        devices: 原始设备列表

    Returns:
        去重后的设备列表
    """
    if not devices:
        return []

    # 分组键：(model, brand, resolution)
    groups: Dict[tuple, List[EmulatorInfo]] = {}

    for dev in devices:
        key = (dev.model, dev.brand, dev.resolution)
        if key not in groups:
            groups[key] = []
        groups[key].append(dev)

    result = []
    for key, group in groups.items():
        if len(group) == 1:
            # 唯一设备，直接保留
            result.append(group[0])
        else:
            # 多台相同特征的设备 → 可能是同一模拟器的多端口
            # 策略：优先保留标准模拟器端口（5555-5587），其次最小端口
            selected = _select_primary_device(group)
            if selected:
                result.append(selected)
                logger.debug(
                    f"去重: {len(group)} 个相同设备 → 保留主端口 {selected.port} "
                    f"({selected.name})"
                )

    return result


def _select_primary_device(group: List[EmulatorInfo]) -> Optional[EmulatorInfo]:
    """从同一组设备中选择主端口

    优先级:
        1. 标准模拟器端口段（5555-5587 奇数）
        2. 常见模拟器主端口（7555 for MuMu, 62001 for Nox, etc）
        3. 最小端口号

    Args:
        group: 具有相同特征的设备列表

    Returns:
        选中的主设备，失败返回 None
    """
    if not group:
        return None

    # 优先级 1: 标准模拟器端口
    standard_ports = [d for d in group if 5555 <= d.port <= 5587 and d.port % 2 == 1]
    if standard_ports:
        return min(standard_ports, key=lambda d: d.port)

    # 优先级 2: 常见模拟器主端口
    primary_port_map = {
        7555: "mumu",       # MuMu 主端口
        62001: "nox",       # 夜神主端口
        5555: "ldplayer",   # 雷电主端口
        21503: "memu",      # 逍遥主端口
    }
    for port, _ in primary_port_map.items():
        for dev in group:
            if dev.port == port:
                return dev

    # 优先级 3: 最小端口
    return min(group, key=lambda d: d.port)
