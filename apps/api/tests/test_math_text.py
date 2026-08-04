from physics_vault_api.services.math_text import (
    normalize_math_delimiters,
    normalize_question_math,
    normalize_short_inline_display_math,
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
