#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
local_bin_dir="$HOME/.local/bin"
dashboard_lib_dir="$HOME/.local/lib/codex-dashboard"
extension_dir="$HOME/.local/share/gnome-shell/extensions/codex-quota-centre@local"
icon_dir="$HOME/.local/share/icons/hicolor/scalable/apps"
unit_dir="$HOME/.config/systemd/user"

command -v codex >/dev/null 2>&1 || {
    echo "error: codex is not available on PATH" >&2
    exit 1
}
command -v gnome-extensions >/dev/null 2>&1 || {
    echo "error: gnome-extensions is not installed" >&2
    exit 1
}
python3 -c 'import dbus; from gi.repository import Gio, GLib' >/dev/null

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
    "$project_root/codex-panel/codex_app_server.py" \
    "$project_root/codex-panel/quota_snapshot.py" \
    "$project_root/codex-panel/quota_sni.py" \
    "$dashboard_lib_dir/"
install -m 0644 \
    "$project_root/extensions/codex-quota-centre@local/extension.js" \
    "$project_root/extensions/codex-quota-centre@local/dashboardModel.mjs" \
    "$project_root/extensions/codex-quota-centre@local/metadata.json" \
    "$project_root/extensions/codex-quota-centre@local/stylesheet.css" \
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

systemctl --user daemon-reload
systemctl --user enable codex-quota.service
systemctl --user restart codex-quota.service

if ! gnome-extensions list --enabled | grep -Fxq \
    'codex-quota-centre@local'; then
    gnome-extensions enable codex-quota-centre@local
fi

echo "Codex Dashboard files installed."
echo "On an upgrade, sign out and back in when convenient to reload GNOME Shell code."
