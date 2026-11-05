import errno

import evdev

KEY_PRESS = 1


class KeypadNotFoundError(Exception):
    pass


class KeypadGrabbedError(Exception):
    pass


def list_keyboards() -> list[evdev.InputDevice]:
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    return [device for device in devices if evdev.ecodes.EV_KEY in device.capabilities()]


def open_keypad_devices(keypad_name: str) -> list[evdev.InputDevice]:
    devices = [device for device in list_keyboards() if device.name == keypad_name]
    if not devices:
        raise KeypadNotFoundError(f"no input device with keys is named {keypad_name!r}")
    return devices


def check_not_grabbed(devices: list[evdev.InputDevice]) -> None:
    """A grabbed device gives this reader no event and no error, so a short grab of its own tells."""
    for device in devices:
        try:
            device.grab()
        except OSError as failure:
            if failure.errno == errno.EBUSY:
                raise KeypadGrabbedError(
                    f"{device.path} ({device.name}) is grabbed by another process, such as an older knob-volume.py"
                ) from failure
            raise
        device.ungrab()


def key_code_name(code: int) -> str:
    names = evdev.ecodes.KEY.get(code) or evdev.ecodes.BTN.get(code) or f"KEY_{code}"
    return names[0] if isinstance(names, list) else names


def pressed_key_code_name(event: evdev.InputEvent) -> str | None:
    if event.type == evdev.ecodes.EV_KEY and event.value == KEY_PRESS:
        return key_code_name(event.code)
    return None
