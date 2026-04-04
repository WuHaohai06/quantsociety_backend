# `expr` — 表达式树 AST（详尽说明）

本目录定义 **因子表达式的 Python 类层次**：每个算子对应一个 **`Expr` 子类**，保存 **子表达式** 与 **属性**（窗口长度、列名常量等）。  
**不包含** 向量化数值计算；求值发生在 **`backend`**，此处仅 **数据结构**。

### 协作者速览（约 5 分钟）

1. **本目录在干什么**：**因子表达式的 AST**——`ColumnRef`、`TsMean`、`Rank` 等 **Python 类**，子节点 + `attrs`（窗口长度等）。
2. **谁构造这些类**：研究员侧通过 **`api/operators`** 工厂函数；**不要**在业务里直接 `import expr` 除非你在扩展算子。
3. **谁消费这些类**：**`ir/analyzer.py`** 遍历 **`Expr`** 生成 **`IRNode`**；之后与 **`Expr` 类** 解耦。
4. **从哪下手**：按 **§3 按语义分类的模块表** 找到文件；与 **`operators_semantics.md`** 中的算子名对照。

---

## 1. 基类与通用行为

### [`base.py`](base.py)

- **`Expr`**：抽象基类；子类实现 **`children`**（子节点元组）、可能 **`__repr__`** 等。  
- 所有节点均可被 **`ir/analyzer.py`** 遍历，生成 **`IRNode`**。

### [`metadata.py`](metadata.py)

- 节点附加元数据（若有）：用于调试或后续优化 passes。

---

## 2. 叶子与常量

### [`column.py`](column.py)

- **`ColumnRef`**：`col("close")`；持有所选 **列名字符串**。

### [`literal.py`](literal.py)

- **数值/布尔常量** 叶子节点。

---

## 3. 按语义分类的节点模块

下列模块与 **`api/operators`** 中 **同名模块** 对应：工厂函数 **构造** 本目录中的类。

| 模块 | 内容 |
|------|------|
| [`arithmetic.py`](arithmetic.py) | 二元/一元算术、`Nary*` 多元运算 |
| [`logical.py`](logical.py) | 比较、逻辑、`IfElse` |
| [`ts.py`](ts.py) | 时序滚动、延迟、`TsMean`、`TsStd`、技术指标 Expr |
| [`cs.py`](cs.py) | 截面 rank、zscore 等 |
| [`group.py`](group.py) | 分组 rank / neutralize |
| [`cleaning.py`](cleaning.py) | 清洗 Expr |
| [`technical.py`](technical.py) | 技术指标 Expr |
| [`context.py`](context.py) | 正交化、换基准 |
| [`transformational.py`](transformational.py) | `Bucket`、`TradeWhen` |
| [`vector.py`](vector.py) | 向量列 Expr（占位为主） |
| [`intraday.py`](intraday.py) | 日内序列 Expr；**`INTRADAY_STUB_OPS`** 集合在此声明 |
| [`fundamental.py`](fundamental.py) | 基本面占位；**`FUNDAMENTAL_STUB_OPS`** |
| [`alternative.py`](alternative.py) | 另类数据占位；**`ALTERNATIVE_STUB_OPS`** |
| [`microstructure.py`](microstructure.py) | 微观结构占位；**`MICROSTRUCTURE_STUB_OPS`** |

**占位集合** 会被 **`api/operator_registry.STUB_IR_OPS`** 合并，用于 **注册表** 与 **后端 stub**。

---

## 4. 编译与遍历顺序

```text
Expr 树根
  → Analyzer.lower()
      → IRNode（op, inputs, attrs）
          → Lowerer.to_logical_plan()
              → PlanNode
                  → Backend.execute()
```

阅读 **`Expr` 子类** 时，重点看：**子节点顺序**（与 IR `inputs` 顺序一致）、**attrs**（如窗口长度）。

---

## 5. `__init__.py`

- 可导出常用节点类（若有）；多数代码路径从 **`api/operators`** 工厂进入，不直接 `from expr import ...`。

---

## 6. 延伸阅读

- [`api/README.md`](../api/README.md)  
- [`ir/README.md`](../ir/README.md) — `Expr` → IR  
- [`docs/operators_semantics.md`](../docs/operators_semantics.md)  
