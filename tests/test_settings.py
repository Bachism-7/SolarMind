from pathlib import Path

import pytest
import yaml

from app.settings import ConfigStore, DEFAULT_SETTINGS, validate_settings


def test_settings_persist_and_reload_from_local_store(tmp_path):
    settings = {section: dict(values) for section, values in DEFAULT_SETTINGS.items()}
    settings["installation"].update(label="Roof array", latitude=37.7749, longitude=-122.4194, timezone="America/Los_Angeles")
    first_store = ConfigStore(tmp_path)
    first_store.save(settings)
    loaded = ConfigStore(tmp_path).load()
    assert loaded == validate_settings(settings)
    assert (tmp_path / "config.yaml").exists()


def test_shareable_config_example_is_valid():
    example_path = Path(__file__).parents[1] / "config.example.yaml"
    example = yaml.safe_load(example_path.read_text(encoding="utf-8"))
    validated = validate_settings(example)
    assert validated["operation"]["dry_run"] is True
    assert validated["operation"]["hardware_enabled"] is False
    assert validated["calibration"]["orientation_note"] == ""


@pytest.mark.parametrize("alias", ["host; rm -rf /", "-oProxyCommand=bad", "host name", "host\ncommand"])
def test_ssh_alias_rejects_shell_and_option_injection(alias):
    settings = {section: dict(values) for section, values in DEFAULT_SETTINGS.items()}
    settings["ssh"]["alias"] = alias
    with pytest.raises(ValueError, match="SSH alias"):
        validate_settings(settings)


def test_ros_setup_path_rejects_shell_metacharacters():
    settings = {section: dict(values) for section, values in DEFAULT_SETTINGS.items()}
    settings["ssh"]["ros_setup_path"] = "/tmp/setup.bash; id"
    with pytest.raises(ValueError, match="absolute POSIX path"):
        validate_settings(settings)
