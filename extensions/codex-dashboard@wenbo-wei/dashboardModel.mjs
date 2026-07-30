// Pure presentation rules shared by the GNOME view.

export const Availability = Object.freeze({
    READY: 'ready',
    STALE: 'stale',
    UNAVAILABLE: 'unavailable',
});


export function normalizeAvailability(value) {
    return Object.values(Availability).includes(value)
        ? value
        : Availability.UNAVAILABLE;
}


export function quotaAvailability(
    quota,
    explicitAvailability = null,
    nowSeconds = Date.now() / 1_000,
    staleAfterSeconds = 300
) {
    let explicit = null;
    if (explicitAvailability !== null &&
        explicitAvailability !== undefined) {
        explicit = normalizeAvailability(explicitAvailability);
        if (explicit === Availability.UNAVAILABLE)
            return Availability.UNAVAILABLE;
    }

    const limits = Array.isArray(quota?.limits) ? quota.limits : [];
    if (!limits.length)
        return Availability.UNAVAILABLE;
    if (explicit === Availability.STALE || quota?._stale === true)
        return Availability.STALE;

    const rawUpdatedAt = quota?.updated_at_seconds;
    const updatedAt = typeof rawUpdatedAt === 'number' ||
        typeof rawUpdatedAt === 'string'
        ? Number(rawUpdatedAt)
        : Number.NaN;
    const now = Number(nowSeconds);
    const staleAfter = Math.max(0, Number(staleAfterSeconds) || 0);
    if (Number.isFinite(updatedAt) && Number.isFinite(now) &&
        now - updatedAt >= staleAfter)
        return Availability.STALE;
    return Availability.READY;
}

export function clamp(value, lower = 0, upper = 1) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric))
        return lower;
    return Math.max(lower, Math.min(upper, numeric));
}


export function roundedPercent(value) {
    return Math.floor(clamp(value, 0, 100) + 0.5);
}


export function formatTokens(value) {
    const tokens = Math.max(0, Number(value) || 0);
    if (tokens >= 1_000_000_000)
        return `${(tokens / 1_000_000_000).toFixed(2)}B`;
    if (tokens >= 1_000_000)
        return `${(tokens / 1_000_000).toFixed(1)}M`;
    if (tokens >= 1_000)
        return `${(tokens / 1_000).toFixed(1)}K`;
    return Math.round(tokens).toLocaleString('en-US');
}


export function formatClockFromSeconds(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value))
        return 'Time unavailable';
    return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
    }).format(new Date(value * 1_000));
}


export function formatReset(seconds, nowSeconds = Date.now() / 1_000) {
    const value = Number(seconds);
    const now = Number(nowSeconds);
    if (!Number.isFinite(value) || !Number.isFinite(now))
        return 'Reset time unavailable';

    // Round once at the hour seam, then split. This cannot produce "5d 24h".
    const totalHours = Math.ceil(Math.max(0, value - now) / 3_600);
    const days = Math.floor(totalHours / 24);
    const hours = totalHours % 24;
    if (days > 0)
        return `Resets in ${days}d${hours ? ` ${hours}h` : ''}`;
    if (hours > 0)
        return `Resets in ${hours}h`;

    const minutes = Math.max(1, Math.ceil(Math.max(0, value - now) / 60));
    return `Resets in ${minutes}m`;
}


export function formatRelativeTime(
    timestamp,
    nowMilliseconds = Date.now()
) {
    if (typeof timestamp !== 'string' || !timestamp)
        return '';
    const milliseconds = Date.parse(timestamp);
    const now = Number(nowMilliseconds);
    if (!Number.isFinite(milliseconds) || !Number.isFinite(now))
        return '';
    const seconds = Math.max(0, now / 1_000 - milliseconds / 1_000);
    if (seconds < 60)
        return 'just now';
    if (seconds < 3_600)
        return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86_400)
        return `${Math.floor(seconds / 3_600)}h ago`;
    return `${Math.floor(seconds / 86_400)}d ago`;
}


export function limitTitle(limit) {
    const minutes = Number(limit?.window_minutes);
    if (minutes === 10_080)
        return '7-day limit';
    if (minutes === 300)
        return '5-hour limit';
    if (minutes > 0 && minutes % 1_440 === 0)
        return `${minutes / 1_440}-day limit`;
    if (minutes > 0 && minutes % 60 === 0)
        return `${minutes / 60}-hour limit`;
    return 'Codex limit';
}


export function planTitle(value) {
    if (typeof value !== 'string' || !value)
        return 'Codex account';
    const words = value
        .trim()
        .toLowerCase()
        .replaceAll(/[-_]+/g, ' ');
    if (words === 'pro')
        return 'Pro';
    if (words === 'pro max')
        return 'Pro Max';
    return words.replaceAll(/\b\w/g, character =>
        character.toUpperCase()
    );
}
