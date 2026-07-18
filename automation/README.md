# ArtBox World：Python + Codex 模型自动化

这套流程不使用固定正文模板，也不需要单独购买 AI API。Codex 桌面版的定时任务负责
语言模型环节；Python 负责所有确定性工作。

## 分工

Python：

- 只读查询 `D:\workspace\xituerp` 的订单和成功发布记录；
- 选择每批最多 20 个产品；
- 下载、校验和压缩 Ozon 主图；
- 校验模型输出的字段、俄文长度、关键词重复和正文结构；
- 生成 Markdown、运行 Astro 构建、Git 提交并推送。

Codex 模型：

- 理解原始俄文商品标题；
- 判断真实主关键词和搜索意图；
- 为每个商品单独重写 Title、Description、ALT、关键词和俄语正文；
- 对重复、含义不清或不适合发布的商品作出跳过决定。

## 两阶段命令

```powershell
python automation/run.py prepare --limit 20
# Codex 读取 model_input.json 并写 model_output.json
python automation/run.py finalize --publish
```

模型输入、输出、待检查队列和待发布清单位于 `automation/data`，均不会提交到 Git。
Windows 的旧固定模板计划任务已停用。新的调度必须使用 Codex 桌面版 Scheduled，才能
真正使用当前账户的模型能力。
