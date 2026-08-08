const MEDIAPIPE_VERSION = "0.10.35";
const MODULE_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}/vision_bundle.mjs`;
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}/wasm`;
const MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

export function createHandGestureController(options = {}) {
  let handLandmarker = null;
  let HandLandmarkerClass = null;
  let drawingUtils = null;
  let video = null;
  let overlay = null;
  let running = false;
  let animation = null;
  let loadingPromise = null;
  let lastVideoTime = -1;
  let lastInferenceAt = 0;
  let smoothX = 0.5;
  let smoothY = 0.5;
  let pinching = false;
  let openPalmSamples = [];
  let swipeCooldownUntil = 0;

  async function load() {
    if (handLandmarker) return handLandmarker;
    if (loadingPromise) return await loadingPromise;
    loadingPromise = (async () => {
      options.onStatus?.("loading", "Loading hand tracking model");
      const visionTasks = await import(MODULE_URL);
      const { FilesetResolver, HandLandmarker, DrawingUtils } = visionTasks;
      HandLandmarkerClass = HandLandmarker;
      const vision = await FilesetResolver.forVisionTasks(WASM_URL);
      const baseOptions = { modelAssetPath: MODEL_URL, delegate: "GPU" };
      try {
        handLandmarker = await HandLandmarker.createFromOptions(vision, {
          baseOptions,
          runningMode: "VIDEO",
          numHands: 2,
          minHandDetectionConfidence: 0.55,
          minHandPresenceConfidence: 0.55,
          minTrackingConfidence: 0.55,
        });
      } catch {
        handLandmarker = await HandLandmarker.createFromOptions(vision, {
          baseOptions: { modelAssetPath: MODEL_URL, delegate: "CPU" },
          runningMode: "VIDEO",
          numHands: 2,
          minHandDetectionConfidence: 0.55,
          minHandPresenceConfidence: 0.55,
          minTrackingConfidence: 0.55,
        });
      }
      drawingUtils = overlay ? new DrawingUtils(overlay.getContext("2d")) : null;
      options.onStatus?.("ready", "Hand controls ready");
      return handLandmarker;
    })();
    try {
      return await loadingPromise;
    } finally {
      loadingPromise = null;
    }
  }

  async function start(nextVideo, nextOverlay) {
    video = nextVideo;
    overlay = nextOverlay || null;
    await load();
    if (overlay && !drawingUtils) {
      const visionTasks = await import(MODULE_URL);
      drawingUtils = new visionTasks.DrawingUtils(overlay.getContext("2d"));
    }
    running = true;
    lastVideoTime = -1;
    options.onActiveChange?.(true);
    animation = window.requestAnimationFrame(processFrame);
  }

  function stop() {
    running = false;
    if (animation) window.cancelAnimationFrame(animation);
    animation = null;
    pinching = false;
    openPalmSamples = [];
    clearOverlay();
    options.onFrame?.({ visible: false, pinching: false, gesture: "none" });
    options.onActiveChange?.(false);
    options.onStatus?.("off", "Hand controls off");
  }

  function dispose() {
    stop();
    handLandmarker?.close?.();
    handLandmarker = null;
  }

  function processFrame(now) {
    if (!running) return;
    animation = window.requestAnimationFrame(processFrame);
    if (!video || video.readyState < 2 || !video.videoWidth || video.currentTime === lastVideoTime || now - lastInferenceAt < 42) return;
    lastInferenceAt = now;
    lastVideoTime = video.currentTime;
    let result;
    try {
      result = handLandmarker.detectForVideo(video, Math.round(performance.now()));
    } catch (error) {
      options.onStatus?.("error", error?.message || "Hand tracking failed");
      return;
    }
    drawResult(result);
    const landmarks = result.landmarks?.[0];
    if (!landmarks) {
      pinching = false;
      openPalmSamples = [];
      options.onFrame?.({ visible: false, pinching: false, gesture: "none", pose: "none", hands: [] });
      return;
    }

    const signal = handSignalFromLandmarks(landmarks);
    smoothX += (signal.x - smoothX) * 0.34;
    smoothY += (signal.y - smoothY) * 0.34;
    const screenSignal = {
      ...signal,
      visible: true,
      x: smoothX * window.innerWidth,
      y: smoothY * window.innerHeight,
      justPinched: signal.pinching && !pinching,
      justReleased: !signal.pinching && pinching,
      handedness: result.handedness?.[0]?.[0]?.categoryName || "",
      handednessScore: result.handedness?.[0]?.[0]?.score || 0,
      hands: (result.landmarks || []).map((hand, index) => ({
        ...handSignalFromLandmarks(hand),
        handedness: result.handedness?.[index]?.[0]?.categoryName || "",
        handednessScore: result.handedness?.[index]?.[0]?.score || 0,
      })),
    };
    pinching = signal.pinching;
    trackSwipe(screenSignal, now);
    options.onFrame?.(screenSignal);
  }

  function trackSwipe(signal, now) {
    if (!signal.openPalm || signal.pinching) {
      openPalmSamples = [];
      return;
    }
    openPalmSamples.push({ x: signal.x, at: now });
    openPalmSamples = openPalmSamples.filter((sample) => now - sample.at <= 520);
    if (now < swipeCooldownUntil || openPalmSamples.length < 3) return;
    const delta = signal.x - openPalmSamples[0].x;
    if (Math.abs(delta) < window.innerWidth * 0.24) return;
    options.onSwipe?.(delta > 0 ? "right" : "left");
    swipeCooldownUntil = now + 850;
    openPalmSamples = [];
  }

  function drawResult(result) {
    if (!overlay || !drawingUtils || !HandLandmarkerClass) return;
    if (overlay.width !== video.videoWidth || overlay.height !== video.videoHeight) {
      overlay.width = video.videoWidth;
      overlay.height = video.videoHeight;
    }
    const context = overlay.getContext("2d");
    context.clearRect(0, 0, overlay.width, overlay.height);
    for (const landmarks of result.landmarks || []) {
      drawingUtils.drawConnectors(landmarks, HandLandmarkerClass.HAND_CONNECTIONS, { color: "#67cce6", lineWidth: 3 });
      drawingUtils.drawLandmarks(landmarks, { color: "#55e6a2", fillColor: "#071012", lineWidth: 1.5, radius: 3.5 });
    }
  }

  function clearOverlay() {
    if (!overlay) return;
    overlay.getContext("2d").clearRect(0, 0, overlay.width, overlay.height);
  }

  return { load, start, stop, dispose, get active() { return running; } };
}

