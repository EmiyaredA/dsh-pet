"""Fail-closed authorization checks; fixtures never touch the real pet library."""
import copy
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from kurisu_spec_revisions import sample_batch_decision, spec_fingerprint
from kurisu_iteration_policy import correction_usage, iteration_decision
from kurisu_quotas import counts
import revise_kurisu_steins_props as revision
from test_kurisu_spec_revisions import fixture as historical_fixture

OLD_SPEC = 'programmer-research-v2-2026-10-31'
NEW_SPEC = 'steins-props-v3-2026-10-31'
DIRECT_IDS = ['a032', 'a035', 'a036', 'a037', 'a038', 'a043',
              'a044', 'a047', 'a049', 'a050', 'a055', 'a057']


def direct_fixture():
    old_state, _ = old_sample_fixture()
    rows = [{
        'id': aid, 'name': '新道具动作-' + aid,
        'direction': 'Use the approved prop for ' + aid + ' then stow it.',
        'props': ['named prop ' + aid], 'spec_revision_id': NEW_SPEC,
        'status': 'planned', 'attempts': [],
    } for aid in DIRECT_IDS]
    gate = {
        'gate_type': 'direct_human_scope', 'spec_revision_id': NEW_SPEC,
        'enabled': True, 'batch_released': True, 'action_ids': list(DIRECT_IDS),
        'sample_action_ids': [], 'sample_decisions': {},
        'user_approval': {'approved': True, 'source': 'user',
                          'spec_revision_id': NEW_SPEC,
                          'user_quote': '按这十二项道具新规格继续。'},
        'spec_fingerprints': {row['id']: spec_fingerprint(row) for row in rows},
    }
    old_state['actions'].extend(rows)
    old_state['spec_batch_gates'][NEW_SPEC] = gate
    return old_state, rows[0], gate


def old_sample_fixture():
    """A released old gate with both exact current-SHA approvals."""
    samples = []
    decisions = {}
    for aid, digit in [('a034', '4'), ('a052', '5')]:
        sha = digit * 64
        samples.append({
            'id': aid, 'name': 'sample-' + aid, 'status': 'approved',
            'spec_revision_id': OLD_SPEC, 'sha256': sha,
            'spec_revision': {'baseline_attempt_count': 1},
            'attempts': [
                {'spec_revision_id': 'historical-spec'},
                {'spec_revision_id': OLD_SPEC, 'spec_action_name': 'sample-' + aid},
            ],
        })
        decisions[aid] = {
            role: {'approved': True, 'source': role,
                   'spec_revision_id': OLD_SPEC, 'sha256': sha,
                   **({'user_quote': 'Accept this exact sample'} if role == 'user'
                      else {'review_file': 'quality/current-' + aid + '.json'})}
            for role in ('user', 'assistant')
        }
    target = {'id': 'a030', 'spec_revision_id': OLD_SPEC, 'attempts': []}
    state = {'actions': samples + [target], 'spec_batch_gates': {
        OLD_SPEC: {'spec_revision_id': OLD_SPEC, 'enabled': True,
                   'sample_action_ids': ['a034', 'a052'],
                   'batch_released': True, 'sample_decisions': decisions},
    }}
    return state, target


