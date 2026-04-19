// Phase 12.7 Sprint 75 Phase 2 — ESM bridge entrypoint.
//
// Loaded as ``<script type="module">`` from base.html, ordered BEFORE
// Alpine's CDN bundle.  ``type="module"`` scripts are defer-by-default
// and run in document order, so anything we register on ``window``
// inside this module is visible when Alpine's ``x-data`` walk begins.
//
// In Phase 2 this module is intentionally near-empty.  Its job is to
// exist as the canonical entry point that future phases migrate legacy
// IIFE-shape factories into — each migrated file will land as an
// ``export`` here and get re-attached to ``window`` so the templates'
// ``x-data="editable({...})"`` lookups keep working without having to
// be rewritten.
//
// Ordering invariant (enforced by scripts/check-frontend-bootstrap-order.sh):
//   bootstrap.js  <script type="module">   // this file
//   alpine.js     <script defer>           // CDN bundle
//
// If a consumer of ``window.pql*`` ever throws at first render, check
// the script-tag order in frontend/templates/base.html before blaming
// the consumer.
