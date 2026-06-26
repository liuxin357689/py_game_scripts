"""
Hero AFK - 专属任务模块

继承平台 FrameTask，实现英雄挂机游戏的自动化任务（截图共享架构）：
    - AutoCloseNotify: 自动完成任务（坐标+像素点）
    - AutoDarkRealm: 暗能秘境（星星计数+模板匹配+像素点）
    - AutoReplaceEquipment: 自动替换装备（模板匹配）
    - AutoChaosRanch: 混沌牧场（模板匹配+坐标像素点）
    - AutoActivityReward: 自动领取活动奖励（模板匹配+角标检测）

截图共享架构：任务不自行管理设备连接和截图，
由 ScreenshotService 推送帧画面，任务只需实现 on_frame(screen)。
"""

from .auto_replace_equipment import AutoReplaceEquipment
from .auto_close_notify import AutoCloseNotify
from .auto_chaos_ranch import AutoChaosRanch
from .auto_dark_realm import AutoDarkRealm
from .auto_activity_reward import AutoActivityReward

__all__ = [
    'AutoReplaceEquipment', 'AutoCloseNotify',
    'AutoChaosRanch', 'AutoDarkRealm',
    'AutoActivityReward',
]
