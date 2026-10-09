import pytest

from docker_picamera.config import Config, ConfigError, load_config

PASSWORD = {"AUTH_PASSWORD": "s3cret"}


def test_defaults_apply_when_only_password_is_set() -> None:
    assert load_config(PASSWORD) == Config(
        username="pi",
        password="s3cret",
        width=800,
        height=600,
        framerate=24,
        rotation=0,
        hflip=False,
        vflip=False,
    )


def test_explicit_values_apply() -> None:
    config = load_config(
        {
            **PASSWORD,
            "AUTH_USERNAME": "cam",
            "RESOLUTION": "1280x720",
            "FRAMERATE": "15",
            "ROTATE": "180",
            "HFLIP": "TRUE",
            "VFLIP": "False",
        }
    )
    assert (config.username, config.width, config.height, config.framerate) == (
        "cam",
        1280,
        720,
        15,
    )
    assert (config.rotation, config.hflip, config.vflip) == (180, True, False)


@pytest.mark.parametrize("environ", [{}, {"AUTH_PASSWORD": ""}])
def test_password_is_required(environ: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"^AUTH_PASSWORD: "):
        load_config(environ)


def test_empty_username_is_rejected() -> None:
    with pytest.raises(ConfigError, match=r"^AUTH_USERNAME: "):
        load_config({**PASSWORD, "AUTH_USERNAME": ""})


@pytest.mark.parametrize("value", ["800by600", "800x", "x600", "0x600", "800x0", "-800x600", ""])
def test_malformed_resolution_names_variable_and_value(value: str) -> None:
    with pytest.raises(ConfigError, match=r"^RESOLUTION: .*" + repr(value)):
        load_config({**PASSWORD, "RESOLUTION": value})


@pytest.mark.parametrize("value", ["0", "-1", "abc", "2.5", ""])
def test_framerate_must_be_positive_integer(value: str) -> None:
    with pytest.raises(ConfigError, match=r"^FRAMERATE: "):
        load_config({**PASSWORD, "FRAMERATE": value})


@pytest.mark.parametrize("value", ["90", "270", "-180", "abc"])
def test_only_0_and_180_rotation(value: str) -> None:
    with pytest.raises(ConfigError, match=r"^ROTATE: only 0 and 180 are supported"):
        load_config({**PASSWORD, "ROTATE": value})


@pytest.mark.parametrize("name", ["HFLIP", "VFLIP"])
def test_flip_must_be_true_or_false(name: str) -> None:
    with pytest.raises(ConfigError, match=rf"^{name}: expected true or false, got 'yes'"):
        load_config({**PASSWORD, name: "yes"})
