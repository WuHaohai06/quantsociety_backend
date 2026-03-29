"""
变换类算子（WorldQuant — Transformational）。

与「每期只依赖当前截面」的 rank/zscore 不同，本模块里：

- **Bucket**：在**每个时间截面**内把连续值变成离散桶 id（先截面分位 rank，再分箱），用于
  分位数组合、与 ``group_*`` 联用等。不是「过去 d 天的分位」，时序分位请用 ``ts_rank`` /
  ``ts_quantile`` 等。

- **TradeWhen**：**有状态**算子——对每个标的沿时间记住「当前对外输出的持仓 alpha」。
  不是逐 bar 独立的 ``if_else``；语义见 ``docs/adr_trade_when.md``，后端必须按 instrument
  内时间序扫描实现。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class Bucket(Expr):
    """截面分桶：同一 ``timestamp`` 上对所有标的的 ``child`` 先算分位排名，再映射成桶编号。

    **直觉**：某一时刻全市场按 ``child`` 从低到高排队，再把 [0,1) 上的分位切成若干档，
    每档一个浮点桶 id（从 0 起）。用于「动量五分组」「价值十分位」等离散暴露。

    **参数与 DSL**（细节以 ``docs/operators_semantics.md`` 为准）：

    - ``buckets_spec``（DSL: ``buckets=``）：如 ``"5"`` 表示近似 **等频** 5 档，
      ``floor(rank_pct * N)`` 钳到 ``[0, N-1]``；与 ``range_spec`` 同时存在时通常优先用 buckets。
    - ``range_spec``（DSL: ``range=``）：逗号分隔的 (0,1) 内切分点，升序；桶 id 为
      ``searchsorted`` 结果，共 ``len(cuts)+1`` 档。
    - ``skip_both``：为 True 时，**最低档与最高档**内的有效点输出 NaN（常用来丢掉极端组）。
    - ``nan_group``：为 True 时输入 NaN 输出 **-1.0** 作为「缺失组」标记；为 False 则输出 NaN。

    **易错点**：桶是 **截面** 相对位置，随当日横截面分布而变；跨日比较的是「当日属于哪一档」，
    不是「与自己历史相比」。
    """

    child: Expr
    range_spec: str | None = None
    buckets_spec: str | None = None
    skip_both: bool = False
    nan_group: bool = False

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TradeWhen(Expr):
    """按标的维护一条「持仓信号」时间序列：何时采纳 ``alpha``、何时强制平仓、其余时刻保持。

    **状态变量**：对每个 ``instrument``，在时间上维护标量 ``position``（本 bar 输出值；未持仓为 NaN）。
    遍历顺序为 **该标的内时间升序**（与 MultiIndex 中停牌导致的缺失一致：只对有数据的 bar 更新）。

    **单步规则**（与 ``docs/adr_trade_when.md`` 一致，便于和回测对齐）：

    1. 若本 bar ``exit_`` 判真（>0.5 或 ==1）：先 **清空**，``position ← NaN``，本 bar 输出 NaN。
    2. 否则若 ``trigger`` 判真：``position ←`` 当前 ``alpha`` 的数值（alpha 为 NaN 则 position 为 NaN）。
    3. 否则：**输出上一 bar 的 position**（保持不变；即「持有直到触发或 exit」）。
    4. ``trigger`` / ``exit_`` / 比较用的量为 **NaN** 时视为假，避免缺失误触发。

    **与 ``if_else`` 的区别**：``if_else`` 无记忆；本算子显式建模 **路径依赖**，用于简化
    「满足条件才更新仓位、否则延续」类表达式，**不包含**滑点、手续费、撮合延迟（非目标见 ADR）。

    **子节点顺序**：``trigger``, ``alpha``, ``exit_``（与 WQ 三参数顺序一致）。
    """

    trigger: Expr
    alpha: Expr
    exit_: Expr

    def children(self) -> tuple[Expr, Expr, Expr]:
        return (self.trigger, self.alpha, self.exit_)
