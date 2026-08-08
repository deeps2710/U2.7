const MEDIAPIPE_VERSION = "0.10.35";
const MODULE_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}/vision_bundle.mjs`;
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}/wasm`;
const MODEL_URL = "https://storage.googleapis.com/mediapipe-tasks/object_detector/efficientdet_lite0_uint8.tflite";

const LABEL_ALIASES = {
  bottle: ["bottle"],
  cup: ["cup"],
  can: ["bottle", "cup"],
  phone: ["cell phone"],
  book: ["book"],
  chair: ["chair"],
  shoe: ["shoe"],
  vase: ["vase"],
};

export function createObjectScanner({ video, overlay, onStatus, onDetections } = {}) {
  let detector = null;
  let loading = null;
  let runningMode = "IMAGE";

  async function load() {
    if (detector) return detector;
    if (loading) return await loading;
    loading = (async () => {
      onStatus?.("loading", "Loading object detector");
      const { FilesetResolver, ObjectDetector } = await import(MODULE_URL);
      const vision = await FilesetResolver.forVisionTasks(WASM_URL);
      const options = {
        baseOptions: { modelAssetPath: MODEL_URL, delegate: "CPU" },
        runningMode,
        maxResults: 8,
        scoreThreshold: 0.14,
      };
      detector = await ObjectDetector.createFromOptions(vision, options);
      onStatus?.("ready", "Object detector ready");
      return detector;
    })();
    try {
      return await loading;
    } finally {
      loading = null;
    }
  }

  async function captureFromVideo(preferredLabel = "") {
    if (!video?.videoWidth || !video?.videoHeight) throw new Error("Camera frame is not ready.");
    await load();
    await setMode("VIDEO");
    const result = detector.detectForVideo(video, Math.round(performance.now()));
    const detections = result.detections || [];
    onDetections?.(summarizeDetections(detections));
    const detection = chooseDetection(detections, preferredLabel)
      || fallbackObjectDetection(video, video.videoWidth, video.videoHeight, preferredLabel, detections);
    drawDetection(detection, video.videoWidth, video.videoHeight);
    if (!detection) return null;
    return isolateDetection(video, detection, video.videoWidth, video.videoHeight);
  }

  async function captureFromImage(image, preferredLabel = "") {
    const width = image.naturalWidth || image.videoWidth || image.width;
    const height = image.naturalHeight || image.videoHeight || image.height;
    if (!width || !height) throw new Error("Image dimensions are unavailable.");
    await load();
    await setMode("IMAGE");
    const result = detector.detect(image);
    const detections = result.detections || [];
    onDetections?.(summarizeDetections(detections));
    const detection = chooseDetection(detections, preferredLabel)
      || fallbackObjectDetection(image, width, height, preferredLabel, detections);
    drawDetection(detection, width, height);
    if (!detection) return null;
    return isolateDetection(image, detection, width, height);
  }

  async function setMode(mode) {
    if (runningMode === mode) return;
    await detector.setOptions({ runningMode: mode });
    runningMode = mode;
  }

  function clearOverlay() {
    if (!overlay) return;
    overlay.getContext("2d").clearRect(0, 0, overlay.width, overlay.height);
  }

  function drawDetection(detection, width, height) {
    if (!overlay) return;
    if (overlay.width !== width || overlay.height !== height) {
      overlay.width = width;
      overlay.height = height;
    }
    const context = overlay.getContext("2d");
    context.clearRect(0, 0, width, height);
    if (!detection) return;
    const box = detection.boundingBox;
    const mirroredX = width - box.originX - box.width;
    context.strokeStyle = "#f1c66d";
    context.lineWidth = Math.max(3, width / 320);
    context.strokeRect(mirroredX, box.originY, box.width, box.height);
    context.fillStyle = "rgba(3, 7, 8, 0.82)";
    context.fillRect(mirroredX, Math.max(0, box.originY - 32), Math.min(box.width, 190), 30);
    context.fillStyle = "#f1c66d";
    context.font = `${Math.max(16, Math.round(width / 42))}px Segoe UI`;
    const label = detection.categories?.[0]?.categoryName || "object";
    const score = Math.round((detection.categories?.[0]?.score || 0) * 100);
    context.fillText(`${label} ${score}%`, mirroredX + 7, Math.max(20, box.originY - 9));
  }

  function dispose() {
    clearOverlay();
    detector?.close?.();
    detector = null;
  }

  return { load, captureFromVideo, captureFromImage, clearOverlay, dispose };
}

