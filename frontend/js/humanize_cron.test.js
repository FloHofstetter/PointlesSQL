// node:test suite for the cron humanizer: the supported shapes get
// prose, everything else falls through to the raw expression so the
// UI never lies about what's scheduled.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { pqlHumanizeCron } from './humanize_cron.js';

test('macros expand to prose', () => {
  assert.equal(pqlHumanizeCron('@hourly'), 'Every hour');
  assert.equal(pqlHumanizeCron('@daily'), 'Daily at 00:00');
  assert.equal(pqlHumanizeCron('@midnight'), 'Daily at 00:00');
  assert.equal(pqlHumanizeCron('@weekly'), 'Weekly on Sunday at 00:00');
  assert.equal(pqlHumanizeCron('@monthly'), 'Monthly on the 1st at 00:00');
  assert.equal(pqlHumanizeCron('@yearly'), 'Yearly on Jan 1 at 00:00');
});

test('an unknown macro falls through to the raw expression', () => {
  assert.equal(pqlHumanizeCron('@fortnightly'), '@fortnightly');
});

test('the all-star ticker and step minutes', () => {
  assert.equal(pqlHumanizeCron('* * * * *'), 'Every minute');
  assert.equal(pqlHumanizeCron('*/1 * * * *'), 'Every minute');
  assert.equal(pqlHumanizeCron('*/15 * * * *'), 'Every 15 minutes');
});

test('integer minute/hour combos', () => {
  assert.equal(pqlHumanizeCron('30 * * * *'), 'Every hour at :30');
  assert.equal(pqlHumanizeCron('0 6 * * *'), 'Daily at 06:00');
  assert.equal(pqlHumanizeCron('0 9 * * mon'), 'Weekly on Monday at 09:00');
  assert.equal(pqlHumanizeCron('0 9 * * 7'), 'Weekly on Sunday at 09:00');
  assert.equal(pqlHumanizeCron('15 8 1 * *'), 'Monthly on the 1st at 08:15');
  assert.equal(pqlHumanizeCron('0 0 22 dec *'), 'Yearly on Dec 22nd at 00:00');
});

test('unparseable expressions fall through verbatim', () => {
  assert.equal(pqlHumanizeCron('61 * * * *'), '61 * * * *');
  assert.equal(pqlHumanizeCron('0 25 * * *'), '0 25 * * *');
  assert.equal(pqlHumanizeCron('not a cron'), 'not a cron');
  assert.equal(pqlHumanizeCron('1 2 3'), '1 2 3');
});

test('null/empty input renders as the empty string', () => {
  assert.equal(pqlHumanizeCron(null), '');
  assert.equal(pqlHumanizeCron('   '), '');
});
