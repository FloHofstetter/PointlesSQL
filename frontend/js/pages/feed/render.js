/**
 * Feed page — Row presentation helpers — icons, labels, classes, avatars, markdown.
 *
 * One slice of the ``feedPage`` Alpine factory.  ``installFeedRender`` mutates
 * the shared component object in place (the project's mixin-installer
 * pattern, mirroring ``installFeedSocial``); ``this`` resolves to the live
 * component at call time, so the method bodies are unchanged from the
 * original single-file factory.
 */

import { avatarFor } from '../../avatars.js';
import { renderInlineMd } from '../../inline_md.js';

// Icon + label maps share the entity-kind keys with the server-side
// registry. Kept inline because the registry's Python config doesn't
// yet emit a JSON consumable.
const KIND_ICONS = {
  dp: 'bi-collection',
  table: 'bi-table',
  model: 'bi-cpu',
  branch: 'bi-bezier2',
  run: 'bi-robot',
  schema: 'bi-diagram-3',
  catalog: 'bi-archive',
  notebook: 'bi-journal-code',
  saved_query: 'bi-code-square',
  issue: 'bi-bug',
  workspace: 'bi-building',
  notification: 'bi-bell',
  comment: 'bi-chat-left-text',
  review: 'bi-star',
  notebook_revision: 'bi-pin-angle-fill',
  notebook_cell_output: 'bi-pin-angle-fill',
};
const KIND_LABELS = {
  dp: 'Data Product',
  table: 'Table',
  model: 'Model',
  branch: 'Branch',
  run: 'Run',
  schema: 'Schema',
  catalog: 'Catalog',
  notebook: 'Notebook',
  saved_query: 'Saved query',
  issue: 'Issue',
  workspace: 'Workspace',
  notification: 'Update',
  comment: 'Comment',
  review: 'Review',
  notebook_revision: 'Pinned revision',
  notebook_cell_output: 'Pinned cell',
};
// Entity kinds whose ``entity_ref`` is an opaque UUID with no
// standalone display value — the summary already names the parent
// surface, so the header line skips the link label and lets the
// kind badge carry the affordance.
const HIDE_ENTITY_REF_KINDS = new Set(['notebook_revision', 'notebook_cell_output']);
// Entity kinds whose ``entity_ref`` is an internal id (a user PK, an
// agent-review id, …) that means nothing on its own — the summary line
// already names the thing, so the object link is suppressed.
const OPAQUE_REF_KINDS = new Set(['user', 'review']);
// Short uppercase lane labels for system-led rows (rows with no human
// actor). Reads as "DATA HEALTH · demo.hr" instead of a fake bold name.
const LANE_EYEBROWS = {
  data_health: 'Data health',
  pipeline: 'Pipeline',
  approval: 'Approval',
  agent_run: 'Agent run',
  badge_award: 'Achievement',
  issue: 'Issue',
  branch: 'Governance',
  fact: 'Pinned',
};

