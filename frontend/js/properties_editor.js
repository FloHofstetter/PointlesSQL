// ES-module shape; window registration via
// bootstrap.js.  The shared dict-editor state machine that backs both
// propertiesEditor and optionsEditor lives in editor_base.js as
// ``createDictEditor`` (promoted out of the earlier private
// ``_makeDictEditor`` helper).
import { createDictEditor } from './editor_base.js';

export function optionsEditor({ patchUrl, initial }) {
  return createDictEditor('options', patchUrl, initial);
}

export function propertiesEditor({ patchUrl, initial }) {
  return createDictEditor('properties', patchUrl, initial);
}
