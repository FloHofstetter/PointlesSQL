// Shared widget renderers for the AI/BI dashboard view + editor.
//
// Data widgets (counter / table / chart) render from the
// ``{columns, rows, row_count, truncated}`` payload of the
// widget-data endpoints; markdown widgets render client-side through
// the escape-first inline_md helpers. ECharts loads lazily via a
// dynamic import so a CDN outage degrades to a visible inline notice
// instead of killing the page.

import { pqlApi } from '../../api.js';
import { renderInlineMd } from '../../inline_md.js';

const TABLE_DISPLAY_CAP = 100;

// el -> live echarts instance / ResizeObserver, so a re-render (params
// applied, widget edited) disposes the previous chart cleanly.
const charts = new WeakMap();
const observers = new WeakMap();

export function renderWidgetError(el, message) {
  disposeChart(el);
  el.innerHTML = '';
  const div = document.createElement('div');
  div.className = 'alert alert-warning small mb-0 py-1 px-2';
  div.textContent = message;
  el.appendChild(div);
}

// Minimal block-level pass over the inline renderer: headings, bullet
// lists, paragraphs. Every line goes through renderInlineMd, which
// HTML-escapes first, so no author markup survives un-sanitised.
export function renderMarkdownWidget(el, markdown) {
  const lines = String(markdown || '').split('\n');
  const blocks = [];
  let list = null;
  let paragraph = [];
  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push(`<p class="mb-2">${paragraph.join('<br>')}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      blocks.push(`<ul class="mb-2">${list.join('')}</ul>`);
      list = null;
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (!line.trim()) {
      flushParagraph();
      flushList();
    } else if (heading) {
      flushParagraph();
      flushList();
      const level = Math.min(heading[1].length + 4, 6);
      blocks.push(`<h${level}>${renderInlineMd(heading[2])}</h${level}>`);
    } else if (/^[-*]\s+/.test(line)) {
      flushParagraph();
      list = list || [];
      list.push(`<li>${renderInlineMd(line.replace(/^[-*]\s+/, ''))}</li>`);
    } else {
      flushList();
      paragraph.push(renderInlineMd(line));
    }
  }
  flushParagraph();
  flushList();
  el.innerHTML = blocks.join('');
}

function disposeChart(el) {
  const chart = charts.get(el);
  if (chart) {
    chart.dispose();
    charts.delete(el);
  }
  const obs = observers.get(el);
  if (obs) {
    obs.disconnect();
    observers.delete(el);
  }
}

function colIndex(columns, name, fallback) {
  const i = columns.findIndex((c) => c.name === name);
  return i >= 0 ? i : fallback;
}

function renderCounter(el, data) {
  el.innerHTML = '';
  const wrap = document.createElement('div');
  wrap.className = 'pql-bi-counter';
  const value = document.createElement('div');
  value.className = 'display-4 fw-semibold';
  const first = data.rows && data.rows.length ? data.rows[0][0] : null;
  value.textContent = typeof first === 'number' ? first.toLocaleString() : String(first ?? '—');
  wrap.appendChild(value);
  if (data.columns && data.columns.length) {
    const label = document.createElement('div');
    label.className = 'text-muted small';
    label.textContent = data.columns[0].name;
    wrap.appendChild(label);
  }
  el.appendChild(wrap);
}

function renderTable(el, data) {
  el.innerHTML = '';
  const table = document.createElement('table');
  table.className = 'table table-sm small mb-1';
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  for (const col of data.columns || []) {
    const th = document.createElement('th');
    th.textContent = col.name;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  const rows = (data.rows || []).slice(0, TABLE_DISPLAY_CAP);
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const cell of row) {
      const td = document.createElement('td');
      td.textContent = String(cell ?? '');
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  el.appendChild(table);
  if ((data.rows || []).length > TABLE_DISPLAY_CAP || data.truncated) {
    const note = document.createElement('div');
    note.className = 'text-muted small';
    note.textContent = `Showing first ${Math.min(rows.length, TABLE_DISPLAY_CAP)} of ${data.row_count} rows${data.truncated ? ' (server-truncated)' : ''}.`;
    el.appendChild(note);
  }
}

function buildChartOption(spec, data) {
  const columns = data.columns || [];
  const rows = data.rows || [];
  const xi = colIndex(columns, spec.x, 0);
  const yi = colIndex(columns, spec.y, columns.length > 1 ? 1 : 0);
  const type = spec.type || 'bar';
  const base = { backgroundColor: 'transparent' };
  if (type === 'pie') {
    return {
      ...base,
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: '70%',
          data: rows.map((r) => ({ name: String(r[xi]), value: r[yi] })),
        },
      ],
    };
  }
  if (type === 'scatter') {
    return {
      ...base,
      tooltip: { trigger: 'item' },
      xAxis: { type: 'value' },
      yAxis: { type: 'value' },
      series: [{ type: 'scatter', data: rows.map((r) => [r[xi], r[yi]]) }],
      grid: { left: 40, right: 16, top: 16, bottom: 28 },
    };
  }
  return {
    ...base,
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rows.map((r) => String(r[xi])) },
    yAxis: { type: 'value' },
    series: [
      {
        type: type === 'area' ? 'line' : type,
        areaStyle: type === 'area' ? {} : undefined,
        data: rows.map((r) => r[yi]),
      },
    ],
    grid: { left: 40, right: 16, top: 16, bottom: 28 },
  };
}

async function renderChart(el, widget, data) {
  let echarts;
  try {
    echarts = await import('echarts');
  } catch (e) {
    renderWidgetError(el, 'Chart library unavailable — check your network and reload.');
    return;
  }
  disposeChart(el);
  el.innerHTML = '';
  const dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
  const chart = echarts.init(el, dark ? 'dark' : null);
  chart.setOption(buildChartOption(widget.chart_spec || {}, data));
  charts.set(el, chart);
  const obs = new ResizeObserver(() => chart.resize());
  obs.observe(el);
  observers.set(el, obs);
}

export async function renderWidget(el, widget, data) {
  if (widget.kind === 'counter') {
    disposeChart(el);
    renderCounter(el, data);
  } else if (widget.kind === 'table') {
    disposeChart(el);
    renderTable(el, data);
  } else if (widget.kind === 'chart') {
    await renderChart(el, widget, data);
  } else {
    renderWidgetError(el, `Unknown widget kind: ${widget.kind}`);
  }
}

// Fetch one widget's data (markdown renders locally) and paint it
// into ``el``. ``dataUrl`` differs between the authenticated and the
// public-token paths, so callers pass it in.
export async function loadWidget(el, widget, dataUrl, values) {
  if (widget.kind === 'markdown') {
    renderMarkdownWidget(el, widget.markdown || '');
    return;
  }
  const res = await pqlApi.fetch(dataUrl, {
    method: 'POST',
    body: { params: values || {} },
    silent: true,
  });
  if (!res.ok) {
    renderWidgetError(el, res.error || 'Query failed.');
    return;
  }
  await renderWidget(el, widget, res.data);
}

// Refresh every widget that has a body element under ``root``.
export async function refreshWidgets(root, widgets, urlFor, values) {
  await Promise.all(
    widgets.map((w) => {
      const el = root.querySelector(`[data-widget-id="${w.id}"]`);
      if (!el) return Promise.resolve();
      return loadWidget(el, w, urlFor(w.id), values);
    })
  );
}
