import test from 'node:test';
import assert from 'node:assert/strict';
import {QueueController, PreviewSession} from '../web/queue.mjs';

// Synthetic IDs below are unit fixtures only; they are never shipped as mappings.
const item = n => ({source_position: n, track_id: `fixture-${n}`, track_name: `Fixture ${n}`,
  occasion_status: 'GENERAL', playable: true, source_fields: {occasion_policy_version: 'FIXTURE'},
  mapping: {youtube_video_id: `testVID000${n}`, match_status: 'VERIFIED', platform_duration_seconds: 180}});

function setup(count = 3) {
  const calls = [], events = [];
  const adapter = {load: (...args) => calls.push(['load', ...args]), play: () => calls.push(['play']),
    pause: () => calls.push(['pause']), stop: () => calls.push(['stop'])};
  const controller = new QueueController(adapter, event => events.push(event));
  controller.prepare({queue_version: 'fixture-version'}, Array.from({length: count}, (_, i) => item(i + 1)));
  return {controller, adapter, calls, events};
}

function playing(controller) {
  controller.onState(1, controller.attempt, controller.items[controller.index].mapping.youtube_video_id, 1);
}

test('queue gate refuses seasonal, unreviewed and invalid videos', () => {
  const {controller} = setup();
  for (const change of [{occasion_status: 'SEASONAL_EVENT'}, {occasion_status: 'UNSCREENED'}, {playable: false}, {mapping: {...item(1).mapping, match_status: 'CANDIDATE'}}, {mapping: {...item(1).mapping, platform_duration_seconds: 0}}]) {
    assert.throws(() => controller.prepare({queue_version: 'bad'}, [{...item(1), ...change}]));
  }
});

test('natural end advances once; stale instance cannot consume next video', () => {
  const {controller, calls} = setup();
  playing(controller);
  const old = controller.attempt;
  controller.onState(0, old, item(1).mapping.youtube_video_id, 0);
  assert.equal(controller.index, 1);
  controller.onState(0, old, item(1).mapping.youtube_video_id, 0);
  controller.onError(100, old);
  assert.equal(controller.index, 1);
  assert.equal(calls.filter(x => x[0] === 'load').length, 2);
});

test('next click and ENDED race cannot jump two items', () => {
  const {controller} = setup();
  playing(controller);
  const old = controller.attempt;
  assert.equal(controller.advanceOnce('USER_NEXT'), true);
  assert.equal(controller.advanceOnce('USER_NEXT'), false);
  controller.onState(0, old, item(1).mapping.youtube_video_id, 0);
  assert.equal(controller.index, 1);
});

test('new attempt cannot naturally end before its PLAYING confirmation', () => {
  const {controller} = setup();
  controller.onState(0, controller.attempt, item(1).mapping.youtube_video_id, 0);
  assert.equal(controller.index, 0);
});

test('autoplay blocking keeps the same index and retries the same player', () => {
  const {controller, calls} = setup();
  controller.onBlocked(controller.attempt);
  assert.equal(controller.state, 'WAITING_FOR_USER');
  controller.start();
  assert.equal(controller.index, 0);
  assert.equal(calls.at(-1)[0], 'play');
  assert.equal(calls.filter(x => x[0] === 'load').length, 1);
});

test('pause and buffering never advance', () => {
  const {controller} = setup();
  playing(controller);
  controller.onState(3, controller.attempt, item(1).mapping.youtube_video_id, 3);
  controller.onState(2, controller.attempt, item(1).mapping.youtube_video_id, 2);
  assert.equal(controller.index, 0);
  assert.equal(controller.state, 'PAUSED');
});

test('153 and HTML5 errors hold the queue; no skip cascade', () => {
  for (const code of [153, 5, 999]) {
    const {controller} = setup();
    controller.onError(code, controller.attempt);
    assert.equal(controller.state, 'ERROR_HOLD');
    assert.equal(controller.index, 0);
    assert.equal(controller.advanceOnce('USER_NEXT'), false);
  }
});

test('item failures advance a finite number of times and finish without loop', () => {
  const {controller, calls} = setup(4);
  for (const code of [2, 100, 101, 150]) controller.onError(code, controller.attempt);
  assert.equal(controller.state, 'FINISHED');
  assert.equal(controller.failureCount, 4);
  assert.equal(calls.filter(x => x[0] === 'load').length, 4);
});

test('STOPPED is set before stopVideo can synchronously emit ENDED', () => {
  const {controller, adapter} = setup();
  playing(controller);
  adapter.stop = () => controller.onState(0, controller.attempt, item(1).mapping.youtube_video_id, 0);
  controller.stop();
  assert.equal(controller.index, 0);
  assert.equal(controller.state, 'STOPPED');
});

test('last normal item finishes, mismatching active identity holds', () => {
  const {controller} = setup(1);
  playing(controller);
  controller.onState(0, controller.attempt, item(1).mapping.youtube_video_id, 0);
  assert.equal(controller.state, 'FINISHED');
  const another = setup().controller;
  another.onState(1, another.attempt, 'otherVID001', 1);
  assert.equal(another.state, 'ERROR_HOLD');
});

test('frozen active queue is isolated from later mapping edits', () => {
  const {controller} = setup();
  const source = [item(1)];
  controller.prepare({queue_version: 'old'}, source);
  source[0].mapping.youtube_video_id = 'changed0001';
  assert.equal(controller.items[0].mapping.youtube_video_id, item(1).mapping.youtube_video_id);
  assert.equal(controller.version, 'old');
});

test('restore cues a validated index and position and does not autoplay', () => {
  const {controller, calls} = setup();
  controller.prepare({queue_version: 'restore-version'}, [item(1), item(2)], {index: 1, startSeconds: 25});
  const load = calls.at(-1);
  assert.equal(load[1].track_id, 'fixture-2');
  assert.equal(load[3], false);
  assert.equal(load[4], 25);
  assert.deepEqual(controller.exportState().track_ids, ['fixture-1', 'fixture-2']);
  assert.throws(() => controller.prepare({queue_version: 'bad'}, [item(1)], {index: 2}));
});

test('unverified preview is allowed only for GENERAL and cannot enter the ordinary queue', () => {
  const candidate = {...item(1), playable: false, mapping: null};
  const preview = new PreviewSession(candidate, 'testVID0001', 'review-1');
  assert.equal(preview.mapping_status, 'UNVERIFIED_PREVIEW');
  assert.throws(() => new PreviewSession({...candidate, occasion_status: 'REVIEW_REQUIRED'}, 'testVID0001', 'review-2'));
  assert.throws(() => new PreviewSession(candidate, 'bad-id', 'review-3'));
  const {controller} = setup();
  assert.throws(() => controller.prepare({queue_version: 'bad'}, [candidate]));
});

test('preview length is observed after PLAYING, END finishes without mapping promotion', () => {
  const preview = new PreviewSession(item(1), 'testVID0001', 'review-1');
  preview.observe(5, 'testVID0001', 0);
  assert.equal(preview.duration, null);
  preview.observe(1, 'testVID0001', 176);
  assert.equal(preview.duration, 176);
  preview.observe(0, 'testVID0001', 176);
  assert.equal(preview.state, 'FINISHED');
  assert.equal(preview.mapping_status, 'UNVERIFIED_PREVIEW');
  assert.throws(() => preview.observe(1, 'testVID0002', 177));
});
