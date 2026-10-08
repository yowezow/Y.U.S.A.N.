from yusan_core.config.settings import Settings


def test_default_settings_are_safe_without_a_key() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "gemini"
    assert settings.gemini_api_key is None
    assert settings.yusan_port == 8765
