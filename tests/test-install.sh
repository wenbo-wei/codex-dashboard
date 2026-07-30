#!/bin/sh
set -eu

project_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
test_root=$(mktemp -d)

cleanup() {
    rm -rf -- "$test_root"
}
trap cleanup 0 HUP INT TERM

setup_case() {
    case_name=$1
    case_root="$test_root/$case_name"
    fake_bin="$case_root/fake-bin"
    schema_dir="$case_root/schemas"
    systemctl_state_dir="$case_root/systemctl-state"

    install -d \
        "$case_root/home" \
        "$case_root/config" \
        "$case_root/data" \
        "$fake_bin" \
        "$schema_dir" \
        "$systemctl_state_dir"
    install -m 0755 "$project_root/tests/fakes/"* "$fake_bin/"
    install -m 0644 \
        "$project_root/tests/schemas/org.gnome.shell.gschema.xml" \
        "$schema_dir/"
    glib-compile-schemas "$schema_dir"

    export HOME="$case_root/home"
    export XDG_CONFIG_HOME="$case_root/config"
    export XDG_DATA_HOME="$case_root/data"
    export GSETTINGS_BACKEND=keyfile
    export GSETTINGS_SCHEMA_DIR="$schema_dir"
    export PATH="$fake_bin:/usr/bin:/bin"
    export FAKE_SYSTEMCTL_STATE_DIR="$systemctl_state_dir"
    unset FAKE_SYSTEMCTL_FAIL_RESTART
    unset FAKE_SYSTEMCTL_FAIL_IS_ENABLED
    unset FAKE_SYSTEMCTL_FAIL_IS_ACTIVE
    unset FAKE_SYSTEMCTL_IS_ENABLED_EXIT
    unset FAKE_SYSTEMCTL_IS_ACTIVE_EXIT
    unset FAKE_GNOME_SHELL_VERSION

    dashboard_data_target="$HOME/.local/bin/codex-dashboard-data"
    quota_publisher_target="$HOME/.local/bin/codex-quota"
    app_server_target="$HOME/.local/lib/codex-dashboard/"\
"codex_app_server.py"
    quota_snapshot_target="$HOME/.local/lib/codex-dashboard/"\
"quota_snapshot.py"
    quota_sni_target="$HOME/.local/lib/codex-dashboard/quota_sni.py"
    extension_dir="$XDG_DATA_HOME/gnome-shell/extensions/"\
"codex-dashboard@wenbo-wei"
    extension_js_target="$extension_dir/extension.js"
    dashboard_model_target="$extension_dir/dashboardModel.mjs"
    metadata_target="$extension_dir/metadata.json"
    stylesheet_target="$extension_dir/stylesheet.css"
    icon_target="$XDG_DATA_HOME/icons/hicolor/scalable/apps/"\
"codex-dashboard-symbolic.svg"
    icon_cache_target="$XDG_DATA_HOME/icons/hicolor/icon-theme.cache"
    unit_target="$XDG_CONFIG_HOME/systemd/user/codex-quota.service"
    export FAKE_SYSTEMCTL_UNIT_PATH="$unit_target"

    printf '%s\n' not-found >"$systemctl_state_dir/enabled-state"
    printf '%s\n' inactive >"$systemctl_state_dir/active-state"
    : >"$systemctl_state_dir/calls.log"
}

assert_owned_targets_absent() {
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
        "$unit_target"
    do
        if [ -e "$owned_target" ] || [ -L "$owned_target" ]; then
            echo "unexpected installed file after rollback: "\
"$owned_target" >&2
            exit 1
        fi
    done
}

seed_owned_target() {
    seed_target=$1
    expected_target=$2
    seed_contents=$3
    seed_mode=$4

    install -d "$(dirname -- "$seed_target")" \
        "$(dirname -- "$expected_target")"
    printf '%s\n' "$seed_contents" >"$seed_target"
    chmod "$seed_mode" "$seed_target"
    cp -a -- "$seed_target" "$expected_target"
}

