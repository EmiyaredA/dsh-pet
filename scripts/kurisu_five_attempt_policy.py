"""Later explicit human campaign: at most five fresh tries per failed action.

Historical attempts/specification and paid billing are never reset. A frozen
baseline makes carryover jobs visible; original task recovery isn't a new try.
The root coordinator alone enables new submission after the prior owner drains.
"""
from __future__ import annotations
import hashlib,json
from kurisu_spec_revisions import spec_fingerprint

def canonical_sha(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def five_attempt_decision(state,action,operation):
 c=state.get('five_attempt_campaign')
 if not isinstance(c,dict) or c.get('generation_enabled') is not True:return None
 deny={'allowed':False,'reason':'Five-attempt human campaign proof/history changed; reconcile original task'}
 if not(c.get('approved') is True and c.get('source')=='user' and c.get('user_quote') and c.get('max_attempts_per_action')==5 and not c.get('revoked_at')):return deny
 if action['id'] not in c.get('actions',{}):return {'allowed':False,'reason':'Approved actions are excluded from this retry campaign'}
 r=c['actions'][action['id']];n=r.get('baseline_attempt_count');attempts=action.get('attempts',[])
 if type(n) is not int or n<0 or len(attempts)<n or r.get('spec_fingerprint')!=spec_fingerprint(action):return deny
 if canonical_sha(attempts[:n])!=r.get('baseline_history_sha256'):return deny
 used=len(attempts)-n
 for index,t in enumerate(attempts[n:],n+1):
  if index in r.get('carryover_attempt_indexes',[]):
   if t.get('release_epoch')!=c.get('prior_scope_id'):return deny
  elif not(t.get('human_campaign_id')==c['id'] and t.get('human_campaign_attempt_number')==index-n and t.get('human_campaign_baseline_attempt_count')==n and t.get('human_campaign_spec_fingerprint')==r['spec_fingerprint']):return deny
 base={'campaign_id':c['id'],'campaign_attempts_used':used,'campaign_attempt_limit':5}
 if action.get('status')=='approved':return {**base,'allowed':False,'reason':'Approved exact-SHA media is immutable in this campaign'}
 if operation=='local_repair':return {**base,'allowed':False,'reason':'Use a distinct reviewed model try; no extra local repair or foreground editing'}
 if operation!='submit':return None
 if used>=5:return {**base,'allowed':False,'reason':'Five campaign attempts exhausted; mark failed and continue other actions'}
 if action.get('status') not in {'planned','processing_failed','exhausted','rejected','quality_withdrawn','generation_failed'}:return {**base,'allowed':False,'reason':'Original task or independent review still pending; recover/review without duplicate generation'}
 return {**base,'allowed':True,'reason':'Later explicit human authorization replaces one-correction rule with five fresh campaign tries',
  'retry_authorization_sha256':canonical_sha(c),
  'retry_metadata':{'human_campaign_id':c['id'],'human_campaign_attempt_number':used+1,'human_campaign_baseline_attempt_count':n,'human_campaign_spec_fingerprint':r['spec_fingerprint']}}
