import pathlib
import selectors
import sys

import evdev

import lg_tv_local_commander.configuration as configuration
import lg_tv_local_commander.keypad as keypad

ACTION_DESCRIPTIONS = {
    configuration.Action.POWER_TOGGLE: "power on or off, one key for both",
    configuration.Action.POWER_ON: "power on",
    configuration.Action.POWER_OFF: "power off",
    configuration.Action.INPUT_HDMI_1: "input HDMI 1",
    configuration.Action.INPUT_HDMI_2: "input HDMI 2",
    configuration.Action.INPUT_HDMI_3: "input HDMI 3",
    configuration.Action.INPUT_HDMI_4: "input HDMI 4",
}


def choose_keypad_name() -> str:
    keyboards = keypad.list_keyboards()
    if not keyboards:
        raise keypad.KeypadNotFoundError("no input device with keys is readable, and the user may lack the group input")
    names = sorted({device.name for device in keyboards})
    for number, name in enumerate(names, start=1):
        print(f"  {number}. {name}")
    while True:
        answer = input("Number of the keypad: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(names):
            return names[int(answer) - 1]
        print(f"{answer!r} is not a number from 1 to {len(names)}.")


def wait_for_key_or_enter(devices: list[evdev.InputDevice]) -> str | None:
    with selectors.DefaultSelector() as selector:
        selector.register(sys.stdin, selectors.EVENT_READ)
        for device in devices:
            selector.register(device, selectors.EVENT_READ)
        while True:
            for selected, _ in selector.select():
                if selected.fileobj is sys.stdin:
                    sys.stdin.readline()
                    return None
                for event in selected.fileobj.read():
                    key = keypad.pressed_key_code_name(event)
                    if key is not None:
                        return key


def ask_for_key_of_each_action(devices: list[evdev.InputDevice]) -> dict[str, configuration.Action]:
    action_of_key: dict[str, configuration.Action] = {}
    for action, description in ACTION_DESCRIPTIONS.items():
        while True:
            print(f"Press the key for {description}, or Enter here to skip: ", end="", flush=True)
            key = wait_for_key_or_enter(devices)
            if key is None:
                print("skipped")
                break
            if key in action_of_key:
                print(f"{key} is already assigned to {ACTION_DESCRIPTIONS[action_of_key[key]]}.")
                continue
            print(key)
            action_of_key[key] = action
            break
    return action_of_key


def assign_keys(configuration_path: pathlib.Path, keypad_name: str) -> None:
    current = configuration.load_configuration(configuration_path)
    print(f"Keypad: {keypad_name}")
    devices = keypad.open_keypad_devices(keypad_name)
    keypad.check_not_grabbed(devices)
    print("The keys also reach the other readers of the keypad, such as knob-volume.py.")
    action_of_key = ask_for_key_of_each_action(devices)
    configuration.save_configuration(current.with_key_bindings(keypad_name, action_of_key), configuration_path)
    print(f"Saved {len(action_of_key)} key bindings to {configuration_path}.")