assert_target_restored() {
    restored_target=$1
    expected_target=$2

    if ! cmp -s -- "$restored_target" "$expected_target"; then
        echo "installed file contents were not restored: "\
"$restored_target" >&2
        exit 1
    fi
    restored_mode=$(stat -c '%a' -- "$restored_target")
    expected_mode=$(stat -c '%a' -- "$expected_target")
    if [ "$restored_mode" != "$expected_mode" ]; then
        echo "installed file mode was not restored: $restored_target "\
"($restored_mode != $expected_mode)" >&2
        exit 1
    fi
}

set_fake_systemctl_state() {
    printf '%s\n' "$1" >"$FAKE_SYSTEMCTL_STATE_DIR/enabled-state"
    printf '%s\n' "$2" >"$FAKE_SYSTEMCTL_STATE_DIR/active-state"
}

assert_fake_systemctl_state() {
    expected_enabled_state=$1
    expected_active_state=$2
    actual_enabled_state=$(cat \
        "$FAKE_SYSTEMCTL_STATE_DIR/enabled-state")
    actual_active_state=$(cat \
        "$FAKE_SYSTEMCTL_STATE_DIR/active-state")

    if [ "$actual_enabled_state" != "$expected_enabled_state" ] ||
        [ "$actual_active_state" != "$expected_active_state" ]; then
        echo "systemd state was not restored: "\
"$actual_enabled_state/$actual_active_state != "\
"$expected_enabled_state/$expected_active_state" >&2
        exit 1
    fi
}

assert_fake_systemctl_calls() {
    expected_calls=$1
    actual_calls=$(cat "$FAKE_SYSTEMCTL_STATE_DIR/calls.log")
    if [ "$actual_calls" != "$expected_calls" ]; then
        echo "unexpected systemctl call sequence" >&2
        printf '%s\n' "$actual_calls" >&2
        exit 1
    fi
}

expect_preflight_failure() {
    failure_description=$1
    if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
        echo "expected preflight failure: $failure_description" >&2
        exit 1
    else
        install_status=$?
    fi
    [ "$install_status" -eq 1 ]
    assert_owned_targets_absent
    [ ! -s "$FAKE_SYSTEMCTL_STATE_DIR/calls.log" ]
}

setup_case clean
gsettings set org.gnome.shell enabled-extensions "['keep@example']"
gsettings set org.gnome.shell disabled-extensions \
    "['codex-dashboard@wenbo-wei']"
"$project_root/scripts/install.sh" >/dev/null

[ "$(gsettings get org.gnome.shell enabled-extensions)" = \
    "['keep@example', 'codex-dashboard@wenbo-wei']" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = \
    "['codex-quota-centre@local']" ]
[ -f "$XDG_DATA_HOME/gnome-shell/extensions/"\
"codex-dashboard@wenbo-wei/extension.js" ]
[ -f "$XDG_DATA_HOME/icons/hicolor/scalable/apps/"\
"codex-dashboard-symbolic.svg" ]
[ -f "$icon_cache_target" ]
[ -f "$XDG_CONFIG_HOME/systemd/user/codex-quota.service" ]
[ ! -e "$HOME/.local/share/gnome-shell/extensions/"\
"codex-dashboard@wenbo-wei" ]
"$project_root/scripts/uninstall.sh" >/dev/null
[ "$(gsettings get org.gnome.shell enabled-extensions)" = \
    "['keep@example']" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = \
    "['codex-quota-centre@local', 'codex-dashboard@wenbo-wei']" ]
[ ! -e "$XDG_DATA_HOME/gnome-shell/extensions/"\
"codex-dashboard@wenbo-wei" ]
[ ! -e "$XDG_CONFIG_HOME/systemd/user/codex-quota.service" ]

setup_case legacy
gsettings set org.gnome.shell enabled-extensions "['keep@example']"
gsettings set org.gnome.shell disabled-extensions "['disabled@example']"
install -d "$XDG_DATA_HOME/gnome-shell/extensions/"\
"codex-quota-centre@local"
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected staged legacy migration" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 2 ]
[ "$(gsettings get org.gnome.shell enabled-extensions)" = \
    "['keep@example']" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = \
    "['disabled@example']" ]

setup_case rollback-existing
set_fake_systemctl_state enabled active
gsettings set org.gnome.shell enabled-extensions \
    "['keep@example', 'codex-quota-centre@local']"
