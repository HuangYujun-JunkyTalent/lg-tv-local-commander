import argparse
import asyncio
import logging
import pathlib
import sys

import lg_tv_local_commander.assign_keys as assign_keys
import lg_tv_local_commander.configuration as configuration
import lg_tv_local_commander.keypad as keypad
import lg_tv_local_commander.listen_to_keypad as listen_to_keypad
import lg_tv_local_commander.television as television

INPUT_ACTION_OF_NUMBER = {
    1: configuration.Action.INPUT_HDMI_1,
    2: configuration.Action.INPUT_HDMI_2,
    3: configuration.Action.INPUT_HDMI_3,
    4: configuration.Action.INPUT_HDMI_4,
}
EXPECTED_FAILURES = (
    configuration.ConfigurationMissingError,
    television.TelevisionUnreachableError,
    television.TelevisionNotPairedError,
    keypad.KeypadNotFoundError,
    keypad.KeypadGrabbedError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lg-tv-local-commander",
        description="Turn an LG webOS TV on and off and switch its HDMI input over the local network.",
    )
    parser.add_argument(
        "--config", type=pathlib.Path, default=configuration.DEFAULT_CONFIGURATION_PATH, dest="configuration_path"
    )
    subcommands = parser.add_subparsers(dest="subcommand", required=True)

    pair = subcommands.add_parser("pair", help="pair with the TV, which shows a prompt to accept")
    pair.add_argument("--ip", required=True, dest="ip_address", help="IP address of the TV")

    subcommands.add_parser("power-on", help="wake the TV with Wake-on-LAN")
    subcommands.add_parser("power-off", help="put the TV into standby")
    subcommands.add_parser("power-toggle", help="put the TV into standby when it is on, and wake it otherwise")

    input_parser = subcommands.add_parser("input", help="switch to an HDMI input, waking the TV first when needed")
    input_parser.add_argument("number", type=int, choices=sorted(INPUT_ACTION_OF_NUMBER))

    assign = subcommands.add_parser("assign-keys", help="press a key of the keypad for each action")
    assign.add_argument("--choose-keypad", action="store_true", help="choose the keypad again from a list")

    press = subcommands.add_parser("press", help="run the action bound to a key code, such as KEY_A")
    press.add_argument("key")

    subcommands.add_parser("listen", help="run the action of each key pressed on the keypad")
    return parser


def pair(configuration_path: pathlib.Path, ip_address: str) -> None:
    print(f"Accept the prompt on the TV at {ip_address}.")
    paired_television = asyncio.run(
        television.pair_with_television(ip_address, configuration.client_key_path(configuration_path))
    )
    if configuration_path.exists():
        current = configuration.load_configuration(configuration_path)
        updated = configuration.Configuration(paired_television, current.keypad_name, current.action_of_key)
    else:
        updated = configuration.Configuration(paired_television, keypad_name=None, action_of_key={})
    configuration.save_configuration(updated, configuration_path)
    print(f"Paired with {ip_address}, MAC address {paired_television.mac_address}, saved to {configuration_path}.")


def run_named_action(configuration_path: pathlib.Path, action: configuration.Action) -> None:
    current = configuration.load_configuration(configuration_path)
    asyncio.run(television.run_action(action, current.television, configuration.client_key_path(configuration_path)))


def press(configuration_path: pathlib.Path, key: str) -> None:
    action = configuration.load_configuration(configuration_path).action_of_key.get(key)
    if action is None:
        print(f"{key} has no action in {configuration_path}.", file=sys.stderr)
        sys.exit(1)
    run_named_action(configuration_path, action)


def configured_or_chosen_keypad_name(configuration_path: pathlib.Path) -> str:
    keypad_name = configuration.load_configuration(configuration_path).keypad_name
    return keypad_name if keypad_name is not None else assign_keys.choose_keypad_name()


def listen(configuration_path: pathlib.Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    current = configuration.load_configuration(configuration_path)
    asyncio.run(listen_to_keypad.listen_to_keypad(current, configuration.client_key_path(configuration_path)))


def main() -> None:
    arguments = build_parser().parse_args()
    configuration_path = arguments.configuration_path
    try:
        if arguments.subcommand == "pair":
            pair(configuration_path, arguments.ip_address)
        elif arguments.subcommand == "power-on":
            run_named_action(configuration_path, configuration.Action.POWER_ON)
        elif arguments.subcommand == "power-off":
            run_named_action(configuration_path, configuration.Action.POWER_OFF)
        elif arguments.subcommand == "power-toggle":
            run_named_action(configuration_path, configuration.Action.POWER_TOGGLE)
        elif arguments.subcommand == "input":
            run_named_action(configuration_path, INPUT_ACTION_OF_NUMBER[arguments.number])
        elif arguments.subcommand == "assign-keys":
            keypad_name = (
                assign_keys.choose_keypad_name()
                if arguments.choose_keypad
                else configured_or_chosen_keypad_name(configuration_path)
            )
            assign_keys.assign_keys(configuration_path, keypad_name)
        elif arguments.subcommand == "press":
            press(configuration_path, arguments.key)
        elif arguments.subcommand == "listen":
            listen(configuration_path)
    except EXPECTED_FAILURES as failure:
        print(failure, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