class OldSampleGateRegressionTests(unittest.TestCase):
    def test_both_exact_current_sha_proofs_still_release_old_gate(self):
        state, action = old_sample_fixture()
        before = copy.deepcopy(state)
        self.assertTrue(sample_batch_decision(state, action)['allowed'])
        self.assertEqual(state, before)

    def test_each_sample_role_sha_is_independently_required(self):
        for aid in ('a034', 'a052'):
            for role in ('user', 'assistant'):
                with self.subTest(sample=aid, role=role):
                    state, action = old_sample_fixture()
                    state['spec_batch_gates'][OLD_SPEC]['sample_decisions'][aid][role]['sha256'] = 'f' * 64
                    self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_each_old_proof_requires_its_own_role_revision_and_evidence(self):
        for aid in ('a034', 'a052'):
            for role in ('user', 'assistant'):
                evidence_key = 'user_quote' if role == 'user' else 'review_file'
                for key, value in [('approved', False), ('source', 'other'),
                                   ('spec_revision_id', 'old'), (evidence_key, '')]:
                    with self.subTest(sample=aid, role=role, key=key):
                        state, action = old_sample_fixture()
                        state['spec_batch_gates'][OLD_SPEC]['sample_decisions'][aid][role][key] = value
                        self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_old_gate_cannot_reuse_approved_historical_samples(self):
        for aid in ('a034', 'a052'):
            for mutation in ('revision', 'attempt_name', 'historical_baseline', 'status'):
                with self.subTest(sample=aid, mutation=mutation):
                    state, action = old_sample_fixture()
                    sample = next(a for a in state['actions'] if a['id'] == aid)
                    if mutation == 'revision':
                        sample['spec_revision_id'] = 'historical-spec'
                    elif mutation == 'attempt_name':
                        sample['attempts'][-1]['spec_action_name'] = 'stale name'
                    elif mutation == 'historical_baseline':
                        sample['spec_revision']['baseline_attempt_count'] = 0
                    else:
                        sample['status'] = 'candidate_ready'
                    self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_closed_old_batch_stays_closed_even_with_valid_sample_decisions(self):
        state, action = old_sample_fixture()
        state['spec_batch_gates'][OLD_SPEC]['batch_released'] = False
        self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_relabelling_old_gate_direct_cannot_bypass_its_double_sha_hold(self):
        state, action = old_sample_fixture()
        gate = state['spec_batch_gates'][OLD_SPEC]
        gate['sample_decisions'].clear()
        gate['gate_type'] = 'direct_human_scope'
        gate['user_approval'] = {'approved': True, 'source': 'user',
                                 'spec_revision_id': OLD_SPEC, 'user_quote': 'continue'}
        self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_valid_new_scope_does_not_release_closed_old_gate(self):
        state, _, _ = direct_fixture()
        old_target = next(a for a in state['actions'] if a['id'] == 'a030')
        state['spec_batch_gates'][OLD_SPEC]['sample_decisions'].clear()
        self.assertFalse(sample_batch_decision(state, old_target)['allowed'])


class DirectHumanScopeTests(unittest.TestCase):
    def test_exact_named_twelve_scope_releases_every_member_without_mutation(self):
        state, _, _ = direct_fixture()
        before = copy.deepcopy(state)
        for aid in DIRECT_IDS:
            action = next(a for a in state['actions'] if a['id'] == aid)
            self.assertTrue(sample_batch_decision(state, action)['allowed'], aid)
        self.assertEqual(state, before)
        for aid in ('a034', 'a052'):
            self.assertEqual(next(a for a in state['actions'] if a['id'] == aid),
                             next(a for a in before['actions'] if a['id'] == aid))

    def test_release_flags_require_actual_true_and_exact_revision(self):
        for key, values in [('enabled', [False, 1, 'true', None]),
                            ('batch_released', [False, 1, 'true', None]),
                            ('spec_revision_id', [OLD_SPEC, '', None]),
                            ('gate_type', ['direct_human', '', None])]:
            for value in values:
                with self.subTest(key=key, value=value):
                    state, action, gate = direct_fixture()
                    gate[key] = value
                    self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_named_scope_cannot_grow_shrink_reorder_duplicate_or_include_samples(self):
        changes = [DIRECT_IDS[:-1], DIRECT_IDS + ['a058'], list(reversed(DIRECT_IDS)),
                   DIRECT_IDS[:-1] + [DIRECT_IDS[0]],
                   DIRECT_IDS[:-1] + ['a034'], DIRECT_IDS[:-1] + ['a052']]
        for ids in changes:
            with self.subTest(ids=ids):
                state, action, gate = direct_fixture()
                gate['action_ids'] = ids
                self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_any_new_sample_configuration_fails_closed(self):
        for key, value in [('sample_action_ids', ['a034', 'a052']),
                           ('sample_decisions', {'a034': {'approved': True}})]:
            with self.subTest(key=key):
                state, action, gate = direct_fixture()
                gate[key] = value
                self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_human_proof_cannot_be_missing_stale_other_role_revoked_or_blank(self):
        changes = [('approved', False), ('approved', 1), ('source', 'assistant'),
                   ('source', ''), ('spec_revision_id', OLD_SPEC),
                   ('spec_revision_id', ''), ('user_quote', ''),
                   ('user_quote', ' \n\t'), ('user_quote', None),
                   ('revoked_at', '2026-10-31T12:00:00Z')]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                state, action, gate = direct_fixture()
                gate['user_approval'][key] = value
                self.assertFalse(sample_batch_decision(state, action)['allowed'])
        state, action, gate = direct_fixture()
        del gate['user_approval']
        self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_every_authorized_rows_name_direction_props_and_revision_are_bound(self):
        for aid in DIRECT_IDS:
            for key, value in [('name', 'another action'), ('direction', 'do something else'),
                               ('props', ['different prop']), ('spec_revision_id', OLD_SPEC)]:
                with self.subTest(row=aid, field=key):
                    state, action, _ = direct_fixture()
                    if aid == action['id']:
                        action = next(a for a in state['actions'] if a['id'] == DIRECT_IDS[1])
                    next(a for a in state['actions'] if a['id'] == aid)[key] = value
                    self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_all_twelve_rows_and_exact_fingerprint_keys_are_required(self):
        for aid in DIRECT_IDS:
            with self.subTest(missing_row=aid):
                state, action, _ = direct_fixture()
                state['actions'] = [a for a in state['actions'] if a['id'] != aid]
                self.assertFalse(sample_batch_decision(state, action)['allowed'])
            with self.subTest(missing_fingerprint=aid):
                state, action, gate = direct_fixture()
                del gate['spec_fingerprints'][aid]
                self.assertFalse(sample_batch_decision(state, action)['allowed'])
        state, action, gate = direct_fixture()
        gate['spec_fingerprints']['a058'] = 'f' * 64
        self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_detached_action_argument_cannot_substitute_an_unapproved_spec(self):
        for key, value in [('name', 'not authorized'), ('direction', 'not authorized'),
                           ('props', ['not authorized'])]:
            with self.subTest(field=key):
                state, action, _ = direct_fixture()
                detached = copy.deepcopy(action)
                detached[key] = value
                self.assertFalse(sample_batch_decision(state, detached)['allowed'])

    def test_duplicate_scope_rows_do_not_allow_first_last_lookup_disagreement(self):
        state, action, _ = direct_fixture()
        duplicate = copy.deepcopy(action)
        duplicate['direction'] = 'unapproved shadow row'
        # Preserve an approved last row so a last-wins dictionary would hide the shadow.
        state['actions'].insert(0, duplicate)
        self.assertFalse(sample_batch_decision(state, action)['allowed'])

    def test_scope_gate_cannot_authorize_an_outside_action_with_same_revision(self):
        for aid in ('a034', 'a052', 'a058'):
            with self.subTest(aid=aid):
                state, action, _ = direct_fixture()
                outside = {**copy.deepcopy(action), 'id': aid}
                self.assertFalse(sample_batch_decision(state, outside)['allowed'])


