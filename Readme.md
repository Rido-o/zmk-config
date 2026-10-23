# Dactyl Cygnus 4x6

ZMK config for a wireless split Dactyl Cygnus 4x6 (Seeed XIAO BLE in each half), using a
[Prospector](https://github.com/carrefinho/prospector-zmk-module) as a dongle.

Much of the code for this comes from <https://github.com/juhakaup/zmk-cygnus-4x6>

## Firmware

Firmware is built locally with [zmk-nix](https://github.com/lilyinstarlight/zmk-nix) (`flake.nix`).

```sh
nix build            # every image, in result/
nix run .#flash      # flash the dongle and both halves, one at a time (notifies when the build is done)
nix run .#update     # move ZMK and the modules to their branch heads, and refresh the deps hash
```

The first build downloads ZMK and Zephyr (about 10 minutes); after that only changed images are recompiled.

`update` follows the branch named in the comment after each `revision:` in `config/west.yml` (`# main`), so keep
those comments to just the branch name. When it moves something it re-downloads the dependencies to work out the
new `zephyrDepsHash` (several minutes); the next `nix build` then reuses that download. To pin a revision by hand
instead, edit it in `west.yml` and run `update` too, or set the hash from the error the next build prints.

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

The picture is drawn from `config/cygnus.keymap` and the physical layout in `boards/shields/cygnus/cygnus-layout.dtsi`
by `tools/draw-keymap.py`. A pre-commit hook redraws it and adds it to any commit that changes either of those, the
script or `flake.lock`. Enable it once per clone:

```sh
git config core.hooksPath .githooks
```

To redraw by hand, run `nix run .#draw-keymap`. It brings its own Python, pycairo and Noto Sans, so the picture
comes out the same on any machine. The hook draws from the working tree, so with only part of a keymap change
staged, the picture shows the unstaged part too.

## Keymap Editing

The keymap lives in `config/cygnus.keymap`.

### ZMK Studio (Recommended)

Studio is enabled on the dongle only.

1. Connect the dongle via USB
2. Unlock Studio: hold the Bluetooth layer combo (`Shift` + `Z` on the left, or `'` + `Shift` on the right)
   and press the `Studio Unlock` key (top row, 5th from the left)
3. Open [ZMK Studio](https://zmk.studio/) (web or desktop app) and connect to the keyboard
