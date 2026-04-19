// Phase 12.7 Sprint 75 — ESM bridge entrypoint.
//
// Loaded as ``<script type="module">`` from base.html, ordered BEFORE
// Alpine's CDN bundle.  ``type="module"`` scripts are defer-by-default
// and run in document order, so anything we register on ``window``
// inside this module is visible when Alpine's ``x-data`` walk begins.
//
// Each migrated factory is imported here as an ES module export and
// re-attached to ``window`` under the same name templates already use
// in their ``x-data="..."`` attributes — so migrating a file from
// IIFE-shape to ESM never requires touching template HTML.
//
// Ordering invariant (enforced by scripts/check-frontend-bootstrap-order.sh):
//   bootstrap.js  <script type="module">   // this file
//   alpine.js     <script defer>           // CDN bundle
//
// If a consumer of ``window.pql*`` ever throws at first render, check
// the script-tag order in frontend/templates/base.html before blaming
// the consumer.

import { editable } from './editable.js';
import { permissionsEditor } from './permissions_editor.js';
import { tagsEditor } from './tags_editor.js';
import { propertiesEditor, optionsEditor } from './properties_editor.js';

window.editable = editable;
window.permissionsEditor = permissionsEditor;
window.tagsEditor = tagsEditor;
window.propertiesEditor = propertiesEditor;
window.optionsEditor = optionsEditor;
