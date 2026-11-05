# LG TV local commander

`lg-tv-local-commander` turns an LG webOS TV on and off and switches it to HDMI 1 to 4 from the keys of a keypad attached to a Linux machine, such as a Raspberry Pi.
The commands go over the local network, with no cloud service.

The TV goes on through a Wake-on-LAN packet to its MAC address.
The TV goes into standby, and switches its input, through the webOS WebSocket API on port 3001, with the client of [bscpylgtv](https://github.com/chros73/bscpylgtv).
A press of the power key reads the power state of the TV first, so a TV in standby with Quick Start+ gets the Wake-on-LAN packet and no second power-off.
An input key wakes the TV first when the TV is off.

## Set up the TV once

1. Give the TV a fixed address with a DHCP reservation on the router.
2. Turn on the TV setting that lets the network turn the TV on, which LG names "Turn on via Wi-Fi" or "Mobile TV On" depending on the model.
3. Connect the TV by cable when possible, because Wake-on-LAN over Wi-Fi fails on some models.

The machine and the TV are on the same subnet, because a Wake-on-LAN broadcast stays in its subnet.

## Install on the machine

The package `python3-evdev` of Debian gives the `evdev` module, which pip would otherwise compile.

```sh
sudo apt install python3-evdev python3-venv
python3 -m venv --system-site-packages ~/.local/share/lg-tv-local-commander/venv
~/.local/share/lg-tv-local-commander/venv/bin/pip install ~/repositories/lg-tv-local-commander
mkdir -p ~/.local/bin
ln -s ~/.local/share/lg-tv-local-commander/venv/bin/lg-tv-local-commander ~/.local/bin/
```

The user who reads the keypad is in the group `input`, which `sudo usermod -aG input $USER` and a new login give.

## Pair with the TV

```sh
lg-tv-local-commander pair --ip 192.168.1.50
```

The TV shows a prompt, and the pairing ends when the prompt is accepted on the TV.
The command saves the client key to `~/.config/lg-tv-local-commander/client-key.sqlite`, and the address and the MAC address of the TV to `~/.config/lg-tv-local-commander/config.json`.

## Run the actions from a shell

| Command | Action |
|---|---|
| `lg-tv-local-commander power-on` | wakes the TV with Wake-on-LAN and waits up to 30 s for it to answer |
| `lg-tv-local-commander power-off` | puts the TV into standby |
| `lg-tv-local-commander power-toggle` | puts the TV into standby when it shows a picture or plays sound, and wakes it otherwise |
| `lg-tv-local-commander input 2` | wakes the TV when needed and switches it to HDMI 2 |
| `lg-tv-local-commander press KEY_A` | runs the action bound to the key `KEY_A` |

## Assign the keys of the keypad

```sh
lg-tv-local-commander assign-keys
```

The script lists the input devices with keys and asks for the number of the keypad, the first time or with `--choose-keypad`.
The script then names each action in turn.
A press of a key of the keypad binds that key to the action, and Enter in the terminal skips the action.
The script replaces the earlier bindings and saves the new ones to `config.json`.

The actions are a power toggle, power on, power off and HDMI 1 to 4.
One key for the toggle and four keys for the inputs take five keys.

## Share the keypad with other programs

The script and the listener read the keypad without grabbing it.
Other programs, such as a volume daemon, read the same keys at the same time, and each program ignores the keys it does not map.
A keypad that another process grabs sends its keys to that process alone, so the script and the listener then name the device and stop.

A key with a code below 256 also reaches the text console of the machine.
The console ignores the codes of 256 and more, so a udev hwdb file that remaps the keys of the keypad to `KEY_MACRO1` and up keeps them out of the console:

```
# /etc/udev/hwdb.d/61-keypad-macro-keys.hwdb
evdev:input:b0003v514Cp4155*
 KEYBOARD_KEY_70004=macro1
 KEYBOARD_KEY_70005=macro2
```

The match line holds the bus `0003` for USB and the USB ID of the keypad in uppercase.
Each entry holds a scan code in lowercase hexadecimal, which `sudo evtest` prints as `MSC_SCAN` for each press.
`sudo systemd-hwdb update && sudo udevadm trigger` applies the file, and `assign-keys` then shows the keys as `KEY_MACRO1` and up.

## Run the listener as a service

```sh
sudo cp systemd/lg-tv-local-commander@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lg-tv-local-commander@$USER.service
journalctl -u lg-tv-local-commander@$USER -f
```

The listener finds the keypad by its name, reads every input device of that name, and opens the keypad again after it disappears and comes back.
The journal shows each key pressed and the action that it runs.
# lg-tv-local-commander
