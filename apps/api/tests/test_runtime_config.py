from physics_vault_api.runtime_config import RuntimeAiConfig, default_vl_config


def test_default_vl_model_uses_qwen_ocr() -> None:
    config = default_vl_config()
    assert config.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.model_name == "qwen3.5-ocr"


def test_runtime_config_migrates_legacy_dashscope_vl_model() -> None:
    config = RuntimeAiConfig.from_dict(
        {
            "vl": {
                "service_type": "Alibaba DashScope",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "sk-test",
                "model_name": "qwen-vl-max",
            }
        }
    )

    assert config.vl.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.vl.model_name == "qwen3.5-ocr"


def test_runtime_config_keeps_authorized_openai_compatible_ocr_model() -> None:
    config = RuntimeAiConfig.from_dict(
        {
            "vl": {
                "service_type": "Alibaba DashScope",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "sk-test",
                "model_name": "qwen3.5-ocr",
            }
        }
    )

    assert config.vl.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.vl.model_name == "qwen3.5-ocr"


def test_runtime_config_moves_qwen35_ocr_to_compatible_endpoint() -> None:
    config = RuntimeAiConfig.from_dict(
        {
            "vl": {
                "service_type": "Alibaba DashScope",
                "base_url": "https://dashscope.aliyuncs.com/api/v1",
                "api_key": "sk-test",
                "model_name": "qwen3.5-ocr",
            }
        }
    )

    assert config.vl.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.vl.model_name == "qwen3.5-ocr"
