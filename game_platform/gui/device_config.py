"""
设备配置管理器

职责:
    - 持久化存储设备相关配置（黑名单、已验证设备、用户设置）
    - 配置文件路径: ~/.game_scripts/device_config.json
    - 提供线程安全的读写操作
    - 自动备份和异常恢复
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Set, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import threading

logger = logging.getLogger(__name__)


@dataclass
class VerifiedDeviceInfo:
    """已验证设备信息"""
    name: str
    model: str
    brand: str
    last_verified: str  # ISO 格式时间字符串
    verification_count: int = 1
    last_connected: Optional[str] = None  # 最后连接时间
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'VerifiedDeviceInfo':
        return cls(**data)


@dataclass
class DeviceSettings:
    """设备管理设置"""
    enable_verification: bool = True  # 是否启用连接验证
    auto_open_settings: bool = True   # 是否自动打开设置界面
    show_verification_tips: bool = True  # 是否显示验证提示
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DeviceSettings':
        return cls(**data)


class DeviceConfigManager:
    """设备配置管理器（单例模式）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._config_dir = Path.home() / ".game_scripts"
        self._config_path = self._config_dir / "device_config.json"
        self._backup_path = self._config_dir / "device_config.json.bak"
        
        # 确保配置目录存在
        self._config_dir.mkdir(exist_ok=True)
        
        # 加载配置
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self._blacklist = set(data.get('blacklist', []))
                self._verified_devices = {
                    addr: VerifiedDeviceInfo.from_dict(info)
                    for addr, info in data.get('verified_devices', {}).items()
                }
                self._settings = DeviceSettings.from_dict(
                    data.get('settings', {})
                )
                
                logger.info(f"配置加载成功: {len(self._blacklist)} 个黑名单, "
                          f"{len(self._verified_devices)} 个已验证设备")
            else:
                # 创建默认配置
                self._blacklist = set()
                self._verified_devices = {}
                self._settings = DeviceSettings()
                self._save_config()
                logger.info("创建默认配置文件")
                
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            # 尝试从备份恢复
            if self._backup_path.exists():
                try:
                    self._restore_from_backup()
                    return
                except Exception as restore_error:
                    logger.error(f"从备份恢复失败: {restore_error}")
            
            # 使用默认配置
            self._blacklist = set()
            self._verified_devices = {}
            self._settings = DeviceSettings()
    
    def _save_config(self):
        """保存配置文件（带备份）"""
        try:
            # 先备份现有文件
            if self._config_path.exists():
                import shutil
                shutil.copy2(self._config_path, self._backup_path)
            
            # 构建配置数据
            data = {
                'blacklist': list(self._blacklist),
                'verified_devices': {
                    addr: info.to_dict() 
                    for addr, info in self._verified_devices.items()
                },
                'settings': self._settings.to_dict(),
                'last_updated': datetime.now().isoformat()
            }
            
            # 原子写入：先写临时文件，再重命名
            temp_path = self._config_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # 替换原文件
            temp_path.replace(self._config_path)
            
            logger.debug("配置保存成功")
            
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            # 尝试从备份恢复
            if self._backup_path.exists():
                try:
                    self._restore_from_backup()
                except Exception:
                    pass
    
    def _restore_from_backup(self):
        """从备份恢复配置"""
        import shutil
        shutil.copy2(self._backup_path, self._config_path)
        logger.info("已从备份恢复配置")
        
        # 重新加载
        with open(self._config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self._blacklist = set(data.get('blacklist', []))
        self._verified_devices = {
            addr: VerifiedDeviceInfo.from_dict(info)
            for addr, info in data.get('verified_devices', {}).items()
        }
        self._settings = DeviceSettings.from_dict(
            data.get('settings', {})
        )
    
    # ---- 黑名单操作 ----
    
    def is_blacklisted(self, address: str) -> bool:
        """检查设备是否在黑名单中"""
        return address in self._blacklist
    
    def add_to_blacklist(self, address: str):
        """将设备加入黑名单"""
        if address not in self._blacklist:
            self._blacklist.add(address)
            self._save_config()
            logger.info(f"设备 {address} 已加入黑名单")
    
    def remove_from_blacklist(self, address: str):
        """从黑名单移除设备"""
        if address in self._blacklist:
            self._blacklist.remove(address)
            self._save_config()
            logger.info(f"设备 {address} 已从黑名单移除")
    
    def get_blacklist(self) -> Set[str]:
        """获取黑名单副本"""
        return self._blacklist.copy()
    
    def clear_blacklist(self):
        """清空黑名单"""
        self._blacklist.clear()
        self._save_config()
        logger.info("黑名单已清空")
    
    # ---- 已验证设备操作 ----
    
    def is_verified(self, address: str) -> bool:
        """检查设备是否已验证"""
        return address in self._verified_devices
    
    def mark_as_verified(self, address: str, name: str, model: str, brand: str):
        """标记设备为已验证"""
        now = datetime.now().isoformat()
        
        if address in self._verified_devices:
            # 更新现有记录
            info = self._verified_devices[address]
            info.last_verified = now
            info.verification_count += 1
        else:
            # 创建新记录
            info = VerifiedDeviceInfo(
                name=name,
                model=model,
                brand=brand,
                last_verified=now,
                verification_count=1
            )
        
        self._verified_devices[address] = info
        self._save_config()
        logger.info(f"设备 {address} 已标记为已验证 (第{info.verification_count}次)")
    
    def update_last_connected(self, address: str):
        """更新最后连接时间"""
        if address in self._verified_devices:
            self._verified_devices[address].last_connected = datetime.now().isoformat()
            self._save_config()
    
    def get_verified_info(self, address: str) -> Optional[VerifiedDeviceInfo]:
        """获取已验证设备信息"""
        return self._verified_devices.get(address)
    
    def get_all_verified(self) -> Dict[str, VerifiedDeviceInfo]:
        """获取所有已验证设备"""
        return self._verified_devices.copy()
    
    def remove_verified(self, address: str):
        """移除已验证设备记录"""
        if address in self._verified_devices:
            del self._verified_devices[address]
            self._save_config()
            logger.info(f"设备 {address} 的验证记录已移除")
    
    def clear_verified_cache(self):
        """清空已验证设备缓存"""
        self._verified_devices.clear()
        self._save_config()
        logger.info("已验证设备缓存已清空")
    
    # ---- 设置操作 ----
    
    @property
    def settings(self) -> DeviceSettings:
        """获取当前设置"""
        return self._settings
    
    def update_settings(self, **kwargs):
        """更新设置"""
        for key, value in kwargs.items():
            if hasattr(self._settings, key):
                setattr(self._settings, key, value)
        self._save_config()
        logger.info(f"设置已更新: {kwargs}")
    
    # ---- 工具方法 ----
    
    def get_config_path(self) -> Path:
        """获取配置文件路径"""
        return self._config_path
    
    def export_config(self, target_path: str):
        """导出配置到指定路径"""
        import shutil
        shutil.copy2(self._config_path, target_path)
        logger.info(f"配置已导出到: {target_path}")
    
    def import_config(self, source_path: str):
        """从指定路径导入配置"""
        import shutil
        shutil.copy2(source_path, self._config_path)
        self._load_config()
        logger.info(f"配置已从 {source_path} 导入")


# 全局单例
_config_manager: Optional[DeviceConfigManager] = None


def get_config_manager() -> DeviceConfigManager:
    """获取配置管理器单例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = DeviceConfigManager()
    return _config_manager
