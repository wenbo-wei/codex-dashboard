// Codex Dashboard GNOME Shell 50 implementation.
import Cairo from 'cairo';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {
    Availability,
    calendarHeatClass,
    calendarTokenValue,
    clamp,
    formatClockFromSeconds,
    formatRelativeTime,
    formatReset,
    formatTodayTokens,
    formatTokens,
    limitTitle,
    normalizeAvailability,
    planTitle,
    quotaAvailability,
    roundedPercent,
} from './dashboardModel.mjs';


const DATA_HELPER = GLib.build_filenamev([
    GLib.get_home_dir(),
    '.local',
    'bin',
    'codex-dashboard-data',
]);
const QUOTA_STATE_PATH = GLib.build_filenamev([
    GLib.get_user_runtime_dir(),
    'codex-quota.json',
]);
const CLOCK_BUTTON_STYLE = 'codex-dashboard-clock-button';
const CODEX_BUTTON_STYLE = 'codex-dashboard-centre-button';
const DATA_HELPER_TIMEOUT_MILLISECONDS = 12_000;


function taskOverviewTitle(value) {
    const title = String(value ?? '');
    if (
        /^[\x20-\x7e]{1,48}$/.test(title)
        && /[A-Za-z]/.test(title)
        && !title.includes('...')
    )
        return title;
    return 'Task overview unavailable';
}


const RingGauge = GObject.registerClass(
class RingGauge extends St.DrawingArea {
    _init() {
        super._init({
            style_class: 'codex-dashboard-ring',
            width: 136,
            height: 136,
        });
        this.set_pivot_point(0.5, 0.5);
        this.set_scale(1.128, 1.128);
        this._fraction = 0;
        this.connect('repaint', () => this._draw());
    }

    setFraction(value) {
        const fraction = clamp(value);
        if (Math.abs(fraction - this._fraction) < 0.0001)
            return;
        this._fraction = fraction;
        this.queue_repaint();
    }

    _draw() {
        const context = this.get_context();
        const [width, height] = this.get_surface_size();
        const radius = Math.max(1, Math.min(width, height) / 2 - 13);
        const centreX = width / 2;
        const centreY = height / 2;
        const start = -Math.PI / 2;

        context.setLineWidth(13);
        context.setLineCap(Cairo.LineCap.ROUND);
        context.setSourceRGBA(0.44, 0.41, 0.60, 0.28);
        context.arc(centreX, centreY, radius, 0, Math.PI * 2);
        context.stroke();

        if (this._fraction > 0) {
            context.setSourceRGBA(0.56, 0.47, 1.0, 1);
            context.arc(
                centreX,
                centreY,
                radius,
                start,
                start + Math.PI * 2 * this._fraction
            );
            context.stroke();
        }
        context.$dispose();
    }
});


const ProgressLine = GObject.registerClass(
class ProgressLine extends St.DrawingArea {
    _init() {
        super._init({
            style_class: 'codex-dashboard-progress',
            height: 9,
            x_expand: true,
        });
        this._fraction = 0;
        this.connect('repaint', () => this._draw());
    }

    setFraction(value) {
        const fraction = clamp(value);
        if (Math.abs(fraction - this._fraction) < 0.0001)
            return;
        this._fraction = fraction;
        this.queue_repaint();
    }

    _draw() {
        const context = this.get_context();
        const [width, height] = this.get_surface_size();
        const lineWidth = Math.max(2, Math.min(7, height));
        const y = height / 2;
        const radius = lineWidth / 2;

        context.setLineWidth(lineWidth);
        context.setLineCap(Cairo.LineCap.ROUND);
        context.setSourceRGBA(0.44, 0.41, 0.60, 0.28);
        context.moveTo(radius, y);
        context.lineTo(Math.max(radius, width - radius), y);
        context.stroke();

        if (this._fraction > 0) {
            context.setSourceRGBA(0.56, 0.47, 1.0, 1);
            context.moveTo(radius, y);
            context.lineTo(
                radius + Math.max(0, width - lineWidth) * this._fraction,
                y
            );
            context.stroke();
        }
        context.$dispose();
    }
});


