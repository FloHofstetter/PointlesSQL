/**
 * Data-product detail page — reactive data fields.
 *
 * One slice of the ``dataProductDetail`` Alpine factory.  ``installDpState``
 * seeds every reactive field on the shared component object from the
 * server-rendered ``product`` + ``ctx`` payload.
 */

export function installDpState(state, product, ctx) {
  Object.assign(state, {
    product: product,
    currentUserId: ctx.current_user_id || 0,
    isAdmin: !!ctx.is_admin,
    isSteward: !!ctx.is_steward,
    detail: null,
    diff: null,
    diffLoading: false,
    diffError: null,
    lineageLoaded: false,
    lineageEmpty: false,
    activity: [],
    activityLoaded: false,
    activityTotal: null,
    comments: [],
    commentsLoaded: false,
    commentsTotal: null,
    newCommentDraft: '',
    // category for the next top-level comment.
    newCommentCategory: 'general',
    // DP-level reactions, keyed by emoji.
    dpReactions: {},
    replyingTo: null,
    replyDraft: '',
    reviews: [],
    reviewsLoaded: false,
    reviewSummary: null,
    myReview: null,
    reviewDraftStars: 0,
    reviewDraftBody: '',
    reviewSort: 'recent',
    following: false,
    followersCount: 0,
    readme: null,
    readmeLoaded: false,
    readmeHistory: [],
    editingReadme: false,
    readmeDraft: '',
    historyOpen: false,
    diffFrom: null,
    diffTo: null,
    diffText: '',
    // auto-generated system passport.
    passport: null,
    passportLoaded: false,
    // related products from cooccurrence cache.
    related: [],
    relatedLoaded: false,
    // open schema-change proposals.
    proposals: [],
    proposalsLoaded: false,
    // "Ask this data product" panel — DP-scoped Lens chat.
    askOpened: false,
    askLoading: false,
    askConfigured: true,
    askError: null,
    askSessionId: null,
    askInput: '',
    askThinking: false,
    askMessages: [],
    // Self-service access state for the Data tab.
    accessStatus: null,
    accessRequests: [],
    accessBusy: false,
    accessNote: '',

    // consumer "Data" tab — meaning-first column view + sample rows.

    // Per-table preview payloads, lazily fetched from the shared
    // catalog-preview endpoint (which masks classified columns
    // server-side, so what shows here already honours governance).
    samples: {},
    sampleOpen: {},
    sampleLoading: {},

    // forks (active branches off this DP's schema).

    forks: [],
    forksLoaded: false,

    // Contributor heatmap.

    heatmap: { cells: [], total: 0 },
    heatmapLoaded: false,
  });
}
