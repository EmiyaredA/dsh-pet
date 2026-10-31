import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kurisu_iteration_policy import (correction_usage,iteration_decision,submission_allowed,
    require_local_repair,submission_priority)
import kurisu_library as lib


def action(aid='a031',attempts=0,**extra):
    return {'id':aid,'name':aid,'status':'planned','attempts':[{'task_id':f'original-{n}','model_id':'h3'} for n in range(attempts)],**extra}

def state(*actions):
    return {'model_id':'h3','limits':{'total_calls':130,'repair_calls':26,'attempts_per_action':5,'other_model_calls':10},
        'iteration_policy':{'id':'human-one','effective_at':'2026-10-31T02:26:09+00:00',
            'source':'先做其他动画，每条只迭代一次，点名才继续','prioritize_unattempted_actions':True,
            'max_corrective_rounds_per_action':1,'stopped_action':'a105'},'actions':list(actions)}


class IterationPolicyTests(unittest.TestCase):
    def test_first_pass_ignores_consumed_repair_pool(self):
        old=action('a009',3);fresh=action();s=state(old,fresh);s['limits']['repair_calls']=0
        self.assertTrue(lib.can_submit(s,fresh));self.assertFalse(lib.can_submit(s,old))

    def test_paid_regeneration_allowed_once_then_blocked_despite_old_cap(self):
        a=action(attempts=1);s=state(a);s['action_attempt_limits']={'a031':5}
        self.assertTrue(lib.can_submit(s,a));a['attempts'].append({'task_id':'second','model_id':'h3'})
        self.assertFalse(lib.can_submit(s,a));self.assertEqual(correction_usage(a)['paid_corrective_rounds'],1)

    def test_local_repair_and_paid_regeneration_share_allowance(self):
        a=action(attempts=1);s=state(a);require_local_repair(s,a)
        a['attempts'][0]['local_reprocess_requests']=[{'at':'first','reason':'quality correction'}]
        self.assertFalse(submission_allowed(s,a))
        with self.assertRaises(PermissionError):require_local_repair(s,a)
        b=action('a032',2)
        with self.assertRaises(PermissionError):require_local_repair(state(b),b)

    def test_history_is_not_reset_by_new_recipe_or_status(self):
        for key,value in [('local_edit',{'type':'prior repair'}),('matte_edits',[{}]),
                          ('edge_revision',{'method':'v1'}),('previous_local_edits',[{}])]:
            a=action(attempts=1);a['attempts'][0][key]=value;a['status']='planned';a['next_worker_version']='v99'
            with self.subTest(key=key):self.assertFalse(submission_allowed(state(a),a))
        a=action(attempts=1,media_revisions=[{'method':'old'}])
        self.assertFalse(submission_allowed(state(a),a))

    def test_reused_and_withdrawn_origins_are_not_unattempted(self):
        a=action('a001',0,reused_origin_history=[{'task_id':'old1'},{'task_id':'old2'}])
        self.assertFalse(submission_allowed(state(a),a));self.assertFalse(correction_usage(a)['first_pass'])

    def test_prompt_revisions_and_network_claim_retries_do_not_consume_round(self):
        a=action(requirement_revisions=[{'note':'laptop wording'}]);s=state(a)
        self.assertTrue(submission_allowed(s,a));self.assertEqual(submission_priority(s,a),0)
        a['attempts']=[{'task_id':'same-paid-task','processing_claim_history':[{},{}],
                        'download_retries':5,'poll_error_count':6}]
        self.assertEqual(correction_usage(a)['corrective_rounds_used'],0)
        self.assertTrue(submission_allowed(s,a))

    def test_original_task_recovery_and_initial_conversion_never_change_history(self):
        a=action('a105',4);s=state(a);before=copy.deepcopy((s,a))
        for operation in ['recover_original','initial_processing']:
            self.assertTrue(iteration_decision(s,a,operation)['allowed'])
        self.assertEqual((s,a),before)
        self.assertEqual(a['attempts'][-1]['task_id'],'original-3')
        self.assertFalse(submission_allowed(s,a))

    def test_prioritize_unattempted_actions_before_corrective_round(self):
        first=action();repair=action('a032',1)
        s=state(repair,first);self.assertLess(submission_priority(s,first),submission_priority(s,repair))

    def test_only_post_policy_human_named_action_can_lift_guard(self):
        a=action('a105',4);s=state(a)
        s['standing_authorization']={'approved':True,'source':'user','user_quote':'finish106'}
        self.assertFalse(submission_allowed(s,a))
        exception={'action_id':'a105','policy_id':'human-one','approved':True,'source':'user',
            'human_named_action':True,'user_quote':'继续a105一次','authorized_at':'2026-10-31T03:00:00+00:00',
            'max_corrective_rounds':4}
        s['iteration_policy']['named_action_exceptions']=[exception]
        self.assertTrue(submission_allowed(s,a));a['attempts'][-1]['local_reprocess_requests']=[{'at':'new'}]
        self.assertFalse(submission_allowed(s,a))
        for bad in [{'authorized_at':'2026-10-30T03:00:00+00:00'},{'action_id':'a104'},
                    {'human_named_action':False},{'source':'automation'},{'approved':False}]:
            b=action('a105',4);ss=state(b);ss['iteration_policy']['named_action_exceptions']=[{**exception,**bad}]
            with self.subTest(bad=bad):self.assertFalse(submission_allowed(ss,b))

    def test_duplicate_request_records_still_monotonically_consume_rounds(self):
        a=action(attempts=1);a['attempts'][0]['local_reprocess_requests']=[{'reason':'x'},{'reason':'x'}]
        self.assertEqual(correction_usage(a)['corrective_rounds_used'],2)

    def test_identical_mirrored_media_revision_is_not_counted_twice(self):
        event={'method':'old','before_sha':'abc'};a=action(attempts=1,media_revisions=[event]);a['attempts'][0]['edge_revision']=event
        self.assertEqual(correction_usage(a)['historical_local_events'],1)

    def test_explicit_malformed_policy_fails_closed_and_legacy_is_unchanged(self):
        a=action(attempts=2);s=state(a);s.pop('iteration_policy');self.assertTrue(lib.can_submit(s,a))
        for value in [None,{}, {'id':'x','source':'user','max_corrective_rounds_per_action':True}]:
            s['iteration_policy']=value;self.assertFalse(submission_allowed(s,a))

    def test_save_separates_source_coverage_from_qualified_and_active(self):
        actions=[action('a001',0,reused=True),action('a002',0,reused_origin_history=[{}]),
            action('a003',1),action('a004',1),action('a005',1)]
        actions[2]['attempts'][0]['source_file']='raw.mp4';actions[2]['status']='approved'
        actions[3]['status']='generating';actions[4]['status']='submission_uncertain';s=state(*actions)
        with tempfile.TemporaryDirectory() as folder,patch.object(lib,'STATE',Path(folder)/'state.json'):
            lib.save(s);saved=json.loads(lib.STATE.read_text())
        self.assertEqual(saved['production_coverage'],{'source_action_count':3,'approved_count':1,
            'active_generation_count':2,'target':106})
        self.assertEqual([a['attempts'] for a in saved['actions']],[a['attempts'] for a in actions])


if __name__=='__main__':unittest.main()