const CodexDashboardButton = GObject.registerClass(
class CodexDashboardButton extends PanelMenu.Button {
    _init(extension) {
        super._init(0.5, 'Codex Dashboard');
        this._extension = extension;
        this._destroyed = false;
        this._loading = false;
        this._loadQueued = false;
        this._lastQuota = null;
        this._lastQuotaAvailability = Availability.UNAVAILABLE;
        this._loadGeneration = 0;
        this._activeLoadGeneration = 0;
        this._dataCancellable = null;
        this._dataProcess = null;
        this._dataTimeoutSource = 0;
        this._quotaReloadSource = 0;

        this._buildPanel();
        this._buildMenu();
        this._watchQuotaState();
        this._readQuotaState();

        this._menuSignal = this.menu.connect(
            'open-state-changed',
            (_menu, open) => {
                if (open)
                    this.loadData();
            }
        );
        this._periodicSource = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT,
            30,
            () => {
                if (this._lastQuota)
                    this._applyQuota(
                        this._lastQuota,
                        this._lastQuotaAvailability
                    );
                return GLib.SOURCE_CONTINUE;
            }
        );
    }

    shutdown() {
        if (this._destroyed)
            return;
        this._destroyed = true;
        this._cancelDataLoad();
        if (this._menuSignal) {
            this.menu.disconnect(this._menuSignal);
            this._menuSignal = 0;
        }
        if (this._quotaMonitorSignal && this._quotaMonitor) {
            this._quotaMonitor.disconnect(this._quotaMonitorSignal);
            this._quotaMonitorSignal = 0;
        }
        this._quotaMonitor?.cancel();
        this._quotaMonitor = null;
        if (this._periodicSource) {
            GLib.Source.remove(this._periodicSource);
            this._periodicSource = 0;
        }
        if (this._quotaReloadSource) {
            GLib.Source.remove(this._quotaReloadSource);
            this._quotaReloadSource = 0;
        }
    }

    _buildPanel() {
        const box = new St.BoxLayout({
            style_class: 'panel-status-indicators-box codex-dashboard-panel-box',
        });
        this._panelIcon = new St.Icon({
            icon_name: 'codex-dashboard-symbolic',
            style_class: 'system-status-icon codex-dashboard-panel-icon',
        });
        this._panelLabel = new St.Label({
            text: 'Codex --%',
            y_align: Clutter.ActorAlign.CENTER,
        });
        box.add_child(this._panelIcon);
        box.add_child(this._panelLabel);
        this.add_child(box);
    }

    _buildMenu() {
        this.menu.actor?.add_style_class_name('codex-dashboard-menu');
        const root = new St.BoxLayout({
            vertical: true,
            style_class: 'codex-dashboard-root',
        });
        // Match GNOME's built-in date menu: custom content is attached
        // directly to the standard popup content box.
        root._delegate = this;
        this.menu.box.add_child(root);

        root.add_child(this._buildQuotaCard());
        root.add_child(this._buildTasksCard());
        root.add_child(this._buildHistoryCard());
    }

    _cardHeader(title, badgeText = null) {
        const row = new St.BoxLayout({
            style_class: 'codex-dashboard-card-header',
            x_expand: true,
        });
        row.add_child(new St.Label({
            text: title,
            style_class: 'codex-dashboard-card-title',
            x_expand: true,
        }));
        if (badgeText === null)
            return [row, null];
        const badge = new St.Label({
            text: badgeText,
            style_class: 'codex-dashboard-badge',
        });
        row.add_child(badge);
        return [row, badge];
    }

    _buildQuotaCard() {
        const card = new St.BoxLayout({
            style_class:
                'codex-dashboard-card codex-dashboard-overview-card',
        });
        this._overviewCard = card;

        const quota = new St.BoxLayout({
            style_class: 'codex-dashboard-overview-quota',
            width: 354,
        });
        const ringStack = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            width: 136,
            height: 136,
        });
        this._quotaRing = new RingGauge();
        ringStack.add_child(this._quotaRing);
        const ringText = new St.BoxLayout({
            vertical: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._quotaPercent = new St.Label({
            text: '--%',
            style_class: 'codex-dashboard-ring-value',
            x_align: Clutter.ActorAlign.CENTER,
        });
        ringText.add_child(this._quotaPercent);
        ringText.add_child(new St.Label({
            text: 'remaining',
            style_class: 'codex-dashboard-ring-caption',
            x_align: Clutter.ActorAlign.CENTER,
        }));
        ringStack.add_child(ringText);
        quota.add_child(ringStack);

        const details = new St.BoxLayout({
            vertical: true,
            style_class: 'codex-dashboard-overview-details',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            translation_y: -1,
        });
        this._quotaPlan = new St.Label({
            text: 'Codex account',
            style_class: 'codex-dashboard-quota-plan',
            x_align: Clutter.ActorAlign.START,
        });
        details.add_child(this._quotaPlan);
        this._quotaWindow = new St.Label({
            text: 'Codex limit',
            style_class: 'codex-dashboard-quota-window',
            x_expand: true,
        });
        details.add_child(this._quotaWindow);
        this._quotaProgress = new ProgressLine();
        details.add_child(this._quotaProgress);
        this._quotaReset = new St.Label({
            text: 'Waiting for quota data',
            style_class: 'codex-dashboard-reset',
        });
        details.add_child(this._quotaReset);
        this._quotaResetDate = new St.Label({
            text: '',
            style_class: 'codex-dashboard-reset-date',
        });
        details.add_child(this._quotaResetDate);
        quota.add_child(details);

        const usage = new St.BoxLayout({
            style_class: 'codex-dashboard-overview-usage',
            x_expand: true,
        });
        const usageContent = new St.BoxLayout({
            vertical: true,
            style_class: 'codex-dashboard-overview-usage-content',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            translation_y: 4,
        });
        usageContent.add_child(new St.Label({
            text: 'Token activity',
            style_class: 'codex-dashboard-usage-title',
            translation_y: 1,
        }));
        const [todayRow, todayValue] = this._usageRow('Today');
        this._usageToday = todayValue;
        usageContent.add_child(todayRow);
        const [weekRow, weekValue] = this._usageRow('Last 7 days');
        this._usageWeek = weekValue;
        usageContent.add_child(weekRow);
        const [ninetyDayRow, ninetyDayValue] =
            this._usageRow('Last 90 days');
        this._usageNinetyDays = ninetyDayValue;
        usageContent.add_child(ninetyDayRow);
        usage.add_child(usageContent);

        card.add_child(quota);
        card.add_child(usage);
        return card;
    }

    _usageRow(title) {
        const row = new St.BoxLayout({
            style_class: 'codex-dashboard-usage-row',
            x_expand: true,
        });
        row.add_child(new St.Label({
            text: title,
            style_class: 'codex-dashboard-usage-label',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        }));
        const value = new St.Label({
            text: '\u2014',
            style_class: 'codex-dashboard-usage-value',
            y_align: Clutter.ActorAlign.CENTER,
        });
        row.add_child(value);
        return [row, value];
    }

    _buildTasksCard() {
        const card = new St.BoxLayout({
            vertical: true,
            style_class: 'codex-dashboard-card',
        });
        const [header, badge] = this._cardHeader('Task overview', 'Syncing');
        this._tasksBadge = badge;
        card.add_child(header);

        this._taskRows = [];
        for (let index = 0; index < 5; index++) {
            const row = new St.BoxLayout({
                style_class: 'codex-dashboard-task-row',
                x_expand: true,
            });
            const dot = new St.Label({
                text: '\u25cf',
                style_class: 'codex-dashboard-task-dot task-neutral',
            });
            row.add_child(dot);
            const title = new St.Label({
                text: index === 0 ? 'Loading terminal tasks' : '',
                style_class: 'codex-dashboard-task-title',
                x_expand: true,
            });
            title.clutter_text.single_line_mode = true;
            row.add_child(title);
            const meta = new St.Label({
                text: '',
                style_class: 'codex-dashboard-task-meta',
            });
            row.add_child(meta);
            if (index > 0)
                row.hide();
            card.add_child(row);
            this._taskRows.push({row, dot, title, meta});
        }
        return card;
    }

    _buildHistoryCard() {
        const card = new St.BoxLayout({
            vertical: true,
            style_class:
                'codex-dashboard-card codex-dashboard-history-card',
        });
        const [header] = this._cardHeader('Three-Month Token Activity');
        card.add_child(header);

        const calendars = new St.BoxLayout({
            style_class: 'codex-dashboard-calendars',
            x_expand: true,
        });
        this._calendarMonths = [];
        for (let month = 0; month < 3; month++) {
            const panel = new St.BoxLayout({
                vertical: true,
                style_class: 'codex-dashboard-calendar-month',
                x_expand: true,
            });
            const name = new St.Label({
                text: 'Month',
                style_class: 'codex-dashboard-calendar-month-name',
            });
            panel.add_child(name);

            const weekdayRow = new St.BoxLayout({
                style_class: 'codex-dashboard-calendar-weekdays',
                x_align: Clutter.ActorAlign.CENTER,
            });
            for (const weekday of ['S', 'M', 'T', 'W', 'T', 'F', 'S']) {
                weekdayRow.add_child(new St.Label({
                    text: weekday,
                    style_class: 'codex-dashboard-calendar-weekday',
                    width: 18,
                    x_align: Clutter.ActorAlign.CENTER,
                }));
            }
            panel.add_child(weekdayRow);

            const weeks = new St.BoxLayout({
                vertical: true,
                style_class: 'codex-dashboard-calendar-weeks',
            });
            const cells = [];
            for (let week = 0; week < 6; week++) {
                const weekRow = new St.BoxLayout({
                    style_class: 'codex-dashboard-calendar-week',
                    x_align: Clutter.ActorAlign.CENTER,
                });
                for (let day = 0; day < 7; day++) {
                    const cell = new St.Label({
                        text: '',
                        style_class:
                            'codex-dashboard-calendar-day heat-level-0',
                        width: 18,
                        height: 18,
                        x_align: Clutter.ActorAlign.CENTER,
                        y_align: Clutter.ActorAlign.CENTER,
                    });
                    cell._heatLevelClass = 'heat-level-0';
                    cell.opacity = 0;
                    weekRow.add_child(cell);
                    cells.push(cell);
                }
                weeks.add_child(weekRow);
            }
            panel.add_child(weeks);
            calendars.add_child(panel);
            this._calendarMonths.push({name, cells});
        }
        card.add_child(calendars);

        const legend = new St.BoxLayout({
            style_class: 'codex-dashboard-heat-legend',
            x_align: Clutter.ActorAlign.END,
            y_align: Clutter.ActorAlign.CENTER,
        });
        legend.add_child(new St.Label({
            text: 'Less',
            style_class: 'codex-dashboard-muted',
        }));
        for (const level of [0, 2, 4]) {
            legend.add_child(new St.Widget({
                style_class:
                    `codex-dashboard-heat-cell ` +
                    `codex-dashboard-heat-legend-cell ` +
                    `heat-level-${level}`,
            }));
        }
        legend.add_child(new St.Label({
            text: 'More',
            style_class: 'codex-dashboard-muted',
        }));
        header.insert_child_at_index(legend, 1);
        return card;
    }

    _watchQuotaState() {
        try {
            const runtimeDirectory =
                Gio.File.new_for_path(GLib.get_user_runtime_dir());
            this._quotaMonitor = runtimeDirectory.monitor_directory(
                Gio.FileMonitorFlags.NONE,
                null
            );
            this._quotaMonitorSignal = this._quotaMonitor.connect(
                'changed',
                (_monitor, file, otherFile) => {
                    const names = [
                        file?.get_basename(),
                        otherFile?.get_basename(),
                    ];
                    if (!names.includes('codex-quota.json'))
                        return;
                    if (this._quotaReloadSource)
                        return;
                    this._quotaReloadSource = GLib.timeout_add(
                        GLib.PRIORITY_DEFAULT,
                        120,
                        () => {
                            this._quotaReloadSource = 0;
                            this._readQuotaState();
                            if (this.menu.isOpen)
                                this.loadData();
                            return GLib.SOURCE_REMOVE;
                        }
                    );
                }
            );
        } catch (error) {
            console.warn(`[${this._extension.uuid}] quota monitor: ${error}`);
        }
    }

    _readQuotaState() {
        try {
            const file = Gio.File.new_for_path(QUOTA_STATE_PATH);
            const [success, contents] = file.load_contents(null);
            if (!success)
                return;
            const quota = JSON.parse(new TextDecoder().decode(contents));
            if (quota && typeof quota === 'object')
                this._applyQuota(quota);
        } catch {
            if (!this._lastQuota)
                this._applyQuota({limits: []});
        }
    }

    setPanelLabel(text) {
        if (typeof text !== 'string' || !text.startsWith('Codex '))
            return;
        this._panelLabel.text = text;
    }

    setPanelLabelFromQuota(quota) {
        const limits = Array.isArray(quota?.limits) ? quota.limits : [];
        if (!limits.length) {
            this.setPanelLabel('Codex --%');
            return;
        }
        const active = limits.reduce((selected, candidate) =>
            Number(candidate?.remaining_percent) <
                Number(selected?.remaining_percent)
                ? candidate
                : selected
        );
        this.setPanelLabel(
            `Codex ${roundedPercent(active?.remaining_percent)}%`
        );
    }

    _removeDataTimeout() {
        if (!this._dataTimeoutSource)
            return;
        try {
            GLib.Source.remove(this._dataTimeoutSource);
        } catch (error) {
            console.warn(
                `[${this._extension.uuid}] data timeout cleanup: ${error}`
            );
        }
        this._dataTimeoutSource = 0;
    }

    _forceExitDataProcess(process) {
        if (!process)
            return;
        try {
            process.force_exit();
        } catch (error) {
            console.warn(
                `[${this._extension.uuid}] data helper cleanup: ${error}`
            );
        }
    }

    _cancelDataLoad() {
        this._activeLoadGeneration = 0;
        this._loadGeneration += 1;
        this._removeDataTimeout();
        const cancellable = this._dataCancellable;
        const process = this._dataProcess;
        this._dataCancellable = null;
        this._dataProcess = null;
        cancellable?.cancel();
        this._forceExitDataProcess(process);
        this._loading = false;
        this._loadQueued = false;
    }

    _dataLoadTimedOut(generation, process, cancellable) {
        if (
            this._destroyed
            || this._activeLoadGeneration !== generation
            || this._dataProcess !== process
        )
            return GLib.SOURCE_REMOVE;
        this._dataTimeoutSource = 0;
        if (this._dataCancellable === cancellable)
            cancellable.cancel();
        this._forceExitDataProcess(process);
        this._finishLoad(
            generation,
            null,
            new Error('Data helper timed out after 12 seconds')
        );
        return GLib.SOURCE_REMOVE;
    }

    loadData() {
        if (this._destroyed)
            return;
        if (this._loading) {
            this._loadQueued = true;
            return;
        }
        this._loading = true;
        this._loadQueued = false;
        const generation = ++this._loadGeneration;
        const cancellable = new Gio.Cancellable();
        this._activeLoadGeneration = generation;
        this._dataCancellable = cancellable;

        let process;
        try {
            process = Gio.Subprocess.new(
                ['/usr/bin/python3', '-I', DATA_HELPER],
                Gio.SubprocessFlags.STDOUT_PIPE |
                    Gio.SubprocessFlags.STDERR_PIPE
            );
        } catch (error) {
            this._finishLoad(generation, null, error);
            return;
        }
        this._dataProcess = process;

        try {
            this._dataTimeoutSource = GLib.timeout_add(
                GLib.PRIORITY_DEFAULT,
                DATA_HELPER_TIMEOUT_MILLISECONDS,
                () => this._dataLoadTimedOut(
                    generation,
                    process,
                    cancellable
                )
            );
            process.communicate_utf8_async(
                null,
                cancellable,
                (source, result) => {
                    let payload = null;
                    let failure = null;
                    try {
                        const [, stdout, stderr] =
                            source.communicate_utf8_finish(result);
                        if (!source.get_successful())
                            throw new Error(stderr || 'Data helper failed');
                        payload = JSON.parse(stdout);
                    } catch (error) {
                        failure = error;
                    }
                    this._finishLoad(generation, payload, failure);
                }
            );
        } catch (error) {
            cancellable.cancel();
            this._forceExitDataProcess(process);
            this._finishLoad(generation, null, error);
        }
    }

    _finishLoad(generation, payload, error) {
        if (this._activeLoadGeneration !== generation)
            return;
        this._activeLoadGeneration = 0;
        this._loading = false;
        this._removeDataTimeout();
        this._dataCancellable = null;
        this._dataProcess = null;
        if (this._destroyed)
            return;
        const validPayload = payload && typeof payload === 'object' &&
            !Array.isArray(payload);
        if (error || !validPayload) {
            this._applyQuota(
                {limits: []},
                Availability.UNAVAILABLE
            );
            this._applyUsage({}, Availability.UNAVAILABLE);
            this._applyTasks([], {}, Availability.UNAVAILABLE);
            if (!error?.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
                console.warn(
                    `[${this._extension.uuid}] data sync: ` +
                    `${error?.message ?? 'invalid helper response'}`
                );
        } else {
            this._applyData(payload);
        }
        const loadQueued = this._loadQueued;
        this._loadQueued = false;
        if (loadQueued)
            this.loadData();
    }

    _applyData(payload) {
        const availability = payload.availability &&
            typeof payload.availability === 'object' &&
            !Array.isArray(payload.availability)
            ? payload.availability
            : {};
        this._applyQuota(
            payload.quota ?? {limits: []},
            normalizeAvailability(availability.quota)
        );
        this._applyUsage(
            payload.usage ?? {},
            normalizeAvailability(availability.usage)
        );
        this._applyTasks(
            payload.tasks ?? [],
            payload.activity_counts ?? {},
            normalizeAvailability(availability.tasks)
        );
        for (const warning of payload.warnings ?? [])
            console.warn(`[${this._extension.uuid}] data: ${warning}`);
    }

    _applyQuota(quota, availability = null) {
        this._lastQuota = quota;
        const state = quotaAvailability(quota, availability);
        this._lastQuotaAvailability = state;
        for (const style of ['quota-stale', 'quota-unavailable'])
            this._overviewCard.remove_style_class_name(style);
        if (state === Availability.STALE)
            this._overviewCard.add_style_class_name('quota-stale');
        else if (state === Availability.UNAVAILABLE)
            this._overviewCard.add_style_class_name('quota-unavailable');

        const limits = state !== Availability.UNAVAILABLE &&
            Array.isArray(quota?.limits)
            ? quota.limits.filter(limit =>
                Number.isFinite(Number(limit?.remaining_percent)))
            : [];
        if (!limits.length) {
            this._quotaRing.setFraction(0);
            this._quotaPercent.text = '--%';
            this._quotaProgress.setFraction(0);
            this._quotaWindow.text = 'Quota unavailable';
            this._quotaPlan.text = planTitle(quota?.plan_type);
            this._quotaReset.text = '';
            this._quotaResetDate.text = '';
            this.setPanelLabel('Codex --%');
            return;
        }

        const active = limits.reduce((selected, candidate) =>
            Number(candidate.remaining_percent) <
                Number(selected.remaining_percent)
                ? candidate
                : selected
        );
        const percent = roundedPercent(active.remaining_percent);
        this._quotaRing.setFraction(percent / 100);
        this._quotaPercent.text = `${percent}%`;
        this._quotaProgress.setFraction(percent / 100);
        this._quotaWindow.text = limitTitle(active);
        this._quotaPlan.text = planTitle(quota.plan_type);
        const resetText = formatReset(active.resets_at);
        this._quotaReset.text = state === Availability.STALE
            ? `Cached \u00b7 ${resetText}`
            : resetText;
        const resetDate = formatClockFromSeconds(active.resets_at);
        this._quotaResetDate.text = resetDate.includes('unavailable')
            ? ''
            : resetDate;
        this.setPanelLabelFromQuota(quota);
    }

    _applyUsage(usage, availability = Availability.UNAVAILABLE) {
        const state = normalizeAvailability(availability);
        if (state === Availability.UNAVAILABLE) {
            this._usageToday.text = '\u2014';
            this._usageNinetyDays.text = '\u2014';
            this._usageWeek.text = '\u2014';
            this._applyCalendarUsage([]);
            return;
        }
        this._usageToday.text = formatTodayTokens(
            usage?.today,
            usage?.current_day_available === true,
            usage?.today_is_estimate === true
                ? usage?.today_estimate
                : null
        );
        this._usageNinetyDays.text = formatTokens(usage?.ninety_days);
        this._usageWeek.text = formatTokens(usage?.seven_days);
        this._applyCalendarUsage(
            Array.isArray(usage?.calendar_months)
                ? usage.calendar_months
                : []
        );
    }

    _applyCalendarUsage(months) {
        const records = months.flatMap(month => {
            const year = Number(month?.year);
            const monthNumber = Number(month?.month);
            if (
                !Number.isInteger(year)
                || !Number.isInteger(monthNumber)
                || monthNumber < 1
                || monthNumber > 12
                || !Array.isArray(month?.days)
            )
                return [];
            return month.days.flatMap(item => {
                const day = Number(item?.day);
                if (!Number.isInteger(day) || day < 1 || day > 31)
                    return [];
                return [{
                    year,
                    month: monthNumber - 1,
                    day,
                    tokens: calendarTokenValue(item?.tokens),
                }];
            });
        });
        const maximum = Math.max(
            0,
            ...records.flatMap(record =>
                record.tokens === null ? [] : [record.tokens])
        );

        for (let index = 0; index < this._calendarMonths.length; index++) {
            const actors = this._calendarMonths[index];
            const monthData = months[index];
            const year = Number(monthData?.year);
            const monthNumber = Number(monthData?.month);
            if (
                !Number.isInteger(year)
                || !Number.isInteger(monthNumber)
                || !Array.isArray(monthData?.days)
            ) {
                actors.name.text = '\u2014';
                for (const cell of actors.cells) {
                    cell.remove_style_class_name(cell._heatLevelClass);
                    cell._heatLevelClass = 'heat-level-0';
                    cell.add_style_class_name(cell._heatLevelClass);
                    cell.text = '';
                    cell.opacity = 0;
                }
                continue;
            }
            const month = monthNumber - 1;
            const firstWeekday =
                new Date(Date.UTC(year, month, 1)).getUTCDay();
            const daysInMonth =
                new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
            const byDay = new Map(monthData.days.map(item => [
                Number(item?.day),
                calendarTokenValue(item?.tokens),
            ]));
            const lastVisibleDay = Math.min(
                daysInMonth,
                Math.max(0, ...byDay.keys())
            );
            actors.name.text = String(monthData.label ?? 'Month');

            for (let cellIndex = 0; cellIndex < actors.cells.length;
                cellIndex++) {
                const cell = actors.cells[cellIndex];
                const day = cellIndex - firstWeekday + 1;
                const visible =
                    day >= 1
                    && day <= daysInMonth
                    && day <= lastVisibleDay;
                cell.remove_style_class_name(cell._heatLevelClass);
                if (!visible) {
                    cell.text = '';
                    cell._heatLevelClass = 'heat-level-0';
                    cell.add_style_class_name(cell._heatLevelClass);
                    cell.opacity = 0;
                    continue;
                }

                const value = byDay.has(day) ? byDay.get(day) : 0;
                cell.text = String(day);
                cell._heatLevelClass =
                    calendarHeatClass(value, maximum);
                cell.add_style_class_name(cell._heatLevelClass);
                cell.opacity = 255;
            }
        }
    }

    _applyTasks(
        tasks,
        counts,
        availability = Availability.UNAVAILABLE
    ) {
        void counts;
        const state = normalizeAvailability(availability);
        if (state === Availability.UNAVAILABLE) {
            this._tasksBadge.text = 'Unavailable';
            this._tasksBadge.set_style_class_name(
                'codex-dashboard-badge badge-warning'
            );
            for (const actors of this._taskRows)
                actors.row.hide();
            const actors = this._taskRows[0];
            actors.row.show();
            actors.title.text = 'Task data unavailable';
            actors.meta.text = '';
            for (const style of [
                'task-live',
                'task-done',
                'task-warning',
                'task-neutral',
            ])
                actors.dot.remove_style_class_name(style);
            actors.dot.add_style_class_name('task-neutral');
            return;
        }
        const entries = Array.isArray(tasks) ? tasks.slice(0, 5) : [];
        if (state === Availability.STALE) {
            this._tasksBadge.text = 'Cached';
            this._tasksBadge.set_style_class_name(
                'codex-dashboard-badge badge-muted'
            );
        } else {
            this._tasksBadge.text =
                `${entries.length} task${entries.length === 1 ? '' : 's'}`;
            this._tasksBadge.set_style_class_name('codex-dashboard-badge');
        }

        for (let index = 0; index < this._taskRows.length; index++) {
            const actors = this._taskRows[index];
            const task = entries[index];
            if (!task) {
                actors.row.hide();
                continue;
            }
            actors.row.show();
            actors.title.text = taskOverviewTitle(task.title);
            const status = String(task.status ?? 'unknown');
            const labels = {
                in_progress: 'Active',
                completed: 'Completed',
                interrupted: 'Interrupted',
                incomplete: 'Incomplete',
                recent: '',
            };
            const classes = {
                in_progress: 'task-live',
                completed: 'task-done',
                interrupted: 'task-warning',
                incomplete: 'task-neutral',
                recent: 'task-neutral',
            };
            for (const style of [
                'task-live',
                'task-done',
                'task-warning',
                'task-neutral',
            ])
                actors.dot.remove_style_class_name(style);
            actors.dot.add_style_class_name(
                classes[status] ?? 'task-neutral'
            );
            const relative = formatRelativeTime(task.updated_at);
            const statusLabel = labels[status] ?? 'Recorded';
            actors.meta.text = statusLabel && relative
                ? `${statusLabel} \u00b7 ${relative}`
                : statusLabel || relative;
        }
        if (!entries.length) {
            const actors = this._taskRows[0];
            actors.row.show();
            actors.title.text = 'No recent tasks';
            actors.meta.text = '';
            for (const style of [
                'task-live',
                'task-done',
                'task-warning',
                'task-neutral',
            ])
                actors.dot.remove_style_class_name(style);
            actors.dot.add_style_class_name('task-neutral');
        }
    }
});


