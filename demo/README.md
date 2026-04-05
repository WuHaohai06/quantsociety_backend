# Demo

这个目录收集仓库里的端到端演示和 notebook，适合快速验证整条链路是否可运行，也适合给新同学建立整体认知。

## Demo 列表

| 目录 | 作用 | 当前推荐度 |
| --- | --- | --- |
| [all_pipeline_demo/README.md](all_pipeline_demo/README.md) | 多因子组合全链路 smoke demo，统一写入 `workspace_data/` | 高 |
| [all_pipeline_single_asset_demo/README.md](all_pipeline_single_asset_demo/README.md) | 单资产择时全链路 smoke demo，统一写入 `workspace_data/` | 高 |
| [portfolio_demo/README.md](portfolio_demo/README.md) | 组合子链路 demo，偏本地 self-contained | 中 |
| [single_asset_demo/README.md](single_asset_demo/README.md) | 历史 notebook-first 单资产目录，保留旧实验资产 | 中 |

## 如果你只想快速验证仓库能不能跑

优先跑这两个：

```bash
python demo/all_pipeline_demo/run_all_pipeline_demo.py
python demo/all_pipeline_single_asset_demo/run_single_asset_pipeline_demo.py
```

对应 smoke test：

```bash
pytest demo/all_pipeline_demo/test_all_pipeline_demo.py -q
pytest demo/all_pipeline_single_asset_demo/test_single_asset_pipeline_demo.py -q
```

## 如何选择 demo

- 你想看完整多因子链路：去 `all_pipeline_demo/`
- 你想看单资产 C→D 全链路：去 `all_pipeline_single_asset_demo/`
- 你只想看组合信号 → holdings → backtest：去 `portfolio_demo/`
- 你要查旧 notebook、旧配置或历史实验：去 `single_asset_demo/`