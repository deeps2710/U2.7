import * as THREE from "./vendor/three.module.min.js";

export function createPhotoReliefModeler({ canvas, onStatus } = {}) {
  let renderer = null;
  let scene = null;
  let camera = null;
  let modelGroup = null;
  let contentGroup = null;
  let depthData = null;
  let reliefMesh = null;
  let depthScale = 0.72;
  let modelScale = 1;
  let wireframe = false;
  let animation = null;
  let resizeObserver = null;
  let dragging = false;
  let lastPointer = null;
  let sourceName = "ultron-model";

  function initialize() {
    if (renderer || !canvas) return;
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x030607, 1);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.96;

    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x030607, 0.055);
    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 50);
    camera.position.set(0, 0.15, 6.8);
    modelGroup = new THREE.Group();
    contentGroup = new THREE.Group();
    modelGroup.add(contentGroup);
    scene.add(modelGroup);

    scene.add(new THREE.HemisphereLight(0xbcefff, 0x07120d, 1.35));
    const key = new THREE.DirectionalLight(0x7fffc0, 2.1);
    key.position.set(2.6, 3.4, 4.8);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x67cce6, 1.25);
    rim.position.set(-3.4, 0.8, -1.4);
    scene.add(rim);
    const grid = new THREE.GridHelper(12, 24, 0x245e58, 0x102a2b);
    grid.position.y = -2.45;
    grid.material.transparent = true;
    grid.material.opacity = 0.28;
    scene.add(grid);

    bindPointerControls();
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
    resize();
    animate();
  }

  async function buildFromImage(dataUrl, options = {}) {
    initialize();
    onStatus?.("processing", "Constructing isolated-object relief");
    const image = await loadImage(dataUrl);
    sourceName = slug(options.name || "isolated-object-relief");
    const aspect = image.naturalWidth / Math.max(1, image.naturalHeight);
    const maxVertices = 92;
    const columns = aspect >= 1 ? maxVertices : Math.max(36, Math.round(maxVertices * aspect));
    const rows = aspect >= 1 ? Math.max(36, Math.round(maxVertices / aspect)) : maxVertices;
    const sample = document.createElement("canvas");
    sample.width = columns;
    sample.height = rows;
    const context = sample.getContext("2d", { willReadFrequently: true });
    context.drawImage(image, 0, 0, columns, rows);
    const pixels = context.getImageData(0, 0, columns, rows).data;
    const luminance = new Float32Array(columns * rows);
    let average = 0;
    let opaquePixels = 0;
    for (let index = 0; index < luminance.length; index += 1) {
      const offset = index * 4;
      const alpha = pixels[offset + 3] / 255;
      const value = (pixels[offset] * 0.2126 + pixels[offset + 1] * 0.7152 + pixels[offset + 2] * 0.0722) / 255;
      luminance[index] = alpha > 0.05 ? value : -1;
      if (alpha > 0.05) {
        average += value;
        opaquePixels += 1;
      }
    }
    average /= Math.max(1, opaquePixels);
    for (let index = 0; index < luminance.length; index += 1) {
      if (luminance[index] < 0) luminance[index] = average;
    }
    depthData = new Float32Array(luminance.length);
    for (let y = 0; y < rows; y += 1) {
      for (let x = 0; x < columns; x += 1) {
        const index = y * columns + x;
        const center = luminance[index];
        const left = luminance[y * columns + Math.max(0, x - 1)];
        const right = luminance[y * columns + Math.min(columns - 1, x + 1)];
        const above = luminance[Math.max(0, y - 1) * columns + x];
        const below = luminance[Math.min(rows - 1, y + 1) * columns + x];
        depthData[index] = (average - center) * 0.82 + (Math.abs(left - right) + Math.abs(above - below)) * 0.55;
      }
    }

    clearModel();
    const displayWidth = aspect >= 1 ? 4.8 : 4.8 * aspect;
    const displayHeight = aspect >= 1 ? 4.8 / aspect : 4.8;
    const geometry = new THREE.PlaneGeometry(displayWidth, displayHeight, columns - 1, rows - 1);
    applyDepth(geometry);
    const texture = new THREE.Texture(image);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    texture.needsUpdate = true;
    reliefMesh = new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({ map: texture, side: THREE.DoubleSide, transparent: true, alphaTest: 0.08, roughness: 0.68, metalness: 0.08, wireframe })
    );
    contentGroup.add(reliefMesh);
    frameContent();
    resetView();
    const stats = modelStats();
    onStatus?.("ready", "Isolated-object relief ready");
    return { ...stats, approximate: true, mode: "isolated_relief" };
  }

  function buildFromScene(sceneSpec) {
    initialize();
    clearModel();
    const objects = Array.isArray(sceneSpec?.objects) ? sceneSpec.objects : [];
    if (!objects.length) throw new Error("The generated scene contains no supported objects.");
    sourceName = slug(sceneSpec.name || "generated-model");
    for (const part of objects) {
      const geometry = primitiveGeometry(part.shape);
      if (!geometry) continue;
      const material = new THREE.MeshStandardMaterial({
        color: validColor(part.color) ? part.color : "#55e6a2",
        roughness: 0.58,
        metalness: 0.12,
        wireframe,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.fromArray(vector(part.position, [0, 0, 0]));
      mesh.rotation.fromArray([...vector(part.rotation, [0, 0, 0]), "XYZ"]);
      mesh.scale.fromArray(vector(part.scale, [1, 1, 1], 0.05));
      contentGroup.add(mesh);
    }
    if (!contentGroup.children.length) throw new Error("The generated scene contains no renderable primitives.");
    frameContent();
    resetView();
    const stats = modelStats();
    onStatus?.("ready", `${sceneSpec.name || "Generated model"} ready`);
    return { ...stats, approximate: Boolean(sceneSpec.approximate), mode: "generated_scene" };
  }

  function buildFromScan(captures, options = {}) {
    initialize();
    const valid = (captures || []).filter((capture) => Array.isArray(capture?.profile) && capture.profile.length >= 12);
    if (!valid.length) throw new Error("No usable object silhouettes were captured.");
    clearModel();
    sourceName = slug(options.name || `${valid[0].label || "object"}-360-scan`);
    const sampleCount = Math.min(...valid.map((capture) => capture.profile.length));
    const geometry = valid.length >= 3
      ? multiViewScanGeometry(valid, sampleCount)
      : rotationalProfileGeometry(valid, sampleCount);
    const color = averageColor(valid.map((capture) => capture.color));
    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({ color, roughness: 0.52, metalness: 0.16, wireframe, side: THREE.DoubleSide })
    );
    contentGroup.add(mesh);
    frameContent();
    resetView();
    const stats = modelStats();
    onStatus?.("ready", valid.length > 1 ? `360 scan fused from ${valid.length} views` : `${valid[0].label || "Object"} single-view profile ready`);
    return { ...stats, approximate: true, mode: valid.length > 1 ? "scan_360" : "single_view_profile", views: valid.length };
  }

  function applyDepth(geometry = reliefMesh?.geometry) {
    if (!geometry || !depthData) return;
    const positions = geometry.getAttribute("position");
    const count = Math.min(positions.count, depthData.length);
    for (let index = 0; index < count; index += 1) positions.setZ(index, depthData[index] * depthScale);
    positions.needsUpdate = true;
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();
  }

  function setDepth(value) {
    depthScale = THREE.MathUtils.clamp(Number(value) || 0.1, 0.08, 1.8);
    applyDepth();
  }

  function setModelScale(value) {
    initialize();
    modelScale = THREE.MathUtils.clamp(Number(value) || 1, 0.2, 3.2);
    modelGroup.scale.setScalar(modelScale);
    return modelScale;
  }

  function scaleBy(factor) {
    return setModelScale(modelScale * Number(factor || 1));
  }

  function setVisible(visible) {
    initialize();
    modelGroup.visible = Boolean(visible);
    return modelGroup.visible;
  }

  function setWireframe(enabled) {
    wireframe = Boolean(enabled);
    contentGroup?.traverse((child) => {
      if (child.isMesh) child.material.wireframe = wireframe;
    });
  }

  function resetView() {
    if (!modelGroup || !camera) return;
    modelGroup.rotation.set(-0.18, 0.58, 0);
    setModelScale(1);
    modelGroup.visible = true;
    camera.position.set(0, 0.15, 6.8);
  }

  function rotateBy(deltaX, deltaY) {
    if (!modelGroup) return;
    modelGroup.rotation.y += deltaX * 0.006;
    modelGroup.rotation.x = THREE.MathUtils.clamp(modelGroup.rotation.x + deltaY * 0.005, -1.2, 1.2);
  }

  function clearModel() {
    if (!contentGroup) return;
    for (const child of [...contentGroup.children]) {
      contentGroup.remove(child);
      child.traverse((item) => {
        if (!item.isMesh) return;
        item.geometry?.dispose();
        item.material?.map?.dispose();
        item.material?.dispose();
      });
    }
    contentGroup.position.set(0, 0, 0);
    contentGroup.scale.set(1, 1, 1);
    reliefMesh = null;
    depthData = null;
  }

  function exportOBJ() {
    if (!hasModel()) throw new Error("Create a 3D model before exporting it.");
    modelGroup.updateMatrixWorld(true);
    const lines = ["# ULTRON 2.7 validated 3D model", `o ${sourceName}`];
    let vertexOffset = 0;
    let vertexCount = 0;
    let triangleCount = 0;
    const point = new THREE.Vector3();
    contentGroup.traverse((child) => {
      if (!child.isMesh) return;
      const geometry = child.geometry;
      const positions = geometry.getAttribute("position");
      for (let index = 0; index < positions.count; index += 1) {
        point.fromBufferAttribute(positions, index).applyMatrix4(child.matrixWorld);
        lines.push(`v ${point.x.toFixed(6)} ${point.y.toFixed(6)} ${point.z.toFixed(6)}`);
      }
      const indices = geometry.index?.array;
      if (indices) {
        for (let index = 0; index < indices.length; index += 3) {
          lines.push(`f ${indices[index] + 1 + vertexOffset} ${indices[index + 1] + 1 + vertexOffset} ${indices[index + 2] + 1 + vertexOffset}`);
          triangleCount += 1;
        }
      } else {
        for (let index = 0; index < positions.count; index += 3) {
          lines.push(`f ${index + 1 + vertexOffset} ${index + 2 + vertexOffset} ${index + 3 + vertexOffset}`);
          triangleCount += 1;
        }
      }
      vertexOffset += positions.count;
      vertexCount += positions.count;
    });
    const blob = new Blob([lines.join("\n") + "\n"], { type: "text/plain" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${sourceName}.obj`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    return { filename: link.download, vertices: vertexCount, triangles: triangleCount };
  }

  function frameContent() {
    contentGroup.position.set(0, 0, 0);
    contentGroup.scale.set(1, 1, 1);
    contentGroup.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(contentGroup);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    contentGroup.position.sub(center);
    contentGroup.scale.setScalar(2.75 / Math.max(size.x, size.y, size.z, 0.1));
  }

  function modelStats() {
    let vertices = 0;
    let triangles = 0;
    contentGroup?.traverse((child) => {
      if (!child.isMesh) return;
      vertices += child.geometry.getAttribute("position")?.count || 0;
      triangles += child.geometry.index ? child.geometry.index.count / 3 : (child.geometry.getAttribute("position")?.count || 0) / 3;
    });
    return { vertices: Math.round(vertices), triangles: Math.round(triangles) };
  }

  function hasModel() {
    return Boolean(contentGroup?.children.length);
  }

  function bindPointerControls() {
    canvas.addEventListener("pointerdown", (event) => {
      dragging = true;
      lastPointer = { x: event.clientX, y: event.clientY };
      canvas.setPointerCapture?.(event.pointerId);
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!dragging || !lastPointer) return;
      rotateBy(event.clientX - lastPointer.x, event.clientY - lastPointer.y);
      lastPointer = { x: event.clientX, y: event.clientY };
    });
    const release = () => {
      dragging = false;
      lastPointer = null;
    };
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener("wheel", (event) => {
      event.preventDefault();
      camera.position.z = THREE.MathUtils.clamp(camera.position.z + event.deltaY * 0.006, 3.2, 10);
    }, { passive: false });
  }

  function resize() {
    if (!renderer || !camera) return;
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  function animate() {
    animation = window.requestAnimationFrame(animate);
    if (renderer && scene && camera) renderer.render(scene, camera);
  }

  function dispose() {
    if (animation) window.cancelAnimationFrame(animation);
    resizeObserver?.disconnect();
    clearModel();
    renderer?.dispose();
  }

  return {
    buildFromImage,
    buildFromScene,
    buildFromScan,
    setDepth,
    setModelScale,
    scaleBy,
    setVisible,
    setWireframe,
    resetView,
    rotateBy,
    clearModel,
    exportOBJ,
    resize,
    dispose,
    get hasModel() { return hasModel(); },
    get scale() { return modelScale; },
  };
}

function rotationalProfileGeometry(captures, sampleCount) {
  const profile = new Array(sampleCount).fill(0);
  for (const capture of captures) {
    for (let index = 0; index < sampleCount; index += 1) profile[index] += Number(capture.profile[index]) || 0;
  }
  for (let index = 0; index < sampleCount; index += 1) profile[index] /= captures.length;
  const averageAspect = captures.reduce((sum, capture) => sum + Math.min(1.2, Number(capture.aspect) || 0.5), 0) / captures.length;
  const maxRadius = THREE.MathUtils.clamp(2.0 * averageAspect, 0.55, 2.0);
  const points = [];
  for (let index = 0; index < sampleCount; index += 1) {
    const sourceIndex = sampleCount - 1 - index;
    const y = -2.4 + (index / (sampleCount - 1)) * 4.8;
    const endTaper = Math.min(1, index / 2, (sampleCount - 1 - index) / 2);
    const radius = Math.max(0.035, profile[sourceIndex] * maxRadius * (0.45 + endTaper * 0.55));
    points.push(new THREE.Vector2(radius, y));
  }
  return new THREE.LatheGeometry(points, 64);
}

function multiViewScanGeometry(captures, sampleCount) {
  const angularSegments = Math.max(48, captures.length * 4);
  const vertices = [];
  const indices = [];
  for (let row = 0; row < sampleCount; row += 1) {
    const sourceIndex = sampleCount - 1 - row;
    const y = -2.4 + (row / (sampleCount - 1)) * 4.8;
    const endTaper = Math.min(1, row / 2, (sampleCount - 1 - row) / 2);
    for (let segment = 0; segment < angularSegments; segment += 1) {
      const capturePosition = (segment / angularSegments) * captures.length;
      const leftIndex = Math.floor(capturePosition) % captures.length;
      const rightIndex = (leftIndex + 1) % captures.length;
      const blend = capturePosition - Math.floor(capturePosition);
      const left = captures[leftIndex];
      const right = captures[rightIndex];
      const leftRadius = (Number(left.profile[sourceIndex]) || 0) * scanRadius(left);
      const rightRadius = (Number(right.profile[sourceIndex]) || 0) * scanRadius(right);
      const radius = Math.max(0.035, THREE.MathUtils.lerp(leftRadius, rightRadius, blend) * (0.45 + endTaper * 0.55));
      const angle = (segment / angularSegments) * Math.PI * 2;
      vertices.push(Math.cos(angle) * radius, y, Math.sin(angle) * radius);
    }
  }
  for (let row = 0; row < sampleCount - 1; row += 1) {
    for (let segment = 0; segment < angularSegments; segment += 1) {
      const next = (segment + 1) % angularSegments;
      const topLeft = row * angularSegments + segment;
      const topRight = row * angularSegments + next;
      const bottomLeft = (row + 1) * angularSegments + segment;
      const bottomRight = (row + 1) * angularSegments + next;
      indices.push(topLeft, bottomLeft, topRight, topRight, bottomLeft, bottomRight);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function scanRadius(capture) {
  return THREE.MathUtils.clamp(2.0 * Math.min(1.2, Number(capture.aspect) || 0.5), 0.55, 2.0);
}

function primitiveGeometry(shape) {
  if (shape === "box") return new THREE.BoxGeometry(1, 1, 1, 2, 2, 2);
  if (shape === "sphere") return new THREE.SphereGeometry(0.5, 40, 28);
  if (shape === "cylinder") return new THREE.CylinderGeometry(0.5, 0.5, 1, 40, 3);
  if (shape === "cone") return new THREE.ConeGeometry(0.5, 1, 40, 3);
  if (shape === "pyramid") return new THREE.ConeGeometry(0.72, 1, 4, 2);
  if (shape === "torus") return new THREE.TorusGeometry(0.62, 0.22, 24, 56);
  if (shape === "capsule") return new THREE.CapsuleGeometry(0.42, 0.9, 8, 24);
  return null;
}

function vector(value, fallback, minimum = -Infinity) {
  if (!Array.isArray(value) || value.length !== 3) return fallback;
  return value.map((item, index) => Math.max(minimum, Number.isFinite(Number(item)) ? Number(item) : fallback[index]));
}

function validColor(value) {
  return /^#[0-9a-f]{6}$/i.test(String(value || ""));
}

function averageColor(colors) {
  const valid = colors.filter(validColor);
  if (!valid.length) return "#67cce6";
  const totals = [0, 0, 0];
  for (const color of valid) {
    totals[0] += Number.parseInt(color.slice(1, 3), 16);
    totals[1] += Number.parseInt(color.slice(3, 5), 16);
    totals[2] += Number.parseInt(color.slice(5, 7), 16);
  }
  return `#${totals.map((value) => Math.round(value / valid.length).toString(16).padStart(2, "0")).join("")}`;
}

function slug(value) {
  return String(value || "ultron-model").replace(/[^a-z0-9_-]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "ultron-model";
}

function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("The isolated object image could not be loaded."));
    image.src = dataUrl;
  });
}
