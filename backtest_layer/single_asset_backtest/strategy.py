from __future__ import annotations

"""Backtrader 策略混入类：在每根 K 线上记录权益、目标/实现仓位，并可选采集成交账本（工业指标）。

``TargetPositionStrategyMixin`` 被 ``strategy_library`` 内嵌策略类继承；回调 ``notify_order`` / ``notify_trade`` 由 Backtrader 触发。
"""
from dataclasses import dataclass


@dataclass
class StrategyTrace:
    """策略运行过程逐 bar 轨迹（时间戳与列表对齐）；供 ``runner`` 组装报告。"""

    timestamps: list
    equity_curve: list[float]
    realized_position: list[float]
    target_position: list[float]
    commission_paid: float = 0.0
    trades: int = 0
    trade_ledger: list[dict] | None = None


class TargetPositionStrategyMixin:
    """与 Backtrader ``bt.Strategy`` 多重继承时使用：统一初始化 trace 与账本采集逻辑。"""

    def _init_trace(self, *, include_trade_ledger: bool = False) -> None:
        """初始化逐 bar 轨迹容器；``include_trade_ledger`` 为 True 时分配事件列表供回调追加。"""
        self.trace = StrategyTrace(
            timestamps=[],
            equity_curve=[],
            realized_position=[],
            target_position=[],
            trade_ledger=[] if include_trade_ledger else None,
        )
        self._track_trade_ledger = bool(include_trade_ledger)
        self._active_trade: dict | None = None

    def _record_bar(self, timestamp, target_weight: float) -> None:
        """每根 bar 结束记录：权益、目标权重；实现权重 = 持仓市值 / 总权益（空仓为 0）。"""
        broker_value = float(self.broker.getvalue())
        close_px = float(self.data.close[0])
        pos_size = float(self.position.size)
        pos_value = pos_size * close_px
        realized_weight = 0.0 if broker_value == 0 else pos_value / broker_value

        self.trace.timestamps.append(timestamp)
        self.trace.equity_curve.append(broker_value)
        self.trace.realized_position.append(realized_weight)
        self.trace.target_position.append(float(target_weight))

        # 持仓存续期间：用当根 K 线高低价相对开仓价更新 MFE（有利摆动）/ MAE（不利摆动）
        if self._track_trade_ledger and self._active_trade is not None and pos_size != 0.0:
            high_px = float(self.data.high[0])
            low_px = float(self.data.low[0])
            self._active_trade["holding_bars"] += 1
            entry = float(self._active_trade["entry_price"])
            direction = int(self._active_trade["direction"])
            if entry > 0.0:
                if direction > 0:
                    favorable = (high_px / entry) - 1.0
                    adverse = (low_px / entry) - 1.0
                else:
                    favorable = (entry / max(low_px, 1e-12)) - 1.0
                    adverse = (entry / max(high_px, 1e-12)) - 1.0
                self._active_trade["mfe"] = max(float(self._active_trade["mfe"]), float(favorable))
                self._active_trade["mae"] = min(float(self._active_trade["mae"]), float(adverse))

    def notify_order(self, order):  # pragma: no cover - callback from backtrader
        """订单成交：累计笔数、佣金；可选写入 ledger；若新开仓则初始化 MFE/MAE 跟踪。"""
        if order.status != order.Completed:
            return

        self.trace.trades += 1
        comm = float(getattr(order.executed, "comm", 0.0) or 0.0)
        self.trace.commission_paid += comm

        exec_dt = order.executed.dt
        event_dt = self.data.num2date(exec_dt).replace(tzinfo=None) if exec_dt else None
        exec_price = float(getattr(order.executed, "price", 0.0) or 0.0)

        if self.trace.trade_ledger is not None:
            self.trace.trade_ledger.append(
                {
                    "event": "order_completed",
                    "datetime": event_dt,
                    "isbuy": bool(order.isbuy()),
                    "size": float(getattr(order.executed, "size", 0.0) or 0.0),
                    "price": exec_price,
                    "value": float(getattr(order.executed, "value", 0.0) or 0.0),
                    "commission": comm,
                    "order_ref": int(getattr(order, "ref", -1) or -1),
                }
            )

        pos_size = float(self.position.size)
        # 有持仓且无在途记录时，视为新开仓起点（工业微观指标用）
        if pos_size != 0.0 and self._active_trade is None:
            self._active_trade = {
                "entry_datetime": event_dt,
                "entry_price": exec_price,
                "direction": 1 if pos_size > 0 else -1,
                "holding_bars": 0,
                "mfe": 0.0,
                "mae": 0.0,
            }

    def notify_trade(self, trade):  # pragma: no cover - callback from backtrader
        """Backtrader 一笔 trade 生命周期结束：合并 ledger 平仓事件并清空 active 状态。"""
        if not trade.isclosed:
            return

        if self.trace.trade_ledger is not None:
            close_dt = self.data.datetime.datetime(0).replace(tzinfo=None)
            close_px = float(self.data.close[0])
            payload = {
                "event": "trade_closed",
                "datetime": close_dt,
                "pnl": float(getattr(trade, "pnl", 0.0) or 0.0),
                "pnlcomm": float(getattr(trade, "pnlcomm", 0.0) or 0.0),
                "size": float(getattr(trade, "size", 0.0) or 0.0),
            }
            if self._active_trade is not None:
                payload.update(
                    {
                        "entry_datetime": self._active_trade.get("entry_datetime"),
                        "exit_datetime": close_dt,
                        "entry_price": float(self._active_trade.get("entry_price", 0.0) or 0.0),
                        "exit_price": close_px,
                        "direction": int(self._active_trade.get("direction", 0) or 0),
                        "holding_bars": int(self._active_trade.get("holding_bars", 0) or 0),
                        "mfe": float(self._active_trade.get("mfe", 0.0) or 0.0),
                        "mae": float(self._active_trade.get("mae", 0.0) or 0.0),
                    }
                )
            self.trace.trade_ledger.append(payload)

        self._active_trade = None
