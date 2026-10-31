import assert from 'node:assert/strict';
import { test } from 'node:test';
import { planDirectedMove } from './motion.ts';

const setup = {
  cx: 110,
  cy: 400,
  W: 1000,
  H: 800,
  dir: -1 as const,
  minDist: 120,
  maxDist: 120,
  margin: 20,
  halfW: 100,
  sideAllow: 40,
};

test('manual run near a blocked edge turns and moves horizontally with the matching facing', () => {
  const plan = planDirectedMove(setup, true);
  assert.ok(plan);
  assert.equal(plan.dir, 1);
  assert.equal(plan.startYRatio, setup.cy / setup.H);
  assert.equal(plan.targetRatio, 0.23);
  assert.ok(plan.targetRatio > plan.startRatio);
});

test('explicit facing and automatic roaming do not silently reverse direction', () => {
  assert.equal(planDirectedMove(setup), null);
  assert.equal(planDirectedMove(setup, false), null);
  const plan = planDirectedMove({ ...setup, cx: 500 });
  assert.ok(plan);
  assert.equal(plan.dir, -1);
  assert.equal(plan.targetRatio, 0.38);
});

test('if neither direction is reachable no movement animation is planned', () => {
  assert.equal(planDirectedMove({ ...setup, cx: 100, W: 200 }, true), null);
});

test('turn-around still respects the actual work area and monitor gaps', () => {
  const plan = planDirectedMove({ ...setup, areas: [{ x: 0, y: 0, width: 1000, height: 800 }] }, true);
  assert.ok(plan);
  assert.equal(plan.dir, 1);
  assert.equal(planDirectedMove({ ...setup, areas: [{ x: 400, y: 0, width: 300, height: 800 }] }, true), null);
});
