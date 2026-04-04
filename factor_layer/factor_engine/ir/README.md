# `ir` — 中间表示 IR（详尽说明）

**IR（Intermediate Representation）** 位于 **高层 `Expr`** 与 **执行向 `PlanNode`** 之间：结构扁平、便于 **依赖分析**、**schema** 推导、与后端解耦。  
典型节点：**`IRNode(op: str, inputs: tuple[IRNode, ...], attrs: dict)`**（具体定义见源码 `ir/nodes.py`）。

### 协作者速览（约 5 分钟）

1. **本目录在干什么**：把 **`Expr`** 降到 **`IRNode`**，结构扁平、**`op` 字符串**稳定，便于 **抽列依赖**、**后端统一**、**多因子 CSE**（在 planner 层）。
2. **核心入口**：**`Analyzer.lower(expr)`** → **`AnalysisResult`**（含 IR 根、依赖列等）；每种 **`Expr`** 类型在 **`analyzer.py`** 里对应一段 **visit** 逻辑。
3. **读代码顺序**：**`nodes.py`**（IR 形状）→ **`analyzer.py`**（ lowering 规则）。
4. **边界**：**不执行 pandas**；**不生成最终物理执行计划**（那是 **`planner`**）。

---

## 1. 为何需要 IR

| 目标 | 说明 |
|------|------|
| **依赖列提取** | `Analyzer` 可从 IR 递归收集 **`ColumnRef`**，告知 `DataSource` 拉哪些列。 |
| **统一后端** | 后端只认 **`op` 字符串** + 子树，不必依赖 Python `Expr` 类层次。 |
| **多因子 CSE** | 在 **`PlanNode`** 层做公共子式合并；IR→Plan 需保持结构稳定。 |

---

## 2. 文件说明

### [`nodes.py`](nodes.py)

- **`IRNode`** 定义：字段名、不可变语义、与 `Expr` 的字段对应关系。  
- 所有 **`op`** 名应与 **`backend/kernels`** 及文档 **一致**。

### [`analyzer.py`](analyzer.py)

- **`Analyzer`**：核心方法 **`lower(expr: Expr) -> AnalysisResult`**。  
- **`AnalysisResult`**：包含 **`ir`**（根 IR 节点）、**依赖列**、schema 等（见类型定义）。  
- **遍历规则**：每种 `Expr` 子类对应一个 **visit** 或 **dispatch** 分支，生成子 IR 再组合。

### [`schema.py`](schema.py)

- 列类型、形状、时间频率等 **推导辅助**（若启用）；具体字段以源码为准。

### [`types.py`](types.py)

- IR 层 **类型枚举/约束**（若有）。

---

## 3. 数据流位置

```mermaid
flowchart LR
  E[Expr]
  A[Analyzer]
  I[IRNode]
  L[Lowerer]
  P[PlanNode]
  E --> A
  A --> I
  I --> L
  L --> P
```

---

## 4. 与 `operator_registry.STUB_IR_OPS` 的关系

- IR 可以包含 **`op`** 在 **STUB** 集合中的节点；**PandasBackend** 对其实现为 **抛错** 或占位返回，取决于注册方式。  
- 新增占位算子时：**`expr`** 工厂 → **`analyzer`** 能 lower → **`kernels`** 注册 stub。

---

## 5. 测试

- `tests/test_planner.py`、`tests/test_backend.py`、`tests/test_end_to_end.py` 间接覆盖；**IR 单测**随项目演进补充。

---

## 6. 延伸阅读

- [`expr/README.md`](../expr/README.md)  
- [`planner/README.md`](../planner/README.md)  
- [`runtime/engine.py`](../runtime/engine.py) 中 `compile()`  
