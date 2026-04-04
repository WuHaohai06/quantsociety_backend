# `api/operators` — 算子工厂（详尽说明）

本目录中的每个 **公开函数** 都是 **无状态的工厂**：入参为子 `Expr` 或标量，返回 **`expr/` 包中对应的 `Expr` 子类实例**。  
**不包含** 任何 pandas 计算逻辑；执行阶段由 **`PandasBackend`**（等）根据 IR 的 **`op` 字符串**  dispatch 到具体内核。

### 协作者速览（约 5 分钟）

1. **本目录在干什么**：每个 **公开函数** 返回一个 **`expr.*` 节点实例**（工厂），名字与 **DSL / IR `op`** 对齐；**不写** rolling、截面等具体数值代码。
2. **和 `expr/` 的关系**：**同主题一个文件**（如 `ts.py` ↔ `expr/ts.py`），改 API 时两边一起改。
3. **和 `backend/` 的关系**：后端 **`kernels`** / **`pandas_backend`** 里实现 **`op` 字符串**；新增算子要同步 **语义文档 + 注册表 + 测试**。
4. **快速查找**：按类点 **下面 §2 按文件清单**；占位算子见 **`STUB_IR_OPS`**。

---

## 1. 设计约定

| 约定 | 说明 |
|------|------|
| **命名** | 与 DSL、IR `op`、文档 `operators_semantics.md` **一致**；不另起 PascalCase API。 |
| **占位算子** | 部分名称出现在 `operator_registry.STUB_IR_OPS` 中，Pandas 后端可能 **未实现**，运行时报错。 |
| **列依赖** | 时序/技术类常要求存在 **`open`/`high`/`low`/`close`/`volume`** 等列名，详见语义文档。 |

---

## 2. 按文件完整清单

### [`arithmetic.py`](arithmetic.py)

四则运算封装（`add`/`multiply`/…）、一元 **`abs`/`log`/`sign`/`sqrt`**、**`sin`/`cos`/`exp`** 等。  
与 **`expr/arithmetic.py`** 节点一一对应；DSL 中可与 `col()` 组合。

### [`logical.py`](logical.py)

比较（`eq`、`lt`、…）、**`and_`/`or_`/`not_`**（规避 Python 关键字）、`is_nan`、`if_else` 等。  
**注意**：字符串 DSL 里不能写 `and(...)`，必须 `and_(...)`。

### [`ts.py`](ts.py)

**时序（Time Series）**：`ts_mean`、`ts_delay`、`ts_std`、`ts_max`/`ts_min`、滚动求和/计数，以及大量 **技术指标** 的高层封装（内部仍是一个个 `Expr` 节点，可能调用 `kernels` 或 TA-Lib）。  
文件通常 **体积大**：新增时同步 **`operators_semantics.md`** 与 **后端 `kernels`**。

### [`cs.py`](cs.py)

**截面（Cross-Sectional）**：`rank`、`zscore`、`normalize`、`quantile` 等；语义为 **每个时间截面上** 对多标的运算。

### [`group.py`](group.py)

**分组**：`group_rank`、`group_neutralize` 等；需要数据中存在 **分组列**（如行业），由 `ExecutionContext` 或数据源提供。

### [`cleaning.py`](cleaning.py)

**清洗与稳健化**：`pasteurize`、`protected_div`、`densify` 等，用于控制 inf/NaN/除零。

### [`technical.py`](technical.py)

**技术指标** 入口：与 TA-Lib 或自研公式对接的薄封装；具体窗口与列要求见语义文档。

### [`context.py`](context.py)

**上下文/基准**：如 **`orthogonalize`**（截面回归残差）、**`change_instrument`**（相对基准序列）；见 `docs/adr_context_benchmark.md`。

### [`transformational.py`](transformational.py)

**变换型**：**`bucket`**（分箱）、**`trade_when`**（条件启用）；语义与 ADR 见 `docs/adr_trade_when.md` 等。

### [`intraday.py`](intraday.py)

**分钟/日内** 相关算子：部分为 **stub**（`INTRADAY_STUB_OPS`），与华泰图表等对照；实装进度见 `operators_roadmap.md`。

### [`vector.py`](vector.py)

**向量列** 算子（如 `vec_avg`/`vec_sum`）：需要 **特殊数据契约**（一行多值），当前多为占位。

### [`future_data.py`](future_data.py)

**基本面 / 另类 / 微观** 等远期数据占位工厂，与 `expr/fundamental|alternative|microstructure` 中 **STUB 集合** 对齐；供 DSL **可解析**、后端逐步实装。

### [`__init__.py`](__init__.py)

**聚合导出**大量名称，使 `from api.operators import rank, ts_mean` 可行；新增算子时 **务必** 在此补充 `__all__` 或导出列表（保持与 `build_dsl_allowlist` 一致）。

---

## 3. 与 `expr/` 的对应关系（如何阅读源码）

调试「这个 DSL 函数构造了什么树」时：

1. 在 **`api/operators/<模块>.py`** 找到函数体。  
2. 查看返回的 **类名**（如 `TsMean(...)`）。  
3. 到 **`expr/ts.py`**（等）查看 **`__init__` 与子节点含义**。

---

## 4. 与 `operator_registry` / DSL 的关系

- **`build_dsl_allowlist()`** 显式导入本目录各模块，把 **可调用对象** 注册进字典。  
- **字符串因子** 若调用未注册函数名 → **解析失败**。  
- **手写因子** 不受白名单限制，但若构造了后端不支持的 `op`，执行阶段 **`NotImplementedError`**。

---

## 5. 延伸阅读

- [`docs/operators_semantics.md`](../../docs/operators_semantics.md) — **权威语义**  
- [`docs/operators_roadmap.md`](../../docs/operators_roadmap.md) — 实现进度  
- [`expr/README.md`](../../expr/README.md) — 节点类型  
- [`backend/README.md`](../../backend/README.md) — 真正执行处  
