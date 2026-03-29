# ADR：`ts_step` 与 `hump`

> **第 10 版更改-shw**：与 Pandas 实装同步，约定与 WQ 可能差异处。

## `ts_step(d, anchor)`

- **输出**：与 `anchor` **相同索引**；在每个 `instrument` 内按 **时间升序**，第 `i` 根 bar（从 0 计）输出 **`float(i % d)`**，周期为 `d`。
- **`anchor`**：任意与因子同形的表达式，**仅用于对齐 MultiIndex**；其数值不参与步进计算。
- **API**：必须显式传入 `anchor`（例如 `ts_step(5, col("close"))`），避免无列引用时无法确定面板形状。

与部分平台上「全局交易日计数」的 `ts_step` 可能不一致；本引擎以 **标的本地 bar 序** 为准。

## `hump(x, hump=0.01)`

- **按 instrument、时间升序**：记上一根**已输出**值为 `out_{t-1}`（首根有效输入前无输出则用当前输入初始化）。
- 当前输入 `x_t` 有限时：`out_t = clip(x_t, out_{t-1} - h, out_{t-1} + h)`；`h` 为 `hump` 参数。
- 输入为 NaN：输出 NaN，**不更新**内部 `out` 状态（下一有效 bar 仍相对上一有效输出裁剪）。

## 实现

- [`backend/pandas_backend.py`](../backend/pandas_backend.py)：`PandasBackend._op_ts_step`、`_op_hump`
