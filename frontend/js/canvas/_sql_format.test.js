// node:test suite for the in-house SQL pretty-formatter: keyword
// uppercasing, structural newlines, literal protection, and the
// refuse-to-mangle passthrough paths.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatSql } from './_sql_format.js';

test('uppercases keywords and breaks before structural clauses', () => {
  assert.equal(formatSql('select 1 from t'), 'SELECT 1\nFROM t');
  assert.equal(
    formatSql('select a from t where x = 1 order by a limit 5'),
    'SELECT a\nFROM t\nWHERE x = 1\nORDER BY a\nLIMIT 5'
  );
});

test('normalises runs of whitespace', () => {
  assert.equal(formatSql('select   1   from    t'), 'SELECT 1\nFROM t');
});

test('non-string and empty inputs pass through untouched', () => {
  assert.equal(formatSql(''), '');
  assert.equal(formatSql('   '), '   ');
  assert.equal(formatSql(null), null);
  assert.equal(formatSql(undefined), undefined);
});

test('backtick- and dollar-quoted inputs are never reformatted', () => {
  assert.equal(formatSql('select `weird` from t'), 'select `weird` from t');
  assert.equal(formatSql('select $$body$$ from t'), 'select $$body$$ from t');
});

test('keywords inside single-quoted literals are left alone', () => {
  const out = formatSql("select 'from where' from t");
  assert.equal(out, "SELECT 'from where'\nFROM t");
});

test('line comments are protected from rewriting', () => {
  const out = formatSql('select 1 from t -- select from nowhere');
  assert.ok(out.endsWith('-- select from nowhere'));
  assert.ok(out.startsWith('SELECT 1\nFROM t'));
});