export default class CodexDashboardExtension extends Extension {
    enable() {
        this._enabled = true;
        this._placing = false;
        this._placeSource = 0;
        this._dateButton = null;

        this._button = new CodexDashboardButton(this);
        const dateButton = Main.panel?.statusArea?.dateMenu;
        const dateContainer = dateButton?.container;
        const centreBox = Main.panel?._centerBox;
        const dateIndex = this._isContainer(centreBox)
            ? centreBox.get_children().indexOf(dateContainer)
            : -1;
        this._applyPanelStyles(dateButton);
        try {
            if (dateIndex >= 0) {
                Main.panel.addToStatusArea(
                    this.uuid,
                    this._button,
                    dateIndex + 1,
                    'center'
                );
            } else {
                // The date menu is normally ready before extensions. Keep a
                // safe fallback; idle integration will correct the position.
                Main.panel.addToStatusArea(
                    this.uuid,
                    this._button,
                    1,
                    'right'
                );
            }
        } catch (error) {
            this._removePanelStyles();
            this._button.shutdown();
            this._button.destroy();
            this._button = null;
            throw error;
        }
        this._scheduleIntegration();
    }

    disable() {
        this._enabled = false;
        if (this._placeSource) {
            GLib.Source.remove(this._placeSource);
            this._placeSource = 0;
        }
        this._removePanelStyles();
        this._button?.shutdown();
        this._button?.destroy();
        this._button = null;
    }

