import assert from 'node:assert/strict';
import test from 'node:test';

import {
    calendarHeatClass,
    calendarTokenValue,
    formatTodayTokens,
} from '../extensions/codex-dashboard@wenbo-wei/dashboardModel.mjs';


test('missing current-day usage stays pending in text and calendar', () => {
    assert.equal(formatTodayTokens(null, false), 'Pending');
    assert.equal(calendarTokenValue(null), null);
    assert.equal(calendarHeatClass(null, 125), 'calendar-pending');
});


test('an explicit zero bucket stays a real zero', () => {
    assert.equal(formatTodayTokens(0, true), '0');
    assert.equal(calendarTokenValue(0), 0);
    assert.equal(calendarHeatClass(0, 125), 'heat-level-0');
});