gsettings set org.gnome.shell disabled-extensions \
    "['codex-dashboard@wenbo-wei', 'disabled@example']"
expected_root="$case_root/expected"
seed_owned_target \
    "$dashboard_data_target" \
    "$expected_root/local-bin/codex-dashboard-data" \
    old-dashboard-data 400
seed_owned_target \
    "$quota_publisher_target" \
    "$expected_root/local-bin/codex-quota" \
    old-quota-publisher 440
seed_owned_target \
    "$app_server_target" \
    "$expected_root/lib/codex_app_server.py" \
    old-app-server 444
seed_owned_target \
    "$quota_snapshot_target" \
    "$expected_root/lib/quota_snapshot.py" \
    old-quota-snapshot 500
seed_owned_target \
    "$quota_sni_target" \
    "$expected_root/lib/quota_sni.py" \
    old-quota-sni 540
seed_owned_target \
    "$extension_js_target" \
    "$expected_root/extension/extension.js" \
    old-extension-js 544
seed_owned_target \
    "$dashboard_model_target" \
    "$expected_root/extension/dashboardModel.mjs" \
    old-dashboard-model 600
seed_owned_target \
    "$metadata_target" \
    "$expected_root/extension/metadata.json" \
    old-metadata 640
seed_owned_target \
    "$stylesheet_target" \
    "$expected_root/extension/stylesheet.css" \
    old-stylesheet 644
seed_owned_target \
    "$icon_target" \
    "$expected_root/icon/codex-dashboard-symbolic.svg" \
    old-icon 700
seed_owned_target \
    "$icon_cache_target" \
    "$expected_root/icon/icon-theme.cache" \
    old-icon-cache 660
seed_owned_target \
    "$unit_target" \
    "$expected_root/systemd/codex-quota.service" \
    '[Unit]
Description=Old quota service

[Service]
ExecStart=/bin/true

[Install]
WantedBy=graphical-session.target' 740
unknown_target="$extension_dir/user-owned-file.txt"
seed_owned_target \
    "$unknown_target" \
    "$expected_root/extension/user-owned-file.txt" \
    user-owned-extension-data 600

export FAKE_SYSTEMCTL_FAIL_RESTART=1
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected service restart failure over existing files" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
[ "$(gsettings get org.gnome.shell enabled-extensions)" = \
    "['keep@example', 'codex-quota-centre@local']" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = \
    "['codex-dashboard@wenbo-wei', 'disabled@example']" ]
assert_target_restored \
    "$dashboard_data_target" \
    "$expected_root/local-bin/codex-dashboard-data"
assert_target_restored \
    "$quota_publisher_target" \
    "$expected_root/local-bin/codex-quota"
assert_target_restored \
    "$app_server_target" \
    "$expected_root/lib/codex_app_server.py"
assert_target_restored \
    "$quota_snapshot_target" \
    "$expected_root/lib/quota_snapshot.py"
assert_target_restored \
    "$quota_sni_target" \
    "$expected_root/lib/quota_sni.py"
assert_target_restored \
    "$extension_js_target" \
    "$expected_root/extension/extension.js"
assert_target_restored \
    "$dashboard_model_target" \
    "$expected_root/extension/dashboardModel.mjs"
assert_target_restored \
    "$metadata_target" \
    "$expected_root/extension/metadata.json"
assert_target_restored \
    "$stylesheet_target" \
    "$expected_root/extension/stylesheet.css"
assert_target_restored \
    "$icon_target" \
    "$expected_root/icon/codex-dashboard-symbolic.svg"
assert_target_restored \
    "$icon_cache_target" \
    "$expected_root/icon/icon-theme.cache"
assert_target_restored \
    "$unit_target" \
    "$expected_root/systemd/codex-quota.service"
assert_target_restored \
    "$unknown_target" \
    "$expected_root/extension/user-owned-file.txt"
assert_fake_systemctl_state enabled active
assert_target_restored \
    "$FAKE_SYSTEMCTL_STATE_DIR/loaded-unit" \
    "$expected_root/systemd/codex-quota.service"
assert_fake_systemctl_calls \
    'is-enabled codex-quota.service
