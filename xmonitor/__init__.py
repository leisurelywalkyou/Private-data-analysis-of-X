"""X 数据监控功能组件与桌宠主程序。

分层：
- core：配置、HTTP、平台数据仓库、通用采集、分析、报告、多平台调度
- platforms：六个平台的适配器与动态注册表
- ui：监控面板、桌宠、设置
"""

from .core import analysis, report
from .core.collector import collect_platform, make_store
from .core.config import get_tz, load_config, save_config
from .core.scheduler import MultiCollectScheduler
from .platforms import available, create, load, unload

__all__ = [
    "analysis", "report", "collect_platform", "make_store",
    "get_tz", "load_config", "save_config", "MultiCollectScheduler",
    "available", "create", "load", "unload",
]
