/**
 * SQL editor — chart view, axis auto-pick, and persisted chart-config.
 *
 * Owns the chart card on the SQL editor: ``toggleView()`` between
 * table and chart modes, ``_autoPickAxes()`` heuristic that prefers a
 * non-numeric X + numeric Y, ``renderChart()`` Chart.js wiring for
 * bar / line / pie / scatter, ``downloadChartPng()`` export, and
 * the debounced ``PATCH /api/queries/{id}/chart-config`` that
 * persists the user's selection so a deep-link replay can seed the
 * same chart.
 *
 * Also owns ``seedFromHistory(id)`` because it's the chart-config
 * deep-link entry point — the editor's ``init()`` calls it when
 * ``?history_id=…`` is present in the URL.
 */

export const chartMethods = {
  toggleView() {
    if (!this.result) return;
    this.viewMode = this.viewMode === 'chart' ? 'table' : 'chart';
    if (this.viewMode === 'chart') {
      this._autoPickAxes();
      this.$nextTick(() => this.renderChart());
    } else {
      this.destroyChart();
    }
  },

  _autoPickAxes() {
    if (!this.result || !Array.isArray(this.result.columns)) return;
    if (this.chartConfig.x && this.chartConfig.y) return;
    const numericTypes = new Set([
      'INTEGER',
      'BIGINT',
      'SMALLINT',
      'TINYINT',
      'DOUBLE',
      'FLOAT',
      'REAL',
      'DECIMAL',
      'NUMERIC',
      'HUGEINT',
      'UINTEGER',
      'UBIGINT',
      'USMALLINT',
      'UTINYINT',
    ]);
    const cols = this.result.columns;
    const isNumeric = (c) => numericTypes.has((c.type || '').toUpperCase().split('(')[0]);
    let xIdx = null,
      yIdx = null;
    for (let i = 0; i < cols.length; i += 1) {
      if (xIdx === null && !isNumeric(cols[i])) xIdx = i;
      if (yIdx === null && isNumeric(cols[i])) yIdx = i;
    }
    if (xIdx === null) xIdx = 0;
    if (yIdx === null) yIdx = cols.length > 1 ? 1 : 0;
    if (!this.chartConfig.x) this.chartConfig.x = cols[xIdx].name;
    if (!this.chartConfig.y) this.chartConfig.y = cols[yIdx].name;
  },

  onChartConfigChange() {
    if (this.viewMode === 'chart') this.renderChart();
    this._scheduleChartSave();
  },

  _scheduleChartSave() {
    if (!this.currentHistoryId) return;
    if (this._chartSaveTimer) clearTimeout(this._chartSaveTimer);
    this._chartSaveTimer = setTimeout(() => {
      this._chartSaveTimer = null;
      this._persistChartConfig();
    }, 500);
  },

  async _persistChartConfig() {
    if (!this.currentHistoryId) return;
    const cfg = this._chartConfigPayload();
    await window.pqlApi.fetch(`/api/queries/${this.currentHistoryId}/chart-config`, {
      method: 'PATCH',
      body: { chart_config: cfg },
      silent: true,
    });
  },

  _chartConfigPayload() {
    if (!this.chartConfig.x || !this.chartConfig.y) return null;
    return {
      type: this.chartConfig.type || 'bar',
      x: this.chartConfig.x,
      y: this.chartConfig.y,
    };
  },

  destroyChart() {
    if (this._chartInstance) {
      try {
        this._chartInstance.destroy();
      } catch (e) {
        /* Chart.js can throw if canvas is gone */
      }
      this._chartInstance = null;
    }
  },

  renderChart() {
    if (!this.result || !window.Chart) return;
    if (!this.chartConfig.x || !this.chartConfig.y) return;
    const canvas = document.getElementById('pql-sql-chart-canvas');
    if (!canvas) return;
    const cols = this.result.columns || [];
    const xIdx = cols.findIndex((c) => c.name === this.chartConfig.x);
    const yIdx = cols.findIndex((c) => c.name === this.chartConfig.y);
    if (xIdx < 0 || yIdx < 0) return;
    this.destroyChart();
    const rows = this.result.rows || [];
    const type = this.chartConfig.type || 'bar';
    let data;
    if (type === 'scatter') {
      data = {
        datasets: [
          {
            label: `${this.chartConfig.y} vs ${this.chartConfig.x}`,
            data: rows.map((r) => ({ x: Number(r[xIdx]), y: Number(r[yIdx]) })),
          },
        ],
      };
    } else if (type === 'pie') {
      const buckets = new Map();
      for (const r of rows) {
        const key = r[xIdx] === null || r[xIdx] === undefined ? '(null)' : String(r[xIdx]);
        const val = Number(r[yIdx]);
        buckets.set(key, (buckets.get(key) || 0) + (Number.isFinite(val) ? val : 0));
      }
      data = {
        labels: [...buckets.keys()],
        datasets: [{ label: this.chartConfig.y, data: [...buckets.values()] }],
      };
    } else {
      data = {
        labels: rows.map((r) => String(r[xIdx] ?? '')),
        datasets: [
          {
            label: this.chartConfig.y,
            data: rows.map((r) => Number(r[yIdx])),
          },
        ],
      };
    }
    const chartType =
      type === 'scatter' ? 'scatter' : type === 'pie' ? 'pie' : type === 'line' ? 'line' : 'bar';
    this._chartInstance = new window.Chart(canvas, {
      type: chartType,
      data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: chartType === 'pie' || chartType === 'scatter' },
        },
      },
    });
  },

  downloadChartPng() {
    const canvas = document.getElementById('pql-sql-chart-canvas');
    if (!canvas || !this._chartInstance) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
      a.download = `pointlessql-chart-${stamp}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  },

  async seedFromHistory(historyId) {
    const res = await window.pqlApi.fetch(`/api/queries/${historyId}`, { silent: true });
    if (!res.ok || !res.data) return;
    this.currentHistoryId = historyId;
    if (res.data.chart_config) {
      try {
        const parsed =
          typeof res.data.chart_config === 'string'
            ? JSON.parse(res.data.chart_config)
            : res.data.chart_config;
        if (parsed && typeof parsed === 'object') {
          this.chartConfig = {
            type: parsed.type || 'bar',
            x: parsed.x || null,
            y: parsed.y || null,
          };
        }
      } catch (e) {
        /* malformed — ignore */
      }
    }
  },
};
