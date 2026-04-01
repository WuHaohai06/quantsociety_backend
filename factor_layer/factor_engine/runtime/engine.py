"""运行时入口：``FactorEngine`` 负责 compile（Expr→IR→Plan）与 run（后端执行）。"""

from pathlib import Path
import time

from api.dsl_parser import parse_factor
from collections.abc import Sequence

from api.factor import Factor
from backend.factory import build_backend
from backend.context import ExecutionContext
from planner.dag import DAGPlan, FactorPlan
from planner.lowerer import Lowerer
from planner.optimizer import Optimizer
from runtime.config import load_config
from storage.cache import CacheManager
from storage.factory import build_data_source
from storage.materializer import ParquetMaterializer
from logging_utils import get_logger

from ir.analyzer import Analyzer


logger = get_logger("runtime.engine")


class FactorEngine:
    """因子引擎：注入后端与数据源，对 :class:`api.factor.Factor` 做编译与执行。"""

    def __init__(self, backend, data_source, cache=None) -> None:
        self.backend = backend
        self.data_source = data_source
        self.cache = cache
        self.analyzer = Analyzer()
        self.lowerer = Lowerer()
        self.optimizer = Optimizer()

    def compile(self, factor: Factor):
        """Expr → Analyzer → Lowerer → Optimizer，返回 (plan, analysis)。"""
        started_at = time.perf_counter()
        logger.info("开始编译因子 '%s'", factor.name)
        analysis = self.analyzer.lower(factor.expr)
        logical_plan = self.lowerer.to_logical_plan(analysis.ir)
        optimized_plan = self.optimizer.optimize(logical_plan)
        logger.info(
            "完成编译因子 '%s'，lookback=%s，耗时 %.2fs",
            factor.name,
            analysis.lookback,
            time.perf_counter() - started_at,
        )
        return optimized_plan, analysis

    def compile_many(self, factors: Sequence[Factor]) -> DAGPlan:
        """多因子根计划列表（共享子式优化可后续做）。"""
        roots: list[FactorPlan] = []
        for factor in factors:
            plan, _ = self.compile(factor)
            roots.append(FactorPlan(factor_name=factor.name, root=plan))
        return DAGPlan(roots=roots)

    @classmethod
    def from_config(cls, config_path: str | Path):
        """读 YAML：建 backend、数据源、可选缓存，并解析因子表达式。"""
        logger.info("加载配置文件: %s", config_path)
        config = load_config(config_path)
        backend = build_backend(config.backend.type)
        data_source = build_data_source(config.data_source)
        cache = CacheManager() if config.engine.enable_cache else None
        factor = parse_factor(
            config.factor.expr,
            name=config.factor.name,
            freq=config.factor.freq,
            universe=config.factor.universe,
            description=config.factor.description,
        )
        logger.info(
            "配置加载完成: factor=%s, backend=%s, data_source=%s, cache=%s",
            factor.name,
            type(backend).__name__,
            type(data_source).__name__,
            "on" if cache is not None else "off",
        )
        return cls(backend=backend, data_source=data_source, cache=cache), factor, config

    @classmethod
    def run_from_config(cls, config_path: str | Path):
        """一键从配置文件跑因子，结果里附带 config 对象。"""
        logger.info("开始从配置执行因子: %s", config_path)
        engine, factor, config = cls.from_config(config_path)
        result = engine.run(factor)
        result["config"] = config
        logger.info("完成从配置执行因子: %s", factor.name)
        return result

    @classmethod
    def materialize_from_config(
        cls,
        config_path: str | Path,
        *,
        lake_root: str | Path | None = None,
        factor_id: str | None = None,
        author: str | None = None,
        frequency: str | None = None,
        description: str | None = None,
        expression: str | None = None,
    ):
        """一键从配置文件执行因子并落盘。"""
        logger.info("开始从配置物化因子: %s", config_path)
        engine, factor, config = cls.from_config(config_path)
        materialization = config.materialization
        result = engine.materialize(
            factor,
            lake_root=lake_root or (materialization.lake_root if materialization else None),
            factor_id=factor_id or (materialization.factor_id if materialization else None),
            author=author or (materialization.author if materialization else None),
            frequency=frequency or (materialization.frequency if materialization else None),
            description=description or (materialization.description if materialization else None),
            expression=(
                expression
                or (materialization.expression if materialization else None)
                or config.factor.expr
            ),
        )
        result["config"] = config
        logger.info("完成从配置物化因子: %s", factor.name)
        return result

    def run(self, factor: Factor):
        """编译后调用 ``backend.execute``，返回 factor、analysis、plan、result。"""
        started_at = time.perf_counter()
        logger.info("开始执行因子 '%s'", factor.name)
        plan, analysis = self.compile(factor)
        ctx = ExecutionContext(data_source=self.data_source, cache=self.cache)
        result = self.backend.execute(plan, ctx)
        non_null_count = int(result.notna().sum()) if hasattr(result, "notna") else None
        logger.info(
            "完成执行因子 '%s'，结果行数=%s，非空=%s，耗时 %.2fs",
            factor.name,
            len(result),
            non_null_count,
            time.perf_counter() - started_at,
        )
        return {
            "factor": factor,
            "analysis": analysis,
            "plan": plan,
            "result": result,
        }

    def materialize(
        self,
        factor: Factor,
        *,
        lake_root: str | Path | None = None,
        factor_id: str | None = None,
        author: str | None = None,
        frequency: str | None = None,
        description: str | None = None,
        expression: str | None = None,
    ):
        """执行单因子并将结果落盘到 factor lake。"""
        logger.info("开始落盘因子 '%s'", factor.name)
        output = self.run(factor)
        materializer = ParquetMaterializer(lake_root=lake_root)
        summary = materializer.materialize(
            factor_id=factor_id or factor.name,
            result=output["result"],
            ir_node=output["analysis"].ir,
            author=author,
            frequency=frequency or factor.freq,
            description=description or factor.description,
            expression=expression,
        )
        output["materialization"] = {
            **summary,
            "lake_root": str(materializer.lake_root),
        }
        logger.info(
            "完成落盘因子 '%s'，factor_id=%s，rows_written=%s",
            factor.name,
            summary["factor_id"],
            summary["rows_written"],
        )
        return output
