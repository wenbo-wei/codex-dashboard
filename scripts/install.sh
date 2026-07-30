#!/bin/sh
set -eu

project_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
extension_uuid='codex-dashboard@wenbo-wei'
legacy_extension_uuid='codex-quota-centre@local'
local_bin_dir="$HOME/.local/bin"
dashboard_lib_dir="$HOME/.local/lib/codex-dashboard"
extension_dir="$HOME/.local/share/gnome-shell/extensions/$extension_uuid"
legacy_extension_dir="$HOME/.local/share/gnome-shell/extensions/$legacy_extension_uuid"
icon_dir="$HOME/.local/share/icons/hicolor/scalable/apps"
unit_dir="$HOME/.config/systemd/user"
legacy_was_enabled=false

command -v codex >/dev/null 2>&1 || {
    echo "error: codex is not available on PATH" >&2
    exit 1
}
command -v gnome-extensions >/dev/null 2>&1 || {
    echo "error: gnome-extensions is not installed" >&2
    exit 1
}
python3 -c 'import dbus; from gi.repository import Gio, GLib' >/dev/null

transaction_dir=$(mktemp -d)
extension_backup_dir="$transaction_dir/extension-backup"
extension_was_present=false
if [ -d "$extension_dir" ]; then
    extension_was_present=true
    install -d "$extension_backup_dir"
    cp -a "$extension_dir/." "$extension_backup_dir/"
fi

cleanup_transaction() {
    rm -rf -- "$transaction_dir"
}

restore_extension_files() {
    rm -f \
        "$extension_dir/extension.js" \
        "$extension_dir/dashboardModel.mjs" \
        "$extension_dir/metadata.json" \
        "$extension_dir/stylesheet.css"
    if [ "$extension_was_present" = true ]; then
        install -d "$extension_dir"
        cp -a "$extension_backup_dir/." "$extension_dir/"
    else
        rmdir "$extension_dir" 2>/dev/null || true
    fi
}

abort_migration() {
    gnome-extensions disable "$extension_uuid" >/dev/null 2>&1 || true
    restore_extension_files
    if [ "$legacy_was_enabled" = true ]; then
        gnome-extensions enable "$legacy_extension_uuid" \
            >/dev/null 2>&1 || true
    fi
    echo "error: $1" >&2
    exit 1
}

stage_migration() {
    echo "Codex Dashboard files staged as $extension_uuid."
    echo "The current GNOME Shell has not discovered the new UUID."
    echo "The legacy extension remains active."
    echo "Sign out, sign back in, and rerun this installer to finish migration."
    exit 2
}

extension_is_listed() {
    if ! codex_dashboard_extension_list=$(
        gnome-extensions list "$1"
    ); then
        return 2
    fi
    printf '%s\n' "$codex_dashboard_extension_list" | grep -Fxq "$2"
}

trap cleanup_transaction 0

install -d \
    "$local_bin_dir" \
    "$dashboard_lib_dir" \
    "$extension_dir" \
    "$icon_dir" \
    "$unit_dir"

install -m 0755 \
    "$project_root/codex-quota/codex-dashboard-data" \
    "$local_bin_dir/codex-dashboard-data"
install -m 0755 \
    "$project_root/codex-quota/codex-quota" \
    "$local_bin_dir/codex-quota"
install -m 0644 \
    "$project_root/backend/codex_app_server.py" \
    "$project_root/backend/quota_snapshot.py" \
    "$project_root/backend/quota_sni.py" \
    "$dashboard_lib_dir/"
install -m 0644 \
    "$project_root/extensions/$extension_uuid/extension.js" \
    "$project_root/extensions/$extension_uuid/dashboardModel.mjs" \
    "$project_root/extensions/$extension_uuid/metadata.json" \
    "$project_root/extensions/$extension_uuid/stylesheet.css" \
    "$extension_dir/"
install -m 0644 \
    "$project_root/assets/codex-dashboard-symbolic.svg" \
    "$icon_dir/codex-dashboard-symbolic.svg"
install -m 0644 \
    "$project_root/systemd/codex-quota.service" \
    "$unit_dir/codex-quota.service"

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null
fi

if ! gnome-extensions info "$extension_uuid" >/dev/null 2>&1; then
    stage_migration
fi

if extension_is_listed --enabled "$legacy_extension_uuid"; then
    legacy_was_enabled=true
elif [ "$?" -eq 2 ]; then
    abort_migration "could not read the enabled extension list"
fi

if [ "$legacy_was_enabled" = true ]; then
    if ! gnome-extensions disable "$legacy_extension_uuid"; then
        abort_migration "could not disable $legacy_extension_uuid"
    fi
fi

if extension_is_listed --active "$extension_uuid"; then
    :
elif [ "$?" -eq 2 ]; then
    abort_migration "could not read the active extension list"
else
    if extension_is_listed --enabled "$extension_uuid"; then
        if ! gnome-extensions disable "$extension_uuid"; then
            abort_migration "could not reset $extension_uuid"
        fi
    elif [ "$?" -eq 2 ]; then
        abort_migration "could not read the enabled extension list"
    fi
    if ! gnome-extensions enable "$extension_uuid"; then
        abort_migration "could not enable $extension_uuid"
    fi
fi

if ! extension_is_listed --active "$extension_uuid"; then
    abort_migration "$extension_uuid did not become active"
fi

rm -f \
    "$legacy_extension_dir/extension.js" \
    "$legacy_extension_dir/dashboardModel.mjs" \
    "$legacy_extension_dir/metadata.json" \
    "$legacy_extension_dir/stylesheet.css" \
    "$legacy_extension_dir/extension-placement-v6.js" \
    "$legacy_extension_dir/stylesheet-placement-v6.css"
if ! rmdir "$legacy_extension_dir" 2>/dev/null &&
    [ -d "$legacy_extension_dir" ]; then
    echo "warning: preserved unrecognized files in $legacy_extension_dir" >&2
fi

systemctl --user daemon-reload
systemctl --user enable codex-quota.service
systemctl --user restart codex-quota.service

echo "Codex Dashboard installed as $extension_uuid."
echo "On an upgrade, sign out and back in when convenient to reload GNOME Shell code."
