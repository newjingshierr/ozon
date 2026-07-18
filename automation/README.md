# ArtBox World 自动化

该目录从 `D:\workspace\xituerp` **只读**获取订单、商品和店铺授权信息，生成 Astro
商品页与压缩后的主图。它不会在 ERP 目录中新增、修改或删除任何文件，也只执行数据库
`SELECT` 查询。

## 安全规则

- 标题中必须存在明确的引号关键词，如 `"AC/DC"`，否则进入待检查队列。
- 必须有数字 Ozon Product ID、有效主图和对应商品链接。
- 商品 ID、来源键和规范化关键词三重去重。
- 同一时间只允许一个任务运行。
- 每轮默认最多新增 20 页。
- Ozon API 密钥只从 ERP 原配置读入内存，不复制到本项目、不写日志、不提交 Git。

## 命令

```powershell
python automation/run.py --dry-run
python automation/run.py
python automation/run.py --publish
```

- `--dry-run`：只读检查，不生成页面。
- 无参数：生成图片和页面、运行 Astro 构建，但不提交。
- `--publish`：生成、构建、Git 提交并推送，随后由 Cloudflare Pages 自动部署。

运行状态、待检查队列和日志均在 `automation/data`、`automation/logs`，已被 Git 忽略。
