"""表达式元数据占位（与 :class:`ir.analyzer.AnalysisResult` 部分职责重叠，可后续合并）。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExprMetadata:
    """单节点上可携带的静态提示：回看长度、是否含时序/截面算子等。"""

    lookback: int = 0
    has_ts_op: bool = False
    has_cs_op: bool = False