is-active codex-quota.service
daemon-reload
enable codex-quota.service
restart codex-quota.service
stop codex-quota.service
disable codex-quota.service
daemon-reload
enable codex-quota.service
stop codex-quota.service
start codex-quota.service
is-enabled codex-quota.service
is-active codex-quota.service'

setup_case rollback
gsettings set org.gnome.shell enabled-extensions "['keep@example']"
gsettings set org.gnome.shell disabled-extensions "['disabled@example']"
export FAKE_SYSTEMCTL_FAIL_RESTART=1
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected service restart failure" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
[ "$(gsettings get org.gnome.shell enabled-extensions)" = \
    "['keep@example']" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = \
    "['disabled@example']" ]
assert_owned_targets_absent
[ ! -e "$icon_cache_target" ]
[ ! -L "$icon_cache_target" ]
assert_fake_systemctl_state not-found inactive
[ ! -e "$FAKE_SYSTEMCTL_STATE_DIR/loaded-unit" ]
assert_fake_systemctl_calls \
    'is-enabled codex-quota.service
is-active codex-quota.service
daemon-reload
enable codex-quota.service
restart codex-quota.service
stop codex-quota.service
disable codex-quota.service
daemon-reload
is-enabled codex-quota.service
is-active codex-quota.service'

setup_case rollback-disabled
set_fake_systemctl_state disabled failed
expected_root="$case_root/expected"
seed_owned_target \
    "$unit_target" \
    "$expected_root/systemd/codex-quota.service" \
    '[Unit]
Description=Disabled old quota service

[Service]
ExecStart=/bin/true

[Install]
WantedBy=graphical-session.target' 600
export FAKE_SYSTEMCTL_FAIL_RESTART=1
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected failure over a disabled service" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
assert_target_restored \
    "$unit_target" \
    "$expected_root/systemd/codex-quota.service"
assert_fake_systemctl_state disabled inactive

setup_case rollback-static
set_fake_systemctl_state static inactive
expected_root="$case_root/expected"
seed_owned_target \
    "$unit_target" \
    "$expected_root/systemd/codex-quota.service" \
    '[Unit]
Description=Static old quota service

[Service]
ExecStart=/bin/true' 640
export FAKE_SYSTEMCTL_FAIL_RESTART=1
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected failure over a static service" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
assert_target_restored \
    "$unit_target" \
    "$expected_root/systemd/codex-quota.service"
assert_fake_systemctl_state static inactive

setup_case systemd-unknown
set_fake_systemctl_state masked inactive
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected unknown systemd state to fail preflight" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
assert_owned_targets_absent
assert_fake_systemctl_calls \
    'is-enabled codex-quota.service'

setup_case systemd-query-failure
set_fake_systemctl_state disabled inactive
expected_root="$case_root/expected"
seed_owned_target \
    "$dashboard_data_target" \
    "$expected_root/local-bin/codex-dashboard-data" \
    preflight-owned-data 640
hardlink_target="$case_root/dashboard-data-hardlink"
ln "$dashboard_data_target" "$hardlink_target"
original_inode=$(stat -c '%i' -- "$dashboard_data_target")
original_link_count=$(stat -c '%h' -- "$dashboard_data_target")
export FAKE_SYSTEMCTL_FAIL_IS_ACTIVE=1
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected systemd query failure to fail preflight" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
assert_target_restored \
    "$dashboard_data_target" \
    "$expected_root/local-bin/codex-dashboard-data"
[ "$(stat -c '%i' -- "$dashboard_data_target")" = "$original_inode" ]
[ "$(stat -c '%i' -- "$hardlink_target")" = "$original_inode" ]
[ "$(stat -c '%h' -- "$dashboard_data_target")" = \
    "$original_link_count" ]
assert_fake_systemctl_calls \
    'is-enabled codex-quota.service
is-active codex-quota.service'

setup_case systemd-enabled-status-mismatch
set_fake_systemctl_state disabled inactive
export FAKE_SYSTEMCTL_IS_ENABLED_EXIT=5
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected inconsistent is-enabled result to fail preflight" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
assert_owned_targets_absent
assert_fake_systemctl_calls \
    'is-enabled codex-quota.service'

