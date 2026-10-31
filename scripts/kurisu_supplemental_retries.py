"""One explicitly granted paid retry, independent of ordinary correction usage.

The reservation consumes the entitlement, including unknown submit outcomes.
Existing-task recovery and initial conversion are never another paid retry.
"""
import re,hashlib,json
from kurisu_spec_revisions import spec_fingerprint

def _proof_valid(proof):
 return bool(isinstance(proof,dict) and proof.get('approved') is True and proof.get('source')=='user'
             and isinstance(proof.get('id'),str) and proof['id'].strip()==proof['id'] and proof['id']
             and isinstance(proof.get('user_quote'),str) and proof['user_quote'].strip()
             and type(proof.get('baseline_attempt_count')) is int and proof['baseline_attempt_count']>=0
             and type(proof.get('baseline_normal_corrective_rounds')) is int and proof['baseline_normal_corrective_rounds']>=0
             and isinstance(proof.get('spec_fingerprint'),str) and re.fullmatch('[0-9a-f]{64}',proof['spec_fingerprint'])
             and proof.get('frozen_status') in {'processing_failed','exhausted','rejected','quality_withdrawn'}
             and proof.get('extra_paid_retries')==1)

def is_exempt_retry_attempt(action,index,attempt):
 """index is the absolute ONE-based attempt number; fake tags do not discount."""
 if type(index) is not int or index<1:return False
 for p in action.get('supplemental_retry_grants',[]):
  if not _proof_valid(p):continue
  if (p['baseline_attempt_count']+1==index and attempt.get('human_retry_grant_id')==p['id']
      and attempt.get('human_retry_exempt_from_normal_correction') is True
      and attempt.get('human_retry_baseline_attempt_count')==p['baseline_attempt_count']
      and attempt.get('human_retry_spec_fingerprint')==p['spec_fingerprint']
      and attempt.get('spec_revision_id')==p.get('spec_revision_id')):return True
 return False

def supplemental_retry_decision(state,action,operation):
 if operation in {'recover_original','initial_processing'}:return None
 proofs=action.get('supplemental_retry_grants',[])
 if not proofs:return None
 p=proofs[-1];deny={'allowed':False,'reason':'Supplemental retry proof/history/specification changed; reconcile before submission'}
 if not _proof_valid(p):return deny
 campaign=state.get('supplemental_retry_authorizations',{}).get(p['id'],{})
 if (campaign.get('id')!=p['id'] or campaign.get('active') is not True or campaign.get('max_extra_per_action')!=1
     or campaign.get('approved') is not True or campaign.get('source')!='user' or campaign.get('revoked_at')
     or p.get('revoked_at') or not isinstance(campaign.get('user_quote'),str) or not campaign['user_quote'].strip() or action['id'] not in campaign.get('action_ids',[])
     or campaign.get('action_grants',{}).get(action['id'])!=p):return deny
 if action['status']=='approved':return {'allowed':False,'reason':'Approved media is excluded from supplemental retries'}
 if spec_fingerprint(action)!=p['spec_fingerprint']:return deny
 attempts=action.get('attempts',[]);tagged=[(i,t) for i,t in enumerate(attempts,1) if t.get('human_retry_grant_id')==p['id']]
 if tagged:
  if len(tagged)!=1 or not is_exempt_retry_attempt(action,*tagged[0]):return deny
  return {'allowed':False,'reason':'This action already consumed its single supplemental retry; continue other actions','human_retry_grant_id':p['id'],'supplemental_retry_consumed':True}
 if len(attempts)!=p['baseline_attempt_count']:return deny
 from kurisu_iteration_policy import correction_usage
 if correction_usage(action)['corrective_rounds_used']!=p['baseline_normal_corrective_rounds']:return deny
 if operation!='submit':return {'allowed':False,'reason':'This entitlement is one paid retry, not an extra local repair'}
 return {'allowed':True,'reason':'Explicit human one-time supplemental paid retry; ordinary correction allowance unchanged',
         'supplemental_retry':True,'human_retry_grant_id':p['id'],
         'retry_authorization_sha256':hashlib.sha256(json.dumps({'proof':p,'campaign':campaign},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
         'retry_metadata':{'human_retry_grant_id':p['id'],'human_retry_exempt_from_normal_correction':True,
                           'human_retry_baseline_attempt_count':p['baseline_attempt_count'],'human_retry_spec_fingerprint':p['spec_fingerprint']}}
