# 量化因子引擎 Agent 框架

研报 PDF → AI 生成 YAML 配置 → 评价脚本评分 → 不达标则 AI 修订 YAML 迭代，达标则以当前 YAML 为最终版本。

## 目标流程

```
研报 PDF → AI → YAML v1 → 配置文件评价脚本.py → 评分
                ↑                    │
                └── 不达标 ←──────────┘
                     AI → YAML v2 … → YAML vN
                达标 → 结束，yaml vN 为最终版本
```

## 六层架构与本项目对应

| 层 | 职责 | 本项目对应 |
|----|------|-------------|
| **1** | CLAUDE.md / rules / memory — 长期上下文，「是什么」 | `config/`、`docs/CLAUDE.md`、`memory/` |
| **2** | Tools / MCP — 动作能力，「能做什么」 | `tools/` |
| **3** | Skills — 按需加载的方法论，「怎么做」 | `skills/` |
| **4** | Hooks — 强制执行，不依赖模型判断 | `hooks/` |
| **5** | Subagents — 隔离上下文的工作者 | `planning/sub_agents/` |
| **6** | Verifiers — 验证闭环，可验 / 可回滚 / 可审计 | `verifiers/`、`scripts/配置文件评价脚本.py` |

## 目录结构

```
factor_agent/
├── README.md                 # 本说明
├── docs/
│   └── CLAUDE.md             # 第1层：系统约定、YAML schema 说明、达标标准
├── config/                   # 第1层：配置与规则
│   ├── settings.py
│   ├── yaml_schema.py        # YAML 结构约定
│   ├── message_schema.py
│   └── logger.py
├── memory/                   # 第1层：长期上下文与压缩
│   ├── context_compression.py
│   ├── store.py
│   └── policies.py
├── tools/                    # 第2层：Tools / MCP
│   ├── registry.py
│   ├── pdf_tools.py
│   ├── yaml_tools.py
│   └── eval_tools.py         # 调用评价脚本
├── skills/                   # 第3层：Skills
│   ├── base.py
│   ├── registry.py
│   ├── report_to_yaml_skill.py
│   └── score_feedback_revise_skill.py
├── hooks/                    # 第4层：Hooks
│   ├── base.py
│   ├── pre_yaml_hooks.py
│   └── post_pass_hooks.py
├── planning/                 # 第5层：任务与子 Agent
│   ├── todo.py
│   ├── task_system.py
│   ├── task_schema.py
│   └── sub_agents/
│       ├── base.py
│       ├── extract_agent.py
│       └── revise_agent.py
├── verifiers/                # 第6层：Verifiers
│   ├── evaluator.py
│   └── audit.py
├── core/                     # Agent 循环与状态
│   ├── agent_loop.py
│   ├── state.py
│   └── autonomous.py
├── scripts/
│   └── 配置文件评价脚本.py   # 评分入口
└── main.py                   # 主入口
```

## 使用说明（待实现）

- 将研报 PDF 放入指定输入目录或通过接口传入。
- 运行 `main.py` 启动 Agent 循环，产出 YAML v1 并调用评价脚本。
- 根据评分与阈值决定是否迭代；达标后最终 YAML 输出到指定路径，版本与评分可审计。

## 依赖与运行（待补充）

- Python 3.x
- 依赖见 `requirements.txt`（待创建）
