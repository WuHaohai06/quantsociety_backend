"""运行时入口：``FactorEngine`` 负责 compile（Expr→IR→Plan）与 run（后端执行）。"""

from pathlib import Path

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

from ir.analyzer import Analyzer


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
        analysis = self.analyzer.lower(factor.expr)
        logical_plan = self.lowerer.to_logical_plan(analysis.ir)
        optimized_plan = self.optimizer.optimize(logical_plan)
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
        return cls(backend=backend, data_source=data_source, cache=cache), factor, config

    @classmethod
    def run_from_config(cls, config_path: str | Path):
        """一键从配置文件跑因子，结果里附带 config 对象。"""
        engine, factor, config = cls.from_config(config_path)
        result = engine.run(factor)
        result["config"] = config
        return result

    def run(self, factor: Factor):
        """编译后调用 ``backend.execute``，返回 factor、analysis、plan、result。"""
        plan, analysis = self.compile(factor)
        ctx = ExecutionContext(data_source=self.data_source, cache=self.cache)
        result = self.backend.execute(plan, ctx)
        return {
            "factor": factor,
            "analysis": analysis,
            "plan": plan,
            "result": result,
        }
