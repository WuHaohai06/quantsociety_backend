from __future__ import annotations

import pandas as pd
import pytest

from single_asset_backtest.contracts import (
    align_target_position_to_index,
    align_target_weights_to_index,
    validate_target_position,
    validate_target_weights,
)


def test_validate_target_position_ffill_and_default_zero():
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "target_position": [0.2, None, 0.4],
        }
    )

    out = validate_target_position(frame)
    assert float(out.iloc[0]) == pytest.approx(0.2)
    assert float(out.iloc[1]) == pytest.approx(0.2)
    assert float(out.iloc[2]) == pytest.approx(0.4)


def test_validate_target_position_reject_out_of_range_strict():
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01"],
            "target_position": [1.2],
        }
    )

    with pytest.raises(ValueError, match="out of bounds"):
        validate_target_position(frame, strict=True)


def test_validate_target_position_reject_duplicate_timestamps():
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01", "2026-01-01"],
            "target_position": [0.1, 0.2],
        }
    )

    with pytest.raises(ValueError, match="duplicate timestamps"):
        validate_target_position(frame)


def test_align_target_position_to_index_uses_ffill():
    s = pd.Series(
        [0.1, -0.2],
        index=pd.to_datetime(["2026-01-01", "2026-01-03"]),
        name="target_position",
    )
    idx = pd.date_range("2026-01-01", periods=4, freq="D")

    aligned = align_target_position_to_index(s, idx)

    assert aligned.index.equals(idx)
    assert aligned.to_list() == pytest.approx([0.1, 0.1, -0.2, -0.2])


def test_validate_target_weights_dataframe_and_bounds():
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"],
            "symbol": ["XAU", "XAG", "XAU", "XAG"],
            "target_weight": [0.6, 0.4, 0.5, -0.5],
        }
    )

    out = validate_target_weights(frame)
    assert isinstance(out.index, pd.MultiIndex)
    assert float(out.loc[(pd.Timestamp("2026-01-01"), "XAU")]) == pytest.approx(0.6)


def test_validate_target_weights_reject_gross_leverage_over_limit():
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01", "2026-01-01"],
            "symbol": ["XAU", "XAG"],
            "target_weight": [0.8, 0.6],
        }
    )

    with pytest.raises(ValueError, match="gross leverage exceeds"):
        validate_target_weights(frame, max_gross_leverage=1.0)


def test_align_target_weights_to_index_ffill_and_fill_zero():
    raw = pd.DataFrame(
        {
            "timestamp": ["2026-01-01", "2026-01-03"],
            "symbol": ["XAU", "XAG"],
            "target_weight": [0.5, -0.2],
        }
    )
    weights = validate_target_weights(raw)

    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    aligned = align_target_weights_to_index(weights, idx, symbols=["XAU", "XAG"])

    assert float(aligned.loc[(pd.Timestamp("2026-01-01"), "XAU")]) == pytest.approx(0.5)
    assert float(aligned.loc[(pd.Timestamp("2026-01-02"), "XAU")]) == pytest.approx(0.5)
    assert float(aligned.loc[(pd.Timestamp("2026-01-02"), "XAG")]) == pytest.approx(0.0)
    assert float(aligned.loc[(pd.Timestamp("2026-01-04"), "XAG")]) == pytest.approx(-0.2)
