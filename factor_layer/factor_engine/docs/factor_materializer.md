# Factor Engine 因子落盘系统使用手册

> 版本：v1.0.0 · 更新日期：2026-03-31
> 本文档面向量化研究员，介绍因子落盘系统（Materialization System）的功能与使用方法。

## 1. 系统简介与功能

因子落盘系统主要用于持久化保存计算完成的因子数据，供后续回测和模型训练使用。系统的核心功能包括：

- **版本控制与防冲突**：通过抽象语法树（AST）记录因子的计算逻辑。一旦因子完成注册，系统会拒绝公式不同但同名的因子写入，防止历史被测数据被意外污染。
- **自动对齐与拼接**：提供专门的读取器（`ResultStore`），支持对不同频率（如 5分钟和日频）的多个因子集进行自动基于时间轴的对齐与宽表拼接。
- **标准化数据格式**：统一以 Parquet 格式存储，统一数据列设计，并将数据类型规范化为 `Float32`，同时自动处理无穷大和缺失异常值。
- **增量更新**：支持收盘后按日期进行增量写入，同时间节点的重复数据将执行安全覆盖（Upsert），避免重复行生成。

---

## 2. 数据处理流程

当调用 `materialize()` 写入因子数据时，系统将固定执行以下处理步骤：

1. **格式转换**：传入的 Pandas Series 会被统一转换为 `[datetime, asset, value]` 格式的长表。`datetime` 转为时间戳，`asset` 转为字符串，`value` 强制转化为单精度浮点数（Float32）以减少存储开销并提高读取速度。
2. **数据清洗**：系统自动将 `+inf` 和 `-inf` 转换为 `NaN`，并删除所有 `value` 为缺失值的行，以稀疏形式存储。
3. **公式校验**：提取因子的逻辑 Hash (AST Hash)，若识别到因子 ID 相同但底层计算公式已修改，系统将抛出 `FactorHashMismatchError` 并拒绝写入。
4. **分区与写入**：数据按年份分区（`year=YYYY`）。若分区内已有对应日期的旧数据，新数据会直接更新覆盖旧值。

---

## 3. 使用方法

### 3.1 写入因子 (落盘)

因子逻辑定稿后可调用以下接口保存结果：

```python
from runtime.engine import FactorEngine
from storage import ParquetMaterializer

# 1. 计算因子
engine = FactorEngine(...)
result_dict = engine.run(factor) 

# 2. 写入数据
mat = ParquetMaterializer(lake_root="./shared_factor_lake")

summary = mat.materialize(
    factor_id="mom_rank_v1",                 # 建议在因子名后显式区分版本号
    result=result_dict["result"],            # FactorEngine 返回的计算结果
    ir_node=result_dict["analysis"].ir,       # 传入 AST 节点以启用公式防冲突校验
    frequency="1d",                          # 因子频率
    description="3日均价截面排序",             # 因子说明
)

print(f"写入完成，共 {summary['rows_written']} 行。")
```

### 3.2 查询已有因子

查询系统中已保存的因子列表及其数据可获取区间：

```python
for f in mat.list_factors():
    print(f"因子ID: {f['factor_id']}, 作者: {f['author']}")
    print(f"数据区间: {f['start_date']} 到 {f['end_date']}")
    print(f"总行数: {f['row_count']}\n")
```

### 3.3 读取与拼接多因子

如需合并调取多个特征用于回归测试，请使用内置的 `ResultStore` 读取类，其底层基于惰性查询逻辑构建。

```python
from storage import build_result_store

store = build_result_store("./shared_factor_lake")

# 读取并拼接不同频率的多个因子
lazy_frame = store.load_factors(
    factor_ids=["volatility_5m_v1", "mom_1d_v2", "turnover_1d_v1"],
    start="2024-01-01",      # 设置数据拉取起始时间
    end="2024-06-30",        # 设置数据拉取结束时间
    align_method="forward_fill"  # 频率对齐方法
)

# 获取最终的 DataFrame 宽表形式
df = lazy_frame.collect().to_pandas()
```

**关于 `align_method="forward_fill"` 的说明**: 
在合并不同频率特征（如合并 5min 记录与日频特征）时，采用 `forward_fill` 将促使低频数据在其更新周期内向后续的高频截面向前平推填充（如引用昨日日频特征填充至今日不同时段的微秒截口），此举通常被用来确保回测时不引入未来函数偏差。

---

## 4. 常见问题解答

### 4.1 写入时报错 `FactorHashMismatchError`
**原因**：因子的语法逻辑已被修改，但仍然使用了既有的 `factor_id` 提交。系统防阻了该风险操作。
**解决方法**：为当前修改后的新因子更改名称标记（例如追加 `_v2` 后缀），重新提交写入请求。

### 4.2 独立脚本无法传递 `ir_node` 参数
通过不传递 `ir_node` 参数系统仍然能处理写入，但这将生成弱相关伪散列值且丧失基于计算树逻辑的版本防护机制。从安全长效视角，建议所有因子归集到标准的 `FactorEngine` 处理流中计算。

### 4.3 合并多因子后提取出大量 `NaN` 
这属于外连接操作的正常连带情况。当样本时间截面存在部分因子缺失有效计算值即会产生 `NaN` 空单元。可在实际推算逻辑处执行 `fillna`。

### 4.4 针对增量数据的周期性更新
如需在日常收盘后将预设因子集自动部署增量跑批，请查阅工程目录代码 `examples/batch_materialize.py`。该脚本提供了批处理配置表，异常容错机制以及自动覆盖执行的基础参考流程。
