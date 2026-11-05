import asyncio
import logging
import pathlib

import evdev

import lg_tv_local_commander.configuration as configuration
import lg_tv_local_commander.keypad as keypad
import lg_tv_local_commander.television as television

SECONDS_BETWEEN_KEYPAD_SEARCHES = 2.0

logger = logging.getLogger(__name__)


async def queue_key_presses(device: evdev.InputDevice, pressed_keys: asyncio.Queue[str]) -> None:
    async for event in device.async_read_loop():
        key = keypad.pressed_key_code_name(event)
        if key is not None:
            await pressed_keys.put(key)


async def queue_key_presses_until_keypad_disappears(
    devices: list[evdev.InputDevice], pressed_keys: asyncio.Queue[str]
) -> None:
    try:
        async with asyncio.TaskGroup() as task_group:
            for device in devices:
                task_group.create_task(queue_key_presses(device, pressed_keys))
    except* OSError as failures:
        logger.warning("Keypad disappeared: %s", failures.exceptions[0])


async def run_actions_of_pressed_keys(
    pressed_keys: asyncio.Queue[str], current: configuration.Configuration, client_key_path: pathlib.Path
) -> None:
    while True:
        key = await pressed_keys.get()
        action = current.action_of_key.get(key)
        if action is None:
            logger.info("%s has no action", key)
            continue
        logger.info("%s runs %s", key, action.value)
        try:
            await television.run_action(action, current.television, client_key_path)
        except Exception:
            logger.exception("%s failed", action.value)


async def listen_to_keypad(current: configuration.Configuration, client_key_path: pathlib.Path) -> None:
    if current.keypad_name is None:
        raise keypad.KeypadNotFoundError("the configuration names no keypad, and `lg-tv-local-commander assign-keys` sets one")
    pressed_keys: asyncio.Queue[str] = asyncio.Queue()
    action_runner = asyncio.create_task(run_actions_of_pressed_keys(pressed_keys, current, client_key_path))
    last_failure = ""
    while not action_runner.done():
        try:
            devices = keypad.open_keypad_devices(current.keypad_name)
            keypad.check_not_grabbed(devices)
            logger.info("Listening to %s", ", ".join(device.path for device in devices))
            last_failure = ""
            await queue_key_presses_until_keypad_disappears(devices, pressed_keys)
        except (keypad.KeypadNotFoundError, keypad.KeypadGrabbedError) as failure:
            if str(failure) != last_failure:
                logger.warning("%s", failure)
                last_failure = str(failure)
        await asyncio.sleep(SECONDS_BETWEEN_KEYPAD_SEARCHES)
    await action_runner
