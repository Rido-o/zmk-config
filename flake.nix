# Builds the firmware with zmk-nix: `nix build` puts every image in result/, `nix run .#flash` flashes the
# dongle and both halves.
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

    zmk-nix = {
      url = "github:lilyinstarlight/zmk-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    nixpkgs,
    zmk-nix,
  }: let
    inherit (nixpkgs) lib;
    forAllSystems = lib.genAttrs (lib.attrNames zmk-nix.packages);

    builds = {
      dongle = {
        shield = "cygnus_dongle prospector_adapter";
        enableZmkStudio = true;
        extraCmakeFlags = [
          "-DCONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_PROXY=y"
          "-DCONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING=y"
        ];
      };
      left.shield = "cygnus_left";
      right.shield = "cygnus_right";
      settings_reset.shield = "settings_reset";
      tester.shield = "tester_xiao";
    };
  in {
    packages = forAllSystems (system: let
      inherit (zmk-nix.legacyPackages.${system}) buildKeyboard;
      pkgs = nixpkgs.legacyPackages.${system};

      images = lib.mapAttrs (_: b:
        buildKeyboard ({
            # Shared by every image, so they reuse one download of the west dependencies
            name = "cygnus";
            src = lib.sourceFilesBySuffices self [".board" ".cmake" ".conf" ".defconfig" ".dts" ".dtsi" ".keymap" ".overlay" ".shield" ".yml" "_defconfig"];
            board = "xiao_ble//zmk";
            # `nix run .#update` refreshes this after changing config/west.yml
            zephyrDepsHash = "sha256-CQl2JLtNrCrB+G7NwiQTzgbKIYi3t7R+uxnbfVbZ0oQ=";
          }
          // b))
      builds;
    in
      images
      // rec {
        default = firmware;

        firmware =
          pkgs.runCommand "cygnus-firmware" {
            passthru.parts = ["dongle" "left" "right"];
          } ''
            mkdir $out
            ${lib.concatStrings (lib.mapAttrsToList (name: image: ''
                cp ${image}/zmk.uf2 $out/cygnus_${name}.uf2
              '')
              images)}
          '';

        # zmk-nix's flasher, with a desktop notification when it starts (once the firmware has finished building)
        flash = pkgs.writeShellApplication {
          name = "flash";
          runtimeInputs = [pkgs.libnotify];
          text = ''
            notify-send --app-name=zmk-config "Cygnus firmware built" "Ready to flash" || true
            exec ${lib.getExe (zmk-nix.packages.${system}.flash.override {inherit firmware;})} "$@"
          '';
        };
        # Moves ZMK and the modules to their branch heads and refreshes zephyrDepsHash; see tools/update.sh
        update = pkgs.writeShellApplication {
          name = "update";
          runtimeInputs = [pkgs.git pkgs.yq pkgs.gnused];
          runtimeEnv.FAKE_HASH = lib.fakeHash;
          text = builtins.readFile ./tools/update.sh;
        };

        # Runs the working tree's script, which writes docs/keymap.png next to it; bundles its own font so the
        # picture doesn't depend on the system's fonts
        draw-keymap = pkgs.writeShellApplication {
          name = "draw-keymap";
          runtimeInputs = [(pkgs.python3.withPackages (p: [p.pycairo])) pkgs.git];
          runtimeEnv.FONTCONFIG_FILE = pkgs.makeFontsConf {fontDirectories = [pkgs.noto-fonts];};
          text = ''
            root=$(git rev-parse --show-toplevel)
            exec python3 "$root/tools/draw-keymap.py" "$@"
          '';
        };
      });

    devShells = forAllSystems (system: {
      default = zmk-nix.devShells.${system}.default;
    });
  };
}
