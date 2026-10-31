#!/usr/bin/env python3
"""Internal Wan motion diagnostic, separate from the 106 animation actions.

No prompts, duration or ratio are sent to this workflow. Prepare creates only a
dedicated canvas node. Submission requires a bounded diagnostic pilot even when
standing quota authorization exists. A diagnostic ID can reserve only once.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import time
from uuid import uuid4

import kurisu_library as lib
from kurisu_queue import all_tasks, model_slots, unresolved_submission
from kurisu_submission_errors import safe_submission_error
from kurisu_motion_reuse import assert_motion_source_reusable

MODEL_ID = 'b217e3cd-884d-4015-a3fa-98ab7608a67e'
MODEL_SLUG = 'wan2.2animate-v4-motion_retargeting'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def dump(value):
    return value.model_dump(mode='json', exclude_none=True) if hasattr(value, 'model_dump') else copy.deepcopy(value)


def get_attempt(state, diagnostic_id):
    return next((t for t in state.get('diagnostic_attempts', []) if t['diagnostic_id'] == diagnostic_id), None)


def manifest_plan(state, diagnostic_id, manifest_path):
    if not re.fullmatch(r'[a-z][a-z0-9-]{3,45}', diagnostic_id):
        raise ValueError('A stable diagnostic ID is required')
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    if (manifest['project_id'] != state['project_id'] or manifest['model_id'] != MODEL_ID
            or manifest['model_slug'] != MODEL_SLUG or MODEL_SLUG in state['excluded_models']):
        raise ValueError('Manifest does not describe the approved Wan diagnostic')
    image, driver = manifest['ref_image_asset_id'], manifest['driver_asset_id']
    # The active padded safe image is an approved composition derivative of
    # canonical_reference_asset_id; the original unpadded ID must not replace it.
    if image != state['reference_asset_id'] or not driver or image == driver:
        raise ValueError('Diagnostic needs the canonical character image and a separate motion driver')
    inputs = {}
    for name in ('ref_image', 'driver'):
        local = (lib.PACK / manifest[name+'_local_file']).resolve()
        if not local.is_relative_to(lib.PACK.resolve()) or sha(local) != manifest[name+'_sha256']:
            raise ValueError('Diagnostic input is outside the pack or its recorded SHA changed')
        inputs[name] = {'asset_id': manifest[name+'_asset_id'], 'local_file': manifest[name+'_local_file'],
                        'sha256': manifest[name+'_sha256']}
    assert_motion_source_reusable(state,lib.PACK,inputs['driver']['sha256'],driver)
    # Do not copy the manifest's schema-default empty prompt into the request.
    body = {'kind': 'video', 'model_id': MODEL_ID, 'mode': 'reference', 'resolution': '832x464',
            'reference_asset_ids': [image], 'video_asset_ids': [driver], 'audio_asset_ids': [],
            'workflow_parameters': {'seed': 314159}}
    return {'diagnostic_id': diagnostic_id, 'node_id': 'kurisu-diagnostic-'+diagnostic_id,
            'purpose': manifest['purpose'], 'model_id': MODEL_ID, 'model_slug': MODEL_SLUG,
            'request_body': body, 'request_sha256': digest(body), 'inputs': inputs,
            'manifest_file': str(path.resolve()), 'manifest_sha256': sha(path),
            'counts_toward_106': False, 'automatic_publication_allowed': False}


def preflight(client, state, plan):
    assert_motion_source_reusable(state,lib.PACK,plan['inputs']['driver']['sha256'],plan['inputs']['driver']['asset_id'])
    model = next((m for m in client.generation.generation_options().models if m.id == MODEL_ID), None)
    cap = model.video_capabilities if model else None
    if not (model and model.slug == MODEL_SLUG and cap and MODEL_SLUG not in state['excluded_models']
            and 'reference' in (cap.supported_modes or []) and not cap.supports_prompt
            and not cap.supports_duration and not cap.supports_ratio and cap.supports_seed
            and '832x464' in cap.resolutions and cap.reference_limits.get('image', 0) >= 1
            and cap.reference_limits.get('video', 0) >= 1 and cap.reference_video_upload_configured
            and cap.seed_minimum <= 314159 <= cap.seed_maximum):
        raise ValueError('Live model capabilities do not satisfy the explicit Wan motion workflow')
    assets = {a.id: a for a in client.files.list_files(project_id=state['project_id']).items}
    for kind, key in [('image', 'ref_image'), ('video', 'driver')]:
        item = assets.get(plan['inputs'][key]['asset_id'])
        if not item or item.media_kind != kind:
            raise ValueError('Diagnostic input is not a formal project '+kind+' asset')
        if sha(lib.PACK / plan['inputs'][key]['local_file']) != plan['inputs'][key]['sha256']:
            raise ValueError('Diagnostic source bytes changed after preparation')


def prepare(client, diagnostic_id, manifest_path):
    state = lib.load(); plan = manifest_plan(state, diagnostic_id, manifest_path)
    existing = state.get('prepared_diagnostics', {}).get(diagnostic_id)
    if existing and any(existing[key] != plan[key] for key in ('request_sha256','inputs','manifest_sha256')):
        raise ValueError('Diagnostic ID already describes different immutable inputs')
    preflight(client, state, plan)
    canvas = client.visual.get_canvas(project_id=state['project_id'])
    if any(a.get('node_id') == plan['node_id'] for a in state['actions']):
        raise ValueError('Diagnostic node must be independent of every animation node')
    nodes = [dump(n) for n in canvas.nodes]
    if not any(n['id'] == plan['node_id'] for n in nodes):
        nodes.append({'id': plan['node_id'], 'kind': 'video', 'title': '诊断 · Wan motion · '+diagnostic_id,
                      'position': {'x': 0, 'y': 9000}, 'generation_draft': copy.deepcopy(plan['request_body'])})
        try:
            client.visual.put_canvas(project_id=state['project_id'], body={'expected_revision': canvas.revision,
                'nodes': nodes, 'edges': [dump(e) for e in canvas.edges], 'categories': [dump(c) for c in canvas.categories]})
        except Exception:
            # An interrupted canvas write can be reconciled by this unique node.
            current = client.visual.get_canvas(project_id=state['project_id'])
            if not any(dump(n)['id'] == plan['node_id'] for n in current.nodes):
                raise
    with lib.production_lock():
        fresh = lib.load()
        assert_motion_source_reusable(fresh,lib.PACK,plan['inputs']['driver']['sha256'],plan['inputs']['driver']['asset_id'])
        old = fresh.setdefault('prepared_diagnostics', {}).get(diagnostic_id)
        if old and any(old[key] != plan[key] for key in ('request_sha256','inputs','manifest_sha256')):
            raise RuntimeError('Diagnostic preparation changed concurrently')
        if not old:
            fresh['prepared_diagnostics'][diagnostic_id] = {**plan, 'prepared_at': lib.now()}
            lib.save(fresh)
        return copy.deepcopy(fresh['prepared_diagnostics'][diagnostic_id])


def paid_allowed(state, diagnostic_id):
    pilot = state.get('authorized_paid_pilot', {})
    if state.get('stage') == 'blocked_task_reconciliation' or state.get('submission_blocker'):
        return False
    limits, used = lib.effective_limits(state), lib.quota_counts(state)
    return bool(pilot.get('approved') and not pilot.get('closed') and not pilot.get('halted')
        and diagnostic_id in pilot.get('diagnostic_ids', []) and MODEL_ID in pilot.get('model_ids', [])
        and used['calls'] < min(limits['total_calls'], pilot.get('calls_ceiling', 0))
        and used['other_model_calls'] < limits['other_model_calls'])


def submit(client, diagnostic_id):
    state = lib.load()
    if get_attempt(state, diagnostic_id):
        return False  # One diagnostic ID can never create a second paid task.
    if not paid_allowed(state, diagnostic_id) or unresolved_submission(state):
        return False
    plan = copy.deepcopy(state.get('prepared_diagnostics', {}).get(diagnostic_id))
    if not plan:
        raise ValueError('Prepare the independent diagnostic node before submission')
    preflight(client, state, plan)
    remote = all_tasks(client, state['project_id'])
    if model_slots(state, remote) >= min(6, state['limits'].get('concurrent_tasks', 6)):
        return False
    previous = all_tasks(client, state['project_id'], plan['node_id'])
    canvas = client.visual.get_canvas(project_id=state['project_id'])
    if not any(dump(n)['id'] == plan['node_id'] for n in canvas.nodes):
        raise ValueError('Prepared diagnostic canvas node is missing')
    with lib.production_lock():
        fresh = lib.load()
        if (get_attempt(fresh, diagnostic_id) or not paid_allowed(fresh, diagnostic_id)
                or unresolved_submission(fresh) or model_slots(fresh, remote) >= min(6, fresh['limits'].get('concurrent_tasks', 6))):
            return False
        assert_motion_source_reusable(fresh,lib.PACK,plan['inputs']['driver']['sha256'],plan['inputs']['driver']['asset_id'])
        if fresh.get('prepared_diagnostics', {}).get(diagnostic_id) != plan:
            raise RuntimeError('Diagnostic input plan changed during preflight')
        record = {**copy.deepcopy(plan), 'started_at': lib.now(), 'reservation_token': str(uuid4()),
                  'status': 'submission_started', 'previous_task_ids': [t.id for t in previous],
                  'release_epoch': fresh['authorized_paid_pilot'].get('id'), 'task_id': None}
        folder = lib.PACK/'quality/diagnostics'/diagnostic_id; folder.mkdir(parents=True, exist_ok=True)
        request_file = folder/'request.json'
        with request_file.open('x') as out:
            out.write(json.dumps(plan['request_body'], ensure_ascii=False, indent=2)+'\n')
        record['request_file'] = str(request_file.relative_to(lib.PACK))
        fresh.setdefault('diagnostic_attempts', []).append(record); lib.save(fresh)
    try:
        result = client.generation.create_generation_task(project_id=state['project_id'], body={**plan['request_body'],
            'canvas_node_id': plan['node_id'], 'expected_canvas_revision': canvas.revision})
        commit_remote(diagnostic_id, record['reservation_token'], result)
    except Exception as exc:
        with lib.production_lock():
            fresh = lib.load(); current = get_attempt(fresh, diagnostic_id)
            if current and current['reservation_token'] == record['reservation_token'] and not current.get('task_id'):
                current.update(status='submission_uncertain', submission_error_type=type(exc).__name__)
                current['submission_error']=safe_submission_error(exc)
                fresh['submission_blocker'] = {'diagnostic_id': diagnostic_id, 'reason': 'Reconcile original diagnostic; never resubmit', 'at': lib.now()}
                lib.save(fresh)
        recover(client, diagnostic_id, download=False)
    return True


def matches(remote, record):
    payload = getattr(remote, 'request_payload', None)
    if not payload or getattr(remote, 'canvas_node_id', None) != record['node_id']:
        return False
    if payload.get('prompt'):
        return False
    expected = record['request_body']
    if any(payload.get(key) != expected[key] for key in ('model_id', 'mode', 'resolution', 'reference_asset_ids', 'video_asset_ids', 'workflow_parameters')):
        return False
    if payload.get('audio_asset_ids'):
        return False
    created = getattr(remote, 'created_at', None)
    return not created or (datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp()+2
        >= datetime.fromisoformat(record['started_at']).timestamp())


def commit_remote(diagnostic_id, token, remote):
    with lib.production_lock():
        state = lib.load(); current = get_attempt(state, diagnostic_id)
        if not current or current['reservation_token'] != token or current.get('task_id') not in (None, remote.id):
            return False
        current.update(task_id=remote.id, status=remote.status, provider_task_id=remote.provider_task_id,
            result_asset_id=remote.result_asset_id, error=remote.error_message, poll_failures=0, next_poll_at=0)
        if state.get('submission_blocker', {}).get('diagnostic_id') == diagnostic_id:
            state.pop('submission_blocker', None)
        lib.save(state); return True


def recover(client, diagnostic_id, download=True):
    state = lib.load(); record = copy.deepcopy(get_attempt(state, diagnostic_id))
    if not record:
        raise ValueError('No paid diagnostic reservation exists to recover')
    if record.get('next_poll_at', 0) > time.time():
        return record
    try:
        if record.get('task_id'):
            remote = client.generation.get_generation_task(task_id=record['task_id'])
        else:
            previous = set(record['previous_task_ids'])
            found = [t for t in all_tasks(client, state['project_id'], record['node_id']) if t.id not in previous and matches(t, record)]
            if not found:
                found = [t for t in all_tasks(client, state['project_id']) if t.id not in previous and matches(t, record)]
            if len(found) != 1:
                return record  # Preserve unknown reservation and its submission block.
            remote = found[0]
        if remote.status == 'failed' and getattr(remote, 'can_retry_materialization', False):
            recovered = client.generation.retry_materialization(task_id=remote.id)
            if recovered.id != remote.id:
                raise ValueError('Diagnostic recovery changed the original task ID')
            remote = recovered
        commit_remote(diagnostic_id, record['reservation_token'], remote)
        if download and remote.status == 'completed' and remote.result_asset_id:
            folder = lib.PACK/'source/diagnostics'/diagnostic_id; folder.mkdir(parents=True, exist_ok=True)
            raw = folder/'original.mp4'
            if not raw.exists():
                partial = folder/(record['reservation_token']+'.download')
                with client.files.download_file(asset_id=remote.result_asset_id) as data:
                    data.save(partial)
                partial.replace(raw)
            source_sha = sha(raw)
            if record.get('source_sha256') and record['source_sha256'] != source_sha:
                raise ValueError('Diagnostic source bytes changed; do not replace the known result')
            with lib.production_lock():
                fresh = lib.load(); current = get_attempt(fresh, diagnostic_id)
                if current and current['reservation_token'] == record['reservation_token'] and current.get('task_id') == remote.id:
                    current.update(source_file=str(raw.relative_to(lib.PACK)), source_sha256=source_sha,
                        downloaded_at=lib.now(), recovery_status='awaiting_independent_source_review')
                    lib.save(fresh)
    except Exception as exc:
        with lib.production_lock():
            fresh = lib.load(); current = get_attempt(fresh, diagnostic_id)
            if current and current['reservation_token'] == record['reservation_token']:
                n = current.get('poll_failures', 0)+1
                current.update(poll_failures=n, last_recovery_error_type=type(exc).__name__, next_poll_at=time.time()+min(60, 5*2**min(n-1, 4)))
                lib.save(fresh)
        raise
    return copy.deepcopy(get_attempt(lib.load(), diagnostic_id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'submit', 'recover'])
    parser.add_argument('--diagnostic-id', required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--no-download', action='store_true')
    args = parser.parse_args()
    from future_props_lab.desktop import desktop_client
    with desktop_client() as client:
        if args.command == 'prepare':
            if not args.manifest:parser.error('prepare requires --manifest')
            result = prepare(client, args.diagnostic_id, args.manifest)
        elif args.command == 'submit':
            result = {'submitted': submit(client, args.diagnostic_id)}
        else:
            result = recover(client, args.diagnostic_id, not args.no_download)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
