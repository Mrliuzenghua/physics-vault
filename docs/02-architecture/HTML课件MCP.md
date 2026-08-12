# HTML 课件 MCP

## 目标

`study_sheet_workflow` 读取教学资源库中的 `01-模板/教学PPT模板-物理题HTML.html`，将结构化高中物理题转换为浏览器可全屏放映的 HTML 课件。模板原件始终只读，成品统一写入 `05-课堂PPT/`，题图复制到该目录的 `images/`。

## 工具

- `get_html_presentation_template`：返回模板结构检查、支持题型、图片边界和离线提示。
- `create_html_presentation`：生成封面、导航、章节过渡和题目页；支持 `dry_run` 与幂等 `operation_id`。
- `validate_html_presentation`：检查页面数、题目页、占位符和相对图片引用。
- `audit_html_presentation_template`：返回当前模板 SHA-256 和必需结构特征。

## 输入与放映

题目输入包含题型、题干、选项、实验数据、答案、分步解析、易错提醒和最多四张题图。所有文本先做 HTML 转义，同时保留 `$...$`、`$$...$$` 等 MathJax 公式语法。

生成课件后用浏览器打开 `.html` 文件：方向键、空格和 PageUp/PageDown 翻页，`H` 键或底部按钮显示/隐藏答案。模板默认在线加载 MathJax，离线课堂需要提前确认网络或后续改成本地 MathJax 资源。

若更重视离线公式质量和固定版式，可对同一批题调用 `create_typst_presentation`，同时保留 HTML 互动版和 Typst PDF 放映版。

## 安全边界

- 不修改 `01-模板/`。
- HTML 只写入 `05-课堂PPT/`，且不覆盖已有文件。
- 图片只读取教学资源库或 Physics Vault 的 `data/` 目录，并限制为常见图片扩展名。
- 只校验带生成标记、且位于受控输出目录内的 HTML 文件。
