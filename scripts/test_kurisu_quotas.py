import copy
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import kurisu_library as lib
import kurisu_queue as queue


QUOTE = '继续保持推进，定时检查，如果没有完成就继续推进（调用额度用完的话可以继续加，直到全部完成为止）'


def ledger(first_calls=43, repairs=20):
    actions = [{'id': f'a{i+1:03d}', 'name': f'action{i+1}', 'group': 'daily',
                'status': 'processing_failed',
                'attempts': [{'task_id': f'original-{i}', 'model_id': 'h3'}]
                            + ([{'task_id': f'repair-{i}', 'model_id': 'h3'}] if i < repairs else [])}
               for i in range(first_calls)]
    return {'actions': actions, 'model_id': 'h3', 'stage': 'blocked_style_validation',
            'limits': {'total_calls': 130, 'repair_calls': 26, 'attempts_per_action': 2,
                       'other_model_calls': 4, 'concurrent_tasks': 6, 'local_processing': 2},
            'production_hold': {'reason': 'unqualified source route'},
            'local_processing_hold': {'reason': 'source gate'},
            'excluded_models': ['excluded-model'], 'action_attempt_limits': {'a002': 3}}


def authorize(state):
    return lib.record_standing_authorization(state, authorization_id='user-2026-10-31',
        user_quote=QUOTE, user_date='2026-10-31', timezone='Asia/Shanghai', automation_id=106)


