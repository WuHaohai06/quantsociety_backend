"""
最简单的示例: 从模拟数据到 target_position 全流程
=================================================

这个文件展示了 single_asset_alpha 模块的最基本用法。
从生成假数据 → 计算信号 → 映射仓位 → 输出文件，一气呵成。

用法:
    cd quantsociety_backend_project
    python strategy_layer/single_asset_alpha/examples/simple_demo.py
"""

import sys
import os
import io

# Windows 控制台 UTF-8
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 确保项目根在 path 中
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# 1. 生成模拟行情数据
# ═══════════════════════════════════════════════════════════════

from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher

print("=" * 60)
print("[Step 1] 生成 500 天模拟行情数据")
print("=" * 60)

market = DataFetcher.generate_sample_data(
    symbol="DEMO",
    periods=500,
    start_date="2023-01-01",
    seed=123,
)

print(market.head())
print(f"\n共 {len(market)} 行, 列: {list(market.columns)}")


# ═══════════════════════════════════════════════════════════════
# 2. 用双均线策略生成信号 (C-1)
# ═══════════════════════════════════════════════════════════════

from strategy_layer.single_asset_alpha.strategies.signals.dual_ma_signal import DualMASignal

print("\n" + "=" * 60)
print("[Step 2] 双均线信号 (快线=5, 慢线=20)")
print("=" * 60)

signal_gen = DualMASignal(
    params={"fast_window": 5, "slow_window": 20, "ma_type": "sma"},
    name="SimpleMA",
)

signals = signal_gen.generate(market)

# 跳过前面 NaN 的预热期，只看有效信号
valid_signals = signals.dropna()
print(f"信号范围: [{valid_signals.min():.3f}, {valid_signals.max():.3f}]")
print(f"信号均值: {valid_signals.mean():.3f}")
print(f"有效信号: {len(valid_signals)} 行 (前 {signals.isna().sum()} 行为预热期)")

print("\n预热结束后的前 10 行信号:")
print(valid_signals.head(10).to_frame("signal").to_string())


# ═══════════════════════════════════════════════════════════════
# 3. 用固定阈值状态机映射仓位 (C-2)
# ═══════════════════════════════════════════════════════════════

from strategy_layer.single_asset_alpha.strategies.position_mappers.simple_mapper import (
    ThresholdPositionMapper,
)

print("\n" + "=" * 60)
print("[Step 3] 阈值状态机 (开多>0.3, 平多<-0.1)")
print("=" * 60)

mapper = ThresholdPositionMapper(
    params={
        "long_entry_threshold": 0.3,   # 信号 > 0.3 → 开多
        "long_exit_threshold": -0.1,   # 信号 < -0.1 → 平多
        "allow_short": False,          # 不做空
        "shift_bars": 1,               # T日信号, T+1执行
    },
    name="SimpleThreshold",
)

positions = mapper.map_to_position(signals, market)

# 只展示仓位发生变化的行 (比全量展示更直观)
changes = positions[positions["target_position"].diff().abs() > 1e-9]
print(f"仓位切换明细 (共 {len(changes)} 次):")
print(changes.head(15).to_string())

tp = positions["target_position"]
print(f"\n汇总: 多头 {(tp > 0).sum()} 天 ({(tp > 0).mean()*100:.0f}%), "
      f"空仓 {(tp == 0).sum()} 天 ({(tp == 0).mean()*100:.0f}%)")


# ═══════════════════════════════════════════════════════════════
# 4. 格式化输出并校验 Schema
# ═══════════════════════════════════════════════════════════════

from strategy_layer.single_asset_alpha.core.schema import TargetPositionSchema

print("\n" + "=" * 60)
print("[Step 4] 格式化为标准 target_position 并校验")
print("=" * 60)

output = TargetPositionSchema.format_output(
    df=positions,
    symbol="DEMO.TEST",
    include_optional=True,
)

errors = TargetPositionSchema.validate(output)
print(f"Schema 校验: {'通过!' if not errors else errors}")

# 展示有动作发生的行
interesting = output[output["action_name"] != "HOLD"].head(10)
print(f"\n有动作发生的行 (前 10 条):")
print(interesting.to_string(index=False))


# ═══════════════════════════════════════════════════════════════
# 5. 保存文件
# ═══════════════════════════════════════════════════════════════

from pathlib import Path

output_dir = Path(PROJECT_ROOT) / "outputs"
output_dir.mkdir(exist_ok=True)

csv_path = output_dir / "DEMO_target_position.csv"
output.to_csv(csv_path, index=False)

print(f"\n已保存: {csv_path}")
print("\n" + "=" * 60)
print("Done! 这就是从数据到 target_position 的完整流程。")
print("=" * 60)
