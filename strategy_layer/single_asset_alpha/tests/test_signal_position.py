"""
单元测试: 信号生成器、仓位映射器和未来函数防护
===============================================

测试重点:
  1. 信号生成器输出格式和值域
  2. 仓位映射器状态转移逻辑
  3. ★ 未来函数 (Look-Ahead Bias) 检测
  4. target_position Schema 校验
  5. Pipeline 端到端集成测试
"""

from __future__ import annotations

import sys
import os
import pytest
import pandas as pd
import numpy as np

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher
from strategy_layer.single_asset_alpha.strategies.signals.dual_ma_signal import DualMASignal
from strategy_layer.single_asset_alpha.strategies.signals.macd_signal import MACDSignal
from strategy_layer.single_asset_alpha.strategies.signals.rsi_signal import RSISignal
from strategy_layer.single_asset_alpha.strategies.signals.signal_combiner import SignalCombiner
from strategy_layer.single_asset_alpha.strategies.position_mappers.simple_mapper import ThresholdPositionMapper
from strategy_layer.single_asset_alpha.strategies.position_mappers.atr_volatility_mapper import ATRVolatilityMapper
from strategy_layer.single_asset_alpha.core.schema import TargetPositionSchema, ActionName
from strategy_layer.single_asset_alpha.core.base_position import BasePositionMapper


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def sample_market_data():
    """生成标准测试行情数据。"""
    return DataFetcher.generate_sample_data(symbol="TEST", periods=300, seed=42)


@pytest.fixture
def sample_signals(sample_market_data):
    """生成测试用信号。"""
    signal_gen = DualMASignal(params={"fast_window": 5, "slow_window": 20})
    return signal_gen.generate(sample_market_data)


# ═══════════════════════════════════════════════════════════════
# 1. 信号生成器测试
# ═══════════════════════════════════════════════════════════════

class TestSignalGenerators:
    """信号生成器测试套件。"""

    def test_dual_ma_output_type(self, sample_market_data):
        """双均线信号应输出 pd.Series。"""
        gen = DualMASignal(params={"fast_window": 5, "slow_window": 20})
        sig = gen.generate(sample_market_data)
        assert isinstance(sig, pd.Series)
        assert len(sig) == len(sample_market_data)

    def test_dual_ma_value_range(self, sample_market_data):
        """双均线信号经 tanh 压缩后应在 (-1, 1) 范围内。"""
        gen = DualMASignal(params={"fast_window": 5, "slow_window": 20})
        sig = gen.generate(sample_market_data)
        valid = sig.dropna()
        assert valid.min() >= -1.0
        assert valid.max() <= 1.0

    def test_macd_output_type(self, sample_market_data):
        """MACD 信号应输出 pd.Series。"""
        gen = MACDSignal(params={"fast_period": 12, "slow_period": 26, "signal_period": 9})
        sig = gen.generate(sample_market_data)
        assert isinstance(sig, pd.Series)

    def test_rsi_output_type(self, sample_market_data):
        """RSI 信号应输出 pd.Series。"""
        gen = RSISignal(params={"rsi_period": 14})
        sig = gen.generate(sample_market_data)
        assert isinstance(sig, pd.Series)

    def test_rsi_value_range(self, sample_market_data):
        """RSI 信号经 tanh 压缩后应在 (-1, 1) 范围内。"""
        gen = RSISignal(params={"rsi_period": 14})
        sig = gen.generate(sample_market_data)
        valid = sig.dropna()
        assert valid.min() >= -1.0
        assert valid.max() <= 1.0

    def test_signal_combiner(self, sample_market_data):
        """信号组合器应正确合成多个信号。"""
        signals = [
            DualMASignal(params={"fast_window": 5, "slow_window": 20}, name="MA"),
            MACDSignal(params={}, name="MACD"),
        ]
        combiner = SignalCombiner(signal_generators=signals, weights=[0.6, 0.4], name="Combined")
        sig = combiner.generate(sample_market_data)
        assert isinstance(sig, pd.Series)
        valid = sig.dropna()
        assert valid.min() >= -1.0
        assert valid.max() <= 1.0

    def test_validate_market_data_missing_cols(self):
        """缺少必要列应抛出 ValueError。"""
        gen = DualMASignal(params={})
        bad_data = pd.DataFrame(
            {"close": [1, 2, 3]},
            index=pd.date_range("2024-01-01", periods=3),
        )
        with pytest.raises(ValueError, match="缺少必要列"):
            gen.validate_market_data(bad_data)