function summarizeDetections(detections) {
  return detections.slice(0, 8).map((detection) => ({
    label: String(detection.categories?.[0]?.categoryName || ""),
    score: Number(detection.categories?.[0]?.score || 0),
    boundingBox: detection.boundingBox,
  }));
}

export function chooseDetection(detections, preferredLabel = "") {
  const aliases = LABEL_ALIASES[String(preferredLabel || "").toLowerCase()] || [String(preferredLabel || "").toLowerCase()];
  const candidates = detections
    .filter((detection) => detection?.boundingBox && detection.categories?.length)
    .map((detection) => {
      const category = detection.categories[0];
      const label = String(category.categoryName || category.displayName || "").toLowerCase();
      const area = Math.max(1, detection.boundingBox.width * detection.boundingBox.height);
      const preferred = aliases.some((alias) => alias && label.includes(alias));
      return { detection, label, preferred, rank: (category.score || 0) * Math.sqrt(area) * (preferred ? 4 : 1) };
    })
    .filter((item) => item.label !== "person");
  if (!candidates.length) return null;
  candidates.sort((left, right) => right.rank - left.rank);
  const preferred = candidates.find((candidate) => candidate.preferred);
  return preferred?.detection || (String(preferredLabel || "").trim() ? null : candidates[0].detection);
}

