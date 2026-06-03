/*
 * Pure DOM-string helpers for canvas node bodies.
 *
 * Stateless formatters the editor uses to paint a node's schema-column
 * strip, footer badge and config summary.  Kept separate from the block
 * catalog so the catalog stays data-only and these stay logic-only; both
 * are imported by the editor and could be imported by any future canvas
 * surface that renders node internals.
 */

const TYPE_ICON_MAP = [
  [
    /^(INT|BIGINT|SMALLINT|TINYINT|INTEGER|HUGEINT|UBIGINT|UINTEGER|USMALLINT|UTINYINT)/i,
    'bi-hash',
  ],
  [/^(DOUBLE|FLOAT|REAL|DECIMAL|NUMERIC)/i, 'bi-calculator'],
  [/^(VARCHAR|TEXT|CHAR|STRING|BLOB|BIT)/i, 'bi-text-paragraph'],
  [/^(DATE|TIMESTAMP|TIME|INTERVAL)/i, 'bi-calendar3'],
  [/^(BOOL|BOOLEAN)/i, 'bi-check2-square'],
  [/^(STRUCT|LIST|MAP|UNION|ARRAY|JSON)/i, 'bi-diagram-3'],
];

/**
 * Map a DuckDB type name to a Bootstrap icon class.
 *
 * @param {string} typeName
 * @returns {string}
 */
export function typeIcon(typeName) {
  const t = String(typeName || '').toUpperCase();
  for (const [re, icon] of TYPE_ICON_MAP) {
    if (re.test(t)) return icon;
  }
  return 'bi-circle';
}

/**
 * Render the first few schema columns as an icon + name + type strip.
 *
 * @param {Array<{name: string, duckdb_type?: string}>} columns
 * @returns {string}
 */
export function renderColsHtml(columns) {
  if (!columns || columns.length === 0) return '';
  const max = 3;
  const shown = columns.slice(0, max);
  const extra = columns.length - shown.length;
  const rows = shown
    .map(
      (c) =>
        `<span><i class="bi ${typeIcon(c.duckdb_type)}"></i> ${escapeHtml(c.name)} <span class="text-muted">${escapeHtml(c.duckdb_type || '')}</span></span>`
    )
    .join('');
  const more = extra > 0 ? `<span class="text-muted">+${extra} more</span>` : '';
  return rows + more;
}

/**
 * Render the node footer: an optional row-count badge plus a status icon.
 *
 * @param {number|null} rowCount
 * @param {('error'|'ok'|null|undefined)} status
 * @returns {string}
 */
export function renderFooterHtml(rowCount, status) {
  const badge =
    rowCount != null
      ? `<span class="badge bg-secondary" title="rows from last preview">${escapeHtml(formatRowCount(rowCount))}</span>`
      : '';
  let statusIcon = '';
  if (status === 'error') {
    statusIcon = '<i class="bi bi-x-circle-fill text-danger" title="validation error"></i>';
  } else if (status === 'ok') {
    statusIcon = '<i class="bi bi-check-circle-fill text-success" title="validated"></i>';
  } else {
    statusIcon = '<i class="bi bi-circle text-muted" title="not yet validated"></i>';
  }
  return `${badge}${statusIcon}`;
}

/**
 * Humanise a row count (e.g. `1.2M rows`, `3.4k rows`, `42 rows`).
 *
 * @param {number|null} n
 * @returns {string}
 */
export function formatRowCount(n) {
  if (n == null) return '';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M rows`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k rows`;
  return `${n} rows`;
}

/**
 * Escape a string for safe interpolation into innerHTML.
 *
 * @param {*} s
 * @returns {string}
 */
export function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Generate a fresh canvas node id (`n-` + a short random suffix).
 *
 * @returns {string}
 */
export function generateNodeId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return 'n-' + crypto.randomUUID().slice(0, 12);
  }
  return 'n-' + Math.random().toString(36).slice(2, 14);
}

/**
 * One-line summary of a block's config, shown in the node body.
 *
 * @param {string} blockType
 * @param {Object} cfg
 * @returns {string}
 */
export function describeConfig(blockType, cfg) {
  if (!cfg) return '';
  switch (blockType) {
    case 'InputPort':
      return cfg.table_fqn
        ? `<code>${cfg.table_fqn}</code>`
        : '<em class="text-muted">no table</em>';
    case 'Filter':
      return cfg.predicate
        ? `<code>${cfg.predicate.slice(0, 40)}</code>`
        : '<em class="text-muted">no predicate</em>';
    case 'Project':
      return cfg.columns && cfg.columns.length > 0
        ? `${cfg.columns.length} col${cfg.columns.length === 1 ? '' : 's'}`
        : '<em class="text-muted">no columns</em>';
    case 'Join':
      return `${cfg.how || 'inner'} on ${(cfg.keys || []).join(', ') || '—'}`;
    case 'SemiJoin':
    case 'AntiJoin':
      return `on ${(cfg.keys || []).join(', ') || '—'}`;
    case 'Except':
      return 'left ∖ right';
    case 'Intersect':
      return 'left ∩ right';
    case 'Unnest':
      return cfg.column ? `<code>${cfg.column}</code>` : '<em class="text-muted">no column</em>';
    case 'FileInput':
      return cfg.path
        ? `<code>${cfg.path}</code> (${cfg.format || 'auto'})`
        : '<em class="text-muted">no path</em>';
    case 'FileOutput':
      return cfg.path
        ? `→ <code>${cfg.path}</code> (${cfg.format || 'parquet'})`
        : '<em class="text-muted">no path</em>';
    case 'GroupBy':
      return `by ${(cfg.keys || []).join(', ') || '—'}, ${(cfg.aggregations || []).length} agg`;
    case 'Limit':
      return `n = ${cfg.n}`;
    case 'SQL':
      return cfg.query
        ? `<code>${(cfg.query || '').slice(0, 36)}…</code>`
        : '<em class="text-muted">no query</em>';
    case 'OutputPort':
      return cfg.materialized_table
        ? `→ <code>${cfg.materialized_table}</code> (${cfg.mode || 'overwrite'})`
        : '<em class="text-muted">no target</em>';
    default:
      return '';
  }
}
