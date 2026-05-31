/**
 * Hardcoded SQL snippets exposed in the CodeMirror autocomplete
 * source so users can type a 3-letter prefix and Tab to expand a
 * common pattern.  Kept small + opinionated; per-user / per-workspace
 * snippet libraries are out of scope for v1.
 */

import { snippetCompletion } from '@codemirror/autocomplete';

export function buildSqlSnippetCompletions() {
  return [
    snippetCompletion('WITH ${1:name} AS (\n  SELECT *\n  FROM ${2:tbl}\n)\nSELECT * FROM ${1}', {
      label: 'cte',
      detail: 'WITH ... AS (...) SELECT',
      type: 'snippet',
    }),
    snippetCompletion('OVER (PARTITION BY ${1:col} ORDER BY ${2:col})', {
      label: 'win',
      detail: 'window OVER (PARTITION BY ... ORDER BY ...)',
      type: 'snippet',
    }),
    snippetCompletion('${1:SUM}(${2:col}) AS ${3:alias}', {
      label: 'agg',
      detail: 'SUM(col) AS alias',
      type: 'snippet',
    }),
    snippetCompletion('CASE WHEN ${1:cond} THEN ${2:val} ELSE ${3:val} END', {
      label: 'case',
      detail: 'CASE WHEN ... THEN ... ELSE ... END',
      type: 'snippet',
    }),
    snippetCompletion('LEFT JOIN ${1:tbl} ON ${2:cond}', {
      label: 'ljoin',
      detail: 'LEFT JOIN ... ON ...',
      type: 'snippet',
    }),
    snippetCompletion('INNER JOIN ${1:tbl} ON ${2:cond}', {
      label: 'ijoin',
      detail: 'INNER JOIN ... ON ...',
      type: 'snippet',
    }),
    snippetCompletion('GROUP BY ${1:col} HAVING ${2:cond}', {
      label: 'gbh',
      detail: 'GROUP BY ... HAVING ...',
      type: 'snippet',
    }),
    snippetCompletion('ORDER BY ${1:col} ${2:DESC} LIMIT ${3:100}', {
      label: 'olim',
      detail: 'ORDER BY ... LIMIT ...',
      type: 'snippet',
    }),
    snippetCompletion('UNNEST(${1:list_col}) AS ${2:flat}', {
      label: 'unnest',
      detail: 'UNNEST(list_col) AS flat',
      type: 'snippet',
    }),
    snippetCompletion('${1:col}::${2:TYPE}', {
      label: 'cast',
      detail: 'col::TYPE',
      type: 'snippet',
    }),
  ];
}
