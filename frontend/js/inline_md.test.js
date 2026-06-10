// node:test suite for the inline-markdown renderer.
//
// Security-relevant: escape-first ordering means no author-supplied
// markup may survive into the x-html sink, and only http(s) /
// root-relative hrefs may become anchors.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { escapeHtml, renderInlineMd } from './inline_md.js';

test('escapeHtml escapes all five HTML-significant characters', () => {
  assert.equal(escapeHtml(`&<>"'`), '&amp;&lt;&gt;&quot;&#39;');
});

test('escapeHtml coerces null and undefined to the empty string', () => {
  assert.equal(escapeHtml(null), '');
  assert.equal(escapeHtml(undefined), '');
});

test('escapeHtml coerces non-string values', () => {
  assert.equal(escapeHtml(42), '42');
});

test('renderInlineMd never lets a script tag survive', () => {
  const out = renderInlineMd('<script>alert(1)</script>');
  assert.ok(!out.includes('<script>'));
  assert.ok(out.includes('&lt;script&gt;'));
});

test('renderInlineMd renders the bold/italic/code subset', () => {
  assert.equal(renderInlineMd('**b**'), '<strong>b</strong>');
  assert.equal(renderInlineMd('a *i* z'), 'a <em>i</em> z');
  assert.equal(renderInlineMd('a _i_ z'), 'a <em>i</em> z');
  assert.equal(renderInlineMd('`code`'), '<code>code</code>');
});

test('renderInlineMd leaves a literal asterisk inside code alone', () => {
  assert.equal(renderInlineMd('`a*b`'), '<code>a*b</code>');
});

test('renderInlineMd links: http(s) and root-relative pass, with noopener', () => {
  assert.equal(
    renderInlineMd('[x](https://example.com)'),
    '<a href="https://example.com" rel="noopener">x</a>'
  );
  assert.equal(renderInlineMd('[x](/tables/foo)'), '<a href="/tables/foo" rel="noopener">x</a>');
});

test('renderInlineMd links: unsafe schemes degrade to the bare label', () => {
  assert.equal(renderInlineMd('[x](javascript:void)'), 'x');
  assert.equal(renderInlineMd('[x](//evil.example)'), 'x');
  // Parens in the href cut the match short, but no anchor may form.
  const out = renderInlineMd('[x](javascript:alert(1))');
  assert.ok(!out.includes('<a'));
  assert.ok(!out.includes('javascript:'));
});

test('renderInlineMd does not italicize underscores inside an href', () => {
  const out = renderInlineMd('[label](/data/foo_bar_baz)');
  assert.equal(out, '<a href="/data/foo_bar_baz" rel="noopener">label</a>');
});
