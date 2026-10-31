"""One-use retry entitlements: in-memory fixtures and fake queue clients only."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kurisu_library as lib
import kurisu_queue as queue
from kurisu_iteration_policy import correction_usage, iteration_decision
from kurisu_quotas import counts
from kurisu_spec_revisions import spec_fingerprint
from kurisu_supplemental_retries import is_exempt_retry_attempt, supplemental_retry_decision
from test_kurisu_queue import Client, action as queue_action

GRANT_ID = 'human-failed-cohort-extra-once-2026-10-31'
QUOTE = '失败批每条额外一次，不占普通纠正额度，仅这一次。'
TAGS = {'human_retry_grant_id', 'human_retry_exempt_from_normal_correction',
        'human_retry_baseline_attempt_count', 'human_retry_spec_fingerprint'}


def fixture(attempt_count=2, aid='a031'):
    action = queue_action(int(aid[1:]))
    action['props'] = ['one ordinary miniature prop']
    action['attempts'] = [{'task_id': 'historical-' + str(i), 'status': 'completed',
                           'model_id': 'default', 'source_file': 'old-' + str(i) + '.mp4'}
                          for i in range(attempt_count)]
    limits = {'total_calls': 240, 'repair_calls': 100, 'attempts_per_action': 8,
              'other_model_calls': 100, 'concurrent_tasks': 6, 'local_processing': 2}
    state = {'actions': [action], 'limits': limits, 'model_id': 'default',
             'project_id': 'project', 'reference_asset_id': 'ref',
             'reference_sha256': 'refhash', 'excluded_models': [], 'stage': 'producing',
             'quota_policy': {'approved_limits': copy.deepcopy(limits),
                              'approved_action_attempt_limits': {aid: 8}},
             'iteration_policy': {'id': 'one-ordinary-correction', 'source': 'user',
                                  'effective_at': '2026-10-31T02:26:09+00:00',
                                  'max_corrective_rounds_per_action': 1}}
    grant = {'id': GRANT_ID, 'approved': True, 'source': 'user', 'user_quote': QUOTE,
             'baseline_attempt_count': attempt_count,
             'baseline_normal_corrective_rounds': correction_usage(action)['corrective_rounds_used'],
             'spec_fingerprint': spec_fingerprint(action), 'spec_revision_id': None,
             'frozen_status': 'processing_failed', 'extra_paid_retries': 1}
    action['supplemental_retry_grants'] = [grant]
    state['supplemental_retry_authorizations'] = {GRANT_ID: {
        'id': GRANT_ID, 'approved': True, 'source': 'user', 'user_quote': QUOTE,
        'active': True, 'max_extra_per_action': 1, 'action_ids': [aid],
        'action_grants': {aid: copy.deepcopy(grant)},
    }}
    return state, action, grant


def campaign(state):
    return state['supplemental_retry_authorizations'][GRANT_ID]


def sync_grant(state, action, grant):
    campaign(state)['action_grants'][action['id']] = copy.deepcopy(grant)


def reserve_in_memory(state, action):
    decision = supplemental_retry_decision(state, action, 'submit')
    assert decision['allowed']
    attempt = {'status': 'submission_started', 'model_id': 'default',
               'spec_revision_id': action.get('spec_revision_id'), **decision['retry_metadata']}
    action['attempts'].append(attempt)
    return attempt


class SupplementalRetryDecisionTests(unittest.TestCase):
    def test_absent_grant_and_recovery_are_no_override_and_read_only(self):
        state, action, _ = fixture()
        before = copy.deepcopy(state)
        for operation in ('recover_original', 'initial_processing'):
            self.assertIsNone(supplemental_retry_decision(state, action, operation))
        self.assertEqual(state, before)
        del action['supplemental_retry_grants']
        self.assertIsNone(supplemental_retry_decision(state, action, 'submit'))

    def test_valid_grant_allows_one_submit_even_when_normal_round_is_exhausted(self):
        state, action, _ = fixture()
        before = copy.deepcopy(state)
        self.assertTrue(iteration_decision(state, action)['allowed'])
        self.assertFalse(iteration_decision(state, action, 'local_repair')['allowed'])
        decision = supplemental_retry_decision(state, action, 'submit')
        self.assertTrue(decision['allowed'])
        self.assertEqual(set(decision['retry_metadata']), TAGS)
        self.assertEqual(state, before)

    def test_consumed_reservation_blocks_paid_and_local_even_with_normal_balance(self):
        for ordinary_history in (1, 2):
            with self.subTest(ordinary_history=ordinary_history):
                state, action, _ = fixture(ordinary_history)
                reserve_in_memory(state, action)
                for status in ('submission_started', 'submission_uncertain', 'failed', 'completed'):
                    action['attempts'][-1]['status'] = status
                    self.assertFalse(iteration_decision(state, action)['allowed'])
                    self.assertFalse(iteration_decision(state, action, 'local_repair')['allowed'])
                self.assertTrue(iteration_decision(state, action, 'recover_original')['allowed'])
                self.assertTrue(iteration_decision(state, action, 'initial_processing')['allowed'])

    def test_extra_paid_retry_preserves_ordinary_usage_and_true_call_repair_counts(self):
        state, action, grant = fixture()
        action['attempts'][0]['local_reprocess_requests'] = [{'reason': 'old ordinary local correction'}]
        grant['baseline_normal_corrective_rounds'] = correction_usage(action)['corrective_rounds_used']
        sync_grant(state, action, grant)
        before_usage = correction_usage(action)
        before_counts = counts(state)
        attempt = reserve_in_memory(state, action)
        self.assertTrue(is_exempt_retry_attempt(action, 3, attempt))
        after_usage = correction_usage(action)
        self.assertEqual(after_usage['corrective_rounds_used'], before_usage['corrective_rounds_used'])
        self.assertEqual(after_usage['paid_corrective_rounds'], before_usage['paid_corrective_rounds'])
        self.assertEqual(after_usage['paid_attempts_including_reused_origins'], 3)
        self.assertFalse(after_usage['first_pass'])
        self.assertEqual(counts(state), {**before_counts, 'calls': before_counts['calls'] + 1,
                                       'repairs': before_counts['repairs'] + 1})
        attempt['local_reprocess_requests'] = [{'reason': 'ordinary event is never free'}]
        self.assertEqual(correction_usage(action)['corrective_rounds_used'], before_usage['corrective_rounds_used'] + 1)

    def test_strict_tags_index_and_grant_binding_prevent_fake_discounts(self):
        state, action, _ = fixture()
        attempt = reserve_in_memory(state, action)
        for field in TAGS:
            with self.subTest(missing=field):
                fake = copy.deepcopy(attempt)
                del fake[field]
                self.assertFalse(is_exempt_retry_attempt(action, 3, fake))
        for index in (0, 1, 2, 4, True):
            self.assertFalse(is_exempt_retry_attempt(action, index, attempt))
        for field, value in [('human_retry_grant_id', 'other'),
                             ('human_retry_exempt_from_normal_correction', 1),
                             ('human_retry_baseline_attempt_count', 1),
                             ('human_retry_spec_fingerprint', 'f' * 64),
                             ('spec_revision_id', 'other')]:
            with self.subTest(field=field):
                self.assertFalse(is_exempt_retry_attempt(action, 3, {**attempt, field: value}))
        unbound = queue_action(32, attempt={**attempt, 'task_id': 'forged'})
        self.assertEqual(correction_usage(unbound)['supplemental_paid_retries_exempt_from_normal_corrections'], 0)

    def test_duplicate_or_wrong_position_coupon_tags_fail_closed(self):
        state, action, _ = fixture()
        attempt = reserve_in_memory(state, action)
        action['attempts'].append(copy.deepcopy(attempt))
        self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])
        self.assertFalse(supplemental_retry_decision(state, action, 'local_repair')['allowed'])
        self.assertEqual(correction_usage(action)['supplemental_paid_retries_exempt_from_normal_corrections'], 1)
        state, action, _ = fixture()
        decision = supplemental_retry_decision(state, action, 'submit')
        action['attempts'][0].update(decision['retry_metadata'])
        self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])
        self.assertEqual(correction_usage(action)['supplemental_paid_retries_exempt_from_normal_corrections'], 0)

    def test_failed_a105_is_included_when_explicitly_in_this_campaign(self):
        state, action, grant = fixture(attempt_count=4, aid='a105')
        state['iteration_policy']['stopped_action'] = 'a105'
        grant['frozen_status'] = 'exhausted'
        sync_grant(state, action, grant)
        self.assertTrue(iteration_decision(state, action)['allowed'])
        reserve_in_memory(state, action)
        self.assertFalse(iteration_decision(state, action)['allowed'])

    def test_missing_frozen_status_and_boolean_baselines_are_not_valid_proofs(self):
        for field, value in [('baseline_attempt_count', True),
                             ('baseline_normal_corrective_rounds', True),
                             ('spec_fingerprint', 'z' * 64), ('frozen_status', None),
                             ('extra_paid_retries', 0), ('extra_paid_retries', 2)]:
            with self.subTest(field=field, value=value):
                state, action, grant = fixture()
                grant[field] = value
                sync_grant(state, action, grant)
                self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])

    def test_quote_and_id_require_nonblank_strings_not_truthy_values(self):
        for field, values in [('user_quote', ['', ' \n\t', None, ['not a quote'], 1]),
                              ('id', ['', '   ', None, 123])]:
            for value in values:
                with self.subTest(field=field, value=value):
                    state, action, grant = fixture()
                    grant[field] = value
                    sync_grant(state, action, grant)
                    self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])

    def test_user_provenance_active_campaign_and_exact_grant_snapshot_required(self):
        for owner, field, value in [
            ('grant', 'approved', False), ('grant', 'approved', 1),
            ('grant', 'source', 'assistant'), ('grant', 'revoked_at', 'now'),
            ('campaign', 'approved', False), ('campaign', 'source', 'automation'),
            ('campaign', 'active', False), ('campaign', 'active', 1),
            ('campaign', 'id', 'different-id'), ('campaign', 'user_quote', '  '),
            ('campaign', 'revoked_at', 'now'), ('grant', 'frozen_status', 'approved'),
        ]:
            with self.subTest(owner=owner, field=field):
                state, action, grant = fixture()
                (grant if owner == 'grant' else campaign(state))[field] = value
                if owner == 'grant':
                    sync_grant(state, action, grant)
                self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])
        for missing in ('active', 'action_ids', 'action_grants'):
            with self.subTest(missing_campaign_field=missing):
                state, action, _ = fixture()
                del campaign(state)[missing]
                self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])
        state, action, _ = fixture()
        campaign(state)['action_grants'][action['id']]['baseline_attempt_count'] += 1
        self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])

    def test_old_history_count_and_ordinary_events_cannot_drift(self):
        for change in ('delete_attempt', 'append_unmarked_attempt', 'add_local_event'):
            with self.subTest(change=change):
                state, action, _ = fixture()
                if change == 'delete_attempt':
                    action['attempts'].pop()
                elif change == 'append_unmarked_attempt':
                    action['attempts'].append({'task_id': 'unrelated-new-task'})
                else:
                    action['attempts'][0]['local_reprocess_requests'] = [{'reason': 'later correction'}]
                self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])
        state, action, grant = fixture()
        grant['baseline_normal_corrective_rounds'] += 1
        sync_grant(state, action, grant)
        self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])

    def test_name_direction_props_or_revision_change_requires_new_authorization(self):
        for field, value in [('name', 'changed'), ('direction', 'changed'),
                             ('props', ['changed']), ('spec_revision_id', 'new-spec')]:
            with self.subTest(field=field):
                state, action, _ = fixture()
                action[field] = value
                self.assertFalse(supplemental_retry_decision(state, action, 'submit')['allowed'])

    def test_approved_media_and_selected011_hold_take_precedence(self):
        for aid in ('a031', 'a034', 'a052'):
            with self.subTest(aid=aid):
                state, action, _ = fixture(aid=aid)
                action['status'] = 'approved'
                self.assertFalse(iteration_decision(state, action)['allowed'])
        state, action, _ = fixture(aid='a011')
        action['human_action_hold'] = {'active': True, 'mode': 'immutable_selected_media'}
        for operation in ('submit', 'local_repair', 'initial_processing'):
            self.assertFalse(iteration_decision(state, action, operation)['allowed'])
        self.assertTrue(iteration_decision(state, action, 'recover_original')['allowed'])

    def test_supplemental_permission_does_not_lift_real_budget_or_attempt_caps(self):
        for field in ('total_calls', 'repair_calls', 'other_model_calls', 'attempts_per_action'):
            with self.subTest(field=field):
                state, action, _ = fixture()
                used = counts(state)
                if field == 'total_calls':
                    state['limits'][field] = used['calls']
                elif field == 'repair_calls':
                    state['limits'][field] = used['repairs']
                elif field == 'other_model_calls':
                    action['next_model_id'] = 'alternate'
                    state['limits'][field] = used['other_model_calls']
                else:
                    state['action_attempt_limits'] = {action['id']: len(action['attempts'])}
                self.assertTrue(supplemental_retry_decision(state, action, 'submit')['allowed'])
                self.assertFalse(lib.can_submit(state, action))


class SupplementalRetryQueueTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.pack = Path(self.folder.name)
        self.patches = [patch.object(lib, 'PACK', self.pack),
                        patch.object(lib, 'STATE', self.pack / 'library.json')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.folder.cleanup()

    def test_reservation_freezes_tags_before_api_and_vendor_payload_has_none(self):
        state, action, _ = fixture()
        lib.save(state)
        client = Client()
        original_create = client.create_generation_task
        def create(**kwargs):
            saved = lib.load()['actions'][0]['attempts'][-1]
            self.assertEqual(saved['status'], 'submission_started')
            self.assertEqual(saved['human_retry_grant_id'], GRANT_ID)
            self.assertTrue(TAGS <= queue.PROTECTED)
            self.assertFalse(TAGS & kwargs['body'].keys())
            return original_create(**kwargs)
        with patch.object(client, 'create_generation_task', side_effect=create):
            self.assertTrue(queue.submit_one(client))
        self.assertEqual(client.created, 1)
        self.assertEqual(len(lib.load()['actions'][0]['attempts']), 3)
        self.assertFalse(queue.submit_one(client))

    def test_lost_create_response_reconciles_same_task_without_new_coupon_or_call(self):
        state, _, _ = fixture()
        lib.save(state)
        client = Client()
        client.raise_after_create = True
        self.assertTrue(queue.submit_one(client))
        saved = lib.load()
        attempt = saved['actions'][0]['attempts'][-1]
        self.assertEqual(attempt['task_id'], 'new1')
        self.assertEqual(attempt['human_retry_grant_id'], GRANT_ID)
        for _ in range(2):
            queue.poll_originals(client)
            self.assertFalse(queue.submit_one(client))
        self.assertEqual(client.created, 1)
        self.assertEqual(counts(lib.load())['calls'], 3)
        self.assertEqual(correction_usage(lib.load()['actions'][0])['corrective_rounds_used'], 1)

    def test_grant_removed_or_rewritten_during_preflight_never_falls_back_to_normal(self):
        for mutation in ('remove', 'revoke', 'quote_rewrite', 'history_change'):
            with self.subTest(mutation=mutation):
                state, _, _ = fixture(attempt_count=1)
                lib.save(state)
                client = Client()
                original_canvas = client.get_canvas
                def canvas(**kwargs):
                    fresh = lib.load()
                    action = fresh['actions'][0]
                    if mutation == 'remove':
                        del action['supplemental_retry_grants']
                    elif mutation == 'revoke':
                        campaign(fresh)['active'] = False
                    elif mutation == 'quote_rewrite':
                        action['supplemental_retry_grants'][0]['user_quote'] = 'A different user proof'
                        campaign(fresh)['user_quote'] = 'A different user proof'
                        campaign(fresh)['action_grants'][action['id']] = copy.deepcopy(action['supplemental_retry_grants'][0])
                    else:
                        action['attempts'][0]['local_reprocess_requests'] = [{'reason': 'concurrent ordinary correction'}]
                    lib.save(fresh)
                    return original_canvas(**kwargs)
                with patch.object(client, 'get_canvas', side_effect=canvas):
                    try:
                        result = queue.submit_one(client)
                    except (RuntimeError, PermissionError):
                        result = False
                self.assertFalse(result)
                self.assertEqual(client.created, 0)
                self.assertEqual(len(lib.load()['actions'][0]['attempts']), 1)
                self.assertFalse((self.pack / 'prompts/library/a031-attempt-2.txt').exists())

    def test_local_worker_cannot_add_change_or_erase_frozen_coupon_tags(self):
        state, _, _ = fixture()
        lib.save(state)
        client = Client()
        self.assertTrue(queue.submit_one(client))
        state = lib.load()
        action = state['actions'][0]
        action['status'] = 'awaiting_processing'
        action['attempts'][-1]['result_asset_id'] = 'already-paid-result'
        lib.save(state)
        job = queue.claim_local()
        self.assertIsNotNone(job)
        for field in TAGS:
            for value in (None, 'rewritten'):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'immutable'):
                    queue.commit_processing(job, {'attempt_patch': {field: value}})
        self.assertEqual(lib.load()['actions'][0]['attempts'][-1]['human_retry_grant_id'], GRANT_ID)


if __name__ == '__main__':
    unittest.main()
