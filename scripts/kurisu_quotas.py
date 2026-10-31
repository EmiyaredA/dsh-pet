"""Audited, bounded quota extensions under an explicit user authorization.

These functions edit an in-memory ledger only. Callers must fresh-load, hold the
production lock, and save. They never reserve attempts or release quality holds.
Stable request IDs make a heartbeat restart safe to replay.
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone as dt_timezone

DEFAULT_LIMITS = {'total_calls': 130, 'repair_calls': 26,
                  'attempts_per_action': 2, 'other_model_calls': 2}
BATCH_MAX = {'total_calls': 20, 'repair_calls': 10, 'other_model_calls': 1}


def counts(state):
    actions = state['actions']
    diagnostics = state.get('diagnostic_attempts', [])
    attempts = [t for a in actions for t in a['attempts']] + diagnostics
    return {'calls': len(attempts),
            # Replacing a withdrawn pre-campaign sample is a repair even on
            # its first campaign call. Its original calls stay in the separate
            # production record; do not invent or recount those attempts.
            'repairs': sum(max(0, len(a['attempts']) - 1)
                           + int(bool(a.get('reused_origin_history')) and bool(a['attempts']))
                           for a in actions),
            'other_model_calls': sum(t.get('model_id', state.get('model_id')) != state.get('model_id')
                                     for t in attempts)}


def effective_limits(state):
    """Legacy defaults remain ceilings until an audited extension is recorded.

    Existing alternate-model and per-action exceptions predate this policy and
    are retained when registering it. Merely editing a global limit cannot lift
    the old total/repair ceilings, nor a registered policy's approved ceilings.
    """
    configured = {**DEFAULT_LIMITS, **state.get('limits', {})}
    ceiling = state.get('quota_policy', {}).get('approved_limits')
    if ceiling is None:
        ceiling = {**configured, 'total_calls': DEFAULT_LIMITS['total_calls'],
                   'repair_calls': DEFAULT_LIMITS['repair_calls']}
    result={key: min(value, ceiling.get(key, value)) for key, value in configured.items()}
    explicit=state.get('explicit_user_budget_ceiling',{})
    if explicit.get('active') is True:
        result['total_calls']=min(result['total_calls'],explicit['total_calls'])
    return result


def attempt_limit(state, action_id):
    configured = state.get('action_attempt_limits', {}).get(
        action_id, state.get('limits', {}).get('attempts_per_action', 2))
    policy = state.get('quota_policy')
    if policy:
        ceiling = policy['approved_action_attempt_limits'].get(
            action_id, policy['approved_limits'].get('attempts_per_action', 2))
        return min(configured, ceiling)
    return configured


def record_standing_authorization(state, *, authorization_id, user_quote,
                                   user_date, timezone, automation_id):
    """Record a direct user instruction; this is not inferred from a timer."""
    if not authorization_id or not user_quote.strip():
        raise ValueError('Explicit user wording and an authorization ID are required')
    old = state.get('standing_authorization')
    if old and old.get('id') == authorization_id:
        if old['user_quote'] != user_quote:
            raise ValueError('Authorization ID already records different wording')
        return copy.deepcopy(old)
    if old:
        state.setdefault('standing_authorization_history', []).append(copy.deepcopy(old))
    approved_limits = effective_limits(state)
    state.setdefault('quota_policy', {
        'version': 1, 'baseline_limits': copy.deepcopy(approved_limits),
        'approved_limits': copy.deepcopy(approved_limits),
        'baseline_action_attempt_limits': copy.deepcopy(state.get('action_attempt_limits', {})),
        'approved_action_attempt_limits': copy.deepcopy(state.get('action_attempt_limits', {})),
        'max_extension_per_request': {**BATCH_MAX, 'attempts_per_named_action': 1},
    })
    auth = {'id': authorization_id, 'approved': True, 'source': 'user',
            'user_quote': user_quote, 'user_date': user_date, 'timezone': timezone,
            'recorded_at': datetime.now(dt_timezone.utc).isoformat(),
            'automation_id': str(automation_id), 'automation_kind': 'heartbeat',
            'target_animation_count': 106,
            'scope': ['total_calls', 'repair_calls', 'named_action_attempts', 'other_model_calls'],
            'until': '106 independently approved animations',
            'preserved_requirements': ['excluded_models', 'source_and_media_quality_gates',
                                      'explicit_scoped_pilots_during_quality_hold'],
            'counts_at_authorization': counts(state)}
    state['standing_authorization'] = auth
    return copy.deepcopy(auth)


def _authorization(state):
    auth = state.get('standing_authorization', {})
    if not (auth.get('approved') and auth.get('source') == 'user'
            and auth.get('user_quote') and not auth.get('revoked_at')):
        raise PermissionError('Quota extensions require an active explicit user standing authorization')
    if sum(a.get('status') == 'approved' for a in state['actions']) >= auth.get('target_animation_count', 106):
        raise ValueError('The authorized animation library is complete; no extension is needed')
    return auth


def _number(value, name, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name} must be an integer between 0 and {maximum}')
    return value


def _request(state, request_id, reason, mode, requested):
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 160:
        raise ValueError('A stable request ID is required for safe replay')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('A concrete extension reason is required')
    for event in state.get('quota_adjustments', []):
        if event['request_id'] == request_id:
            if event['mode'] != mode or event['requested'] != requested or event['reason'] != reason:
                raise ValueError('Quota request ID already belongs to a different request')
            return copy.deepcopy(event)
    return None


def _apply(state, *, request_id, reason, mode, requested, delta):
    auth = _authorization(state)
    if set(delta) - {'total_calls', 'repair_calls', 'other_model_calls', 'actions'}:
        raise ValueError('Unsupported quota field')
    for key, maximum in BATCH_MAX.items():
        _number(delta[key], key, maximum)
    known = {a['id'] for a in state['actions'] if 'id' in a}
    if set(delta['actions']) - known:
        raise ValueError('Per-action extensions require existing stable action IDs')
    if any(type(n) is not int or n != 1 for n in delta['actions'].values()):
        raise ValueError('A request may add only one attempt per named action')
    needed_scope = {key for key in BATCH_MAX if delta[key]}
    if delta['actions']:
        needed_scope.add('named_action_attempts')
    if needed_scope - set(auth.get('scope', [])):
        raise PermissionError('This quota field is outside the recorded standing authorization')
    before = {'limits': effective_limits(state),
              'action_attempt_limits': {aid: attempt_limit(state, aid) for aid in delta['actions']}}
    after = copy.deepcopy(before)
    for key in BATCH_MAX:
        after['limits'][key] += delta[key]
    explicit=state.get('explicit_user_budget_ceiling',{})
    if explicit.get('active') is True and after['limits']['total_calls']>explicit['total_calls']:
        raise PermissionError('Latest explicit human cumulative ceiling cannot be exceeded by standing extensions')
    for aid in delta['actions']:
        after['action_attempt_limits'][aid] += 1
    event = {'request_id': request_id, 'mode': mode, 'reason': reason,
             'authorization_id': auth['id'], 'at': datetime.now(dt_timezone.utc).isoformat(),
             'requested': copy.deepcopy(requested), 'delta': copy.deepcopy(delta),
             'before': before, 'after': after, 'actual_counts': counts(state),
             'changed': any(delta[key] for key in BATCH_MAX) or bool(delta['actions']),
             'quality_hold_released': False, 'attempt_history_reset': False}
    # All validation and replay checks precede mutations.
    if 'quota_policy' not in state:
        raise ValueError('Register the standing authorization before extending quotas')
    state['limits'].update(after['limits'])
    state.setdefault('action_attempt_limits', {}).update(after['action_attempt_limits'])
    state['quota_policy']['approved_limits'] = copy.deepcopy(after['limits'])
    state['quota_policy']['approved_action_attempt_limits'].update(after['action_attempt_limits'])
    state.setdefault('quota_adjustments', []).append(event)
    return copy.deepcopy(event)


def extend_quota(state, *, request_id, reason, total_calls=0, repair_calls=0,
                 action_ids=(), other_model_calls=0):
    """Add at most 20 calls / 10 repairs / 1 per named action / 1 model test."""
    requested = {'total_calls': total_calls, 'repair_calls': repair_calls,
                 'action_ids': sorted(set(action_ids)), 'other_model_calls': other_model_calls}
    old = _request(state, request_id, reason, 'extend', requested)
    if old is not None:
        return old
    delta = {key: requested[key] for key in BATCH_MAX}
    delta['actions'] = {aid: 1 for aid in requested['action_ids']}
    return _apply(state, request_id=request_id, reason=reason, mode='extend', requested=requested, delta=delta)


def ensure_quota(state, *, request_id, reason, calls_needed=0, repairs_needed=0,
                 action_ids=(), other_model_calls_needed=0):
    """Ensure room for a finite next batch, extending only its shortfall.

    action_ids means one further attempt for each named action, not a reset.
    A shortfall above one bounded extension raises rather than looping silently.
    Even a no-op check is recorded once under its idempotent request ID.
    """
    _number(calls_needed, 'calls_needed', BATCH_MAX['total_calls'])
    _number(repairs_needed, 'repairs_needed', BATCH_MAX['repair_calls'])
    _number(other_model_calls_needed, 'other_model_calls_needed', BATCH_MAX['other_model_calls'])
    requested = {'calls_needed': calls_needed, 'repairs_needed': repairs_needed,
                 'action_ids': sorted(set(action_ids)), 'other_model_calls_needed': other_model_calls_needed}
    old = _request(state, request_id, reason, 'ensure', requested)
    if old is not None:
        return old
    actual, limits = counts(state), effective_limits(state)
    delta = {'total_calls': max(0, actual['calls'] + calls_needed - limits['total_calls']),
             'repair_calls': max(0, actual['repairs'] + repairs_needed - limits['repair_calls']),
             'other_model_calls': max(0, actual['other_model_calls'] + other_model_calls_needed - limits['other_model_calls']),
             'actions': {}}
    by_id = {a['id']: a for a in state['actions'] if 'id' in a}
    for aid in requested['action_ids']:
        if aid not in by_id:
            raise ValueError('Per-action extensions require existing stable action IDs')
        shortfall = len(by_id[aid]['attempts']) + 1 - attempt_limit(state, aid)
        if shortfall > 1:
            raise ValueError('Per-action shortfall exceeds one authorized increment')
        if shortfall > 0:
            delta['actions'][aid] = 1
    return _apply(state, request_id=request_id, reason=reason, mode='ensure', requested=requested, delta=delta)