function fallbackObjectDetection(source, sourceWidth, sourceHeight, preferredLabel, detections = []) {
  const target = String(preferredLabel || "").toLowerCase();
  if (!/\b(?:bottle|can|cup|vase)\b/.test(target)) return null;
  const scale = Math.min(1, 320 / Math.max(sourceWidth, sourceHeight));
  const width = Math.max(32, Math.round(sourceWidth * scale));
  const height = Math.max(32, Math.round(sourceHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(source, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height).data;
  const mask = new Uint8Array(width * height);
  for (let index = 0; index < mask.length; index += 1) {
    const offset = index * 4;
    const red = pixels[offset];
    const green = pixels[offset + 1];
    const blue = pixels[offset + 2];
    const maximum = Math.max(red, green, blue);
    const minimum = Math.min(red, green, blue);
    const saturation = maximum ? (maximum - minimum) / maximum : 0;
    mask[index] = red > 65 && saturation > 0.24 && red > green * 1.12 && red > blue * 1.06 ? 1 : 0;
  }
  const closed = closeMask(mask, width, height, 2);
  const bounds = bestTallComponent(closed, width, height);
  const selected = bounds || salientTallRegion(pixels, width, height, sourceWidth, sourceHeight, detections);
  if (!selected) return null;
  const inverse = 1 / scale;
  return {
    boundingBox: {
      originX: Math.max(0, Math.floor(selected.left * inverse)),
      originY: Math.max(0, Math.floor(selected.top * inverse)),
      width: Math.min(sourceWidth, Math.ceil((selected.right - selected.left + 1) * inverse)),
      height: Math.min(sourceHeight, Math.ceil((selected.bottom - selected.top + 1) * inverse)),
    },
    categories: [{ categoryName: target || "bottle", displayName: target || "bottle", score: 0.28 }],
  };
}

function salientTallRegion(pixels, width, height, sourceWidth, sourceHeight, detections) {
  const area = width * height;
  const gray = new Float32Array(area);
  const saturation = new Float32Array(area);
  for (let index = 0; index < area; index += 1) {
    const offset = index * 4;
    const red = pixels[offset];
    const green = pixels[offset + 1];
    const blue = pixels[offset + 2];
    gray[index] = red * 0.2126 + green * 0.7152 + blue * 0.0722;
    const maximum = Math.max(red, green, blue);
    saturation[index] = maximum ? (maximum - Math.min(red, green, blue)) / maximum : 0;
  }
  const edge = new Float32Array(area);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x;
      edge[index] = Math.min(100, Math.abs(gray[index + 1] - gray[index - 1]) + Math.abs(gray[index + width] - gray[index - width]));
    }
  }
  const edgeIntegral = integralImage(edge, width, height);
  const grayIntegral = integralImage(gray, width, height);
  const graySquared = new Float32Array(area);
  for (let index = 0; index < area; index += 1) graySquared[index] = gray[index] * gray[index];
  const graySquaredIntegral = integralImage(graySquared, width, height);
  const saturationIntegral = integralImage(saturation, width, height);
  const scaleX = width / sourceWidth;
  const scaleY = height / sourceHeight;
  const people = detections
    .filter((detection) => {
      if (String(detection.categories?.[0]?.categoryName || "").toLowerCase() !== "person") return false;
      const box = detection.boundingBox;
      const areaRatio = (box.width * box.height) / Math.max(1, sourceWidth * sourceHeight);
      return box.width / sourceWidth < 0.75 && areaRatio < 0.7;
    })
    .map((detection) => ({
      left: detection.boundingBox.originX * scaleX,
      top: detection.boundingBox.originY * scaleY,
      right: (detection.boundingBox.originX + detection.boundingBox.width) * scaleX,
      bottom: (detection.boundingBox.originY + detection.boundingBox.height) * scaleY,
    }));
  let best = null;
  const widths = [20, 26, 32, 38, 44, 50];
  const heights = [80, 100, 120, 140, 160];
  for (const boxWidth of widths) {
    for (const boxHeight of heights) {
      if (boxWidth >= width || boxHeight >= height || boxHeight / boxWidth < 1.7 || boxHeight / boxWidth > 6) continue;
      for (let y = 4; y + boxHeight < height - 4; y += 6) {
        for (let x = 4; x + boxWidth < width - 4; x += 6) {
          if (x < width * 0.1 || x + boxWidth > width * 0.86) continue;
          const boxArea = boxWidth * boxHeight;
          if (people.some((person) => overlapArea(x, y, boxWidth, boxHeight, person) / boxArea > 0.32)) continue;
          const edgeMean = integralSum(edgeIntegral, width, x, y, boxWidth, boxHeight) / boxArea;
          const grayMean = integralSum(grayIntegral, width, x, y, boxWidth, boxHeight) / boxArea;
          const variance = Math.max(0, integralSum(graySquaredIntegral, width, x, y, boxWidth, boxHeight) / boxArea - grayMean * grayMean);
          const saturationMean = integralSum(saturationIntegral, width, x, y, boxWidth, boxHeight) / boxArea;
          if (saturationMean < 0.08) continue;
          const score = edgeMean * 1.8 + Math.sqrt(variance) * 0.8 + saturationMean * 8;
          if (score < 55 || (best && score <= best.score)) continue;
          best = { score, left: x, top: y, right: x + boxWidth - 1, bottom: y + boxHeight - 1 };
        }
      }
    }
  }
  return best;
}

function integralImage(values, width, height) {
  const stride = width + 1;
  const integral = new Float64Array(stride * (height + 1));
  for (let y = 1; y <= height; y += 1) {
    let row = 0;
    for (let x = 1; x <= width; x += 1) {
      row += values[(y - 1) * width + x - 1];
      integral[y * stride + x] = integral[(y - 1) * stride + x] + row;
    }
  }
  return integral;
}

