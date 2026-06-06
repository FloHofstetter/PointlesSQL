/*
 * DataFrame Studio — Alpine factory (composition root).
 *
 * A thin adapter over the shared Drawflow canvas shell
 * (``canvas/compose.js#assembleCanvasEditor``): it supplies the Studio
 * catalog (the data-product dataframe blocks minus sinks / DataProduct),
 * reuses the data-product config-form bundle + partials verbatim, and adds
 * Studio-only behaviour (compile / preview / emit) instead of the DP
 * save / materialise / version paths.
 *
 * The graph compiles to a governed SELECT through
 * ``/api/dataframe-studio/*`` and is emitted to a notebook cell or the
 * clipboard — there is no UC materialise and no version ledger.
 */

import { assembleCanvasEditor, genericEditorState } from '../canvas/compose.js';
import { configFormStructuredMethods } from '../canvas/config_form_structured.js';
import { buildStudioCatalog } from '../dataframe_studio/catalog.js';
import { studioLifecycleMethods } from '../dataframe_studio/lifecycle.js';
import { studioPersistenceMethods } from '../dataframe_studio/persistence.js';
import { configFormMethods } from '../dp_canvas/editor/config_form.js';

const STUDIO_BUNDLES = [
  configFormMethods,
  configFormStructuredMethods,
  studioPersistenceMethods,
  studioLifecycleMethods,
];

function studioEditorState() {
  const catalog = buildStudioCatalog();
  return {
    ...genericEditorState(),

    // The Studio is single-user authoring — always writable.
    canWrite: true,
    paletteGroups: catalog.paletteGroups,

    // Config-form input buffers the reused DP config forms bind to.
    projectInput: '',
    joinKeyInput: '',
    semiJoinKeyInput: '',
    antiJoinKeyInput: '',
    groupKeyInput: '',
    mergeOnInput: '',
    renameRowsBuf: [],

    // Studio output surfaces.
    compiledSql: '',
    compiledColumns: [],
    compileError: null,
    copyState: 'idle',

    previewOpen: false,
    previewBusy: false,
    previewLimit: 100,
    previewResult: null,
    previewError: null,
  };
}

export function dataframeStudio(ctx) {
  return assembleCanvasEditor(
    {
      catalog: buildStudioCatalog(),
      bundles: STUDIO_BUNDLES,
      state: () => studioEditorState(),
      caps: { hasPreview: true, hasSchemaFlow: true },
    },
    ctx
  );
}
