# Typst 课件 MCP

## 目标

`study_sheet_workflow` 读取教学资源库中的 `01-模板/教学PPT模板-物理题Typst.typ`，把结构化高中物理题生成 16:9 Typst 课件。每次同时输出可编辑的 `.typ` 源文件和可离线放映的 `.pdf`，成品统一写入 `05-课堂PPT/`。

## 工具

- `get_typst_presentation_template`：返回模板、编译器、支持题型与公式策略。
- `create_typst_presentation`：生成封面、每题的题目页和解析页、课堂回顾页；支持 `dry_run` 和幂等 `operation_id`。
- `validate_typst_presentation`：校验源文件、PDF 页数、模板占位符和 SHA-256。
- `audit_typst_presentation_template`：只读检查模板结构与 Typst 版本。

## 公式与版式

输入可继续使用常见 LaTeX 写法，例如 `$m_Av_A+m_Bv_B=(m_A+m_B)v$`、`$v=\dfrac{5}{3}\,\text{m/s}$`。工作流将分式、根式、上下标、常用运算符和单位转换为 Typst 原生数学语法，再由 Typst 直接排版到 PDF，不经过图片或 Office 公式转换。

默认画布为 320 mm × 180 mm，比例为 16:9。每道题生成“题目页 + 解析页”，图片复制到 `05-课堂PPT/images/` 并使用相对路径。

## 与网页课件并存

- HTML 版适合浏览器交互、键盘翻页和课堂隐藏答案。
- Typst 版适合完全离线放映、稳定打印和高质量物理公式。
- 两种格式使用相同的结构化题目输入，可以同时生成并对照使用。

## 安全边界

- 模板只从 `01-模板/` 读取，MCP 不改写模板原件。
- 成品只写入 `05-课堂PPT/`，不覆盖已有文件。
- 图片只允许来自教学资源库或 Physics Vault 的 `data/` 目录。
- 校验工具只接受带生成标记和清单、且位于受控输出目录内的 `.typ` 文件。
