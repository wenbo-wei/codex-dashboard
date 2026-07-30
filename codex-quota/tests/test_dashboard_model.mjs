import assert from 'node:assert/strict';

import {
    Availability,
    formatRelativeTime,
    formatReset,
    formatTokens,
    limitTitle,
    normalizeAvailability,
    planTitle,
    quotaAvailability,
    roundedPercent,
} from '../../extensions/codex-quota-centre@local/dashboardModel.mjs';


assert.equal(formatReset(6 * 86_400, 1), 'Resets in 6d');
assert.equal(
    formatReset(6 * 86_400 - 1, 0),
    'Resets in 6d',
);
assert.notEqual(
    formatReset(6 * 86_400 - 1, 0),
    'Resets in 5d 24h',
);
assert.equal(formatReset(3_601, 0), 'Resets in 2h');
assert.equal(formatTokens(1_234_567), '1.2M');
assert.equal(roundedPercent(54.5), 55);
assert.equal(limitTitle({window_minutes: 10_080}), '7-day limit');
assert.equal(planTitle('pro'), 'Pro');
assert.equal(planTitle('pro max'), 'Pro Max');
assert.equal(Object.isFrozen(Availability), true);
assert.equal(normalizeAvailability('ready'), Availability.READY);
assert.equal(normalizeAvailability('unexpected'), Availability.UNAVAILABLE);
assert.equal(
    quotaAvailability(
        {
            limits: [{remaining_percent: 50}],
            _stale: false,
            updated_at_seconds: 1_000,
        },
        Availability.READY,
        1_301,
    ),
    Availability.STALE,
);
assert.equal(
    quotaAvailability(
        {
            limits: [{remaining_percent: 50}],
            _stale: false,
            updated_at_seconds: 1_000,
        },
        'unexpected',
        1_001,
    ),
    Availability.UNAVAILABLE,
);
assert.equal(
    formatRelativeTime('2026-01-01T00:00:00Z', Date.parse(
        '2026-01-01T02:00:00Z'
    )),
    '2h ago',
);

console.log('dashboardModel behavior tests passed');
