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

        flash = zmk-nix.packages.${system}.flash.override {inherit firmware;};
        # Like zmk-nix's updater (which can't find zephyrDepsHash here): moves each west.yml revision to the head of
        # the branch named in its comment, then refreshes zephyrDepsHash. Every image shares the deps, so any one will do.
        update = pkgs.writeShellApplication {
          name = "update";
          runtimeInputs = [pkgs.git pkgs.yq pkgs.gnused];
          text = ''
            root=$(git rev-parse --show-toplevel)
            west=$root/config/west.yml

            changed=0
            while IFS=$'\t' read -r url rev; do
              branch=$(grep -F "$rev" "$west" | sed -n 's/.*# *//p')
              [ -n "$branch" ] || continue
              new=$(git ls-remote "$url" "refs/heads/$branch" | cut -f1)
              [ -n "$new" ] || { echo "no branch '$branch' in $url" >&2; exit 1; }
              [ "$new" = "$rev" ] && echo "$url: up to date" && continue
              sed -i "s|$rev|$new|" "$west"
              echo "$url: ''${rev:0:7} -> ''${new:0:7}"
              changed=1
            done < <(
              # shellcheck disable=SC2016 # $r and $remote are jq variables
              yq -r '.manifest.remotes as $r | .manifest.projects[] | .remote as $remote
                | [(($r[] | select(.name == $remote))."url-base" + "/" + (."repo-path" // .name)), .revision] | @tsv' "$west"
            )
            [ "$changed" = 1 ] || { echo "nothing to update"; exit 0; }

            cur=$(nix eval --raw "$root#dongle.westDeps.outputHash")
            drv=$(nix eval --raw "$root#dongle.westDeps" --apply 'd: (d.overrideAttrs { outputHash = "${lib.fakeHash}"; }).drvPath')
            new=$(nix build --no-link "$drv^*" 2>&1 | sed -n 's/^ *got: *//p' || true)
            [ -n "$new" ] || { echo "could not compute the new zephyrDepsHash" >&2; exit 1; }
            sed -i "s|$cur|$new|" "$root/flake.nix"
            echo "zephyrDepsHash: $new"
          '';
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
