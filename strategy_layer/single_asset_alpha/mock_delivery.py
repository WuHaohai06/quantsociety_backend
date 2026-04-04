"""
Sprint 0 Mock 交付脚本
=======================

目的: 快速生成一份符合 target_position Schema 的数据文件，
立即交付给研究员 D ，使其可以立刻开始搭建 Backtrader 回测框架。

用法:
    cd quantsociety_backend_project
    python strategy_layer/single_asset_alpha/mock_delivery.py

输出:
    outputs/MOCK_000001.SZ_target_position.csv
    outputs/MOCK_000001.SZ_target_position.parquet
"""

from __future__ import annotations

import sys
import os
import io

# Windows 控制台 UTF-8 编码
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
import numpy as np
from pathlib import Path

from strategy_layer.single_asset_alpha.core.schema import TargetPositionSchema, ActionName
from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher


def generate_mock_target_position(
    symbol: str = "000001.SZ",
    periods: int = 500,
    seed: int = 42,
) -> pd.DataFrame:
    """生成 Mock 目标仓位数据。

    使用简单随机状态机模拟仓位切换，专门用于验证下游 Backtrader 适配层。
    """
    rng = np.random.default_rng(seed)

    # 生成模拟行情
    market_data = DataFetcher.generate_sample_data(
        symbol=symbol, periods=periods, seed=seed
    )

    # 模拟状态机: 随机在 {FLAT, LONG} 之间切换
    n = len(market_data)
    positions = np.zeros(n)
    actions = np.full(n, ActionName.HOLD.value, dtype=object)
    signal_values = np.zeros(n)

    current = 0.0
    for i in range(n):
        # 简单的随机信号
        sig = rng.normal(0, 1)
        signal_values[i] = sig

        if current == 0.0:
            if sig > 1.5:
                current = 1.0
                actions[i] = ActionName.ENTRY_LONG.value
        else:
            if sig < -1.0:
                current = 0.0
                actions[i] = ActionName.EXIT_LONG.value

        positions[i] = current

    # 环形位移近似「上一 bar 信号本 bar 生效」；首 bar 置 0。正式策略请用 PositionMapper.apply_shift
    positions = np.roll(positions, 1)
    positions[0] = 0.0
    signal_values = np.roll(signal_values, 1)
    signal_values[0] = 0.0

    # 组装 Schema
    output = pd.DataFrame({
        "timestamp": market_data.index,
        "symbol": symbol,
        "target_position": positions,
        "signal_value": signal_values,
        "action_name": actions,
    })

    return output


def main():
    print("=" * 60)
    print("🚀 Sprint 0 Mock 交付: 生成 target_position 示例文件")
    print("=" * 60)

    symbol = "000001.SZ"
    # 单资产 alpha 包的上三级 = 仓库根下的 outputs，便于与 pipeline 默认输出目录一致
    output_dir = Path(__file__).parent.parent.parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    mock_df = generate_mock_target_position(symbol=symbol, periods=500)

    # strict=True 会检查 target_position 值域；Mock 数据应已落在 [-1,1]
    errors = TargetPositionSchema.validate(mock_df)
    if errors:
        print("⚠️ Schema 校验警告:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✅ Schema 校验通过")

    # 保存 CSV (方便研究员 D 预览)
    csv_path = output_dir / f"MOCK_{symbol}_target_position.csv"
    mock_df.to_csv(csv_path, index=False)
    print(f"📄 CSV 输出: {csv_path}")

    # 保存 Parquet (正式交付格式)
    parquet_path = output_dir / f"MOCK_{symbol}_target_position.parquet"
    mock_df.to_parquet(parquet_path, index=False)
    print(f"📄 Parquet 输出: {parquet_path}")

    # 打印预览
    print(f"\n{'='*60}")
    print(f"📊 数据预览 (前 20 行):")
    print(f"{'='*60}")
    print(mock_df.head(20).to_string(index=False))

    # 统计摘要
    tp = mock_df["target_position"]
    print(f"\n📈 仓位统计:")
    print(f"  多头天数: {(tp > 0).sum()} ({(tp > 0).mean()*100:.1f}%)")
    print(f"  空仓天数: {(tp == 0).sum()} ({(tp == 0).mean()*100:.1f}%)")
    print(f"  仓位切换: {(tp.diff().abs() > 1e-9).sum()} 次")
    print(f"  平均仓位: {tp.mean():.4f}")

    print(f"\n{'='*60}")
    print(f"✅ Mock 交付完成！请将文件发送给研究员 D (孙海崴)")
    print(f"   他可以立即基于此文件搭建 Backtrader 回测框架 (D-1)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
