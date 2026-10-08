import pytest
from yusan_core.system.manager import SystemManager


def test_selects_platform_adapter() -> None:
    assert SystemManager("Darwin").adapter.__name__.endswith("macos")
    assert SystemManager("Windows").adapter.__name__.endswith("windows")
    assert SystemManager("Linux").adapter.__name__.endswith("linux")


def test_rejects_unknown_platform() -> None:
    with pytest.raises(RuntimeError, match="Unsupported platform"):
        SystemManager("Plan9").open_url("https://example.com")