def revision_fixture():
    state = historical_fixture()
    state['actions'].append({'id': 'a057', 'name': 'historical-a057',
                             'direction': 'historical direction', 'group': '生活',
                             'status': 'processing_failed', 'attempts': []})
    for aid in DIRECT_IDS:
        action = next(a for a in state['actions'] if a['id'] == aid)
        action['status'] = 'processing_failed'
        action['attempts'] = [
            {'task_id': aid + '-old-' + str(index), 'status': 'completed',
             'spec_revision_id': OLD_SPEC, 'source_file': 'archive/' + aid + '.mp4',
             'source_sha256': str(index) * 64,
             'prompt_file': 'prompts/' + aid + '.txt',
             'request': {'literal': 'untouched old request'},
             **({'local_reprocess_requests': [{'reason': 'historical correction'}]}
                if index == 2 else {})}
            for index in range(3)
        ]
        action['spec_revision_id'] = OLD_SPEC
        action['file'] = 'historical/' + aid + '.webm'
        action['sha256'] = 'a' * 64
        action['quality_hold'] = {'reason': 'historical visual failure'}
        action['repair_instruction'] = 'historical repair text'
    for aid, sha in revision.SAMPLES.items():
        sample = next(a for a in state['actions'] if a['id'] == aid)
        sample.update(status='approved', sha256=sha, file='accepted/' + aid + '.webm',
                      human_approval={'sha256': sha, 'source': 'user'},
                      poster='accepted/' + aid + '.png')
    state['spec_batch_gates'] = {OLD_SPEC: {'opaque_old_gate': 'must remain byte-for-byte'}}
    state['authorized_paid_pilot'] = {'closed': True}
    return state


