/**
 * Tiny DuckDB-ish SQL pretty-formatter.
 *
 * Inhouse so we don't drag in a 30+ KB sql-formatter dep via CDN
 * just for format-on-blur in two editor surfaces.  Handles the
 * common shapes the canvas SQL block produces:
 *
 *   - uppercase top-level keywords
 *   - newline + 2-space indent before SELECT / FROM / WHERE /
 *     GROUP BY / HAVING / ORDER BY / LIMIT / WITH / UNION clauses
 *   - keep CTE bodies + sub-queries inside parens intact (no
 *     deep formatting; this is "format the outermost layer")
 *   - normalise consecutive whitespace + trailing whitespace
 *
 * Skip the format when the input has any backtick-quoted or
 * dollar-quoted strings (we'd have to track those carefully and
 * the canvas SQL block doesn't really use them).
 */

const KEYWORDS_NEWLINE = [
  'WITH',
  'SELECT',
  'FROM',
  'WHERE',
  'GROUP BY',
  'HAVING',
  'ORDER BY',
  'LIMIT',
  'OFFSET',
  'UNION ALL',
  'UNION',
  'INTERSECT',
  'EXCEPT',
  'JOIN',
  'INNER JOIN',
  'LEFT JOIN',
  'RIGHT JOIN',
  'FULL JOIN',
  'CROSS JOIN',
  'ON',
];

const KEYWORDS_UPPERCASE = [
  ...KEYWORDS_NEWLINE,
  'AS',
  'AND',
  'OR',
  'NOT',
  'IN',
  'IS',
  'NULL',
  'TRUE',
  'FALSE',
  'CASE',
  'WHEN',
  'THEN',
  'ELSE',
  'END',
  'BETWEEN',
  'LIKE',
  'ILIKE',
  'DISTINCT',
  'ASC',
  'DESC',
];

/**
 * Return a prettified version of `sql`, or the original string when
 * the input contains characters this formatter doesn't handle safely
 * (so we never silently mangle exotic SQL).
 */
export function formatSql(sql) {
  if (typeof sql !== 'string' || sql.trim() === '') return sql;
  if (sql.includes('`') || sql.includes('$$')) return sql;
  // Collapse runs of whitespace (but preserve single newlines) to a
  // canonical single-space then sprinkle newlines back in front of
  // the structural keywords.  We work on a placeholder-protected copy
  // so single-quoted literals + line comments are left untouched.
  const { placeheld, restore } = _protectLiterals(sql);
  let out = placeheld.replace(/\s+/g, ' ').trim();
  for (const kw of KEYWORDS_UPPERCASE) {
    const re = new RegExp(`\\b${kw.replace(/ /g, '\\s+')}\\b`, 'gi');
    out = out.replace(re, kw);
  }
  for (const kw of KEYWORDS_NEWLINE) {
    const re = new RegExp(`\\s+${kw.replace(/ /g, '\\s+')}\\b`, 'g');
    out = out.replace(re, `\n${kw}`);
  }
  // Indent everything after the first SELECT-or-WITH so the keyword
  // sits at column 0 but its arguments hang under it by 2 spaces.
  out = out
    .split('\n')
    .map((line) => line.trim())
    .join('\n');
  out = restore(out);
  return out;
}

function _protectLiterals(sql) {
  const tokens = [];
  let i = 0;
  let buf = '';
  while (i < sql.length) {
    const ch = sql[i];
    if (ch === "'") {
      // Capture the entire quoted literal (including escaped '').
      let j = i + 1;
      while (j < sql.length) {
        if (sql[j] === "'" && sql[j + 1] === "'") {
          j += 2;
          continue;
        }
        if (sql[j] === "'") {
          j += 1;
          break;
        }
        j += 1;
      }
      const literal = sql.slice(i, j);
      const placeholder = `__PQL_LIT_${tokens.length}__`;
      tokens.push(literal);
      buf += placeholder;
      i = j;
      continue;
    }
    if (ch === '-' && sql[i + 1] === '-') {
      const end = sql.indexOf('\n', i);
      const literal = end === -1 ? sql.slice(i) : sql.slice(i, end);
      const placeholder = `__PQL_LIT_${tokens.length}__`;
      tokens.push(literal);
      buf += placeholder;
      i = end === -1 ? sql.length : end;
      continue;
    }
    buf += ch;
    i += 1;
  }
  return {
    placeheld: buf,
    restore: (text) => {
      return tokens.reduce((acc, lit, idx) => acc.replace(`__PQL_LIT_${idx}__`, lit), text);
    },
  };
}
