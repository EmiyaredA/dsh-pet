import copy
import unittest
import kurisu_library as lib
import kurisu_queue as queue
from kurisu_iteration_policy import require_local_repair


def fixture(new_policy=False):
    actions=[{'id':f'a{i:03}','name':f'action{i}','status':'processing_failed' if i<3 else 'planned',
        'batch':1,'queue_order':i,'attempts':[{'task_id':str(i),'model_id':'default','release_epoch':'pilot',
        'source_background':{'passed':False}}] if i<3 else []} for i in [1,2,3]]
    s={'actions':actions,'model_id':'default','limits':{'total_calls':130,'repair_calls':26,'attempts_per_action':5},
       'stage':'producing','authorized_paid_pilot':{'id':'pilot','approved':True,'first_pass_only':True,
       'source_recovery_only':True,'max_per_action_this_scope':1,'release_unbounded_or_old_repairs':False,
       'calls_ceiling':5,'action_ids':['a001','a002','a003']}}
    if new_policy:
        s['iteration_policy']={'id':'human-new','source':'失败就推进其他，每条只迭代一次',
            'max_corrective_rounds_per_action':1,'continue_other_actions_after_failure':True,
            'prioritize_unattempted_actions':True,'stopped_action':'a105'}
    return s


def fail_two(s):
    for a in s['actions'][:2]:queue.note_defect(s,a,a['attempts'][-1],'background')


class FailureContinuationTests(unittest.TestCase):
    def test_legacy_or_missing_explicit_flag_still_halts(self):
        for explicit in [False,True]:
            s=fixture(explicit)
            if explicit:s['iteration_policy'].pop('continue_other_actions_after_failure')
            fail_two(s)
            self.assertTrue(s['authorized_paid_pilot']['halted']);self.assertIn('production_hold',s)
            self.assertFalse(s['quality_stop_events'][-1]['automatic_quality_halt_suppressed'])
            self.assertFalse(queue.paid_allowed(s,s['actions'][2]))

    def test_new_policy_keeps_rejections_and_continues_next_first_pass(self):
        s=fixture(True);original_sources=copy.deepcopy([a['attempts'] for a in s['actions'][:2]])
        fail_two(s);event=s['quality_stop_events'][-1];fresh=s['actions'][2]
        self.assertTrue(event['automatic_quality_halt_suppressed']);self.assertTrue(event['new_calls_allowed'])
        self.assertEqual(event['action_ids'],['a001','a002']);self.assertNotIn('production_hold',s)
        self.assertNotIn('halted',s['authorized_paid_pilot'])
        self.assertEqual([a['status'] for a in s['actions'][:2]],['processing_failed']*2)
        self.assertTrue(all(not a['attempts'][0]['source_background']['passed'] for a in s['actions'][:2]))
        self.assertTrue(all(a['attempts'][0]['hard_source_defects']==['background'] for a in s['actions'][:2]))
        self.assertEqual([a['attempts'][0]['task_id'] for a in s['actions'][:2]],['1','2'])
        self.assertTrue(queue.paid_allowed(s,fresh));self.assertTrue(lib.can_submit(s,fresh))
        self.assertEqual([a['id'] for a in queue.ranked(s)],['a003'])

    def test_shared_correction_limit_and_unknown_submission_block_remain(self):
        s=fixture(True);fail_two(s);fresh=s['actions'][2]
        s['submission_blocker']={'reason':'original submission outcome unknown'}
        self.assertFalse(queue.paid_allowed(s,fresh));s.pop('submission_blocker')
        s['stage']='blocked_task_reconciliation';self.assertFalse(queue.paid_allowed(s,fresh))
        s['stage']='producing';old=s['actions'][0];old['attempts'].append({'task_id':'one-correction','model_id':'default'})
        old['status']='planned';self.assertFalse(lib.can_submit(s,old))
        with self.assertRaises(PermissionError):require_local_repair(s,old)
        # The exemption is explicitly scoped; it never opens an old-repair pilot.
        s=fixture(True);s['authorized_paid_pilot']['first_pass_only']=False;fail_two(s)
        self.assertTrue(s['authorized_paid_pilot']['halted'])


if __name__=='__main__':unittest.main()