class RevisionPreservationTests(unittest.TestCase):
    def test_exact_twelve_replaced_history_counts_and_all_outside_rows_preserved(self):
        state = revision_fixture()
        before = copy.deepcopy(state)
        old_counts = counts(state)
        old_attempts = {a['id']: json.dumps(a['attempts'], ensure_ascii=False)
                        for a in state['actions']}
        changes = revision.revise(state, '2026-10-31T12:00:00+00:00')
        self.assertEqual([row['id'] for row in changes], DIRECT_IDS)
        self.assertEqual(counts(state), old_counts)
        self.assertEqual(state['spec_batch_gates'][OLD_SPEC], before['spec_batch_gates'][OLD_SPEC])
        self.assertEqual([a for a in state['actions'] if a['id'] not in DIRECT_IDS],
                         [a for a in before['actions'] if a['id'] not in DIRECT_IDS])
        for action in state['actions']:
            self.assertEqual(json.dumps(action['attempts'], ensure_ascii=False),
                             old_attempts[action['id']])
        for aid in DIRECT_IDS:
            action = next(a for a in state['actions'] if a['id'] == aid)
            old = next(a for a in before['actions'] if a['id'] == aid)
            self.assertEqual(action['status'], 'planned')
            self.assertEqual(action['spec_revision_id'], NEW_SPEC)
            self.assertNotIn('file', action)
            self.assertEqual(action['spec_revision_history'][-1]['previous_action_metadata']['file'], old['file'])
            self.assertEqual(correction_usage(action), correction_usage(old))

    def test_revision_is_idempotent_without_new_exceptions_or_budget_resets(self):
        state = revision_fixture()
        revision.revise(state, '2026-10-31T12:00:00+00:00')
        once = copy.deepcopy(state)
        self.assertEqual(revision.revise(state, '2026-10-31T12:01:00+00:00'), [])
        self.assertEqual(state, once)

    def test_high_historical_usage_gets_firstpass_then_one_shared_correction_only(self):
        for correction_kind in ('paid', 'local'):
            with self.subTest(correction_kind=correction_kind):
                state = revision_fixture()
                action = next(a for a in state['actions'] if a['id'] == DIRECT_IDS[0])
                old_usage = correction_usage(action)
                self.assertGreater(old_usage['corrective_rounds_used'], 1)
                revision.revise(state, '2026-10-31T12:00:00+00:00')
                self.assertTrue(iteration_decision(state, action)['allowed'])
                self.assertFalse(iteration_decision(state, action, 'local_repair')['allowed'])
                action['attempts'].append({'task_id': 'new-firstpass', 'status': 'completed',
                                           'spec_revision_id': NEW_SPEC,
                                           'spec_action_name': action['name'],
                                           'source_file': 'new-firstpass.mp4'})
                self.assertTrue(iteration_decision(state, action)['allowed'])
                self.assertTrue(iteration_decision(state, action, 'local_repair')['allowed'])
                if correction_kind == 'paid':
                    action['attempts'].append({'task_id': 'new-correction', 'spec_revision_id': NEW_SPEC})
                else:
                    action['attempts'][-1]['local_reprocess_requests'] = [{'reason': 'single authorized correction'}]
                self.assertFalse(iteration_decision(state, action)['allowed'])
                self.assertFalse(iteration_decision(state, action, 'local_repair')['allowed'])
                self.assertGreater(correction_usage(action)['corrective_rounds_used'],
                                   old_usage['corrective_rounds_used'])

    def assert_main_stops_before_revision_or_save(self, state, report):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pack = root / 'pack'
            batch = pack / 'quality/batches/programmer-research-v2-batch30-firstpass-01.json'
            batch.parent.mkdir(parents=True)
            batch.write_text(json.dumps(report))
            with patch.object(revision.lib, 'ROOT', root), patch.object(revision.lib, 'PACK', pack), \
                 patch.object(revision.lib, 'production_lock', return_value=nullcontext()), \
                 patch.object(revision.lib, 'load', return_value=state), \
                 patch.object(revision.lib, 'save') as save, patch.object(revision, 'revise') as mutate:
                with self.assertRaises(AssertionError):
                    revision.main()
                mutate.assert_not_called()
                save.assert_not_called()

    def test_main_requires_prior_batch_completed_with_no_unfinished_counters(self):
        report = {'status': 'completed', 'in_progress': 0, 'awaiting_review': 0, 'not_submitted': 0}
        for key, value in [('status', 'running'), ('in_progress', 1),
                           ('awaiting_review', 1), ('not_submitted', 1)]:
            with self.subTest(field=key):
                self.assert_main_stops_before_revision_or_save(revision_fixture(), {**report, key: value})

    def test_main_requires_global_no_inflight_even_for_an_unrelated_action(self):
        report = {'status': 'completed', 'in_progress': 0, 'awaiting_review': 0, 'not_submitted': 0}
        for status in ('generating', 'submission_uncertain', 'local_processing', 'awaiting_processing'):
            with self.subTest(status=status):
                state = revision_fixture()
                next(a for a in state['actions'] if a['id'] == 'a011')['status'] = status
                self.assert_main_stops_before_revision_or_save(state, report)
        state = revision_fixture()
        next(a for a in state['actions'] if a['id'] == 'a011')['attempts'][0]['processing_claim'] = {'token': 'active'}
        self.assert_main_stops_before_revision_or_save(state, report)

    def test_main_requires_closed_prior_pilot(self):
        state = revision_fixture()
        state['authorized_paid_pilot']['closed'] = False
        report = {'status': 'completed', 'in_progress': 0, 'awaiting_review': 0, 'not_submitted': 0}
        self.assert_main_stops_before_revision_or_save(state, report)


if __name__ == '__main__':
    unittest.main()