function integralSum(integral, width, x, y, boxWidth, boxHeight) {
  const stride = width + 1;
  const right = x + boxWidth;
  const bottom = y + boxHeight;
  return integral[bottom * stride + right] - integral[y * stride + right] - integral[bottom * stride + x] + integral[y * stride + x];
}

function overlapArea(x, y, width, height, bounds) {
  const overlapWidth = Math.max(0, Math.min(x + width, bounds.right) - Math.max(x, bounds.left));
  const overlapHeight = Math.max(0, Math.min(y + height, bounds.bottom) - Math.max(y, bounds.top));
  return overlapWidth * overlapHeight;
}

function closeMask(mask, width, height, radius) {
  const dilated = new Uint8Array(mask.length);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let active = 0;
      for (let dy = -radius; dy <= radius && !active; dy += 1) {
        for (let dx = -radius; dx <= radius; dx += 1) {
          const nx = x + dx;
          const ny = y + dy;
          if (nx >= 0 && nx < width && ny >= 0 && ny < height && mask[ny * width + nx]) {
            active = 1;
            break;
          }
        }
      }
      dilated[y * width + x] = active;
    }
  }
  const eroded = new Uint8Array(mask.length);
  for (let y = radius; y < height - radius; y += 1) {
    for (let x = radius; x < width - radius; x += 1) {
      let active = 1;
      for (let dy = -radius; dy <= radius && active; dy += 1) {
        for (let dx = -radius; dx <= radius; dx += 1) {
          if (!dilated[(y + dy) * width + x + dx]) {
            active = 0;
            break;
          }
        }
      }
      eroded[y * width + x] = active;
    }
  }
  return eroded;
}

function bestTallComponent(mask, width, height) {
  const visited = new Uint8Array(mask.length);
  const queue = new Int32Array(mask.length);
  let best = null;
  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || visited[start]) continue;
    let head = 0;
    let tail = 0;
    let area = 0;
    let left = width;
    let right = 0;
    let top = height;
    let bottom = 0;
    queue[tail++] = start;
    visited[start] = 1;
    while (head < tail) {
      const index = queue[head++];
      const x = index % width;
      const y = Math.floor(index / width);
      area += 1;
      left = Math.min(left, x);
      right = Math.max(right, x);
      top = Math.min(top, y);
      bottom = Math.max(bottom, y);
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          if (!dx && !dy) continue;
          const nx = x + dx;
          const ny = y + dy;
          if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue;
          const next = ny * width + nx;
          if (!mask[next] || visited[next]) continue;
          visited[next] = 1;
          queue[tail++] = next;
        }
      }
    }
    const boxWidth = right - left + 1;
    const boxHeight = bottom - top + 1;
    const areaRatio = area / mask.length;
    const touchesEdge = left <= 2 || right >= width - 3 || top <= 2 || bottom >= height - 3;
    const aspect = boxHeight / Math.max(1, boxWidth);
    const fill = area / Math.max(1, boxWidth * boxHeight);
    if (touchesEdge || areaRatio < 0.002 || areaRatio > 0.22 || boxHeight < height * 0.16 || aspect < 1.35) continue;
    const score = area * Math.min(3.5, aspect) * (0.45 + fill);
    if (!best || score > best.score) best = { score, left, right, top, bottom };
  }
  return best;
}

function isolateDetection(source, detection, sourceWidth, sourceHeight) {
  const raw = detection.boundingBox;
  const paddingX = raw.width * 0.14;
  const paddingY = raw.height * 0.1;
  const x = Math.max(0, Math.floor(raw.originX - paddingX));
  const y = Math.max(0, Math.floor(raw.originY - paddingY));
  const width = Math.min(sourceWidth - x, Math.ceil(raw.width + paddingX * 2));
  const height = Math.min(sourceHeight - y, Math.ceil(raw.height + paddingY * 2));
  const maxSide = 360;
  const scale = Math.min(1, maxSide / Math.max(width, height));
  const crop = document.createElement("canvas");
  crop.width = Math.max(32, Math.round(width * scale));
  crop.height = Math.max(32, Math.round(height * scale));
  crop.getContext("2d", { willReadFrequently: true }).drawImage(source, x, y, width, height, 0, 0, crop.width, crop.height);
  const isolated = isolateForeground(crop);
  const category = detection.categories[0];
  return {
    label: String(category.categoryName || category.displayName || "object").toLowerCase(),
    score: Number(category.score || 0),
    boundingBox: { x, y, width, height, sourceWidth, sourceHeight },
    image: isolated.image,
    profile: isolated.profile,
    color: isolated.color,
    aspect: isolated.aspect,
    signature: isolated.signature,
    foregroundRatio: isolated.foregroundRatio,
  };
}

