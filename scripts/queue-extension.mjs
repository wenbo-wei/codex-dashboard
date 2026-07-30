import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import System from 'system';


function fail(message) {
    printerr(`queue-extension: ${message}`);
    System.exit(2);
}


function extensionSettings() {
    return new Gio.Settings({schema_id: 'org.gnome.shell'});
}


function writeSettings(settings, enabled, disabled) {
    settings.delay();
    if (!settings.set_strv('enabled-extensions', enabled) ||
        !settings.set_strv('disabled-extensions', disabled)) {
        settings.revert();
        fail('could not update GNOME Shell extension settings');
    }
    settings.apply();
    Gio.Settings.sync();
}


function writeSnapshot(settings, path) {
    try {
        const written = GLib.file_set_contents(
            path,
            JSON.stringify({
                enabled: settings.get_strv('enabled-extensions'),
                disabled: settings.get_strv('disabled-extensions'),
            })
        );
        if (!written)
            fail('could not write the settings snapshot');
    } catch (error) {
        fail(`could not write the settings snapshot: ${error.message}`);
    }
}


function restoreSnapshot(path) {
    let contents;
    try {
        const [ok, bytes] = GLib.file_get_contents(path);
        if (!ok)
            fail('could not read the settings snapshot');
        contents = new TextDecoder().decode(bytes);
    } catch (error) {
        fail(`could not read the settings snapshot: ${error.message}`);
    }

    let snapshot;
    try {
        snapshot = JSON.parse(contents);
    } catch (error) {
        fail(`settings snapshot is invalid: ${error.message}`);
    }
    if (!Array.isArray(snapshot?.enabled) ||
        !snapshot.enabled.every(value => typeof value === 'string') ||
        !Array.isArray(snapshot?.disabled) ||
        !snapshot.disabled.every(value => typeof value === 'string'))
        fail('settings snapshot has invalid extension lists');

    writeSettings(
        extensionSettings(),
        snapshot.enabled,
        snapshot.disabled
    );
}


if (ARGV[0] === '--restore') {
    if (ARGV.length !== 2)
        fail('expected --restore SNAPSHOT_PATH');
    restoreSnapshot(ARGV[1]);
    System.exit(0);
}

if (ARGV[0] === '--snapshot') {
    if (ARGV.length !== 2)
        fail('expected --snapshot SNAPSHOT_PATH');
    writeSnapshot(extensionSettings(), ARGV[1]);
    System.exit(0);
}

if (ARGV[0] === '--disable') {
    if (ARGV.length < 2 ||
        !ARGV.slice(1).every(uuid => typeof uuid === 'string' && uuid))
        fail('expected --disable UUID [UUID ...]');
    const disabledUuids = new Set(ARGV.slice(1));
    const settings = extensionSettings();
    writeSettings(
        settings,
        settings.get_strv('enabled-extensions')
            .filter(uuid => !disabledUuids.has(uuid)),
        [
            ...new Set([
                ...settings.get_strv('disabled-extensions'),
                ...disabledUuids,
            ]),
        ]
    );
    System.exit(0);
}

if (ARGV.length !== 2)
    fail('expected NEW_UUID LEGACY_UUID');

const [extensionUuid, legacyExtensionUuid] = ARGV;
if (!extensionUuid || !legacyExtensionUuid ||
    extensionUuid === legacyExtensionUuid)
    fail('extension UUIDs must be non-empty and distinct');

const settings = extensionSettings();
const originalEnabled = settings.get_strv('enabled-extensions');
const originalDisabled = settings.get_strv('disabled-extensions');
const enabled = [
    ...new Set(
        originalEnabled
            .filter(uuid =>
                uuid !== extensionUuid && uuid !== legacyExtensionUuid)
    ),
    extensionUuid,
];
const disabled = [
    ...new Set(
        originalDisabled
            .filter(uuid =>
                uuid !== extensionUuid && uuid !== legacyExtensionUuid)
    ),
    legacyExtensionUuid,
];

writeSettings(settings, enabled, disabled);
