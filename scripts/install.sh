#!/bin/sh
set -eu

project_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
extension_uuid='codex-dashboard@wenbo-wei'
legacy_extension_uuid='codex-quota-centre@local'
systemd_unit_name='codex-quota.service'

require_absolute_path() {
    case "$2" in
        /*)
            ;;
        *)
            echo "error: $1 must be an absolute path" >&2
            exit 1
            ;;
    esac
}

home_dir=${HOME:-}
require_absolute_path HOME "$home_dir"
xdg_data_home=${XDG_DATA_HOME:-"$home_dir/.local/share"}
require_absolute_path XDG_DATA_HOME "$xdg_data_home"
xdg_config_home=${XDG_CONFIG_HOME:-"$home_dir/.config"}
require_absolute_path XDG_CONFIG_HOME "$xdg_config_home"
local_bin_dir="$home_dir/.local/bin"
dashboard_lib_dir="$home_dir/.local/lib/codex-dashboard"
extension_dir="$xdg_data_home/gnome-shell/extensions/$extension_uuid"
legacy_extension_dir="$xdg_data_home/gnome-shell/extensions/$legacy_extension_uuid"
icon_theme_dir="$xdg_data_home/icons/hicolor"
icon_dir="$icon_theme_dir/scalable/apps"
unit_dir="$xdg_config_home/systemd/user"
dashboard_data_target="$local_bin_dir/codex-dashboard-data"
quota_publisher_target="$local_bin_dir/codex-quota"
app_server_target="$dashboard_lib_dir/codex_app_server.py"
quota_snapshot_target="$dashboard_lib_dir/quota_snapshot.py"
quota_sni_target="$dashboard_lib_dir/quota_sni.py"
extension_js_target="$extension_dir/extension.js"
dashboard_model_target="$extension_dir/dashboardModel.mjs"
metadata_target="$extension_dir/metadata.json"
stylesheet_target="$extension_dir/stylesheet.css"
icon_target="$icon_dir/codex-dashboard-symbolic.svg"
unit_target="$unit_dir/$systemd_unit_name"
icon_cache_target="$icon_theme_dir/icon-theme.cache"
legacy_was_present=false
legacy_was_enabled=false
extension_queued=false
install_succeeded=false
owned_backup_complete=false
owned_install_attempted=false
settings_snapshot_taken=false
systemd_snapshot_taken=false
systemd_reload_attempted=false
systemd_enable_attempted=false
systemd_restart_attempted=false
icon_cache_backup_complete=false
icon_cache_update_attempted=false
systemd_enabled_state=
systemd_active_state=
gjs_bin=

require_owned_directory() {
    if [ -L "$2" ]; then
        echo "error: $1 must not be a symbolic link: $2" >&2
        exit 1
    fi
    if [ -e "$2" ] && [ ! -d "$2" ]; then
        echo "error: $1 is not a directory: $2" >&2
        exit 1
    fi
}

require_file_target() {
    if [ -d "$2" ]; then
        echo "error: $1 is a directory: $2" >&2
        exit 1
    fi
}

require_owned_directory "dashboard library directory" "$dashboard_lib_dir"
require_owned_directory "extension directory" "$extension_dir"
require_owned_directory "legacy extension directory" "$legacy_extension_dir"
for owned_target in \
    "$dashboard_data_target" \
    "$quota_publisher_target" \
    "$app_server_target" \
    "$quota_snapshot_target" \
    "$quota_sni_target" \
    "$extension_js_target" \
    "$dashboard_model_target" \
    "$metadata_target" \
    "$stylesheet_target" \
    "$icon_target" \
    "$unit_target" \
    "$icon_cache_target"
do
    require_file_target "owned file target" "$owned_target"
done

command -v codex >/dev/null 2>&1 || {
    echo "error: codex is not available on PATH" >&2
    exit 1
}
command -v gnome-extensions >/dev/null 2>&1 || {
    echo "error: gnome-extensions is not installed" >&2
    exit 1
}
command -v systemctl >/dev/null 2>&1 || {
    echo "error: systemctl is not installed" >&2
    exit 1
}
gjs_bin=$(command -v gjs) || {
    echo "error: gjs is not installed" >&2
    exit 1
}
command -v gnome-shell >/dev/null 2>&1 || {
    echo "error: gnome-shell is not installed" >&2
    exit 1
}
if ! gnome_shell_version_output=$(
    LC_ALL=C gnome-shell --version 2>/dev/null
); then
    echo "error: could not determine the GNOME Shell version" >&2
    exit 1
fi
case "$gnome_shell_version_output" in
    'GNOME Shell '*)
        gnome_shell_version=${gnome_shell_version_output#GNOME Shell }
        gnome_shell_major=${gnome_shell_version%%.*}
        ;;
    *)
        gnome_shell_major=
        ;;
esac
if [ "$gnome_shell_major" != 50 ]; then
    echo "error: GNOME Shell 50 is required" >&2
    exit 1
fi
[ -x /usr/bin/python3 ] || {
    echo "error: /usr/bin/python3 is not installed" >&2
    exit 1
}
/usr/bin/python3 -c \
    'import sys; raise SystemExit(sys.version_info < (3, 11))' || {
    echo "error: /usr/bin/python3 3.11 or newer is required" >&2
    exit 1
}
/usr/bin/python3 -c \
    'import dbus; from gi.repository import Gio, GLib' >/dev/null

backup_owned_target() {
    backup_target=$2
    if [ -e "$1" ] || [ -L "$1" ]; then
        install -d "$(dirname -- "$backup_target")"
        cp -a -- "$1" "$backup_target"
    fi
}

backup_owned_targets() {
    backup_owned_target \
        "$dashboard_data_target" \
        "$owned_backup_dir/local-bin/codex-dashboard-data"
    backup_owned_target \
        "$quota_publisher_target" \
        "$owned_backup_dir/local-bin/codex-quota"
    backup_owned_target \
        "$app_server_target" \
        "$owned_backup_dir/lib/codex_app_server.py"
    backup_owned_target \
        "$quota_snapshot_target" \
        "$owned_backup_dir/lib/quota_snapshot.py"
    backup_owned_target \
        "$quota_sni_target" \
        "$owned_backup_dir/lib/quota_sni.py"
    backup_owned_target \
        "$extension_js_target" \
        "$owned_backup_dir/extension/extension.js"
    backup_owned_target \
        "$dashboard_model_target" \
        "$owned_backup_dir/extension/dashboardModel.mjs"
    backup_owned_target \
        "$metadata_target" \
        "$owned_backup_dir/extension/metadata.json"
    backup_owned_target \
        "$stylesheet_target" \
        "$owned_backup_dir/extension/stylesheet.css"
    backup_owned_target \
        "$icon_target" \
        "$owned_backup_dir/icon/codex-dashboard-symbolic.svg"
    backup_owned_target \
        "$unit_target" \
        "$owned_backup_dir/systemd/codex-quota.service"
}

restore_owned_target() {
    restore_target=$1
    backup_target=$2
    rm -f -- "$restore_target" || return 1
    if [ -e "$backup_target" ] || [ -L "$backup_target" ]; then
        install -d "$(dirname -- "$restore_target")" || return 1
        cp -a -- "$backup_target" "$restore_target" || return 1
    fi
}

restore_owned_targets() {
    restore_status=0
    restore_owned_target \
        "$dashboard_data_target" \
        "$owned_backup_dir/local-bin/codex-dashboard-data" ||
        restore_status=1
    restore_owned_target \
        "$quota_publisher_target" \
        "$owned_backup_dir/local-bin/codex-quota" ||
        restore_status=1
    restore_owned_target \
        "$app_server_target" \
        "$owned_backup_dir/lib/codex_app_server.py" ||
        restore_status=1
    restore_owned_target \
        "$quota_snapshot_target" \
        "$owned_backup_dir/lib/quota_snapshot.py" ||
        restore_status=1
    restore_owned_target \
        "$quota_sni_target" \
        "$owned_backup_dir/lib/quota_sni.py" ||
        restore_status=1
    restore_owned_target \
        "$extension_js_target" \
        "$owned_backup_dir/extension/extension.js" ||
        restore_status=1
    restore_owned_target \
        "$dashboard_model_target" \
        "$owned_backup_dir/extension/dashboardModel.mjs" ||
        restore_status=1
    restore_owned_target \
        "$metadata_target" \
        "$owned_backup_dir/extension/metadata.json" ||
        restore_status=1
    restore_owned_target \
        "$stylesheet_target" \
        "$owned_backup_dir/extension/stylesheet.css" ||
        restore_status=1
    restore_owned_target \
        "$icon_target" \
        "$owned_backup_dir/icon/codex-dashboard-symbolic.svg" ||
        restore_status=1
    restore_owned_target \
        "$unit_target" \
        "$owned_backup_dir/systemd/codex-quota.service" ||
        restore_status=1
    return "$restore_status"
}

backup_icon_cache() {
    if [ -e "$icon_cache_target" ] || [ -L "$icon_cache_target" ]; then
        cp -a -- "$icon_cache_target" "$icon_cache_backup"
    fi
    icon_cache_backup_complete=true
}

restore_icon_cache() {
    rm -f -- "$icon_cache_target" || return 1
    if [ -e "$icon_cache_backup" ] || [ -L "$icon_cache_backup" ]; then
        install -d "$(dirname -- "$icon_cache_target")" || return 1
        cp -a -- "$icon_cache_backup" "$icon_cache_target" || return 1
    fi
}

read_systemd_enabled_state() {
    queried_state=
    query_status=0
    if queried_state=$(LC_ALL=C systemctl --user is-enabled \
        "$systemd_unit_name" 2>/dev/null); then
        :
    else
        query_status=$?
    fi
    case "$queried_state" in
        enabled | static)
            [ "$query_status" -eq 0 ] || return 1
            printf '%s\n' "$queried_state"
            ;;
        disabled)
            [ "$query_status" -eq 1 ] || return 1
            printf '%s\n' "$queried_state"
            ;;
        not-found)
            [ "$query_status" -eq 4 ] || return 1
            printf '%s\n' "$queried_state"
            ;;
        *)
            return 1
            ;;
    esac
}

read_systemd_active_state() {
    queried_state=
    query_status=0
    if queried_state=$(LC_ALL=C systemctl --user is-active \
        "$systemd_unit_name" 2>/dev/null); then
        :
    else
        query_status=$?
    fi
    case "$queried_state" in
        active)
            [ "$query_status" -eq 0 ] || return 1
            printf '%s\n' "$queried_state"
            ;;
        inactive)
            [ "$query_status" -eq 3 ] || return 1
            printf '%s\n' "$queried_state"
            ;;
        failed)
            [ "$query_status" -eq 3 ] || return 1
            printf '%s\n' failed
            ;;
        *)
            return 1
            ;;
    esac
}

snapshot_systemd_state() {
    if ! systemd_enabled_state=$(read_systemd_enabled_state); then
        abort_migration \
            "could not determine whether $systemd_unit_name is enabled"
    fi
    if ! queried_active_state=$(read_systemd_active_state); then
        abort_migration \
            "could not determine whether $systemd_unit_name is active"
    fi
    case "$queried_active_state" in
        failed)
            systemd_active_state=inactive
            ;;
        *)
            systemd_active_state=$queried_active_state
            ;;
    esac
    if [ "$systemd_enabled_state" = not-found ] &&
        [ "$systemd_active_state" = active ]; then
        abort_migration \
            "$systemd_unit_name cannot be active when its unit is not found"
    fi
    systemd_snapshot_taken=true
}

prepare_systemd_rollback() {
    prepare_status=0
    if [ "$systemd_restart_attempted" = true ]; then
        if ! systemctl --user stop "$systemd_unit_name" \
            >/dev/null 2>&1; then
            prepare_status=1
        fi
    fi
    if [ "$systemd_enable_attempted" = true ]; then
        if ! systemctl --user disable "$systemd_unit_name" \
            >/dev/null 2>&1; then
            prepare_status=1
        fi
    fi
    return "$prepare_status"
}

restore_systemd_state() {
    restore_status=0
    reload_restored=true
    if [ "$systemd_reload_attempted" = true ] &&
        ! systemctl --user daemon-reload; then
        restore_status=1
        reload_restored=false
    fi

    if [ "$systemd_enable_attempted" = true ]; then
        case "$systemd_enabled_state" in
            enabled)
                if ! systemctl --user enable "$systemd_unit_name" \
                    >/dev/null 2>&1; then
                    restore_status=1
                fi
                ;;
            disabled)
                if ! systemctl --user disable "$systemd_unit_name" \
                    >/dev/null 2>&1; then
                    restore_status=1
                fi
                ;;
        esac
    fi
    if [ "$systemd_restart_attempted" = true ] &&
        [ "$systemd_enabled_state" != not-found ]; then
        if ! systemctl --user stop "$systemd_unit_name" \
            >/dev/null 2>&1; then
            restore_status=1
        fi
        if [ "$systemd_active_state" = active ] &&
            [ "$reload_restored" = true ] &&
            ! systemctl --user start "$systemd_unit_name" \
                >/dev/null 2>&1; then
            restore_status=1
        fi
    fi

    if ! restored_enabled_state=$(read_systemd_enabled_state); then
        restore_status=1
    elif [ "$restored_enabled_state" != "$systemd_enabled_state" ]; then
        restore_status=1
    fi
    if ! restored_active_state=$(read_systemd_active_state); then
        restore_status=1
    elif [ "$restored_active_state" != "$systemd_active_state" ]; then
        restore_status=1
    fi
    return "$restore_status"
}

cleanup_transaction() {
    exit_status=$?
    trap - 0
    if [ "$install_succeeded" != true ] &&
        [ "$settings_snapshot_taken" = true ]; then
        if ! "$gjs_bin" -m \
            "$project_root/scripts/queue-extension.mjs" \
            --restore \
            "$transaction_dir/extension-settings.json"; then
            echo "warning: could not restore GNOME extension settings" >&2
        fi
    fi
    if [ "$install_succeeded" != true ] &&
        [ "$systemd_snapshot_taken" = true ] &&
        { [ "$systemd_enable_attempted" = true ] ||
          [ "$systemd_restart_attempted" = true ]; }; then
        if ! prepare_systemd_rollback; then
            echo "warning: could not fully stop or disable "\
"$systemd_unit_name during rollback" >&2
        fi
    fi
    if [ "$install_succeeded" != true ] &&
        [ "$owned_backup_complete" = true ] &&
        [ "$owned_install_attempted" = true ]; then
        if ! restore_owned_targets; then
            echo "warning: could not fully restore installed files" >&2
        fi
    fi
    if [ "$install_succeeded" != true ] &&
        [ "$icon_cache_backup_complete" = true ] &&
        [ "$icon_cache_update_attempted" = true ]; then
        if ! restore_icon_cache; then
            echo "warning: could not restore $icon_cache_target" >&2
        fi
    fi
    if [ "$install_succeeded" != true ] &&
        [ "$systemd_snapshot_taken" = true ] &&
        [ "$systemd_reload_attempted" = true ]; then
        if ! restore_systemd_state; then
            echo "warning: could not fully restore $systemd_unit_name state" \
                >&2
        fi
    fi
    rm -rf -- "$transaction_dir"
    exit "$exit_status"
}

abort_migration() {
    echo "error: $1" >&2
    exit 1
}

stage_migration() {
    install_succeeded=true
    echo "Codex Dashboard files staged as $extension_uuid."
    echo "The current GNOME Shell has not discovered the new UUID."
    echo "The legacy extension installation is preserved."
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

snapshot_systemd_state
transaction_dir=$(mktemp -d)
owned_backup_dir="$transaction_dir/owned"
icon_cache_backup="$transaction_dir/icon-theme.cache"
trap cleanup_transaction 0
backup_owned_targets
owned_backup_complete=true
backup_icon_cache

install -d \
    "$local_bin_dir" \
    "$dashboard_lib_dir" \
    "$extension_dir" \
    "$icon_dir" \
    "$unit_dir"

owned_install_attempted=true
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
    "$unit_target"

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    icon_cache_update_attempted=true
    gtk-update-icon-cache -f -t "$icon_theme_dir" >/dev/null
fi

if [ -d "$legacy_extension_dir" ] ||
    gnome-extensions info "$legacy_extension_uuid" >/dev/null 2>&1; then
    legacy_was_present=true
fi

if extension_is_listed --enabled "$legacy_extension_uuid"; then
    legacy_was_enabled=true
elif [ "$?" -eq 2 ]; then
    abort_migration "could not read the enabled extension list"
fi

if ! "$gjs_bin" -m \
    "$project_root/scripts/queue-extension.mjs" \
    --snapshot \
    "$transaction_dir/extension-settings.json"; then
    abort_migration "could not snapshot GNOME extension settings"
fi
settings_snapshot_taken=true

if ! gnome-extensions info "$extension_uuid" >/dev/null 2>&1; then
    if [ "$legacy_was_present" = true ]; then
        stage_migration
    fi
    if ! "$gjs_bin" -m \
        "$project_root/scripts/queue-extension.mjs" \
        "$extension_uuid" \
        "$legacy_extension_uuid"; then
        abort_migration "could not queue $extension_uuid for the next login"
    fi
    extension_queued=true
else
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
fi

systemd_reload_attempted=true
systemctl --user daemon-reload
systemd_enable_attempted=true
systemctl --user enable "$systemd_unit_name"
systemd_restart_attempted=true
systemctl --user restart "$systemd_unit_name"

install_succeeded=true
if ! rm -f \
    "$legacy_extension_dir/extension.js" \
    "$legacy_extension_dir/dashboardModel.mjs" \
    "$legacy_extension_dir/metadata.json" \
    "$legacy_extension_dir/stylesheet.css" \
    "$legacy_extension_dir/extension-placement-v6.js" \
    "$legacy_extension_dir/stylesheet-placement-v6.css"; then
    echo "warning: could not fully retire legacy extension files" >&2
fi
if ! rmdir "$legacy_extension_dir" 2>/dev/null &&
    [ -d "$legacy_extension_dir" ]; then
    echo "warning: preserved unrecognized files in $legacy_extension_dir" >&2
fi

if [ "$extension_queued" = true ]; then
    echo "Codex Dashboard installed and queued for the next login."
else
    echo "Codex Dashboard installed as $extension_uuid."
fi
echo "On an upgrade, sign out and back in when convenient to reload GNOME Shell code."
