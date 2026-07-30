#!/bin/sh
set -eu

project_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
test_root=$(mktemp -d)
schema_dir="$test_root/schemas"
config_dir="$test_root/config"

cleanup() {
    rm -rf -- "$test_root"
}
trap cleanup 0 HUP INT TERM

install -d "$schema_dir" "$config_dir"
install -m 0644 \
    "$project_root/tests/schemas/org.gnome.shell.gschema.xml" \
    "$schema_dir/"
glib-compile-schemas "$schema_dir"

export GSETTINGS_BACKEND=keyfile
export GSETTINGS_SCHEMA_DIR="$schema_dir"
export XDG_CONFIG_HOME="$config_dir"

gsettings set org.gnome.shell enabled-extensions \
    "['keep@example', 'codex-quota-centre@local']"
gsettings set org.gnome.shell disabled-extensions \
    "['codex-dashboard@wenbo-wei', 'disabled@example']"

snapshot="$test_root/extension-settings.json"
gjs -m "$project_root/scripts/queue-extension.mjs" \
    --snapshot \
    "$snapshot"

gjs -m "$project_root/scripts/queue-extension.mjs" \
    codex-dashboard@wenbo-wei \
    codex-quota-centre@local

enabled=$(gsettings get org.gnome.shell enabled-extensions)
disabled=$(gsettings get org.gnome.shell disabled-extensions)
[ "$enabled" = "['keep@example', 'codex-dashboard@wenbo-wei']" ]
[ "$disabled" = "['disabled@example', 'codex-quota-centre@local']" ]

gjs -m "$project_root/scripts/queue-extension.mjs" \
    --restore \
    "$snapshot"

[ "$(gsettings get org.gnome.shell enabled-extensions)" = \
    "['keep@example', 'codex-quota-centre@local']" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = \
    "['codex-dashboard@wenbo-wei', 'disabled@example']" ]

gjs -m "$project_root/scripts/queue-extension.mjs" \
    codex-dashboard@wenbo-wei \
    codex-quota-centre@local

[ "$(gsettings get org.gnome.shell enabled-extensions)" = "$enabled" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = "$disabled" ]

gjs -m "$project_root/scripts/queue-extension.mjs" \
    --disable \
    codex-dashboard@wenbo-wei

[ "$(gsettings get org.gnome.shell enabled-extensions)" = \
    "['keep@example']" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = \
    "['disabled@example', 'codex-quota-centre@local', "\
"'codex-dashboard@wenbo-wei']" ]

gjs -m "$project_root/scripts/queue-extension.mjs" \
    --disable \
    codex-dashboard@wenbo-wei

[ "$(gsettings get org.gnome.shell enabled-extensions)" = \
    "['keep@example']" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = \
    "['disabled@example', 'codex-quota-centre@local', "\
"'codex-dashboard@wenbo-wei']" ]
