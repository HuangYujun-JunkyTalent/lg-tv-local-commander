import dataclasses
import enum
import json
import pathlib

DEFAULT_CONFIGURATION_PATH = pathlib.Path.home() / ".config" / "lg-tv-local-commander" / "config.json"
CLIENT_KEY_FILE_NAME = "client-key.sqlite"


class Action(enum.Enum):
    POWER_TOGGLE = "power-toggle"
    POWER_ON = "power-on"
    POWER_OFF = "power-off"
    INPUT_HDMI_1 = "input-1"
    INPUT_HDMI_2 = "input-2"
    INPUT_HDMI_3 = "input-3"
    INPUT_HDMI_4 = "input-4"


INPUT_IDENTIFIER_OF_ACTION = {
    Action.INPUT_HDMI_1: "HDMI_1",
    Action.INPUT_HDMI_2: "HDMI_2",
    Action.INPUT_HDMI_3: "HDMI_3",
    Action.INPUT_HDMI_4: "HDMI_4",
}


@dataclasses.dataclass(frozen=True)
class Television:
    ip_address: str
    mac_address: str


@dataclasses.dataclass(frozen=True)
class Configuration:
    television: Television
    keypad_name: str | None
    action_of_key: dict[str, Action]

    def with_key_bindings(self, keypad_name: str, action_of_key: dict[str, Action]) -> "Configuration":
        return dataclasses.replace(self, keypad_name=keypad_name, action_of_key=action_of_key)


class ConfigurationMissingError(Exception):
    pass


def client_key_path(configuration_path: pathlib.Path) -> pathlib.Path:
    return configuration_path.parent / CLIENT_KEY_FILE_NAME


def load_configuration(configuration_path: pathlib.Path) -> Configuration:
    if not configuration_path.exists():
        raise ConfigurationMissingError(
            f"{configuration_path} does not exist, and `lg-tv-local-commander pair --ip <address>` creates it"
        )
    fields = json.loads(configuration_path.read_text())
    return Configuration(
        television=Television(
            ip_address=fields["television"]["ip_address"],
            mac_address=fields["television"]["mac_address"],
        ),
        keypad_name=fields.get("keypad_name"),
        action_of_key={key: Action(action) for key, action in fields.get("action_of_key", {}).items()},
    )


def save_configuration(configuration: Configuration, configuration_path: pathlib.Path) -> None:
    fields = {
        "television": dataclasses.asdict(configuration.television),
        "keypad_name": configuration.keypad_name,
        "action_of_key": {key: action.value for key, action in configuration.action_of_key.items()},
    }
    configuration_path.parent.mkdir(parents=True, exist_ok=True)
    configuration_path.write_text(json.dumps(fields, indent=2) + "\n")
