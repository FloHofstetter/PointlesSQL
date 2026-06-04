/**
 * Data-product detail-page Alpine factory.
 *
 * Owns the tab-driven lazy-load state for a single data product —
 * Overview/Schema/Discussion/Reviews/Activity/Lineage/Diff/Readme —
 * plus DP-level reactions, follow state, comment threads with replies,
 * 1-5-star reviews, schema-change proposals, README edit + diff,
 * Cytoscape lineage render, and the contributor heatmap.
 *
 * Lifted from the inline ``<script>`` block in
 * ``pages/_partials/data_product/scripts.html``. ``bootstrap.js``
 * re-attaches the factory to ``window.dataProductDetail`` so the
 * existing template ``x-data='dataProductDetail({{ product|tojson }},
 * {ctx…})'`` resolves unchanged.
 *
 * The component surface is composed from focused mixin installers under
 * ``data_product/`` (state, lifecycle, schema, content, social, ask,
 * access, insights).  The derived views stay as native getters on the
 * instance below so Alpine reads them as reactive computed properties.
 */

import { installDpLifecycle } from './data_product/lifecycle.js';
import { installDpSchema } from './data_product/schema.js';
import { installDpContent } from './data_product/content.js';
import { installDpSocial } from './data_product/social.js';
import { installDpAsk } from './data_product/ask.js';
import { installDpAccess } from './data_product/access.js';
import { installDpInsights } from './data_product/insights.js';
import { installDpState } from './data_product/state.js';

export function dataProductDetail(product, ctx) {
  ctx = ctx || {};
  const obj = {

    get canEditReadme() {
      return this.isAdmin || this.isSteward;
    },

    // derived computed surfaces -----------------------

    get healthBand() {
      const b = (this.detail && this.detail.badges) || {};
      const fresh = b.freshness_on_time_30d_pct;
      const rollbackPassed = b.last_rollback_passed;
      let status = 'unknown';
      let label = 'No telemetry yet';
      if (fresh !== null && fresh !== undefined) {
        if (fresh >= 95 && rollbackPassed !== false) {
          status = 'green';
          label = 'Healthy';
        } else if (fresh >= 75) {
          status = 'yellow';
          label = 'Degraded freshness';
        } else {
          status = 'red';
          label = 'Freshness below threshold';
        }
        if (rollbackPassed === false) {
          status = 'red';
          label = 'Last rollback failed';
        }
      }
      return {
        status,
        label,
        freshness_pct: fresh,
        downstream: b.downstream_count || 0,
        agent_runs_7d: b.agent_run_count_7d || 0,
        sla_minutes: this.product.sla_minutes,
      };
    },

    get firstSchemaTable() {
      if (!this.detail || !this.detail.tables || this.detail.tables.length === 0) {
        return null;
      }
      return this.detail.tables[0];
    },

    get schemaPreviewColumns() {
      const t = this.firstSchemaTable;
      if (!t || !t.columns) return [];
      return t.columns.slice(0, 10);
    },

    get consumeSnippets() {
      const t = this.firstSchemaTable;
      const fqn = t
        ? this.product.catalog + '.' + this.product.schema + '.' + t.name
        : this.product.catalog + '.' + this.product.schema + '.<table>';
      return {
        pql: 'from pointlessql import PQL\npql = PQL()\ndf = pql.read_table("' + fqn + '")',
        sql: 'SELECT *\nFROM ' + fqn + '\nLIMIT 100;',
        python:
          'import pandas as pd\nfrom pointlessql import PQL\ndf = pql.read_table("' +
          fqn +
          '")\nprint(df.head())',
      };
    },

    get openProposals() {
      return (this.proposals || []).filter((p) => p.status === 'open');
    },

    get sortedReviews() {
      const arr = (this.reviews || []).slice();
      if (this.reviewSort === 'stars-desc') {
        arr.sort((a, b) => b.stars - a.stars);
      } else if (this.reviewSort === 'stars-asc') {
        arr.sort((a, b) => a.stars - b.stars);
      } else {
        arr.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
      }
      return arr;
    },

    get topLevelComments() {
      return (this.comments || []).filter((c) => c.parent_comment_id === null);
    }
  };

  installDpState(obj, product, ctx);
  installDpLifecycle(obj);
  installDpSchema(obj);
  installDpContent(obj);
  installDpSocial(obj);
  installDpAsk(obj);
  installDpAccess(obj);
  installDpInsights(obj);
  return obj;
}
