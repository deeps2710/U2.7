import assert from "node:assert/strict";
import { createDesktopGestureInterpreter, swipeCommand } from "../web/hand-mouse.js";
import { handSignalFromLandmarks } from "../web/hand-gestures.js";

const events = [];
const statuses = [];
const interpreter = createDesktopGestureInterpreter({
  onEvent: (event) => events.push(event),
  onStatus: (status) => statuses.push(status),
});

function signal(overrides = {}) {
  return {
    visible: true,
    cursorX: 0.5,
    cursorY: 0.5,
    palmX: 0.5,
    palmY: 0.5,
    spread: 0.8,
    pinchTarget: "",
    pose: "pointer",
    hands: [],
    ...overrides,
  };
}

interpreter.update(signal({ cursorX: 0.2, cursorY: 0.3 }), 100);
interpreter.update(signal({ cursorX: 0.7, cursorY: 0.6 }), 150);
assert.ok(events.some((event) => event.type === "move"));

interpreter.update(signal({ pinchTarget: "index" }), 200);
interpreter.update(signal({ pinchTarget: "index" }), 245);
interpreter.update(signal(), 290);
interpreter.update(signal(), 335);
assert.ok(events.some((event) => event.type === "button" && event.button === "left" && event.state === "down"));
assert.ok(events.some((event) => event.type === "button" && event.button === "left" && event.state === "up"));

interpreter.update(signal({ pose: "two_finger", palmY: 0.5 }), 400);
interpreter.update(signal({ pose: "two_finger", palmY: 0.62 }), 450);
assert.ok(events.some((event) => event.type === "scroll" && event.vertical < 0));

interpreter.update(signal({ pose: "three_finger", palmY: 0.45 }), 600);
interpreter.update(signal({ pose: "three_finger", palmY: 0.66 }), 700);
assert.ok(events.some((event) => event.type === "command" && event.command === "minimize_all"));

interpreter.update(signal({ pose: "pointer" }), 900);
interpreter.update(signal({ pose: "fist" }), 1000);
interpreter.update(signal({ pose: "fist" }), 2000);
assert.equal(interpreter.paused, true);
assert.ok(events.some((event) => event.type === "pause"));

interpreter.update(signal({ pose: "pointer" }), 2100);
interpreter.update(signal({ pose: "fist" }), 2200);
interpreter.update(signal({ pose: "fist" }), 3200);
assert.equal(interpreter.paused, false);
assert.ok(events.some((event) => event.type === "resume"));

assert.equal(swipeCommand("three_finger", "up"), "restore_all");
assert.equal(swipeCommand("four_finger", "left"), "desktop_left");
assert.equal(swipeCommand("pinky", "right"), "browser_forward");
assert.ok(statuses.length > 0);

const dropoutEvents = [];
const dropoutInterpreter = createDesktopGestureInterpreter({ onEvent: (event) => dropoutEvents.push(event) });
dropoutInterpreter.update(signal({ pinchTarget: "index" }), 100);
dropoutInterpreter.update({ visible: false }, 140);
dropoutInterpreter.update(signal({ pinchTarget: "index" }), 180);
assert.equal(dropoutEvents.filter((event) => event.type === "button" && event.state === "down").length, 0);
dropoutInterpreter.update(signal({ pinchTarget: "index" }), 220);
assert.equal(dropoutEvents.filter((event) => event.type === "button" && event.state === "down").length, 1);
assert.ok(dropoutEvents.some((event) => event.type === "release_all"));

const swipeDropoutEvents = [];
const swipeDropoutInterpreter = createDesktopGestureInterpreter({ onEvent: (event) => swipeDropoutEvents.push(event) });
swipeDropoutInterpreter.update(signal({ pose: "three_finger", palmY: 0.2 }), 100);
swipeDropoutInterpreter.update({ visible: false }, 140);
swipeDropoutInterpreter.update(signal({ pose: "three_finger", palmY: 0.75 }), 180);
assert.equal(swipeDropoutEvents.filter((event) => event.type === "command").length, 0);

function landmarksFor(extended = [], thumbTip = { x: 0.3, y: 0.72, z: 0 }) {
  const points = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.68, z: 0 }));
  points[0] = { x: 0.5, y: 0.9, z: 0 };
  points[4] = thumbTip;
  const fingers = [
    ["index", 5, 6, 7, 8, 0.4],
    ["middle", 9, 10, 11, 12, 0.47],
    ["ring", 13, 14, 15, 16, 0.54],
    ["pinky", 17, 18, 19, 20, 0.61],
  ];
  for (const [name, mcp, pip, dip, tip, x] of fingers) {
    points[mcp] = { x, y: 0.68, z: 0 };
    if (extended.includes(name)) {
      points[pip] = { x, y: 0.5, z: 0 };
      points[dip] = { x, y: 0.35, z: 0 };
      points[tip] = { x, y: 0.2, z: 0 };
    } else {
      points[pip] = { x, y: 0.54, z: 0 };
      points[dip] = { x, y: 0.58, z: 0 };
      points[tip] = { x, y: 0.64, z: 0 };
    }
  }
  return points;
}

assert.equal(handSignalFromLandmarks(landmarksFor(["index"])).pose, "pointer");
assert.equal(handSignalFromLandmarks(landmarksFor(["index", "middle", "ring"])).pose, "three_finger");
assert.equal(handSignalFromLandmarks(landmarksFor(["index", "middle", "ring", "pinky"])).pose, "four_finger");
const pinchingLandmarks = landmarksFor(["index"], { x: 0.405, y: 0.205, z: 0 });
assert.equal(handSignalFromLandmarks(pinchingLandmarks).pinchTarget, "index");

console.log(`hand mouse smoke passed with ${events.length} native events`);