export function isolateForeground(canvas) {
  const context = canvas.getContext("2d", { willReadFrequently: true });
  const width = canvas.width;
  const height = canvas.height;
  const image = context.getImageData(0, 0, width, height);
  const data = image.data;
  const border = [];
  const borderSize = Math.max(2, Math.round(Math.min(width, height) * 0.04));
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (x >= borderSize && x < width - borderSize && y >= borderSize && y < height - borderSize) continue;
      const offset = (y * width + x) * 4;
      border.push([data[offset], data[offset + 1], data[offset + 2]]);
    }
  }
  const background = [0, 1, 2].map((channel) => median(border.map((sample) => sample[channel])));
  const distances = border.map((sample) => colorDistance(sample, background));
  const threshold = Math.max(34, median(distances) * 2.4);
  const mask = new Uint8Array(width * height);
  for (let index = 0; index < mask.length; index += 1) {
    const offset = index * 4;
    const distance = colorDistance([data[offset], data[offset + 1], data[offset + 2]], background);
    mask[index] = distance >= threshold ? 1 : 0;
  }
  const component = centralComponent(mask, width, height);
  const selectedMask = component.mask;
  const bounds = component.bounds || { left: 0, top: 0, right: width - 1, bottom: height - 1 };
  const outputWidth = Math.max(2, bounds.right - bounds.left + 1);
  const outputHeight = Math.max(2, bounds.bottom - bounds.top + 1);
  const output = document.createElement("canvas");
  output.width = outputWidth;
  output.height = outputHeight;
  const outputContext = output.getContext("2d");
  const outputImage = outputContext.createImageData(outputWidth, outputHeight);
  let red = 0;
  let green = 0;
  let blue = 0;
  let foreground = 0;
  for (let y = bounds.top; y <= bounds.bottom; y += 1) {
    for (let x = bounds.left; x <= bounds.right; x += 1) {
      const sourceIndex = y * width + x;
      if (!selectedMask[sourceIndex]) continue;
      const sourceOffset = sourceIndex * 4;
      const outputOffset = ((y - bounds.top) * outputWidth + (x - bounds.left)) * 4;
      outputImage.data[outputOffset] = data[sourceOffset];
      outputImage.data[outputOffset + 1] = data[sourceOffset + 1];
      outputImage.data[outputOffset + 2] = data[sourceOffset + 2];
      outputImage.data[outputOffset + 3] = 255;
      red += data[sourceOffset];
      green += data[sourceOffset + 1];
      blue += data[sourceOffset + 2];
      foreground += 1;
    }
  }
  outputContext.putImageData(outputImage, 0, 0);
  const profile = widthProfile(selectedMask, width, height, bounds, 72);
  return {
    image: output.toDataURL("image/png"),
    profile,
    color: rgbToHex(red / Math.max(1, foreground), green / Math.max(1, foreground), blue / Math.max(1, foreground)),
    aspect: outputWidth / outputHeight,
    signature: profileSignature(profile, outputImage.data),
    foregroundRatio: foreground / Math.max(1, outputWidth * outputHeight),
  };
}

