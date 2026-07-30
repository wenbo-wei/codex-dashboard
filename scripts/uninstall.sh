#!/bin/sh
set -eu

extension_uuid='codex-quota-centre@local'
dashboard_lib_dir="$HOME/.local/lib/codex-dashboard"
extension_dir="$HOME/.local/share/gnome-shell/extensions/$extension_uuid"

if command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions disable "$extension_uuid" >/dev/null 2>&1 || true
fi
systemctl --user disable --now codex-quota.service >/dev/null 2>&1 || true

rm -f \
    "$HOME/.local/bin/codex-dashboard-data" \
    "$HOME/.local/bin/codex-quota" \
    "$HOME/.config/systemd/user/codex-quota.service" \
    "$HOME/.local/share/icons/hicolor/scalable/apps/codex-dashboard-symbolic.svg"
rm -f \
    "$dashboard_lib_dir/codex_app_server.py" \
    "$dashboard_lib_dir/quota_snapshot.py" \
    "$dashboard_lib_dir/quota_sni.py"
rm -f \
    "$extension_dir/extension.js" \
    "$extension_dir/dashboardModel.mjs" \
    "$extension_dir/metadata.json" \
    "$extension_dir/stylesheet.css"

rmdir "$dashboard_lib_dir" "$extension_dir" 2>/dev/null || true
systemctl --user daemon-reload

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null
fi

echo "Codex Dashboard removed. Codex sessions and account data were not touched."