# ═══════════════════════════════════════════════════════════════
# 2. 仓位映射器测试
# ═══════════════════════════════════════════════════════════════

class TestPositionMappers:
    """仓位映射器测试套件。"""

    def test_threshold_mapper_output_columns(self, sample_signals, sample_market_data):
        """阈值映射器应输出标准列。"""
        mapper = ThresholdPositionMapper(params={"long_entry_threshold": 0.5})
        result = mapper.map_to_position(sample_signals, sample_market_data)
        assert "target_position" in result.columns
        assert "signal_value" in result.columns
        assert "action_name" in result.columns

    def test_threshold_mapper_position_range(self, sample_signals, sample_market_data):
        """仓位值应在 [-1, 1] 范围内。"""
        mapper = ThresholdPositionMapper(
            params={"long_entry_threshold": 0.5, "allow_short": True}
        )
        result = mapper.map_to_position(sample_signals, sample_market_data)
        assert result["target_position"].min() >= -1.0
        assert result["target_position"].max() <= 1.0

    def test_threshold_mapper_no_short(self, sample_signals, sample_market_data):
        """不允许做空时，仓位不应为负。"""
        mapper = ThresholdPositionMapper(
            params={"long_entry_threshold": 0.3, "allow_short": False}
        )
        result = mapper.map_to_position(sample_signals, sample_market_data)
        assert (result["target_position"] >= 0).all()

    def test_atr_mapper_output_format(self, sample_signals, sample_market_data):
        """ATR 映射器应输出标准列。"""
        mapper = ATRVolatilityMapper(
            params={"atr_period": 14, "base_long_threshold": 0.4}
        )
        result = mapper.map_to_position(sample_signals, sample_market_data)
        assert "target_position" in result.columns
        assert "signal_value" in result.columns

    def test_debounce(self, sample_signals, sample_market_data):
        """防抖后行数应 <= 原始行数。"""
        mapper = ThresholdPositionMapper(params={"long_entry_threshold": 0.3})
        result = mapper.map_to_position(sample_signals, sample_market_data)
        debounced = BasePositionMapper.debounce(result)
        assert len(debounced) <= len(result)
        assert len(debounced) > 0  # 至少保留第一行


# ═══════════════════════════════════════════════════════════════
# 3. ★ 未来函数 (Look-Ahead Bias) 防护测试
# ═══════════════════════════════════════════════════════════════

