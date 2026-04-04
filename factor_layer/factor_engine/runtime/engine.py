"""运行时入口：``FactorEngine`` 负责 compile（Expr→IR→Plan）与 run（后端执行）。

合并说明：保留上游 ``factor_engine`` 的 CSE / ``run_many`` / ``PerfConfig``；保留本仓库的日志与因子物化（``materialize*``）。
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from api.dsl_parser import parse_factor
from api.factor import Factor
from backend.context import ExecutionContext
from backend.factory import build_backend
from ir.analyzer import AnalysisResult, Analyzer
from logging_utils import get_logger
from planner.cse import apply_cse
from planner.dag import DAGPlan, FactorPlan
from planner.logical_plan import PlanNode
from planner.lowerer import Lowerer
from planner.optimizer import Optimizer
from runtime.config import load_config
from runtime.perf_config import PerfConfig
from storage.cache import CacheManager
from storage.factory import build_data_source
from storage.materializer import ParquetMaterializer

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
            getattr(analysis, "lookback", None),
            time.perf_counter() - started_at,
        )
        return optimized_plan, analysis

    def _dag_from_factors(
        self,
        factors: Sequence[Factor],
        *,
        enable_cse: bool | None = None,
        perf: PerfConfig | None = None,
    ) -> tuple[DAGPlan, dict[str, AnalysisResult]]:
        """编译多因子并可选 CSE；每个因子只 ``compile`` 一次。"""
        perf = perf or PerfConfig.from_env()
        if enable_cse is None:
            enable_cse = perf.enable_cse
        plans: list[PlanNode] = []
        names: list[str] = []
        analyses: dict[str, AnalysisResult] = {}
        for factor in factors:
            plan, analysis = self.compile(factor)
            plans.append(plan)
            names.append(factor.name)
            analyses[factor.name] = analysis
        if enable_cse and len(plans) > 0:
            new_plans, shared = apply_cse(plans)
        else:
            new_plans, shared = plans, {}
        roots = [
            FactorPlan(factor_name=n, root=r) for n, r in zip(names, new_plans, strict=True)
        ]
        return DAGPlan(roots=roots, shared_nodes=shared), analyses

    def compile_many(
        self,
        factors: Sequence[Factor],
        *,
        enable_cse: bool | None = None,
        perf: PerfConfig | None = None,
    ) -> DAGPlan:
        """多因子编译：可选 **公共子表达式消除（CSE）**，重复子树只保留一份于 ``shared_nodes``。

        CSE 默认开启；可用环境变量 ``FACTOR_ENGINE_DISABLE_CSE=1`` 关闭，或传入
        ``perf=PerfConfig.from_env()`` / ``enable_cse=False``。
        """
        dag, _ = self._dag_from_factors(
            factors, enable_cse=enable_cse, perf=perf
        )
        return dag

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
        """一键从配置文件执行因子并落盘到因子湖（Parquet）。"""
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
        """执行单因子并将结果落盘到 factor lake（Parquet）。"""
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

    def run_many(
        self,
        factors: Sequence[Factor],
        *,
        perf: PerfConfig | None = None,
        enable_cse: bool | None = None,
    ) -> dict[str, Any]:
        """多因子求值：先执行 ``DAGPlan.shared_nodes``，再各因子根；含 ``plan_ref`` 时必须用此入口。"""
        dag, analyses = self._dag_from_factors(
            factors, enable_cse=enable_cse, perf=perf
        )
        perf = perf or PerfConfig.from_env()
        ctx = ExecutionContext(
            data_source=self.data_source,
            cache=self.cache,
            shared_result_cache={},
            perf=perf,
        )
        if ctx.shared_result_cache is not None:
            for sid, sub in dag.shared_nodes.items():
                ctx.shared_result_cache[sid] = self.backend.execute(sub, ctx)
        out: dict[str, Any] = {}
        for fp in dag.roots:
            out[fp.factor_name] = self.backend.execute(fp.root, ctx)
        return {
            "results": out,
            "dag": dag,
            "analyses": analyses,
        }

    def run_many_parallel(
        self,
        factors: Sequence[Factor],
        *,
        n_jobs: int | None = None,
        perf: PerfConfig | None = None,
        enable_cse: bool | None = None,
    ) -> dict[str, Any]:
        """在 ``run_many`` 基础上对**各因子根**并行求值（共享子式仍先串行算完）。"""
        try:
            from joblib import Parallel, delayed
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "run_many_parallel 需要 joblib：pip install 'factor-engine[parallel]'"
            ) from exc

        dag, analyses = self._dag_from_factors(
            factors, enable_cse=enable_cse, perf=perf
        )
        perf = perf or PerfConfig.from_env()
        workers = n_jobs if n_jobs is not None else perf.max_workers
        ctx = ExecutionContext(
            data_source=self.data_source,
            cache=self.cache,
            shared_result_cache={},
            perf=perf,
        )
        if ctx.shared_result_cache is not None:
            for sid, sub in dag.shared_nodes.items():
                ctx.shared_result_cache[sid] = self.backend.execute(sub, ctx)

        def _one(fp: FactorPlan):
            res = self.backend.execute(fp.root, ctx)
            return fp.factor_name, res

        # 默认 threading：共享 ``ExecutionContext`` / 数据源，避免 loky 进程间 pickle 大对象失败
        raw = Parallel(n_jobs=workers, backend="threading")(
            delayed(_one)(fp) for fp in dag.roots
        )
        results = dict(raw)
        return {"results": results, "dag": dag, "analyses": analyses}
