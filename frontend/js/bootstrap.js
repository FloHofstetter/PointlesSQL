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

// Singletons consumed by the editor factories below.  Imported first
// so the import graph resolves toast → api before the editors that
// depend on ``window.pqlApi`` evaluate.
import { pqlToast } from './toast.js';
import { pqlApi } from './api.js';

window.pqlToast = pqlToast;
window.pqlApi = pqlApi;

// Pure utility helpers — no Alpine factories, but used directly from
// templates as ``x-text="pqlRelativeTime(iso)"`` etc.
import { pqlParseServerIso, pqlRelativeTime } from './relative_time.js';
import { pqlHumanizeCron } from './humanize_cron.js';

window.pqlParseServerIso = pqlParseServerIso;
window.pqlRelativeTime = pqlRelativeTime;
window.pqlHumanizeCron = pqlHumanizeCron;

// Inline-editor factories (Phase 3).
import { editable } from './editable.js';
import { permissionsEditor } from './permissions_editor.js';
import { tagsEditor } from './tags_editor.js';
import { propertiesEditor, optionsEditor } from './properties_editor.js';

window.editable = editable;
window.permissionsEditor = permissionsEditor;
window.tagsEditor = tagsEditor;
window.propertiesEditor = propertiesEditor;
window.optionsEditor = optionsEditor;

// Federation create-forms + delete-confirm (Phase 4).  Sprint 92
// split federation.js into three sibling modules; bootstrap.js
// imports from each directly so the window-name surface stays
// identical without an extra façade layer.
import { createConnectionForm } from './federation_connections.js';
import {
    createCredentialForm,
    createExternalLocationForm,
} from './federation_credentials.js';
import {
    createForeignCatalogForm,
    deleteConfirm,
} from './federation_catalogs.js';

window.createConnectionForm = createConnectionForm;
window.createExternalLocationForm = createExternalLocationForm;
window.createCredentialForm = createCredentialForm;
window.createForeignCatalogForm = createForeignCatalogForm;
window.deleteConfirm = deleteConfirm;

// List table + job-row hover actions + SQL editor (Phase 4).
import { listTable } from './list_table.js';
import { jobRowActions } from './job_row_actions.js';
import { sqlEditor } from './sql_editor.js';

window.listTable = listTable;
window.jobRowActions = jobRowActions;
window.sqlEditor = sqlEditor;

// Cmd+K command palette (Sprint 92 lifted out of the partial's
// inline <script>; bootstrap.js re-attaches the factory under
// the same window name so the partial's x-data="commandPalette()"
// keeps working unchanged).
import { commandPalette } from './components/command_palette.js';

window.commandPalette = commandPalette;
