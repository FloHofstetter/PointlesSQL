// node:test suite for the debugger mixin's pure helpers: breakpoint
// parsing, DAP request envelope building, and the stack-frame /
// scope / variable mappers that feed the debug panel.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  buildDapRequest,
  mapScopes,
  mapStackFrames,
  mapVariables,
  parseBreakpointLines,
} from './debugger.js';

test('parseBreakpointLines splits on commas and whitespace', () => {
  assert.deepEqual(parseBreakpointLines('2, 5, 9'), [2, 5, 9]);
  assert.deepEqual(parseBreakpointLines('2 5\t9'), [2, 5, 9]);
  assert.deepEqual(parseBreakpointLines(' 3 ,, 1 '), [1, 3]);
});

test('parseBreakpointLines sorts and de-duplicates', () => {
  assert.deepEqual(parseBreakpointLines('9,2,9,2,5'), [2, 5, 9]);
});

test('parseBreakpointLines drops non-positive and non-integer tokens', () => {
  assert.deepEqual(parseBreakpointLines('0, -1, 1.5, abc, 4'), [4]);
});

test('parseBreakpointLines handles empty and non-string input', () => {
  assert.deepEqual(parseBreakpointLines(''), []);
  assert.deepEqual(parseBreakpointLines('   '), []);
  assert.deepEqual(parseBreakpointLines(null), []);
  assert.deepEqual(parseBreakpointLines(undefined), []);
  assert.deepEqual(parseBreakpointLines(42), []);
});

test('buildDapRequest wraps command + arguments, no client seq', () => {
  const req = buildDapRequest('setBreakpoints', { source: { path: '/x' } });
  assert.deepEqual(req, {
    type: 'request',
    command: 'setBreakpoints',
    arguments: { source: { path: '/x' } },
  });
  // seq is stamped server-side by the kernel session.
  assert.ok(!('seq' in req));
});

test('buildDapRequest defaults arguments to an empty object', () => {
  assert.deepEqual(buildDapRequest('debugInfo'), {
    type: 'request',
    command: 'debugInfo',
    arguments: {},
  });
  assert.deepEqual(buildDapRequest('attach', null).arguments, {});
});

test('mapStackFrames extracts id/name/line and flattens source', () => {
  const body = {
    stackFrames: [
      { id: 3, name: '<module>', line: 2, source: { name: 'cell-1', path: '/tmp/c1.py' } },
      { id: 4, name: 'helper', line: 7, source: { path: '/tmp/c1.py' } },
      { id: 5 },
    ],
  };
  assert.deepEqual(mapStackFrames(body), [
    { id: 3, name: '<module>', line: 2, source: 'cell-1' },
    { id: 4, name: 'helper', line: 7, source: '/tmp/c1.py' },
    { id: 5, name: '(unknown)', line: null, source: '' },
  ]);
});

test('mapStackFrames tolerates missing or malformed bodies', () => {
  assert.deepEqual(mapStackFrames(null), []);
  assert.deepEqual(mapStackFrames({}), []);
  assert.deepEqual(mapStackFrames({ stackFrames: 'nope' }), []);
});

test('mapScopes carries name, reference, and expensive flag', () => {
  const body = {
    scopes: [
      { name: 'Locals', variablesReference: 11 },
      { name: 'Globals', variablesReference: 12, expensive: true },
      {},
    ],
  };
  assert.deepEqual(mapScopes(body), [
    { name: 'Locals', variablesReference: 11, expensive: false },
    { name: 'Globals', variablesReference: 12, expensive: true },
    { name: '', variablesReference: 0, expensive: false },
  ]);
  assert.deepEqual(mapScopes(undefined), []);
});

test('mapVariables keeps one display level of name/type/value', () => {
  const body = {
    variables: [
      { name: 'x', type: 'int', value: '42', variablesReference: 0 },
      { name: 'df', type: 'DataFrame', value: '<df>', variablesReference: 99 },
      { name: 'noType', value: 7 },
      { value: 'orphan' },
      null,
    ],
  };
  assert.deepEqual(mapVariables(body), [
    { name: 'x', type: 'int', value: '42' },
    { name: 'df', type: 'DataFrame', value: '<df>' },
    { name: 'noType', type: '', value: '7' },
  ]);
  assert.deepEqual(mapVariables({}), []);
});