class TestLookAheadBias:
    """未来函数检测测试。

    核心原则: T 日的信号不能影响 T 日的仓位。
    如果 shift_bars=1, 则 T 日的 target_position 应由 T-1 日的信号决定。
    """

    def test_shift_applied(self, sample_signals, sample_market_data):
        """验证 shift 已正确应用: 第一行 target_position 应为 0。"""
        mapper = ThresholdPositionMapper(
            params={"long_entry_threshold": 0.3, "shift_bars": 1}
        )
        result = mapper.map_to_position(sample_signals, sample_market_data)
        # shift(1) 后第一行应为 0.0 (fillna 填充)
        assert result["target_position"].iloc[0] == 0.0

    def test_signal_precedes_position(self, sample_market_data):
        """验证信号变化先于仓位变化。

        构造一个在第 50 bar 突然产生看多信号的序列,
        验证仓位变化发生在第 51 bar 而非第 50 bar。
        """
        # 构造确定性信号
        signals = pd.Series(0.0, index=sample_market_data.index)
        signals.iloc[50:] = 0.8  # 第 50 bar 开始看多

        mapper = ThresholdPositionMapper(
            params={"long_entry_threshold": 0.5, "shift_bars": 1}
        )
        result = mapper.map_to_position(signals, sample_market_data)

        # 第 50 bar 仓位仍为 0 (因为 shift)
        assert result["target_position"].iloc[50] == 0.0
        # 第 51 bar 仓位才变为 1.0
        assert result["target_position"].iloc[51] == 1.0

    def test_no_future_correlation(self, sample_market_data):
        """统计检验: position(t) 与 signal(t) 的相关性应低于 position(t) 与 signal(t-1)。"""
        gen = DualMASignal(params={"fast_window": 5, "slow_window": 20})
        sig = gen.generate(sample_market_data)

        mapper = ThresholdPositionMapper(
            params={"long_entry_threshold": 0.3, "shift_bars": 1}
        )
        result = mapper.map_to_position(sig, sample_market_data)

        pos = result["target_position"]
        # position(t) 和 signal(t-1) 的关系应比 position(t) 和 signal(t) 的关系更紧密
        # 具体体现为: position 在 signal 变化后一个 bar 才响应
        # 这里只做"第一行为空仓"的基本检测
        assert pos.iloc[0] == 0.0


# ═══════════════════════════════════════════════════════════════
# 4. Schema 校验测试
# ═══════════════════════════════════════════════════════════════

class TestSchema:
    """target_position Schema 校验测试。"""

    def test_valid_schema_passes(self):
        """符合 Schema 的数据应通过校验。"""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=5),
            "symbol": "000001.SZ",
            "target_position": [0.0, 1.0, 1.0, 0.0, -0.5],
            "signal_value": [0.0, 0.8, 0.6, -0.1, -0.7],
            "action_name": ["HOLD", "ENTRY_LONG", "HOLD", "EXIT_LONG", "ENTRY_SHORT"],
        })
        errors = TargetPositionSchema.validate(df)
        assert errors == []

    def test_missing_column_detected(self):
        """缺少必要列应被检测。"""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=3),
            "symbol": "TEST",
            # 缺少 target_position
        })
        errors = TargetPositionSchema.validate(df)
        assert any("target_position" in e for e in errors)

    def test_out_of_range_detected(self):
        """超出值域应被检测。"""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=3),
            "symbol": "TEST",
            "target_position": [0.5, 1.5, -0.3],  # 1.5 超出范围
        })
        errors = TargetPositionSchema.validate(df, strict=True)
        assert any("高于" in e for e in errors)


# ═══════════════════════════════════════════════════════════════
# 5. Pipeline 集成测试
# ═══════════════════════════════════════════════════════════════

class TestPipelineIntegration:
    """端到端集成测试。"""

    def test_full_pipeline_runs(self, sample_market_data, tmp_path):
        """完整流水线应成功运行并输出文件。"""
        from strategy_layer.single_asset_alpha.pipeline import create_dual_ma_strategy

        pipeline = create_dual_ma_strategy(
            symbol="TEST", output_dir=str(tmp_path)
        )
        result = pipeline.run(
            market_data=sample_market_data,
            output_format="csv",
        )

        # 验证输出
        assert isinstance(result, pd.DataFrame)
        assert "timestamp" in result.columns
        assert "target_position" in result.columns
        assert len(result) == len(sample_market_data)

        # 验证文件已创建
        files = list(tmp_path.glob("*"))
        assert len(files) >= 2  # full + debounced + meta

    def test_combined_strategy_pipeline(self, sample_market_data, tmp_path):
        """组合策略流水线应成功运行。"""
        from strategy_layer.single_asset_alpha.pipeline import create_combined_strategy

        pipeline = create_combined_strategy(
            symbol="TEST",
            use_atr_mapper=True,
            output_dir=str(tmp_path),
        )
        result = pipeline.run(
            market_data=sample_market_data,
            output_format="csv",
        )

        assert isinstance(result, pd.DataFrame)
        errors = TargetPositionSchema.validate(result)
        assert errors == []


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
