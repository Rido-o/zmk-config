# Dactyl Cygnus 4x6

ZMK config for a wireless split Dactyl Cygnus 4x6 (Seeed XIAO BLE in each half), using a
[Prospector](https://github.com/carrefinho/prospector-zmk-module) as a dongle.

Much of the code for this comes from <https://github.com/juhakaup/zmk-cygnus-4x6>

## Firmware

Firmware is built locally with [zmk-nix](https://github.com/lilyinstarlight/zmk-nix) (`flake.nix`). The GitHub
mirror also builds it with GitHub Actions (`build.yaml`; keep the two lists in sync).

```sh
nix build            # every image, in result/
nix run .#flash      # flash the dongle and both halves, one at a time
nix run .#update     # after changing config/west.yml: bump the west dependencies and their hash
```

The first build downloads ZMK and Zephyr (about 10 minutes); after that only changed images are recompiled.

| Image | Flash to |
| --- | --- |
| `cygnus_dongle.uf2` (`cygnus_dongle prospector_adapter`) | The Prospector dongle (BLE central, connects to the host over USB/BT) |
| `cygnus_left.uf2` / `cygnus_right.uf2` | Each keyboard half (BLE peripherals) |
| `cygnus_settings_reset.uf2` | Any device, to wipe its pairing/settings before reflashing (copy it by hand) |
| `cygnus_tester.uf2` (`tester_xiao`) | A XIAO, for testing the switch wiring (copy it by hand) |

The halves only work with the dongle. If they won't connect after flashing,
flash `settings_reset` to all three devices, then reflash the normal firmware.

## Keymap

Hold Backspace for Symbols, hold Enter for Navigation, and hold Shift + Z (or `'` + Shift) for Bluetooth.
Press Esc + Tab together to toggle Qwerty, and both Shifts together to toggle Gaming.

![Every layer of the Cygnus keymap](docs/keymap.png)

A faint grey key does nothing. A dashed key (▽) passes through to the Base layer. The purple key is the one you
hold (or press, for a toggle) to reach that layer.

The picture is drawn from `config/cygnus.keymap` by `tools/draw-keymap.py`. Redraw it after changing the keymap
and commit it along with the change. On NixOS the script fetches its own Python and pycairo; elsewhere it needs
`pycairo` and the Noto Sans font.

```sh
tools/draw-keymap.py
```

## Keymap Editing

The keymap lives in `config/cygnus.keymap`.

### ZMK Studio (Recommended)

Studio is enabled on the dongle only.

1. Connect the dongle via USB
2. Unlock Studio: hold the Bluetooth layer combo (`Shift` + `Z` on the left, or `'` + `Shift` on the right)
   and press the `Studio Unlock` key (top row, 5th from the left)
3. Open [ZMK Studio](https://zmk.studio/) (web or desktop app) and connect to the keyboard