    _scheduleIntegration() {
        if (!this._enabled || this._placing || this._placeSource)
            return;
        this._placeSource = GLib.idle_add(
            GLib.PRIORITY_DEFAULT_IDLE,
            () => {
                this._placeSource = 0;
                if (!this._enabled)
                    return GLib.SOURCE_REMOVE;
                this._placing = true;
                try {
                    this._integrate();
                } catch (error) {
                    this._warn('integrate dashboard', error);
                } finally {
                    this._placing = false;
                }
                return GLib.SOURCE_REMOVE;
            }
        );
    }

    _integrate() {
        const dateButton = Main.panel?.statusArea?.dateMenu;
        const dateContainer = dateButton?.container;
        const centreBox = Main.panel?._centerBox;
        const dashboardContainer = this._button?.container;
        if (
            !this._isContainer(centreBox)
            || !this._isActor(dateButton)
            || !this._isActor(dateContainer)
            || !this._isActor(dashboardContainer)
        )
            return;

        if (!this._moveAfterDate(
            dashboardContainer,
            centreBox,
            dateContainer
        ))
            return;
        this._applyPanelStyles(dateButton);
    }

    _moveAfterDate(actor, target, dateContainer) {
        const source = actor.get_parent();
        const targetChildren = target.get_children();
        const dateIndex = targetChildren.indexOf(dateContainer);
        const actorIndex = targetChildren.indexOf(actor);
        if (!source || dateIndex < 0)
            return false;
        if (source === target && actorIndex === dateIndex + 1)
            return true;

        const sourceIndex = source.get_children().indexOf(actor);
        source.remove_child(actor);
        try {
            const liveDateIndex =
                target.get_children().indexOf(dateContainer);
            if (liveDateIndex < 0)
                throw new Error('clock left centre box');
            target.insert_child_at_index(actor, liveDateIndex + 1);
            return true;
        } catch (error) {
            const restoreIndex = Math.min(
                Math.max(0, sourceIndex),
                source.get_children().length
            );
            source.insert_child_at_index(actor, restoreIndex);
            this._warn('move after clock', error);
            return false;
        }
    }

