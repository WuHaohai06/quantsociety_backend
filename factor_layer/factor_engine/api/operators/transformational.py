"""变换类算子 API：``bucket``（截面分桶）、``trade_when``（有状态持仓信号）。

参数名 ``range`` / ``buckets`` / ``skipBoth`` / ``NaNGroup`` 与 WQ DSL 风格一致（注意 ``range``
为 Python 保留含义，此处作参数名使用）。详细语义见 ``expr.transformational`` 与
``docs/operators_semantics.md``。
"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.transformational import Bucket, TradeWhen


def bucket(
    x: Expr,
    range: str | None = None,
    buckets: str | None = None,
    skipBoth: bool = False,
    NaNGroup: bool = False,
) -> Expr:
    """截面分桶：每个时间截面上对 ``x`` 做分位 rank 后再分箱，得到桶 id（浮点）。

    - ``buckets="N"``：等频 N 档（优先于 ``range``）。
    - ``range="0.2,0.4,..."``：(0,1) 内切分点，档数为切点数+1。
    - ``skipBoth=True``：最低/最高档内的有效点置 NaN。
    - ``NaNGroup=True``：输入 NaN 输出 -1.0；否则输出 NaN。

    不是时序分位桶；时序请用 ``ts_rank`` / ``ts_quantile`` 等组合。
    """
    return Bucket(
        child=ensure_expr(x),
        range_spec=range,
        buckets_spec=buckets,
        skip_both=skipBoth,
        nan_group=NaNGroup,
    )


def trade_when(trigger: Expr, alpha: Expr, exit_: Expr) -> Expr:
    """有状态：每标的沿时间维护对外输出的持仓值（alpha）。

    单 bar 语义（详见 ``docs/adr_trade_when.md``）：``exit_`` 真则清空；否则 ``trigger`` 真则
    取当前 ``alpha``；否则重复上一 bar 输出。trigger/exit 的 NaN 当假。用于「条件触发更新、
    否则持有」类逻辑，不是无状态的 ``if_else``。
    """
    return TradeWhen(
        trigger=ensure_expr(trigger),
        alpha=ensure_expr(alpha),
        exit_=ensure_expr(exit_),
    )
