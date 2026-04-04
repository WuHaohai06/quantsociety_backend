"""
single_asset_alpha — 单标的择时信号与目标仓位生成模块
=====================================================

研究员 C (汤宏恩) 专属工作目录。

职责链路:
    行情/因子数据 → C-1 信号生成 → C-2 状态机映射 → target_position 标准文件

本模块 **不 import Backtrader**；与研究员 D 衔接时请用 ``integration.backtest_bridge``（其内部再调回测）。
"""

__version__ = "0.1.0"
__author__ = "汤宏恩 (研究员C)"
