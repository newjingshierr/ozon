# ArtBox World 模型重写与发布任务

工作目录是 `D:\ozo`。`D:\workspace\xituerp` 严格只读：禁止编辑、新增、删除其中任何
文件，禁止在其中产生 Python bytecode；运行 Python 时设置 `PYTHONDONTWRITEBYTECODE=1`。

每次运行严格执行：

1. 检查 `D:\ozo` Git 状态。若存在与本自动化无关的未提交修改，停止并报告，不得覆盖。
2. 设置 `PYTHONDONTWRITEBYTECODE=1`，运行：
   `python automation\run.py prepare --limit 20`
3. 读取 `D:\ozo\automation\data\model_input.json`。若 items 为空，报告没有待处理商品并结束。
4. 你必须亲自使用语言模型能力逐个理解 `original_product_title`，不能调用固定文案模板：
   - 判断最自然、最准确的俄语主搜索关键词；引号内容只是提示，不是必须照抄；
   - 为该商品独立重写俄语 SEO Title、Meta Description、图片 ALT、5–12 个相关关键词；
   - 写 1200–8000 字符的原创俄语 Markdown 正文，至少 3 个 `##` 标题；
   - 每页围绕该产品的具体搜索意图组织，页面之间不得复用固定段落；
   - 只能使用输入中的事实，不得虚构材质、官方授权、库存、价格、评论、历史或性能；
   - 对无法可靠判断、与现有主题重复或不适合发布的项目设为 `status: skip` 并说明原因。
5. 严格按照 input 中的 output_schema，把 UTF-8 JSON 写入
   `D:\ozo\automation\data\model_output.json`。batch_id 必须原样复制，source_key 不得修改，
   每个输入项目必须恰好对应一个输出项目。
6. 运行：`python automation\run.py finalize --publish`
7. 若校验失败，读取错误，仅修改 model_output.json 中相关项目并重试一次；不得降低 Python
   校验标准。仍失败则停止并报告。
8. 最后报告：输入数、发布数、跳过数、提交 SHA、构建结果。不要操作 Yandex Webmaster；
   sitemap 会由 Astro 自动更新。
