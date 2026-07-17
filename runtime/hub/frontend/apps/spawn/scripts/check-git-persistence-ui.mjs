import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(scriptDir, '../src/App.tsx'), 'utf8');

function assertMatch(description, pattern) {
  if (!pattern.test(appSource)) {
    throw new Error(`Missing spawn git persistence UI contract: ${description}`);
  }
  console.log(`${description}=ok`);
}

assertMatch(
  'checkbox_visibility_requires_selected_resource_git_clone_and_admin_choice',
  /const showRepoPersistenceChoice = Boolean\(selectedResource && allowGitClone && allowPersistenceChoice\);/
);
assertMatch(
  'default_checked_state_follows_admin_default',
  /const repoPersistValue = repoPersist \?\? defaultPersistence;/
);
assertMatch(
  'default_checked_state_resyncs_after_config_load',
  /setRepoPersist\(defaultPersistence\);/
);
assertMatch(
  'checkbox_checked_state_uses_resolved_value',
  /checked=\{repoPersistValue\}/
);
assertMatch(
  'checkbox_label_text_is_exact',
  />Keep this repository after the server stops</
);
assertMatch(
  'checkbox_help_text_is_exact',
  />\s*If enabled, an existing repository folder will be reused and not overwritten\.\s*</
);
assertMatch(
  'hidden_repo_persist_field_tracks_resolved_value_for_git_clone_resources',
  /\{allowGitClone && <input type="hidden" name="repo_persist" value=\{repoPersistValue \? 'true' : 'false'\} \/>\}/
);
assertMatch(
  'checkbox_toggle_updates_hidden_field_source_state',
  /onChange=\{e => setRepoPersist\(e\.target\.checked\)\}/
);

console.log('spawn_git_persistence_ui_source_check=ok');