setup_case systemd-active-status-mismatch
set_fake_systemctl_state disabled inactive
export FAKE_SYSTEMCTL_IS_ACTIVE_EXIT=5
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected inconsistent is-active result to fail preflight" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
assert_owned_targets_absent
assert_fake_systemctl_calls \
    'is-enabled codex-quota.service
is-active codex-quota.service'

setup_case rollback-cache-symlink
cache_payload="$case_root/original-cache-payload"
expected_cache_payload="$case_root/expected-cache-payload"
printf '%s\n' original-symlink-cache >"$cache_payload"
chmod 640 "$cache_payload"
cp -a -- "$cache_payload" "$expected_cache_payload"
install -d "$(dirname -- "$icon_cache_target")"
ln -s "$cache_payload" "$icon_cache_target"
original_cache_link=$(readlink "$icon_cache_target")
export FAKE_SYSTEMCTL_FAIL_RESTART=1
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected failure with a symlinked icon cache" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
[ -L "$icon_cache_target" ]
[ "$(readlink "$icon_cache_target")" = "$original_cache_link" ]
assert_target_restored "$cache_payload" "$expected_cache_payload"
assert_owned_targets_absent
assert_fake_systemctl_state not-found inactive

setup_case relative-home
HOME=relative-home
export HOME
expect_preflight_failure "relative HOME"

setup_case relative-data-home
XDG_DATA_HOME=relative-data
export XDG_DATA_HOME
expect_preflight_failure "relative XDG_DATA_HOME"

setup_case relative-config-home
XDG_CONFIG_HOME=relative-config
export XDG_CONFIG_HOME
expect_preflight_failure "relative XDG_CONFIG_HOME"

setup_case unsupported-shell
export FAKE_GNOME_SHELL_VERSION=51.0
expect_preflight_failure "unsupported GNOME Shell version"

setup_case install-extension-symlink
outside_extension="$case_root/outside-extension"
protected_extension_file="$outside_extension/extension.js"
install -d "$outside_extension" "$(dirname -- "$extension_dir")"
printf '%s\n' do-not-touch >"$protected_extension_file"
ln -s "$outside_extension" "$extension_dir"
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected installer to reject a symlinked extension directory" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
[ -L "$extension_dir" ]
[ "$(cat "$protected_extension_file")" = do-not-touch ]
[ ! -s "$FAKE_SYSTEMCTL_STATE_DIR/calls.log" ]

setup_case install-owned-file-directory-symlink
outside_directory="$case_root/outside-owned-target"
install -d "$outside_directory" "$extension_dir"
ln -s "$outside_directory" "$extension_js_target"
if "$project_root/scripts/install.sh" >/dev/null 2>&1; then
    echo "expected installer to reject a file target linked to a directory" >&2
    exit 1
else
    install_status=$?
fi
[ "$install_status" -eq 1 ]
[ -L "$extension_js_target" ]
[ ! -e "$outside_directory/extension.js" ]
[ ! -s "$FAKE_SYSTEMCTL_STATE_DIR/calls.log" ]

setup_case uninstall-extension-symlink
outside_extension="$case_root/outside-extension"
protected_extension_file="$outside_extension/extension.js"
install -d "$outside_extension" "$(dirname -- "$extension_dir")"
printf '%s\n' do-not-touch >"$protected_extension_file"
ln -s "$outside_extension" "$extension_dir"
gsettings set org.gnome.shell enabled-extensions \
    "['keep@example', 'codex-dashboard@wenbo-wei']"
gsettings set org.gnome.shell disabled-extensions \
    "['codex-quota-centre@local']"
if "$project_root/scripts/uninstall.sh" >/dev/null 2>&1; then
    echo "expected uninstaller to reject a symlinked extension directory" >&2
    exit 1
else
    uninstall_status=$?
fi
[ "$uninstall_status" -eq 1 ]
[ -L "$extension_dir" ]
[ "$(cat "$protected_extension_file")" = do-not-touch ]
[ "$(gsettings get org.gnome.shell enabled-extensions)" = \
    "['keep@example', 'codex-dashboard@wenbo-wei']" ]
[ "$(gsettings get org.gnome.shell disabled-extensions)" = \
    "['codex-quota-centre@local']" ]
[ ! -s "$FAKE_SYSTEMCTL_STATE_DIR/calls.log" ]
