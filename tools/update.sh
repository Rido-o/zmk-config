#!/usr/bin/env bash
# Like zmk-nix's updater (which can't find zephyrDepsHash here): moves each config/west.yml revision to the head of
# the branch named in its comment, then refreshes zephyrDepsHash in flake.nix. Every image shares the deps, so any
# one will do. Run it with `nix run .#update`, which supplies git, yq and FAKE_HASH.

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
  echo "$url: ${rev:0:7} -> ${new:0:7}"
  changed=1
done < <(
  # shellcheck disable=SC2016 # $r and $remote are jq variables
  yq -r '.manifest.remotes as $r | .manifest.projects[] | .remote as $remote
    | [(($r[] | select(.name == $remote))."url-base" + "/" + (."repo-path" // .name)), .revision] | @tsv' "$west"
)
[ "$changed" = 1 ] || { echo "nothing to update"; exit 0; }

cur=$(nix eval --raw "$root#dongle.westDeps.outputHash")
drv=$(nix eval --raw "$root#dongle.westDeps" --apply "d: (d.overrideAttrs { outputHash = \"$FAKE_HASH\"; }).drvPath")
new=$(nix build --no-link "$drv^*" 2>&1 | sed -n 's/^ *got: *//p' || true)
[ -n "$new" ] || { echo "could not compute the new zephyrDepsHash" >&2; exit 1; }
sed -i "s|$cur|$new|" "$root/flake.nix"
echo "zephyrDepsHash: $new"
