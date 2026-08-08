const BUTTON_FOR_PINCH = Object.freeze({ index: "left", middle: "right", ring: "middle" });

export function createDesktopGestureInterpreter(options = {}) {
  let paused = false;
  let pressedButton = "";
  let pinchCandidate = "";
  let pinchCandidateFrames = 0;
  let pinchReleaseFrames = 0;
  let lastCursor = { x: 0.5, y: 0.5 };
  let cursorReady = false;
  let lastHandAt = 0;
  let lastPose = "none";
  let poseStartedAt = 0;
  let poseAnchor = null;
  let poseLastPoint = null;
  let swipeCooldownUntil = 0;
  let fistStartedAt = 0;
  let fistLatched = false;
  let twoFingerPoint = null;
  let twoFingerSpread = null;
  let twoFingerZooming = false;
  let twoHandDistance = null;
  let sensitivity = clampNumber(options.sensitivity ?? 1, 0.55, 1.8);

  function update(signal, now = performance.now()) {
    if (!signal?.visible) {
      handleMissingHand(now);
      return;
    }
    lastHandAt = now;
    updatePoseState(signal, now);

    if (handleFistPause(signal, now)) return;
    if (paused) {
      status("paused", "Desktop hand control paused. Hold a fist to resume.", signal);
      return;
    }

    const twoHandZoom = handleTwoHandZoom(signal);
    if (twoHandZoom) {
      releasePressedButton();
      resetTwoFingerMode();
      return;
    }
    twoHandDistance = null;

    handlePinchButtons(signal);
    if (pressedButton) {
      moveCursor(signal, true);
      status("dragging", `${capitalize(pressedButton)} button held`, signal);
      return;
    }

    if (signal.pose === "pointer") {
      resetTwoFingerMode();
      moveCursor(signal, false);
      status("pointing", "Point to move the desktop cursor", signal);
      return;
    }
    cursorReady = false;

    if (signal.pose === "two_finger") {
      handleTwoFingerMode(signal);
      return;
    }
    resetTwoFingerMode();

    if (["three_finger", "four_finger", "pinky"].includes(signal.pose)) {
      handleDiscreteSwipe(signal, now);
      return;
    }
    status("ready", gestureLabel(signal), signal);
  }

  function handleMissingHand() {
    const hadHand = Boolean(lastHandAt);
    if (pressedButton) releasePressedButton();
    cursorReady = false;
    resetTwoFingerMode();
    twoHandDistance = null;
    pinchCandidate = "";
    pinchCandidateFrames = 0;
    pinchReleaseFrames = 0;
    lastPose = "none";
    poseStartedAt = 0;
    poseAnchor = null;
    poseLastPoint = null;
    fistStartedAt = 0;
    fistLatched = false;
    if (hadHand) emit({ type: "release_all" });
    lastHandAt = 0;
    status("no_hand", "Show one hand to the camera");
  }

  function handleFistPause(signal, now) {
    if (signal.pose !== "fist") {
      fistStartedAt = 0;
      fistLatched = false;
      return false;
    }
    releasePressedButton();
    resetTwoFingerMode();
    if (!fistStartedAt) fistStartedAt = now;
    const heldFor = now - fistStartedAt;
    if (!fistLatched && heldFor >= 950) {
      paused = !paused;
      fistLatched = true;
      emit({ type: paused ? "pause" : "resume", reason: "fist_hold" });
      options.onPauseChange?.(paused);
    }
    status(paused ? "paused" : "arming_pause", paused ? "Paused. Open your hand, then hold a fist to resume." : "Keep holding the fist to pause", signal, heldFor);
    return true;
  }

  function handlePinchButtons(signal) {
    const targetButton = BUTTON_FOR_PINCH[signal.pinchTarget] || "";
    if (pressedButton) {
      if (targetButton === pressedButton) {
        pinchReleaseFrames = 0;
        return;
      }
      pinchReleaseFrames += 1;
      if (pinchReleaseFrames >= 2) releasePressedButton();
      return;
    }
    pinchReleaseFrames = 0;
    if (!targetButton) {
      pinchCandidate = "";
      pinchCandidateFrames = 0;
      return;
    }
    if (pinchCandidate === targetButton) pinchCandidateFrames += 1;
    else {
      pinchCandidate = targetButton;
      pinchCandidateFrames = 1;
    }
    if (pinchCandidateFrames < 2) return;
    moveCursor(signal, true);
    pressedButton = targetButton;
    emit({ type: "button", button: pressedButton, state: "down" });
    pinchCandidate = "";
    pinchCandidateFrames = 0;
  }

  function releasePressedButton() {
    if (!pressedButton) return;
    emit({ type: "button", button: pressedButton, state: "up" });
    pressedButton = "";
    pinchReleaseFrames = 0;
  }

  function moveCursor(signal, force) {
    const mapped = mapCursor(signal.cursorX, signal.cursorY);
    if (!cursorReady) {
      lastCursor = mapped;
      cursorReady = true;
    }
    const distance = Math.hypot(mapped.x - lastCursor.x, mapped.y - lastCursor.y);
    const alpha = force ? 0.72 : Math.min(0.82, 0.2 + distance * 5.8 * sensitivity);
    lastCursor = {
      x: lastCursor.x + (mapped.x - lastCursor.x) * alpha,
      y: lastCursor.y + (mapped.y - lastCursor.y) * alpha,
    };
    emit({ type: "move", x: lastCursor.x, y: lastCursor.y });
  }

  function mapCursor(x, y) {
    const marginX = 0.12;
    const marginTop = 0.09;
    const marginBottom = 0.17;
    return {
      x: clampNumber((Number(x) - marginX) / (1 - marginX * 2), 0, 1),
      y: clampNumber((Number(y) - marginTop) / (1 - marginTop - marginBottom), 0, 1),
    };
  }

  function handleTwoFingerMode(signal) {
    const point = { x: signal.palmX, y: signal.palmY };
    if (!twoFingerPoint) {
      twoFingerPoint = point;
      twoFingerSpread = signal.spread;
      status("scroll_ready", "Move two fingers to scroll; spread or close them to zoom", signal);
      return;
    }
    const dx = point.x - twoFingerPoint.x;
    const dy = point.y - twoFingerPoint.y;
    const spreadDelta = Number(signal.spread) - Number(twoFingerSpread);
    const palmMotion = Math.hypot(dx, dy);
    if (Math.abs(spreadDelta) > 0.035 && Math.abs(spreadDelta) > palmMotion * 1.4) {
      twoFingerZooming = true;
      emit({ type: "zoom", delta: spreadDelta > 0 ? 120 : -120 });
      status("zooming", spreadDelta > 0 ? "Zooming in" : "Zooming out", signal);
    } else if (!twoFingerZooming || Math.abs(spreadDelta) < 0.018) {
      twoFingerZooming = false;
      const vertical = Math.abs(dy) > 0.006 ? Math.round(-dy * 2600 * sensitivity) : 0;
      const horizontal = Math.abs(dx) > 0.007 ? Math.round(dx * 2400 * sensitivity) : 0;
      if (vertical || horizontal) emit({ type: "scroll", vertical, horizontal });
      status("scrolling", vertical || horizontal ? "Scrolling" : "Two-finger scroll ready", signal);
    }
    twoFingerPoint = point;
    twoFingerSpread = signal.spread;
  }

  function handleTwoHandZoom(signal) {
    const openHands = (signal.hands || []).filter((hand) => hand.pose === "four_finger");
    if (openHands.length < 2) return false;
    const distance = Math.hypot(openHands[0].palmX - openHands[1].palmX, openHands[0].palmY - openHands[1].palmY);
    if (twoHandDistance !== null) {
      const delta = distance - twoHandDistance;
      if (Math.abs(delta) > 0.018) emit({ type: "zoom", delta: delta > 0 ? 120 : -120 });
    }
    twoHandDistance = distance;
    status("zooming", "Two-hand zoom", signal);
    return true;
  }

  function resetTwoFingerMode() {
    twoFingerPoint = null;
    twoFingerSpread = null;
    twoFingerZooming = false;
  }

  function handleDiscreteSwipe(signal, now) {
    const point = { x: signal.palmX, y: signal.palmY };
    if (!poseAnchor || signal.pose !== lastPose || now - poseStartedAt > 720) {
      poseAnchor = point;
      poseLastPoint = point;
      poseStartedAt = now;
      status("gesture_ready", `${poseName(signal.pose)} swipe ready`, signal);
      return;
    }
    poseLastPoint = point;
    if (now < swipeCooldownUntil) return;
    const dx = point.x - poseAnchor.x;
    const dy = point.y - poseAnchor.y;
    if (Math.max(Math.abs(dx), Math.abs(dy)) < 0.15) return;
    const horizontal = Math.abs(dx) > Math.abs(dy) * 1.18;
    const command = swipeCommand(signal.pose, horizontal ? (dx > 0 ? "right" : "left") : dy > 0 ? "down" : "up");
    if (!command) return;
    emit({ type: "command", command });
    options.onAction?.(command);
    swipeCooldownUntil = now + 900;
    poseAnchor = point;
    status("gesture_sent", commandLabel(command), signal);
  }

  function updatePoseState(signal, now) {
    if (signal.pose === lastPose) return;
    lastPose = signal.pose;
    poseStartedAt = now;
    poseAnchor = { x: signal.palmX, y: signal.palmY };
    poseLastPoint = poseAnchor;
  }

  function setPaused(nextPaused) {
    const next = Boolean(nextPaused);
    if (paused === next) return;
    releasePressedButton();
    paused = next;
    emit({ type: paused ? "pause" : "resume", reason: "interface" });
    options.onPauseChange?.(paused);
  }

  function stop() {
    releasePressedButton();
    emit({ type: "release_all" });
    resetTwoFingerMode();
    cursorReady = false;
    lastHandAt = 0;
  }

  function setSensitivity(value) {
    sensitivity = clampNumber(value, 0.55, 1.8);
    return sensitivity;
  }

  function status(state, detail, signal, progress = 0) {
    options.onStatus?.({ state, detail, pose: signal?.pose || "none", progress, paused });
  }

  function emit(event) {
    options.onEvent?.(event);
  }

  return {
    update,
    stop,
    setPaused,
    setSensitivity,
    get paused() {
      return paused;
    },
    get pressedButton() {
      return pressedButton;
    },
  };
}

