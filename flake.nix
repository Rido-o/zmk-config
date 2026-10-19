# Builds the firmware with zmk-nix: `nix build` puts every image in result/, `nix run .#flash` flashes the
# dongle and both halves. Keep `builds` in sync with build.yaml (still used by GitHub Actions).
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
            src = lib.sourceFilesBySuffices self [".board" ".cmake" ".conf" ".defconfig" ".dts" ".dtsi" ".json" ".keymap" ".overlay" ".shield" ".yml" "_defconfig"];
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

        flash = zmk-nix.packages.${system}.flash.override {inherit firmware;};
        update = zmk-nix.packages.${system}.update;
      });

    devShells = forAllSystems (system: {
      default = zmk-nix.devShells.${system}.default;
    });
  };
}