    _isActor(actor) {
        return Boolean(actor) &&
            typeof actor.get_parent === 'function' &&
            typeof actor.add_style_class_name === 'function';
    }

    _isContainer(actor) {
        return Boolean(actor) &&
            typeof actor.get_children === 'function' &&
            typeof actor.remove_child === 'function' &&
            typeof actor.insert_child_at_index === 'function';
    }

    _addStyle(actor, name) {
        if (this._isActor(actor))
            actor.add_style_class_name(name);
    }

    _removeStyle(actor, name) {
        if (this._isActor(actor))
            actor.remove_style_class_name(name);
    }

    _applyPanelStyles(dateButton) {
        if (this._dateButton && this._dateButton !== dateButton)
            this._removeStyle(this._dateButton, CLOCK_BUTTON_STYLE);
        this._dateButton = this._isActor(dateButton) ? dateButton : null;
        this._addStyle(this._dateButton, CLOCK_BUTTON_STYLE);
        this._addStyle(this._button, CODEX_BUTTON_STYLE);
        this._queuePanelRefresh(this._dateButton, this._button);
    }

    _removePanelStyles() {
        const dateButton = this._dateButton;
        const codexButton = this._button;
        this._removeStyle(dateButton, CLOCK_BUTTON_STYLE);
        this._removeStyle(codexButton, CODEX_BUTTON_STYLE);
        this._dateButton = null;
        this._queuePanelRefresh(dateButton, codexButton);
    }

    _queuePanelRefresh(...actors) {
        const centreBox = Main.panel?._centerBox;
        for (const actor of [...actors, centreBox]) {
            try {
                actor?.queue_relayout?.();
                actor?.queue_redraw?.();
            } catch (error) {
                this._warn('refresh panel layout', error);
            }
        }
    }

    _warn(message, error) {
        console.warn(`[${this.uuid}] ${message}: ${error}`);
    }
}
