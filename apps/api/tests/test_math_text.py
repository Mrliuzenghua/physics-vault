from physics_vault_api.services.math_text import (
    normalize_math_delimiters,
    normalize_question_math,
    normalize_standard_latex,
    normalize_short_inline_display_math,
    repair_unbalanced_inline_math,
)


def test_short_display_math_inside_sentence_becomes_inline() -> None:
    text = (
        "其能级差约为$$1.3 \\times 10^{-18}\\text{ J}$$，"
        "普朗克常量$$h=6.6 \\times 10^{-34}\\text{ J}\\cdot\\text{s}$$。"
    )

    assert normalize_short_inline_display_math(text) == (
        "其能级差约为$1.3 \\times 10^{-18}\\text{ J}$，"
        "普朗克常量$h=6.6 \\times 10^{-34}\\text{ J}\\cdot\\text{s}$。"
    )


def test_standalone_display_math_stays_display() -> None:
    text = "由能量关系可得\n$$E=h\\nu$$\n所以频率可求。"

    assert normalize_short_inline_display_math(text) == text


def test_balanced_display_math_ending_in_brace_is_not_truncated() -> None:
    text = "$$E=6.6 \\times 10^{-34}\\text{ J}$$"

    normalized, replacements = normalize_math_delimiters(text)

    assert normalized == text
    assert replacements == 0


def test_standalone_mixed_display_delimiter_is_repaired() -> None:
    text = "$$E=6.6 \\times 10^{-34}\\text{ J}$"

    normalized, replacements = normalize_math_delimiters(text)

    assert normalized == "$$E=6.6 \\times 10^{-34}\\text{ J}$$"
    assert replacements == 1


def test_mixed_inline_delimiters_are_repaired() -> None:
    text = "电压$U$$随时间$t$$变化，距离$$H$为定值。"

    assert normalize_short_inline_display_math(text) == "电压$U$随时间$t$变化，距离$H$为定值。"


def test_unbalanced_inline_math_is_closed_before_chinese_text() -> None:
    normalized, replacements = repair_unbalanced_inline_math("在$t = 0时刻同时经过路标")

    assert normalized == "在$t = 0$时刻同时经过路标"
    assert replacements == 1


def test_stray_math_open_before_chinese_text_is_removed() -> None:
    normalized, replacements = repair_unbalanced_inline_math("重力加速度$(取10m/s^2")

    assert normalized == "重力加速度(取10m/s^2"
    assert replacements == 1


def test_unbalanced_inline_math_at_end_is_closed() -> None:
    normalized, replacements = repair_unbalanced_inline_math("结果为$F = ma")

    assert normalized == "结果为$F = ma$"
    assert replacements == 1


def test_chinese_inside_text_command_does_not_close_math() -> None:
    normalized, replacements = repair_unbalanced_inline_math(r"单位为$\text{米/秒}")

    assert normalized == r"单位为$\text{米/秒}$"
    assert replacements == 1


def test_question_math_normalizes_options_and_analysis() -> None:
    question = {
        "title": "波长约为$$1.5 \\times 10^{-7}\\text{ m}$$",
        "options": [{"opt": "A", "content": "频率约为$$2.0 \\times 10^{16}\\text{ Hz}$$"}],
        "analysis": "由$$c=\\lambda f$$可知",
    }

    normalized = normalize_question_math(question)

    assert normalized["title"] == "波长约为$1.5 \\times 10^{-7}\\text{ m}$"
    assert normalized["options"][0]["content"] == "频率约为$2.0 \\times 10^{16}\\text{ Hz}$"
    assert normalized["analysis"] == "由$c=\\lambda f$可知"

def test_standard_latex_repairs_unwrapped_fragments_and_chinese_subscripts() -> None:
    normalized = normalize_standard_latex(
        "输入功率P_{电}，g取10\\text{m/s}^2，已知$P_{机}=0.9P_{电}$。"
    )

    assert normalized == "输入功率$P_{\\text{电}}$，g取$10\\text{m/s}^2$，已知$P_{\\text{机}}=0.9P_{\\text{电}}$。"