function centralComponent(mask, width, height) {
  const visited = new Uint8Array(mask.length);
  let best = null;
  const centerX = width / 2;
  const centerY = height / 2;
  const queue = new Int32Array(mask.length);
  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || visited[start]) continue;
    let head = 0;
    let tail = 0;
    queue[tail++] = start;
    visited[start] = 1;
    const pixels = [];
    let left = width;
    let right = 0;
    let top = height;
    let bottom = 0;
    let sumX = 0;
    let sumY = 0;
    while (head < tail) {
      const index = queue[head++];
      pixels.push(index);
      const x = index % width;
      const y = Math.floor(index / width);
      left = Math.min(left, x);
      right = Math.max(right, x);
      top = Math.min(top, y);
      bottom = Math.max(bottom, y);
      sumX += x;
      sumY += y;
      const neighbors = [index - 1, index + 1, index - width, index + width];
      for (const next of neighbors) {
        if (next < 0 || next >= mask.length || visited[next] || !mask[next]) continue;
        const nx = next % width;
        if (Math.abs(nx - x) > 1) continue;
        visited[next] = 1;
        queue[tail++] = next;
      }
    }
    if (pixels.length < mask.length * 0.004) continue;
    const centroidX = sumX / pixels.length;
    const centroidY = sumY / pixels.length;
    const centerDistance = Math.hypot((centroidX - centerX) / width, (centroidY - centerY) / height);
    const score = pixels.length * (1.25 - Math.min(0.8, centerDistance));
    if (!best || score > best.score) best = { score, pixels, bounds: { left, right, top, bottom } };
  }
  const selected = new Uint8Array(mask.length);
  for (const index of best?.pixels || []) selected[index] = 1;
  return { mask: selected, bounds: best?.bounds || null };
}

function widthProfile(mask, width, height, bounds, samples) {
  const values = new Array(samples).fill(0);
  const objectWidth = Math.max(1, bounds.right - bounds.left + 1);
  for (let sample = 0; sample < samples; sample += 1) {
    const y = Math.min(bounds.bottom, Math.round(bounds.top + (sample / (samples - 1)) * (bounds.bottom - bounds.top)));
    let left = width;
    let right = -1;
    for (let x = bounds.left; x <= bounds.right; x += 1) {
      if (!mask[y * width + x]) continue;
      left = Math.min(left, x);
      right = Math.max(right, x);
    }
    values[sample] = right >= left ? (right - left + 1) / objectWidth : sample ? values[sample - 1] : 0;
  }
  for (let pass = 0; pass < 3; pass += 1) {
    const copy = values.slice();
    for (let index = 1; index < values.length - 1; index += 1) values[index] = (copy[index - 1] + copy[index] * 2 + copy[index + 1]) / 4;
  }
  const max = Math.max(...values, 0.01);
  return values.map((value) => Math.max(0.035, Math.min(1, value / max)));
}

function profileSignature(profile, rgba) {
  const signature = profile.filter((_value, index) => index % 6 === 0).map((value) => Math.round(value * 100) / 100);
  let alphaCount = 0;
  let luminance = 0;
  for (let offset = 0; offset < rgba.length; offset += 16) {
    if (!rgba[offset + 3]) continue;
    luminance += (rgba[offset] * 0.21 + rgba[offset + 1] * 0.72 + rgba[offset + 2] * 0.07) / 255;
    alphaCount += 1;
  }
  signature.push(Math.round((luminance / Math.max(1, alphaCount)) * 100) / 100);
  return signature;
}

export function signatureDistance(left, right) {
  if (!left?.length || !right?.length) return 1;
  const count = Math.min(left.length, right.length);
  let total = 0;
  for (let index = 0; index < count; index += 1) total += Math.abs(left[index] - right[index]);
  return total / count;
}

function median(values) {
  if (!values.length) return 0;
  const sorted = values.slice().sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)];
}

function colorDistance(left, right) {
  return Math.hypot(left[0] - right[0], left[1] - right[1], left[2] - right[2]);
}

function rgbToHex(red, green, blue) {
  return `#${[red, green, blue].map((value) => Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, "0")).join("")}`;
}
