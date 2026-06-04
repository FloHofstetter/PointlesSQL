/**
 * Feed page — Reactive data fields for the feed page Alpine component.
 *
 * One slice of the ``feedPage`` Alpine factory.  ``installFeedState`` mutates
 * the shared component object in place (the project's mixin-installer
 * pattern, mirroring ``installFeedSocial``); ``this`` resolves to the live
 * component at call time, so the method bodies are unchanged from the
 * original single-file factory.
 */

export function installFeedState(state, isAdmin) {
  Object.assign(state, {
    isAdmin: !!isAdmin,
    loaded: false,
    filter: 'all',
    kindFilter: [],
    searchDraft: '',
    rows: [],
    bufferedRows: [],
    newCount: 0,
    density: 'comfortable',
    connState: 'disconnected',
    trending: [],
    people: [],
    savedSearches: [],

    // Triage state — the "needs you" inbox + the ambient seen-cursor.
    // ``focusMode`` collapses the stream so the inbox can be drained to
    // zero; the counts + ``caughtUp`` come from the /api/feed response
    // and drive the zone header, the caught-up divider, and the badge.
    focusMode: false,
    needsActionCount: 0,
    unreadForYouCount: 0,
    unseenCount: 0,
    caughtUp: false,
    seenAt: null,

    // Coarse lane slice over the unified stream. Sits above the
    // social ``filters`` axis below; the two compose (category narrows
    // by event lane, filter narrows by audience).
    category: 'all',
    categoryCounts: {},
    categories: [
      { key: 'all', label: 'All', icon: 'bi-grid' },
      { key: 'approval', label: 'Approvals', icon: 'bi-shield-check' },
      { key: 'health', label: 'Data health', icon: 'bi-heart-pulse' },
      { key: 'social', label: 'Social', icon: 'bi-chat-dots' },
      { key: 'pipeline', label: 'Pipeline', icon: 'bi-diagram-2' },
      { key: 'governance', label: 'Governance', icon: 'bi-bank' },
    ],

    filters: [
      { key: 'all', label: 'For you', icon: 'bi-stars' },
      { key: 'mentions', label: 'Mentions', icon: 'bi-at' },
      { key: 'my', label: 'My activity', icon: 'bi-person' },
      { key: 'followed_users', label: 'Following', icon: 'bi-people' },
    ],
    kindOptions: [
      { key: 'dp', label: 'Data Products', icon: 'bi-collection' },
      { key: 'table', label: 'Tables', icon: 'bi-table' },
      { key: 'model', label: 'Models', icon: 'bi-cpu' },
      { key: 'branch', label: 'Branches', icon: 'bi-bezier2' },
      { key: 'run', label: 'Runs', icon: 'bi-robot' },
      { key: 'schema', label: 'Schemas', icon: 'bi-diagram-3' },
      { key: 'catalog', label: 'Catalogs', icon: 'bi-archive' },
      { key: 'notebook', label: 'Notebooks', icon: 'bi-journal-code' },
      { key: 'saved_query', label: 'Queries', icon: 'bi-code-square' },
      { key: 'issue', label: 'Issues', icon: 'bi-bug' },
    ],
    densityOptions: [
      { key: 'comfortable', label: 'Comfortable', icon: 'bi-list-ul' },
      { key: 'compact', label: 'Compact', icon: 'bi-list' },
      { key: 'headlines', label: 'Headlines', icon: 'bi-text-left' },
    ],

    // Internal SSE state (not reactive — Alpine doesn't need to
    // observe these).
    _sse: null,
    _sseBackoffMs: 1000,
    _sseReconnectTimer: null,
    _sseFirstFailedAt: 0
  });
}
