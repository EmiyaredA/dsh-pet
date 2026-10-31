import copy,unittest
import kurisu_library as lib
from kurisu_iteration_policy import iteration_decision
from kurisu_queue import paid_allowed
from publish_kurisu_library import current_action
class HumanHoldTests(unittest.TestCase):
 def action(self):return {'id':'a011','status':'approved','attempts':[],'human_action_hold':{'active':True,'source':'user','user_quote':'等用户点名再动'}}
 def test_named_old_exception_does_not_lift_current_hold(self):
  a=self.action();s={'actions':[a],'iteration_policy':{'id':'old','source':'user','max_corrective_rounds_per_action':1,'named_action_exceptions':[]}}
  for operation in ['submit','local_repair','initial_processing']:
   with self.subTest(operation=operation):self.assertFalse(iteration_decision(s,a,operation)['allowed'])
  self.assertTrue(iteration_decision(s,a,'recover_original')['allowed'])
 def test_hold_blocks_review_before_mutating_approved_media_or_attempts(self):
  a=self.action();s={'actions':[a]};old=copy.deepcopy(s)
  for verdict in ['pass','reject']:
   with self.subTest(verdict=verdict),self.assertRaises(PermissionError):lib.review(s,a['id'],verdict,'automatic')
  self.assertEqual(s,old)
 def test_budget_clarification_blocks_new_calls_but_not_other_action_initial_processing(self):
  a={'id':'a084','attempts':[]};s={'actions':[a],'submission_blocker':{'type':'budget_clarification'}}
  self.assertFalse(paid_allowed(s,a));self.assertTrue(iteration_decision(s,a,'initial_processing')['allowed'])
 def test_selected_existing_media_can_publish_only_its_locked_sha(self):
  a=self.action();a.update(sha256='a'*64);a['human_action_hold'].update(mode='immutable_selected_media',sha256='a'*64);s={'actions':[a]}
  self.assertIs(current_action(s,a['id'],'a'*64),a)
  self.assertFalse(iteration_decision(s,a,'submit')['allowed']);self.assertFalse(iteration_decision(s,a,'initial_processing')['allowed'])
  self.assertTrue(iteration_decision(s,a,'recover_original')['allowed'])
  a['sha256']='b'*64
  with self.assertRaises(PermissionError):current_action(s,a['id'],'b'*64)
if __name__=='__main__':unittest.main()