export function installFeedRender(state) {
  Object.assign(state, {
    iconForKind(kind) {
      return KIND_ICONS[kind] || 'bi-circle';
    },
    kindLabel(kind) {
      return KIND_LABELS[kind] || kind;
    },

    // Item-level helpers.
    itemClasses(r) {
      const rk = r.render_kind || r.kind;
      return {
        'pql-feed-item--unread': r.kind === 'notification' && !r.read_at,
        'pql-feed-item--mention': rk === 'mention',
        'pql-feed-item--comment': rk === 'comment',
        'pql-feed-item--review': rk === 'review',
        'pql-feed-item--agent-run': rk === 'agent_run',
        'pql-feed-item--badge': rk === 'badge_award',
        'pql-feed-item--issue': rk === 'issue',
        'pql-feed-item--branch': rk === 'branch',
        'pql-feed-item--approval': rk === 'approval',
        'pql-feed-item--data-health': rk === 'data_health',
        'pql-feed-item--pipeline': rk === 'pipeline',
        'pql-feed-item--sev-warn': r.severity === 'warn',
        'pql-feed-item--sev-error': r.severity === 'error',
        'pql-feed-item--resolved': !!r._resolved,
        'pql-feed-item--fresh': !!r._fresh,
      };
    },

    // A row is "person-led" when a human/agent name owns the headline
    // (comments, reviews, mentions, branch promotions, agent runs, and
    // approvals once the principal resolves to a display name). System-led
    // rows (data-health, pipeline, badges, bare notifications) carry no
    // actor and render as a lane eyebrow + object instead of a fake name.
    isPersonLed(r) {
      return !!r.actor_display_name;
    },

    // Avatar descriptor for the header — a coloured-initials disc for
    // people, a lane-tinted glyph for system events. Consumed by the
    // template's ``rowAvatar`` binding.
    rowAvatar(r) {
      if (this.isPersonLed(r)) {
        return avatarFor({ name: r.actor_display_name, id: r.actor_user_id });
      }
      return avatarFor({
        kind: r.render_kind || r.kind,
        severity: r.severity,
        icon: this.avatarIcon(r),
      });
    },

    // Bootstrap icon for a system row's glyph avatar.
    avatarIcon(r) {
      const rk = r.render_kind || r.kind;
      if (rk === 'agent_run') return 'bi-robot';
      if (rk === 'approval') return 'bi-shield-check';
      if (rk === 'data_health') return 'bi-heart-pulse';
      if (rk === 'pipeline') return 'bi-diagram-2';
      if (rk === 'badge_award') return 'bi-award-fill';
      if (rk === 'issue') return 'bi-bug';
      if (rk === 'branch') return 'bi-bezier2';
      return this.iconForKind(r.entity_kind || r.kind);
    },

    // Short lane label shown before the object on system-led rows.
    laneEyebrow(r) {
      return LANE_EYEBROWS[r.render_kind || r.kind] || 'Update';
    },

    // Concise screen-reader label for the whole card — "who verb object".
    cardAria(r) {
      const who = r.actor_display_name || this.laneEyebrow(r);
      return [who, this.verbLabel(r), this.entityLinkLabel(r)].filter(Boolean).join(' ');
    },

    // Verb connecting a person to the object on person-led rows.
    verbLabel(r) {
      const rk = r.render_kind || r.kind;
      if (rk === 'comment') return 'commented on';
      if (rk === 'review') return 'reviewed';
      if (rk === 'mention') return 'mentioned you in';
      if (rk === 'agent_run') {
        return r.event_type && r.event_type.endsWith('.failed') ? 'failed on' : 'completed on';
      }
      if (rk === 'approval') return 'needs your approval on';
      if (rk === 'branch') return this.branchVerb(r.event_type).toLowerCase();
      if (rk === 'issue') return this.issueBadgeLabel(r.event_type).toLowerCase();
      if (rk === 'badge_award') return 'earned';
      if (rk === 'fact') return 'pinned';
      return '';
    },

    // Human-friendly object label — shortens opaque run UUIDs and hides
    // internal-id refs (user PK, review id) that mean nothing alone.
    entityLinkLabel(r) {
      const kind = r.entity_kind;
      const ref = r.entity_ref;
      if (kind && HIDE_ENTITY_REF_KINDS.has(kind)) return '';
      if (!ref) return kind ? this.kindLabel(kind) : '';
      if (kind === 'run') return 'run ' + String(ref).slice(0, 8);
      if (OPAQUE_REF_KINDS.has(kind)) return '';
      return String(ref);
    },

    // Whether to render the object link at all (suppressed for opaque
    // refs the friendly-label step blanks out).
    showObjectLink(r) {
      return !!this.entityLinkLabel(r);
    },

    // Inline-markdown → safe HTML for summary / body strings, so
    // ``**bold**`` and ``[links](…)`` render instead of showing markers.
    mdInline(s) {
      return renderInlineMd(s || '');
    },

    // Expand / collapse a clamped comment or review snippet.
    toggleSnippet(r) {
      r._expanded = !r._expanded;
    },

    // Icon for a severity-bearing status chip — paired with colour so
    // severity is glanceable, not communicated by colour alone.
    sevIcon(severity) {
      if (severity === 'error') return 'bi-x-octagon';
      if (severity === 'warn') return 'bi-exclamation-triangle';
      return 'bi-check-circle';
    },

    issueBadgeClass(eventType) {
      if (!eventType) return 'text-bg-secondary';
      if (eventType.endsWith('.opened')) return 'text-bg-success';
      if (eventType.endsWith('.closed')) return 'text-bg-secondary';
      if (eventType.endsWith('.resolved')) return 'text-bg-primary';
      return 'text-bg-secondary';
    },

    issueBadgeLabel(eventType) {
      if (!eventType) return 'Issue';
      if (eventType.endsWith('.opened')) return 'Opened';
      if (eventType.endsWith('.closed')) return 'Closed';
      if (eventType.endsWith('.resolved')) return 'Resolved';
      return 'Updated';
    },

    branchVerb(eventType) {
      if (!eventType) return 'Branch';
      if (eventType.endsWith('.created')) return 'Created';
      if (eventType.endsWith('.promoted')) return 'Promoted';
      if (eventType.endsWith('.discarded')) return 'Discarded';
      return 'Updated';
    },
  });
}