export function swipeCommand(pose, direction) {
  const commands = {
    "three_finger:down": "minimize_all",
    "three_finger:up": "restore_all",
    "three_finger:right": "app_next",
    "three_finger:left": "app_previous",
    "four_finger:right": "desktop_right",
    "four_finger:left": "desktop_left",
    "four_finger:up": "task_view",
    "pinky:left": "browser_back",
    "pinky:right": "browser_forward",
  };
  return commands[`${pose}:${direction}`] || "";
}

function gestureLabel(signal) {
  if (signal.pinchTarget === "index") return "Index pinch detected";
  if (signal.pinchTarget === "middle") return "Middle pinch detected";
  if (signal.pinchTarget === "ring") return "Ring pinch detected";
  if (signal.pose === "four_finger") return "Open hand detected";
  return "Hold up your index finger to move the cursor";
}

function poseName(pose) {
  return String(pose || "hand").replaceAll("_", " ");
}

function commandLabel(command) {
  const labels = {
    minimize_all: "Desktop shown",
    restore_all: "Windows restored",
    app_next: "Next app",
    app_previous: "Previous app",
    desktop_left: "Previous desktop",
    desktop_right: "Next desktop",
    task_view: "Task View opened",
    browser_back: "Back",
    browser_forward: "Forward",
  };
  return labels[command] || command;
}

function capitalize(value) {
  const text = String(value || "");
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

function clampNumber(value, minimum, maximum) {
  const number = Number(value);
  if (!Number.isFinite(number)) return minimum;
  return Math.max(minimum, Math.min(maximum, number));
}
