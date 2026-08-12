from physics_vault_api.services.question_splitter import ExamQuestionSplitter


def _asset(index: int, filename: str) -> dict[str, str]:
    return {
        "image_id": f"image_{index:04d}",
        "filename": filename,
        "relative_path": f"data/import/{filename}",
    }


def test_section_aware_split_ignores_numbered_instructions_and_recovers_image_prefixed_questions() -> None:
    markdown = """注意事项：

> 1．答卷前填写姓名。
> 2．答案不能答在试卷上。

一、单项选择题：本题共2小题

![](image1.png){width="2in"
height="1in"}1. 第一题题干

A. 选项甲
B. 选项乙
C. 选项丙
D. 选项丁

2．第二题题干

A. 选项甲
B. 选项乙
C. 选项丙
D. 选项丁

二、多项选择题：本题共1小题

![](image2.emf)3. 第三题题干

A. 选项甲
B. 选项乙
C. 选项丙
D. 选项丁

三、非选择题

4.（6分）用气垫导轨验证动量守恒定律。

（1）选择正确操作：
A. 先接通气泵
B. 后放置滑块
（2）记录实验数据。
"""

    parsed = ExamQuestionSplitter().split(
        markdown,
        batch_id="batch-section-aware",
        source="fixture",
        media_assets=[_asset(1, "image1.png"), _asset(2, "image2.emf")],
    )

    assert parsed["question_count"] == 4
    questions = parsed["questions"]
    assert [question["question_no"] for question in questions] == [1, 2, 3, 4]
    assert [question["question_type"] for question in questions] == [
        "single_choice",
        "single_choice",
        "multi_choice",
        "experiment",
    ]
    assert all("答卷前" not in question["title"] for question in questions)
    assert len(questions[0]["figures"]) == 1
    assert len(questions[2]["figures"]) == 1
    assert questions[3]["options"] == []
    assert "A. 先接通气泵" in questions[3]["title"]


def test_choice_question_supports_image_only_option_lines() -> None:
    markdown = """一、单项选择题

1. 下列图像正确的是

A.
![](a.wmf)
B.
![](b.wmf)
C.
![](c.wmf)
D.
![](d.wmf)
"""
    assets = [_asset(index, f"{letter}.wmf") for index, letter in enumerate("abcd", start=1)]

    parsed = ExamQuestionSplitter().split(
        markdown,
        batch_id="batch-image-options",
        source="fixture",
        media_assets=assets,
    )

    question = parsed["questions"][0]
    assert question["question_type"] == "single_choice"
    assert [option["opt"] for option in question["options"]] == ["A", "B", "C", "D"]
    assert all(option["content"].startswith("![fig:") for option in question["options"])
    assert len(question["figures"]) == 4


def test_choice_question_extracts_inline_options_after_a_floating_image() -> None:
    markdown = """一、单项选择题

1. 如图所示，下列说法正确的是 ![](stem.emf)A. 选项甲 B. 选项乙 C. 选项丙 D. 选项丁
"""

    parsed = ExamQuestionSplitter().split(
        markdown,
        batch_id="batch-inline-options",
        source="fixture",
        media_assets=[_asset(1, "stem.emf")],
    )

    question = parsed["questions"][0]
    assert question["title"].endswith("]")
    assert [option["opt"] for option in question["options"]] == ["A", "B", "C", "D"]
    assert [option["content"] for option in question["options"]] == ["选项甲", "选项乙", "选项丙", "选项丁"]