class QuotaTests(unittest.TestCase):
    def test_first_replacement_of_reused_sample_is_a_repair_without_recounting_legacy_calls(self):
        s=ledger(1,0)
        a={'id':'a099','attempts':[],'reused_origin_history':[{'origin_record':'production.json'}]}
        s['actions'].append(a)
        self.assertEqual(lib.quota_counts(s),{'calls':1,'repairs':0,'other_model_calls':0})
        a['attempts'].append({'model_id':'h3','task_id':'new-replacement'})
        self.assertEqual(lib.quota_counts(s),{'calls':2,'repairs':1,'other_model_calls':0})
        a['attempts'].append({'model_id':'h3','task_id':'another-replacement'})
        self.assertEqual(lib.quota_counts(s),{'calls':3,'repairs':2,'other_model_calls':0})

    def test_withdrawn_reused_sample_cannot_bypass_full_repair_quota_with_zero_attempts(self):
        s=ledger(43,26)
        a={'id':'a099','attempts':[],'reused_origin_history':[{'origin_record':'production.json'}]}
        self.assertFalse(lib.can_submit(s,a))
        s['actions']=s['actions'][:1]
        self.assertTrue(lib.can_submit(s,a))

    def test_registration_keeps_all_63_calls_20_repairs_and_existing_exceptions(self):
        s = ledger(); original = copy.deepcopy(s)
        auth = authorize(s)
        self.assertEqual(lib.quota_counts(s)['calls'], 63)
        self.assertEqual(lib.quota_counts(s)['repairs'], 20)
        self.assertEqual(s['actions'], original['actions'])
        for key in original:
            self.assertEqual(s[key], original[key])
        self.assertEqual(auth['user_quote'], QUOTE)
        self.assertEqual(auth['automation_id'], '106')
        self.assertEqual(lib.attempt_limit(s, 'a002'), 3)
        self.assertEqual(lib.effective_limits(s)['other_model_calls'], 4)

    def test_no_standing_authorization_cannot_extend_or_ensure_default_caps(self):
        s = ledger(); before = copy.deepcopy(s)
        for fn in (lib.extend_quota, lib.ensure_quota):
            with self.assertRaises(PermissionError):
                fn(s, request_id='no-authorization', reason='next batch')
        self.assertEqual(s, before)
        self.assertFalse(lib.can_submit(ledger(104, 26), {'id': 'new', 'attempts': []}))

    def test_audited_extension_permits_more_than_130_calls_and_26_repairs(self):
        s = ledger(104, 27); authorize(s); before = copy.deepcopy(s['actions'])
        a = s['actions'][0]
        self.assertFalse(lib.can_submit(s, a))
        event = lib.extend_quota(s, request_id='batch-after-130', reason='Continue the unfinished library',
            total_calls=20, repair_calls=10, action_ids=['a001'], other_model_calls=1)
        self.assertEqual(s['limits']['total_calls'], 150)
        self.assertEqual(s['limits']['repair_calls'], 36)
        self.assertEqual(s['limits']['other_model_calls'], 5)
        self.assertTrue(lib.can_submit(s, a))
        self.assertEqual(event['actual_counts']['calls'], 131)
        self.assertEqual(event['actual_counts']['repairs'], 27)
        self.assertEqual(event['before']['limits']['total_calls'], 130)
        self.assertEqual(event['after']['limits']['total_calls'], 150)
        self.assertEqual(s['actions'], before)
        self.assertEqual(s['stage'], 'blocked_style_validation')
        self.assertEqual(s['production_hold'], {'reason': 'unqualified source route'})
        self.assertEqual(s['local_processing_hold'], {'reason': 'source gate'})
        self.assertEqual(s['excluded_models'], ['excluded-model'])

    def test_per_action_extension_is_scoped_and_does_not_reset_attempts(self):
        s = ledger(); authorize(s)
        lib.extend_quota(s, request_id='a001-only', reason='Specific revised action', action_ids=['a001'])
        self.assertEqual(lib.attempt_limit(s, 'a001'), 3)
        self.assertEqual(lib.attempt_limit(s, 'a002'), 3)  # prior explicit exception
        self.assertEqual(lib.attempt_limit(s, 'a003'), 2)
        self.assertEqual(len(s['actions'][0]['attempts']), 2)
        self.assertFalse(lib.can_submit(s, s['actions'][2]))
        self.assertTrue(lib.can_submit(s, s['actions'][0]))

    def test_invalid_or_unbounded_requests_fail_atomically(self):
        s = ledger(); authorize(s); before = copy.deepcopy(s)
        for kw in ({'total_calls': 21}, {'repair_calls': 11}, {'other_model_calls': 2},
                   {'total_calls': -1}, {'repair_calls': True}, {'total_calls': 1.5},
                   {'action_ids': ['a999']}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                lib.extend_quota(s, request_id='invalid', reason='next batch', **kw)
            self.assertEqual(s, before)
        with self.assertRaises(ValueError):
            lib.extend_quota(s, request_id='invalid', reason='', total_calls=1)
        self.assertEqual(s, before)

    def test_heartbeat_replay_is_idempotent_after_more_actual_calls(self):
        s = ledger(); authorize(s)
        args = {'request_id': 'heartbeat106-batch7', 'reason': 'Next named batch',
                'total_calls': 20, 'action_ids': ['a001']}
        original = lib.extend_quota(s, **args)
        s['actions'][0]['attempts'].append({'task_id': 'new-paid-task', 'model_id': 'h3'})
        self.assertEqual(lib.extend_quota(s, **args), original)
        self.assertEqual(s['limits']['total_calls'], 150)
        self.assertEqual(lib.attempt_limit(s, 'a001'), 3)
        self.assertEqual(len(s['quota_adjustments']), 1)
        self.assertEqual(lib.calls(s), 64)
        with self.assertRaisesRegex(ValueError, 'different request'):
            lib.extend_quota(s, **{**args, 'total_calls': 10})

    def test_ensure_extends_only_shortfall_and_checks_other_model_usage(self):
        s = ledger(104, 26)
        for a in s['actions'][:4]:
            a['attempts'][0]['model_id'] = 'alternate'
        authorize(s)
        args = {'request_id': 'next-pilot', 'reason': 'Two controlled pilot slots',
                'calls_needed': 2, 'repairs_needed': 1, 'action_ids': ['a001'],
                'other_model_calls_needed': 1}
        event = lib.ensure_quota(s, **args)
        self.assertEqual(event['delta'], {'total_calls': 2, 'repair_calls': 1,
                                        'other_model_calls': 1, 'actions': {'a001': 1}})
        self.assertEqual(lib.quota_counts(s), {'calls': 130, 'repairs': 26, 'other_model_calls': 4})
        self.assertEqual(lib.ensure_quota(s, **args), event)
        self.assertEqual(len(s['quota_adjustments']), 1)

    def test_noop_ensure_is_recorded_once_and_does_not_increase_available_quota(self):
        s = ledger(); authorize(s)
        before = copy.deepcopy(s['limits'])
        args = {'request_id': 'capacity-check', 'reason': 'Already enough first-call room', 'calls_needed': 2}
        self.assertFalse(lib.ensure_quota(s, **args)['changed'])
        self.assertFalse(lib.ensure_quota(s, **args)['changed'])
        self.assertEqual(s['limits'], before)
        self.assertEqual(len(s['quota_adjustments']), 1)

    def test_revoked_authorization_or_completed_library_cannot_expand(self):
        for scenario in ['revoked', 'complete']:
            s = ledger(106, 0); authorize(s)
            if scenario == 'revoked':
                s['standing_authorization']['revoked_at'] = 'later'
            else:
                for a in s['actions']:
                    a['status'] = 'approved'
            before = copy.deepcopy(s)
            with self.assertRaises((PermissionError, ValueError)):
                lib.extend_quota(s, request_id='not-needed', reason='next batch', total_calls=1)
            self.assertEqual(s, before)

    def test_raw_quota_edits_cannot_bypass_registered_approved_ceiling(self):
        s = ledger(104, 26); authorize(s)
        s['limits']['total_calls'] = 999
        s['limits']['repair_calls'] = 999
        s['action_attempt_limits']['a001'] = 999
        self.assertEqual(lib.effective_limits(s)['total_calls'], 130)
        self.assertEqual(lib.attempt_limit(s, 'a001'), 2)
        self.assertFalse(lib.can_submit(s, s['actions'][0]))

    def test_extended_total_and_repair_ceilings_are_still_enforced(self):
        s = ledger(104, 36); authorize(s)
        lib.extend_quota(s, request_id='new-ceilings', reason='Finite extended budget',
                         total_calls=20, repair_calls=10, action_ids=['a001'])
        self.assertEqual(lib.calls(s), 140)
        self.assertFalse(lib.can_submit(s, s['actions'][0]))  # 36 repairs used
        fresh = {'id': 'a105', 'attempts': []}
        self.assertTrue(lib.can_submit(s, fresh))
        for i in range(10):
            s['actions'].append({'id': f'new-{i}', 'attempts': [{'model_id': 'h3'}]})
        self.assertEqual(lib.calls(s), 150)
        self.assertFalse(lib.can_submit(s, fresh))

    def test_extension_fields_must_belong_to_the_recorded_authorization_scope(self):
        s = ledger(); authorize(s)
        s['standing_authorization']['scope'] = ['total_calls']
        before = copy.deepcopy(s)
        with self.assertRaises(PermissionError):
            lib.extend_quota(s, request_id='not-other-models', reason='Outside scope', other_model_calls=1)
        self.assertEqual(s, before)

    def test_ensure_refuses_unbounded_existing_shortfall_and_never_loops(self):
        s = ledger(43, 43); authorize(s); before = copy.deepcopy(s)
        with self.assertRaisesRegex(ValueError, 'repair_calls'):
            lib.ensure_quota(s, request_id='too-much', reason='repair backlog', repairs_needed=1)
        self.assertEqual(s, before)

    def test_cli_extension_is_locked_sdk_free_and_replay_safe(self):
        s = ledger(); authorize(s)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(lib, 'PACK', root), patch.object(lib, 'STATE', root/'library.json'):
                lib.save(s)
                args = ['kurisu_library.py', 'quota-extend', '--request-id', 'cli-batch1',
                        '--reason', 'Next controlled production batch', '--total-add', '20',
                        '--repair-add', '10', '--quota-action', 'a001', '--other-model-add', '1']
                for _ in range(2):
                    with patch('sys.argv', args), redirect_stdout(StringIO()):
                        lib.main()
                saved = lib.load()
                self.assertEqual(saved['limits']['total_calls'], 150)
                self.assertEqual(len(saved['quota_adjustments']), 1)
                self.assertEqual(saved['actions'], s['actions'])
                self.assertEqual(saved['production_hold'], s['production_hold'])
                self.assertFalse(lib.STATE.with_suffix('.lock').exists())

    def test_extended_room_does_not_release_quality_hold_or_approve_a_pilot(self):
        s = ledger(); authorize(s)
        lib.extend_quota(s, request_id='room-only', reason='Prepare capacity, keep source review hold',
                         total_calls=20, action_ids=['a001'])
        a = s['actions'][0]
        self.assertTrue(lib.can_submit(s, a))
        self.assertFalse(queue.paid_allowed(s, a))
        self.assertNotIn('authorized_paid_pilot', s)

    def test_cli_ensure_preserves_63_20_and_adds_only_the_named_action_shortfall(self):
        s = ledger(); authorize(s)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(lib, 'PACK', root), patch.object(lib, 'STATE', root/'library.json'):
                lib.save(s)
                with patch('sys.argv', ['kurisu_library.py', 'quota-ensure', '--request-id', 'ensure-cli',
                     '--reason', 'One revised action after route proof', '--calls-needed', '1',
                     '--repairs-needed', '1', '--quota-action', 'a001']), redirect_stdout(StringIO()):
                    lib.main()
                saved = lib.load()
                self.assertEqual(saved['limits'], s['limits'])
                self.assertEqual(lib.attempt_limit(saved, 'a001'), 3)
                self.assertEqual(lib.quota_counts(saved)['calls'], 63)
                self.assertEqual(lib.quota_counts(saved)['repairs'], 20)


if __name__ == '__main__':
    unittest.main()