export function handSignalFromLandmarks(landmarks) {
  if (!Array.isArray(landmarks) || landmarks.length < 21) {
    return { visible: false, x: 0.5, y: 0.5, pinching: false, openPalm: false, gesture: "none", pose: "none" };
  }
  const thumbTip = landmarks[4];
  const indexTip = landmarks[8];
  const wrist = landmarks[0];
  const middleMcp = landmarks[9];
  const palmScale = Math.max(distance3(wrist, middleMcp), 0.04);
  const palmPoints = [landmarks[0], landmarks[5], landmarks[9], landmarks[13], landmarks[17]];
  const palmCenter = averagePoint(palmPoints);
  const fingers = {
    index: fingerExtended(landmarks, 5, 6, 8),
    middle: fingerExtended(landmarks, 9, 10, 12),
    ring: fingerExtended(landmarks, 13, 14, 16),
    pinky: fingerExtended(landmarks, 17, 18, 20),
  };
  const extendedCount = Object.values(fingers).filter(Boolean).length;
  const pinchRatios = {
    index: distance3(thumbTip, landmarks[8]) / palmScale,
    middle: distance3(thumbTip, landmarks[12]) / palmScale,
    ring: distance3(thumbTip, landmarks[16]) / palmScale,
    pinky: distance3(thumbTip, landmarks[20]) / palmScale,
  };
  const pinchTarget = nearestPinchTarget(pinchRatios);
  const pinchRatio = pinchRatios.index;
  const pinching = pinchTarget === "index";
  const openPalm = extendedCount === 4;
  const thumbFolded = distance3(thumbTip, palmCenter) / palmScale < 1.18;
  let pose = "neutral";
  if (extendedCount === 0 && thumbFolded && !pinchTarget) pose = "fist";
  else if (fingers.index && !fingers.middle && !fingers.ring && !fingers.pinky) pose = "pointer";
  else if (fingers.index && fingers.middle && !fingers.ring && !fingers.pinky) pose = "two_finger";
  else if (fingers.index && fingers.middle && fingers.ring && !fingers.pinky) pose = "three_finger";
  else if (extendedCount === 4) pose = "four_finger";
  else if (fingers.pinky && !fingers.index && !fingers.middle && !fingers.ring) pose = "pinky";
  return {
    visible: true,
    x: 1 - indexTip.x,
    y: indexTip.y,
    cursorX: 1 - indexTip.x,
    cursorY: indexTip.y,
    palmX: 1 - palmCenter.x,
    palmY: palmCenter.y,
    palmScale,
    pinchRatio,
    pinchRatios,
    pinchTarget,
    pinching,
    openPalm,
    fingers,
    extendedCount,
    spread: distance3(landmarks[8], landmarks[12]) / palmScale,
    pose,
    gesture: pinchTarget ? `${pinchTarget}_pinch` : openPalm ? "open_palm" : pose,
  };
}

function nearestPinchTarget(ratios) {
  const candidates = Object.entries(ratios)
    .filter(([name, ratio]) => name !== "pinky" && ratio < (name === "index" ? 0.46 : 0.43))
    .sort((left, right) => left[1] - right[1]);
  if (!candidates.length) return "";
  if (candidates.length > 1 && candidates[1][1] - candidates[0][1] < 0.055) return "";
  return candidates[0][0];
}

function fingerExtended(landmarks, mcpIndex, pipIndex, tipIndex) {
  const wrist = landmarks[0];
  const mcp = landmarks[mcpIndex];
  const pip = landmarks[pipIndex];
  const tip = landmarks[tipIndex];
  const angle = jointAngle(mcp, pip, tip);
  return angle > 2.42 && distance3(wrist, tip) > distance3(wrist, pip) * 1.04;
}

function jointAngle(a, center, c) {
  const ax = (a?.x || 0) - (center?.x || 0);
  const ay = (a?.y || 0) - (center?.y || 0);
  const az = (a?.z || 0) - (center?.z || 0);
  const cx = (c?.x || 0) - (center?.x || 0);
  const cy = (c?.y || 0) - (center?.y || 0);
  const cz = (c?.z || 0) - (center?.z || 0);
  const denominator = Math.max(Math.hypot(ax, ay, az) * Math.hypot(cx, cy, cz), 1e-6);
  return Math.acos(Math.max(-1, Math.min(1, (ax * cx + ay * cy + az * cz) / denominator)));
}

function averagePoint(points) {
  const total = points.reduce(
    (result, point) => ({ x: result.x + (point?.x || 0), y: result.y + (point?.y || 0), z: result.z + (point?.z || 0) }),
    { x: 0, y: 0, z: 0 }
  );
  return { x: total.x / points.length, y: total.y / points.length, z: total.z / points.length };
}

function distance3(a, b) {
  return Math.hypot((a?.x || 0) - (b?.x || 0), (a?.y || 0) - (b?.y || 0), (a?.z || 0) - (b?.z || 0));
}
