# single_asset_demo

这个目录是历史保留的单资产 demo / notebook 工作区，早于当前 `workspace_data` 统一落盘的 smoke demo。

## 当前目录里有什么

| 内容 | 说明 |
| --- | --- |
| `single_asset_end_to_end_demo.ipynb` | 较早的单资产 notebook 演示 |
| `configs/` | 历史配置文件 |
| `outputs/` | 历史本地产物 |
| `cache/`、`factor_lake/` | 历史实验过程遗留数据 |

## 与新 demo 的关系

如果你要跑当前推荐的单资产端到端 smoke 流程，请优先使用：

- [../all_pipeline_single_asset_demo/README.md](../all_pipeline_single_asset_demo/README.md)

新目录的特点是：

- 脚本和测试更完整
- 路径统一到 `workspace_data/`
- notebook 也直接围绕新 runner 构建

## 何时还会用到这里

- 你需要回看旧 notebook
- 你需要比对历史配置和旧输出结构
- 你在追踪单资产 demo 的演化过程