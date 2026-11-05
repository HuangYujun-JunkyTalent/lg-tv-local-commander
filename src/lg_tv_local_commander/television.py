import asyncio
import contextlib
import importlib.resources
import pathlib
import socket
import time
from collections.abc import AsyncIterator

import bscpylgtv
import bscpylgtv.exceptions
import websockets.exceptions

import lg_tv_local_commander.configuration as configuration

WAKE_ON_LAN_PORT = 9
BROADCAST_ADDRESS = "255.255.255.255"
SECONDS_TO_WAIT_FOR_WAKE_UP = 30.0
SECONDS_BETWEEN_WAKE_UP_PROBES = 1.0
# The manifest without a signature that bscpylgtv ships for webOS 26, which rejects the signed default manifest.
WEBOS_MANIFEST_PATH = importlib.resources.files("lg_tv_local_commander") / "webos-manifest.json"
POWER_STATES_WITH_PICTURE_OR_SOUND = {"Active", "Screen Off", "Screen Saver"}
CONNECTION_FAILURES = (
    OSError,
    asyncio.TimeoutError,
    websockets.exceptions.WebSocketException,
    bscpylgtv.exceptions.PyLGTVPairException,
)


class TelevisionUnreachableError(Exception):
    pass


class TelevisionNotPairedError(Exception):
    pass


def magic_packet(mac_address: str) -> bytes:
    mac_bytes = bytes.fromhex(mac_address.replace(":", "").replace("-", ""))
    if len(mac_bytes) != 6:
        raise ValueError(f"MAC address {mac_address!r} has {len(mac_bytes)} bytes instead of 6")
    return b"\xff" * 6 + mac_bytes * 16


def send_wake_on_lan(television: configuration.Television) -> None:
    packet = magic_packet(television.mac_address)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.sendto(packet, (BROADCAST_ADDRESS, WAKE_ON_LAN_PORT))
        udp_socket.sendto(packet, (television.ip_address, WAKE_ON_LAN_PORT))


async def create_client(ip_address: str, client_key_path: pathlib.Path) -> bscpylgtv.WebOsClient:
    client_key_path.parent.mkdir(parents=True, exist_ok=True)
    return await bscpylgtv.WebOsClient.create(
        ip_address,
        key_file_path=str(client_key_path),
        manifest_file_path=str(WEBOS_MANIFEST_PATH),
        timeout_connect=2,
        connect_retry_attempts=1,
        ping_interval=None,
        states=[],
    )


@contextlib.asynccontextmanager
async def connected_client(
    television: configuration.Television, client_key_path: pathlib.Path
) -> AsyncIterator[bscpylgtv.WebOsClient]:
    client = await create_client(television.ip_address, client_key_path)
    if not client.is_registered():
        raise TelevisionNotPairedError(
            f"{client_key_path} holds no client key for {television.ip_address}, "
            "and `lg-tv-local-commander pair` creates one"
        )
    try:
        await client.connect()
    except CONNECTION_FAILURES as failure:
        raise TelevisionUnreachableError(f"{television.ip_address} refused or ignored the connection: {failure!r}") from failure
    try:
        yield client
    finally:
        await client.disconnect()


async def has_picture_or_sound(client: bscpylgtv.WebOsClient) -> bool:
    power_state = await client.get_power_state()
    return power_state.get("state") in POWER_STATES_WITH_PICTURE_OR_SOUND


async def is_television_on(television: configuration.Television, client_key_path: pathlib.Path) -> bool:
    try:
        async with connected_client(television, client_key_path) as client:
            return await has_picture_or_sound(client)
    except TelevisionUnreachableError:
        return False


async def wake_television(television: configuration.Television, client_key_path: pathlib.Path) -> None:
    deadline = time.monotonic() + SECONDS_TO_WAIT_FOR_WAKE_UP
    while time.monotonic() < deadline:
        send_wake_on_lan(television)
        if await is_television_on(television, client_key_path):
            return
        await asyncio.sleep(SECONDS_BETWEEN_WAKE_UP_PROBES)
    raise TelevisionUnreachableError(
        f"{television.ip_address} did not turn on within {SECONDS_TO_WAIT_FOR_WAKE_UP:.0f} s of Wake-on-LAN "
        f"to {television.mac_address}"
    )


async def turn_television_on(television: configuration.Television, client_key_path: pathlib.Path) -> None:
    if not await is_television_on(television, client_key_path):
        await wake_television(television, client_key_path)


async def turn_television_off(television: configuration.Television, client_key_path: pathlib.Path) -> None:
    try:
        async with connected_client(television, client_key_path) as client:
            await client.power_off()
    except TelevisionUnreachableError:
        return


async def toggle_television_power(television: configuration.Television, client_key_path: pathlib.Path) -> None:
    if await is_television_on(television, client_key_path):
        await turn_television_off(television, client_key_path)
    else:
        await wake_television(television, client_key_path)


async def switch_input(
    television: configuration.Television, client_key_path: pathlib.Path, input_identifier: str
) -> None:
    await turn_television_on(television, client_key_path)
    async with connected_client(television, client_key_path) as client:
        await client.set_input(input_identifier)


async def run_action(
    action: configuration.Action, television: configuration.Television, client_key_path: pathlib.Path
) -> None:
    if action is configuration.Action.POWER_TOGGLE:
        await toggle_television_power(television, client_key_path)
    elif action is configuration.Action.POWER_ON:
        await turn_television_on(television, client_key_path)
    elif action is configuration.Action.POWER_OFF:
        await turn_television_off(television, client_key_path)
    else:
        await switch_input(television, client_key_path, configuration.INPUT_IDENTIFIER_OF_ACTION[action])


def read_mac_address_from_arp_table(ip_address: str) -> str | None:
    for line in pathlib.Path("/proc/net/arp").read_text().splitlines()[1:]:
        columns = line.split()
        if columns[0] == ip_address and columns[3] != "00:00:00:00:00:00":
            return columns[3]
    return None


async def pair_with_television(ip_address: str, client_key_path: pathlib.Path) -> configuration.Television:
    client = await create_client(ip_address, client_key_path)
    try:
        await client.connect()
    except bscpylgtv.exceptions.PyLGTVPairException as failure:
        raise TelevisionNotPairedError(
            f"{ip_address} answered but did not grant the pairing, "
            "because its prompt was declined, timed out or could not show while the screen was off"
        ) from failure
    except CONNECTION_FAILURES as failure:
        raise TelevisionUnreachableError(f"{ip_address} refused or ignored the connection: {failure!r}") from failure
    await client.disconnect()
    mac_address = read_mac_address_from_arp_table(ip_address)
    if mac_address is None:
        raise TelevisionUnreachableError(f"the ARP table of this machine has no MAC address for {ip_address}")
    return configuration.Television(ip_address=ip_address, mac_address=mac_address)
