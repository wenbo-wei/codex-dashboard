#!/bin/sh
set -eu

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
extension_uuid='codex-dashboard@wenbo-wei'
legacy_extension_uuid='codex-quota-centre@local'

fail() {
    echo "error: $*" >&2
    exit 1
}

require_absolute_path() {
    case "$2" in
        /*)
            ;;
        *)
            fail "$1 must be an absolute path"
            ;;
    esac
}

require_owned_directory() {
    if [ -L "$2" ]; then
        fail "$1 must not be a symbolic link: $2"
    fi
    if [ -e "$2" ] && [ ! -d "$2" ]; then
        fail "$1 is not a directory: $2"
    fi
}

home_dir=${HOME:-}
require_absolute_path HOME "$home_dir"
xdg_data_home=${XDG_DATA_HOME:-"$home_dir/.local/share"}
require_absolute_path XDG_DATA_HOME "$xdg_data_home"
xdg_config_home=${XDG_CONFIG_HOME:-"$home_dir/.config"}
require_absolute_path XDG_CONFIG_HOME "$xdg_config_home"
xdg_cache_home=${XDG_CACHE_HOME:-"$home_dir/.cache"}
require_absolute_path XDG_CACHE_HOME "$xdg_cache_home"
xdg_runtime_dir=${XDG_RUNTIME_DIR:-"/run/user/$(id -u)"}
require_absolute_path XDG_RUNTIME_DIR "$xdg_runtime_dir"
dashboard_lib_dir="$home_dir/.local/lib/codex-dashboard"
task_overview_cache_dir="$xdg_cache_home/codex-dashboard"
extension_dir="$xdg_data_home/gnome-shell/extensions/$extension_uuid"
legacy_extension_dir="$xdg_data_home/gnome-shell/extensions/$legacy_extension_uuid"
icon_theme_dir="$xdg_data_home/icons/hicolor"
settings_helper="$script_dir/queue-extension.mjs"

require_owned_directory "dashboard library directory" "$dashboard_lib_dir"
require_owned_directory \
    "task overview cache directory" \
    "$task_overview_cache_dir"
require_owned_directory "extension directory" "$extension_dir"
require_owned_directory "legacy extension directory" "$legacy_extension_dir"
[ -f "$settings_helper" ] ||
    fail "release source is incomplete: $settings_helper"
gjs_bin=$(command -v gjs) ||
    fail "gjs is required to retire queued extension UUIDs"
command -v systemctl >/dev/null 2>&1 ||
    fail "systemctl is required to remove the user service"

"$gjs_bin" -m \
    "$settings_helper" \
    --disable \
    "$extension_uuid" \
    "$legacy_extension_uuid"
systemctl --user disable --now codex-quota.service >/dev/null 2>&1 || true
systemctl --user stop codex-task-overviews.service >/dev/null 2>&1 || true

rm -f \
    "$home_dir/.local/bin/codex-dashboard-data" \
    "$home_dir/.local/bin/codex-dashboard-task-overviews" \
    "$home_dir/.local/bin/codex-quota" \
    "$xdg_config_home/systemd/user/codex-task-overviews.service" \
    "$xdg_config_home/systemd/user/codex-quota.service" \
    "$xdg_runtime_dir/codex-dashboard-today.json" \
    "$icon_theme_dir/scalable/apps/codex-dashboard-symbolic.svg"
rm -f \
    "$dashboard_lib_dir/codex_app_server.py" \
    "$dashboard_lib_dir/codex_thread_index.py" \
    "$dashboard_lib_dir/quota_snapshot.py" \
    "$dashboard_lib_dir/quota_sni.py" \
    "$dashboard_lib_dir/task_overviews.py"
rm -f \
    "$task_overview_cache_dir/task-overviews.json" \
    "$task_overview_cache_dir/task-overviews.lock"
rm -f \
    "$extension_dir/extension.js" \
    "$extension_dir/dashboardModel.mjs" \
    "$extension_dir/metadata.json" \
    "$extension_dir/stylesheet.css"
rm -f \
    "$legacy_extension_dir/extension.js" \
    "$legacy_extension_dir/dashboardModel.mjs" \
    "$legacy_extension_dir/metadata.json" \
    "$legacy_extension_dir/stylesheet.css" \
    "$legacy_extension_dir/extension-placement-v6.js" \
    "$legacy_extension_dir/stylesheet-placement-v6.css"

rmdir \
    "$dashboard_lib_dir" \
    "$task_overview_cache_dir" \
    "$extension_dir" \
    "$legacy_extension_dir" \
    2>/dev/null || true
for preserved_directory in \
    "$dashboard_lib_dir" \
    "$task_overview_cache_dir" \
    "$extension_dir" \
    "$legacy_extension_dir"
do
    if [ -d "$preserved_directory" ]; then
        echo "warning: preserved unrecognized files in "\
"$preserved_directory" >&2
    fi
done
systemctl --user daemon-reload

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$icon_theme_dir" >/dev/null
fi

echo "Codex Dashboard removed. Codex sessions and account data were not touched."
