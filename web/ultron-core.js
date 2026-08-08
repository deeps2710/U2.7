import * as THREE from "./vendor/three.module.min.js";

const STATE_PROFILES = {
  inactive: { scale: 0.16, spin: 0.02, ringSpeed: 0.03, neural: 0.06, signal: 0.02, light: 0.08, opacity: 0.15, particles: 0.03, exposure: 0.72 },
  idle: { scale: 0.96, spin: 0.28, ringSpeed: 0.48, neural: 0.72, signal: 0.48, light: 1.0, opacity: 0.94, particles: 0.62, exposure: 1.0 },
  waiting_for_wake_word: { scale: 0.88, spin: 0.15, ringSpeed: 0.24, neural: 0.48, signal: 0.2, light: 0.66, opacity: 0.78, particles: 0.38, exposure: 0.92 },
  listening: { scale: 0.92, spin: 0.12, ringSpeed: 0.2, neural: 0.92, signal: 1.02, light: 0.88, opacity: 0.96, particles: 0.52, exposure: 0.96 },
  transcribing: { scale: 0.96, spin: 0.42, ringSpeed: 0.92, neural: 0.96, signal: 1.18, light: 1.08, opacity: 1.0, particles: 0.78, exposure: 1.0 },
  thinking: { scale: 1.0, spin: 0.78, ringSpeed: 1.82, neural: 1.1, signal: 1.45, light: 1.2, opacity: 1.0, particles: 1.0, exposure: 1.04 },
  speaking: { scale: 1.05, spin: 0.48, ringSpeed: 0.94, neural: 1.22, signal: 1.32, light: 1.34, opacity: 1.0, particles: 0.94, exposure: 1.06 },
};

const STATE_COLORS = {
  inactive: 0x607174,
  idle: 0x55e6a2,
  waiting_for_wake_word: 0xf1c66d,
  listening: 0x67cce6,
  transcribing: 0x67cce6,
  thinking: 0xf1c66d,
  speaking: 0x55e6a2,
};

const pulseMatrix = new THREE.Matrix4();
const pulsePosition = new THREE.Vector3();
const pulseScale = new THREE.Vector3();
const pulseRotation = new THREE.Quaternion();

export function createArmillaryCore({ scene, camera, renderer }) {
  camera.position.set(0, 0.72, 11.6);
  camera.lookAt(0, 0.18, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;

  const root = new THREE.Group();
  root.position.set(0, 0.55, 0);
  root.rotation.x = -0.04;
  scene.add(root);

  const processor = makeProcessor();
  const lattice = makeNeuralLattice();
  const orbitSystem = makeOrbitSystem();
  root.add(processor.group, lattice.group, orbitSystem.group);

  const particles = makeBackgroundParticles();
  scene.add(particles.points);

  const ambient = new THREE.AmbientLight(0x27443f, 0.38);
  const keyLight = new THREE.PointLight(0x55e6a2, 2.2, 7.5, 2.0);
  keyLight.position.set(1.4, 1.6, 2.5);
  const rimLight = new THREE.PointLight(0x67cce6, 1.1, 6.0, 2.0);
  rimLight.position.set(-2.0, -0.8, 1.4);
  scene.add(ambient, keyLight, rimLight);

  const current = { ...STATE_PROFILES.idle };
  const currentColor = new THREE.Color(STATE_COLORS.idle);
  const targetColor = new THREE.Color(STATE_COLORS.idle);
  let visualState = "idle";
  let stateStartedAt = 0;
  let speechStartedAt = 0;
  let speechText = "";
  let textEmphasis = 0.35;
  let voiceProfile = { pitch: 0.86, rate: 0.94, volume: 0.95 };
  let targetRootX = 0;
  let targetRootY = 0.55;
  let bootProgress = 1;
  let bootActive = false;

  return {
    startBoot() {
      bootActive = true;
      bootProgress = 0;
      Object.assign(current, {
        scale: 0.025,
        spin: 0.04,
        ringSpeed: 0.02,
        neural: 0.01,
        signal: 0.01,
        light: 0.02,
        opacity: 0.01,
        particles: 0.01,
        exposure: 0.68,
      });
      root.scale.setScalar(0.01);
      root.position.z = -2.4;
      root.rotation.y = -1.35;
      processor.group.scale.setScalar(0.18);
      lattice.group.scale.setScalar(0.34);
      orbitSystem.group.scale.setScalar(0.5);
      particles.material.opacity = 0;
    },
    setBootProgress(progress) {
      bootProgress = THREE.MathUtils.clamp(Number(progress) || 0, 0, 1);
    },
    finishBoot() {
      bootProgress = 1;
      bootActive = false;
    },
    setState(state) {
      const next = STATE_PROFILES[state] ? state : "idle";
      if (next !== visualState) {
        visualState = next;
        stateStartedAt = performance.now() / 1000;
      }
    },
    setSpeechText(text) {
      speechText = String(text || "");
      speechStartedAt = performance.now() / 1000;
      textEmphasis = estimateTextEmphasis(speechText);
    },
    setVoiceProfile(profile = {}) {
      voiceProfile = {
        pitch: Number(profile.pitch ?? voiceProfile.pitch),
        rate: Number(profile.rate ?? voiceProfile.rate),
        volume: Number(profile.volume ?? voiceProfile.volume),
      };
    },
    setLayoutMode(mode) {
      targetRootX = mode === "compact" ? 0 : -1.72;
      targetRootY = mode === "compact" ? 0.55 : 0.78;
    },
    update(time, state = visualState) {
      if (STATE_PROFILES[state] && state !== visualState) {
        visualState = state;
        stateStartedAt = time;
      }
      const desired = dynamicProfile(
        visualState,
        time - stateStartedAt,
        time - speechStartedAt,
        speechText,
        textEmphasis,
        voiceProfile
      );
      const boot = bootActive ? THREE.MathUtils.smootherstep(bootProgress, 0, 1) : 1;
      const processorReveal = bootActive ? revealStage(bootProgress, 0.01, 0.38) : 1;
      const latticeReveal = bootActive ? revealStage(bootProgress, 0.2, 0.67) : 1;
      const orbitReveal = bootActive ? revealStage(bootProgress, 0.4, 0.84) : 1;
      const particleReveal = bootActive ? revealStage(bootProgress, 0.58, 1) : 1;
      if (bootActive) {
        desired.scale *= THREE.MathUtils.lerp(0.08, 1, boot);
        desired.opacity *= processorReveal;
        desired.neural *= latticeReveal;
        desired.signal *= latticeReveal;
        desired.light *= processorReveal;
        desired.particles *= particleReveal;
        desired.exposure = THREE.MathUtils.lerp(0.68, desired.exposure, boot);
      }
      for (const key of Object.keys(current)) {
        current[key] = bootActive ? desired[key] : THREE.MathUtils.lerp(current[key], desired[key], 0.055);
      }

      targetColor.setHex(STATE_COLORS[visualState] || STATE_COLORS.idle);
      currentColor.lerp(targetColor, 0.045);
      root.position.x = bootActive ? targetRootX * boot : THREE.MathUtils.lerp(root.position.x, targetRootX, 0.08);
      root.position.y = bootActive ? THREE.MathUtils.lerp(0.55, targetRootY, boot) : THREE.MathUtils.lerp(root.position.y, targetRootY, 0.08);
      root.position.z = bootActive ? THREE.MathUtils.lerp(-2.4, 0, boot) : THREE.MathUtils.lerp(root.position.z, 0, 0.1);
      root.scale.setScalar(current.scale);
      root.rotation.y += 0.00135 * current.spin + (bootActive ? (1 - boot) * 0.026 : 0);
      root.rotation.x = -0.04 + Math.sin(time * 0.22) * 0.025 * current.opacity;

      processor.group.scale.setScalar(THREE.MathUtils.lerp(0.18, 1, processorReveal));
      lattice.group.scale.setScalar(THREE.MathUtils.lerp(0.34, 1, latticeReveal));
      orbitSystem.group.scale.setScalar(THREE.MathUtils.lerp(0.5, 1, orbitReveal));
      updateProcessor(processor, time, withReveal(current, processorReveal), currentColor);
      updateNeuralLattice(lattice, time, withReveal(current, latticeReveal), currentColor);
      updateOrbitSystem(orbitSystem, time, withReveal(current, orbitReveal), currentColor);
      updateBackgroundParticles(particles, time, withReveal(current, particleReveal));

      keyLight.color.copy(currentColor);
      keyLight.intensity = (1.35 + current.light * 1.15 + Math.sin(time * 2.8) * current.signal * 0.12) * processorReveal;
      rimLight.intensity = (0.48 + current.neural * 0.58) * latticeReveal;
      renderer.toneMappingExposure = current.exposure;
    },
  };
}

function dynamicProfile(state, stateAge, speechAge, text, textEmphasis, voiceProfile) {
  const base = { ...(STATE_PROFILES[state] || STATE_PROFILES.idle) };
  if (state === "waiting_for_wake_word") {
    const boot = THREE.MathUtils.smootherstep(Math.min(stateAge / 0.7, 1), 0, 1);
    base.scale = THREE.MathUtils.lerp(0.78, base.scale, boot);
    base.opacity = THREE.MathUtils.lerp(0.52, base.opacity, boot);
    base.neural = THREE.MathUtils.lerp(0.28, base.neural, boot);
    base.light = THREE.MathUtils.lerp(0.4, base.light, boot);
  }
  if (state === "inactive") {
    const shutdown = THREE.MathUtils.smootherstep(Math.min(stateAge / 2.7, 1), 0, 1);
    base.scale = THREE.MathUtils.lerp(1.0, base.scale, shutdown);
    base.opacity = THREE.MathUtils.lerp(1.0, base.opacity, shutdown);
    base.neural = THREE.MathUtils.lerp(0.9, base.neural, shutdown);
    base.light = THREE.MathUtils.lerp(1.0, base.light, shutdown);
  }
  if (state !== "speaking") return base;

  const phrase = 0.5 + 0.5 * Math.sin(speechAge * 0.58 + 0.3 * Math.sin(speechAge * 0.2));
  const syllableA = Math.max(0, Math.sin(speechAge * 3.2 + 0.7 * Math.sin(speechAge * 0.7)));
  const syllableB = Math.max(0, Math.sin(speechAge * 5.1 + 1.3));
  const accent = Math.max(syllableA, syllableB * 0.78);
  const pitch = THREE.MathUtils.clamp(Number(voiceProfile.pitch || 0.86), 0, 1.4);
  const rate = THREE.MathUtils.clamp(Number(voiceProfile.rate || 0.94), 0.55, 1.6);
  const volume = THREE.MathUtils.clamp(Number(voiceProfile.volume || 0.95), 0, 1);
  const prosody = THREE.MathUtils.clamp(textEmphasis * 0.46 + pitch * 0.24 + volume * 0.24 + rate * 0.08, 0.3, 1.25);
  const envelope = THREE.MathUtils.clamp(phrase * 0.36 + accent * 0.64, 0, 1) * (text.trim() ? 1 : 0.72);

  base.scale = 1.0 + envelope * 0.065;
  base.ringSpeed = 0.82 + envelope * 0.55;
  base.neural = 1.02 + envelope * 0.38 * prosody;
  base.signal = 1.0 + envelope * 0.65 * prosody;
  base.light = 1.08 + envelope * 0.55;
  base.particles = 0.78 + envelope * 0.32;
  return base;
}

function makeProcessor() {
  const group = new THREE.Group();

  const emitterUniforms = {
    uTime: { value: 0 },
    uEnergy: { value: 1 },
    uOpacity: { value: 1 },
    uColor: { value: new THREE.Color(STATE_COLORS.idle) },
  };
  const emitter = new THREE.Mesh(
    new THREE.SphereGeometry(0.33, 40, 40),
    new THREE.ShaderMaterial({
      uniforms: emitterUniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: `
        varying vec3 vNormal;
        varying vec3 vWorld;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vec4 world = modelMatrix * vec4(position, 1.0);
          vWorld = world.xyz;
          gl_Position = projectionMatrix * viewMatrix * world;
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform float uEnergy;
        uniform float uOpacity;
        uniform vec3 uColor;
        varying vec3 vNormal;
        varying vec3 vWorld;
        void main() {
          vec3 viewDir = normalize(cameraPosition - vWorld);
          float facing = max(dot(normalize(vNormal), viewDir), 0.0);
          float rim = pow(1.0 - facing, 2.8);
          float pulse = 0.86 + sin(uTime * 5.2) * 0.08 + sin(uTime * 11.0) * 0.025;
          vec3 color = mix(uColor * 0.72, vec3(0.86, 1.0, 0.97), facing * 0.55);
          color += uColor * rim * 0.65;
          float alpha = clamp((0.58 + facing * 0.32 + rim * 0.25) * uOpacity, 0.0, 0.96);
          gl_FragColor = vec4(color * pulse * (0.72 + uEnergy * 0.42), alpha);
        }
      `,
    })
  );

  const coreGeometry = new THREE.IcosahedronGeometry(0.64, 2);
  const coreMaterial = new THREE.MeshStandardMaterial({
    color: 0x07110f,
    emissive: 0x1c9c70,
    emissiveIntensity: 0.58,
    metalness: 0.76,
    roughness: 0.28,
    flatShading: true,
    transparent: true,
    opacity: 0.92,
  });
  const coreMesh = new THREE.Mesh(coreGeometry, coreMaterial);
  const coreEdgeMaterial = new THREE.LineBasicMaterial({
    color: STATE_COLORS.idle,
    transparent: true,
    opacity: 0.72,
    blending: THREE.AdditiveBlending,
  });
  const coreEdges = new THREE.LineSegments(new THREE.EdgesGeometry(coreGeometry, 18), coreEdgeMaterial);

  const frameGeometry = new THREE.IcosahedronGeometry(0.9, 1);
  const frameMaterial = new THREE.MeshStandardMaterial({
    color: 0x0b1717,
    emissive: 0x17453e,
    emissiveIntensity: 0.35,
    metalness: 0.9,
    roughness: 0.34,
    transparent: true,
    opacity: 0.16,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const frame = new THREE.Mesh(frameGeometry, frameMaterial);
  const frameEdgeMaterial = new THREE.LineBasicMaterial({
    color: 0x67cce6,
    transparent: true,
    opacity: 0.28,
    blending: THREE.AdditiveBlending,
  });
  const frameEdges = new THREE.LineSegments(new THREE.EdgesGeometry(frameGeometry, 12), frameEdgeMaterial);

  const irisRings = [];
  const irisDefinitions = [
    { radius: 0.75, rotation: [Math.PI / 2, 0.2, 0], color: 0x55e6a2 },
    { radius: 0.79, rotation: [0.3, Math.PI / 2, 0.6], color: 0x67cce6 },
    { radius: 0.83, rotation: [0.9, 0.4, Math.PI / 2], color: 0xf1c66d },
  ];
  for (const definition of irisDefinitions) {
    const material = new THREE.MeshBasicMaterial({
      color: definition.color,
      transparent: true,
      opacity: 0.38,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(new THREE.TorusGeometry(definition.radius, 0.012, 6, 96), material);
    mesh.rotation.set(...definition.rotation);
    irisRings.push({ mesh, material });
    group.add(mesh);
  }

  const shellUniforms = {
    uTime: { value: 0 },
    uEnergy: { value: 1 },
    uOpacity: { value: 1 },
    uColor: { value: new THREE.Color(STATE_COLORS.idle) },
  };
  const cortexShell = new THREE.Mesh(
    new THREE.SphereGeometry(1.24, 48, 36),
    new THREE.ShaderMaterial({
      uniforms: shellUniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      vertexShader: `
        varying vec3 vNormal;
        varying vec3 vLocal;
        varying vec3 vWorld;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vLocal = position;
          vec4 world = modelMatrix * vec4(position, 1.0);
          vWorld = world.xyz;
          gl_Position = projectionMatrix * viewMatrix * world;
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform float uEnergy;
        uniform float uOpacity;
        uniform vec3 uColor;
        varying vec3 vNormal;
        varying vec3 vLocal;
        varying vec3 vWorld;
        void main() {
          vec3 viewDir = normalize(cameraPosition - vWorld);
          float facing = max(dot(normalize(vNormal), viewDir), 0.0);
          float fresnel = pow(1.0 - facing, 3.1);
          float longitude = atan(vLocal.z, vLocal.x);
          float latitude = asin(clamp(normalize(vLocal).y, -1.0, 1.0));
          float latBand = pow(0.5 + 0.5 * sin(latitude * 21.0 - uTime * 0.7), 20.0);
          float lonBand = pow(0.5 + 0.5 * sin(longitude * 18.0 + uTime * 0.45), 24.0);
          float circuit = max(latBand * 0.7, lonBand * 0.45) * (0.25 + fresnel * 0.75);
          float alpha = clamp((fresnel * 0.19 + circuit * 0.065 * uEnergy) * uOpacity, 0.0, 0.28);
          vec3 color = mix(vec3(0.08, 0.22, 0.22), uColor, 0.7 + circuit * 0.3);
          gl_FragColor = vec4(color * (0.75 + uEnergy * 0.35), alpha);
        }
      `,
    })
  );

  group.add(cortexShell, frame, frameEdges, coreMesh, coreEdges, emitter);
  return {
    group,
    emitter,
    emitterUniforms,
    shellUniforms,
    coreMesh,
    coreMaterial,
    coreEdgeMaterial,
    frame,
    frameMaterial,
    frameEdgeMaterial,
    irisRings,
  };
}

function updateProcessor(processor, time, profile, color) {
  const reveal = profile.reveal ?? 1;
  processor.emitterUniforms.uTime.value = time;
  processor.emitterUniforms.uEnergy.value = profile.light;
  processor.emitterUniforms.uOpacity.value = profile.opacity * reveal;
  processor.emitterUniforms.uColor.value.copy(color);
  processor.shellUniforms.uTime.value = time;
  processor.shellUniforms.uEnergy.value = profile.neural;
  processor.shellUniforms.uOpacity.value = profile.opacity * reveal;
  processor.shellUniforms.uColor.value.copy(color);

  processor.coreMaterial.emissive.copy(color).multiplyScalar(0.56);
  processor.coreMaterial.emissiveIntensity = 0.34 + profile.light * 0.46;
  processor.coreMaterial.opacity = (0.58 + profile.opacity * 0.35) * reveal;
  processor.coreEdgeMaterial.color.copy(color);
  processor.coreEdgeMaterial.opacity = (0.35 + profile.neural * 0.36) * reveal;
  processor.frameMaterial.opacity = (0.08 + profile.opacity * 0.1) * reveal;
  processor.frameEdgeMaterial.opacity = (0.12 + profile.neural * 0.18) * reveal;
  processor.frame.rotation.y -= 0.0016 * profile.spin;
  processor.frame.rotation.x += 0.0009 * profile.spin;
  processor.coreMesh.rotation.y += 0.0032 * profile.spin;
  processor.coreMesh.rotation.z -= 0.0014 * profile.spin;
  const heartbeat = 1 + Math.sin(time * (2.4 + profile.signal * 0.35)) * 0.018 * profile.signal;
  processor.emitter.scale.setScalar(heartbeat);
  processor.irisRings.forEach((ring, index) => {
    ring.material.opacity = (0.16 + profile.neural * (0.17 + index * 0.025)) * reveal;
    ring.mesh.rotation.z += (index % 2 ? -1 : 1) * 0.0022 * profile.ringSpeed;
  });
}

function makeNeuralLattice() {
  const group = new THREE.Group();
  const points = fibonacciSphere(96, 1.13);
  const pointPositions = new Float32Array(points.length * 3);
  const pointColors = new Float32Array(points.length * 3);
  const emerald = new THREE.Color(0x55e6a2);
  const cyan = new THREE.Color(0x67cce6);
  points.forEach((point, index) => {
    point.toArray(pointPositions, index * 3);
    const blend = (point.y / 1.13 + 1) * 0.36 + ((index * 17) % 11) / 30;
    const color = emerald.clone().lerp(cyan, THREE.MathUtils.clamp(blend, 0, 1));
    color.toArray(pointColors, index * 3);
  });

  const nodeGeometry = new THREE.BufferGeometry();
  nodeGeometry.setAttribute("position", new THREE.BufferAttribute(pointPositions, 3));
  nodeGeometry.setAttribute("color", new THREE.BufferAttribute(pointColors, 3));
  const nodeMaterial = new THREE.PointsMaterial({
    size: 0.04,
    sizeAttenuation: true,
    vertexColors: true,
    transparent: true,
    opacity: 0.88,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const nodes = new THREE.Points(nodeGeometry, nodeMaterial);

  const edges = nearestNeighborEdges(points, 3);
  const edgePositions = new Float32Array(edges.length * 6);
  const edgeColors = new Float32Array(edges.length * 6);
  edges.forEach(([from, to], index) => {
    from.toArray(edgePositions, index * 6);
    to.toArray(edgePositions, index * 6 + 3);
    const fromColor = emerald.clone().lerp(cyan, (from.y / 1.13 + 1) * 0.5);
    const toColor = emerald.clone().lerp(cyan, (to.y / 1.13 + 1) * 0.5);
    fromColor.toArray(edgeColors, index * 6);
    toColor.toArray(edgeColors, index * 6 + 3);
  });
  const edgeGeometry = new THREE.BufferGeometry();
  edgeGeometry.setAttribute("position", new THREE.BufferAttribute(edgePositions, 3));
  edgeGeometry.setAttribute("color", new THREE.BufferAttribute(edgeColors, 3));
  const edgeMaterial = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 0.3,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const connections = new THREE.LineSegments(edgeGeometry, edgeMaterial);

  const hubPoints = points.filter((_point, index) => index % 9 === 0);
  const hubGeometry = new THREE.BufferGeometry().setFromPoints(hubPoints);
  const hubMaterial = new THREE.PointsMaterial({
    color: 0xf1c66d,
    size: 0.075,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.9,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const hubs = new THREE.Points(hubGeometry, hubMaterial);

  const greenPulses = makePulseMesh(14, 0x55e6a2);
  const amberPulses = makePulseMesh(7, 0xf1c66d);
  group.add(connections, nodes, hubs, greenPulses, amberPulses);
  return { group, points, edges, nodes, nodeMaterial, connections, edgeMaterial, hubs, hubMaterial, greenPulses, amberPulses };
}

function updateNeuralLattice(lattice, time, profile, color) {
  const reveal = profile.reveal ?? 1;
  lattice.group.rotation.y -= 0.0011 * profile.spin;
  lattice.group.rotation.x = Math.sin(time * 0.19) * 0.08;
  lattice.nodeMaterial.opacity = (0.28 + profile.neural * 0.52) * reveal;
  lattice.nodeMaterial.size = 0.028 + profile.neural * 0.012;
  lattice.edgeMaterial.opacity = (0.08 + profile.neural * 0.24) * reveal;
  lattice.hubMaterial.color.lerp(color, 0.018);
  lattice.hubMaterial.opacity = (0.24 + profile.signal * 0.5) * reveal;
  lattice.hubMaterial.size = 0.05 + profile.signal * 0.022;
  lattice.greenPulses.material.color.copy(color);
  lattice.greenPulses.material.opacity = Math.min(1, 0.25 + profile.signal * 0.58) * reveal;
  lattice.amberPulses.material.opacity = Math.min(0.92, 0.12 + profile.signal * 0.42) * reveal;
  updatePulseMesh(lattice.greenPulses, lattice.edges, time, profile.signal, 0);
  updatePulseMesh(lattice.amberPulses, lattice.edges, time * 0.83, profile.signal * 0.82, 5);
}

function makePulseMesh(count, color) {
  const geometry = new THREE.OctahedronGeometry(0.032, 0);
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.8,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const mesh = new THREE.InstancedMesh(geometry, material, count);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.frustumCulled = false;
  return mesh;
}

function updatePulseMesh(mesh, edges, time, speed, offset) {
  const count = mesh.count;
  for (let index = 0; index < count; index += 1) {
    const edge = edges[(index * 13 + offset * 7) % edges.length];
    const phase = fract(time * (0.11 + (index % 5) * 0.013) * Math.max(0.04, speed) + index / count + offset * 0.071);
    const eased = phase * phase * (3 - 2 * phase);
    pulsePosition.lerpVectors(edge[0], edge[1], eased);
    const size = (0.4 + Math.sin(Math.PI * phase) * 0.9) * (0.55 + speed * 0.34);
    pulseScale.setScalar(Math.max(0.08, size));
    pulseMatrix.compose(pulsePosition, pulseRotation, pulseScale);
    mesh.setMatrixAt(index, pulseMatrix);
  }
  mesh.instanceMatrix.needsUpdate = true;
}

function makeOrbitSystem() {
  const group = new THREE.Group();
  const definitions = [
    { radius: 1.55, tube: 0.014, rotation: [1.18, 0.15, 0.1], speed: 0.52, color: 0x55e6a2 },
    { radius: 1.82, tube: 0.012, rotation: [0.38, 1.0, 0.42], speed: -0.38, color: 0x67cce6 },
    { radius: 2.08, tube: 0.016, rotation: [1.48, -0.58, -0.18], speed: 0.28, color: 0x55e6a2 },
    { radius: 2.34, tube: 0.011, rotation: [0.72, -0.82, 0.92], speed: -0.22, color: 0xf1c66d },
  ];
  const orbits = definitions.map((definition, index) => {
    const orbit = new THREE.Group();
    orbit.rotation.set(...definition.rotation);

    const bandMaterial = new THREE.MeshStandardMaterial({
      color: 0x102326,
      emissive: definition.color,
      emissiveIntensity: 0.36,
      metalness: 0.88,
      roughness: 0.32,
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
    });
    const band = new THREE.Mesh(new THREE.TorusGeometry(definition.radius, definition.tube, 6, 160), bandMaterial);

    const dashMaterial = new THREE.LineBasicMaterial({
      color: definition.color,
      transparent: true,
      opacity: 0.42,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const dashes = makeDashedRing(definition.radius + 0.018, dashMaterial, 132, index + 2);

    const markerMaterial = new THREE.MeshBasicMaterial({
      color: definition.color,
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const marker = new THREE.Mesh(new THREE.OctahedronGeometry(0.055 + index * 0.004, 0), markerMaterial);
    orbit.add(band, dashes, marker);
    group.add(orbit);
    return { group: orbit, band, bandMaterial, dashes, dashMaterial, marker, markerMaterial, ...definition, index };
  });

  const tickMaterial = new THREE.LineBasicMaterial({
    color: 0x67cce6,
    transparent: true,
    opacity: 0.22,
    blending: THREE.AdditiveBlending,
  });
  const ticks = makeRadialTicks(2.48, tickMaterial);
  ticks.rotation.set(Math.PI / 2, 0, 0);
  group.add(ticks);
  return { group, orbits, ticks, tickMaterial };
}

function updateOrbitSystem(system, time, profile, color) {
  const reveal = profile.reveal ?? 1;
  system.group.rotation.y += 0.00035 * profile.spin;
  system.orbits.forEach((orbit) => {
    const drift = time * orbit.speed * profile.ringSpeed * 0.11;
    orbit.group.rotation.x = orbit.rotation[0] + Math.sin(drift * 0.42 + orbit.index) * 0.055;
    orbit.group.rotation.y = orbit.rotation[1] + drift;
    orbit.group.rotation.z = orbit.rotation[2] + Math.cos(drift * 0.33 + orbit.index) * 0.035;
    const markerAngle = time * orbit.speed * (0.42 + profile.ringSpeed * 0.2) + orbit.index * 1.37;
    orbit.marker.position.set(Math.cos(markerAngle) * orbit.radius, Math.sin(markerAngle) * orbit.radius, 0);
    orbit.marker.rotation.x += 0.02 * profile.ringSpeed;
    orbit.marker.rotation.y -= 0.015 * profile.ringSpeed;
    orbit.bandMaterial.opacity = (0.17 + profile.opacity * 0.27) * reveal;
    orbit.bandMaterial.emissiveIntensity = 0.14 + profile.neural * 0.28;
    orbit.dashMaterial.opacity = (0.12 + profile.neural * (0.18 + orbit.index * 0.018)) * reveal;
    orbit.markerMaterial.opacity = Math.min(1, 0.3 + profile.signal * 0.5) * reveal;
    if (orbit.index === 0) orbit.markerMaterial.color.lerp(color, 0.035);
  });
  system.tickMaterial.opacity = (0.08 + profile.neural * 0.13) * reveal;
  system.ticks.rotation.z += 0.0008 * profile.ringSpeed;
}

function makeDashedRing(radius, material, segments, offset) {
  const positions = [];
  for (let index = 0; index < segments; index += 1) {
    if ((index + offset) % 7 > 2) continue;
    const start = (index / segments) * Math.PI * 2;
    const end = ((index + 0.72) / segments) * Math.PI * 2;
    positions.push(Math.cos(start) * radius, Math.sin(start) * radius, 0);
    positions.push(Math.cos(end) * radius, Math.sin(end) * radius, 0);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.LineSegments(geometry, material);
}

function makeRadialTicks(radius, material) {
  const positions = [];
  for (let index = 0; index < 24; index += 1) {
    const angle = (index / 24) * Math.PI * 2;
    const length = index % 6 === 0 ? 0.12 : 0.065;
    positions.push(Math.cos(angle) * (radius - length), Math.sin(angle) * (radius - length), 0);
    positions.push(Math.cos(angle) * radius, Math.sin(angle) * radius, 0);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.LineSegments(geometry, material);
}

function makeBackgroundParticles() {
  const count = 430;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const emerald = new THREE.Color(0x2db77c);
  const cyan = new THREE.Color(0x4c9fb3);
  const random = seededRandom(271828);
  for (let index = 0; index < count; index += 1) {
    const radius = 2.8 + random() * 5.4;
    const theta = random() * Math.PI * 2;
    const phi = Math.acos(2 * random() - 1);
    positions[index * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[index * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    positions[index * 3 + 2] = radius * Math.cos(phi);
    emerald.clone().lerp(cyan, random()).multiplyScalar(0.55 + random() * 0.45).toArray(colors, index * 3);
  }
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const material = new THREE.PointsMaterial({
    size: 0.025,
    sizeAttenuation: true,
    vertexColors: true,
    transparent: true,
    opacity: 0.42,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  return { points: new THREE.Points(geometry, material), material };
}

function updateBackgroundParticles(particles, time, profile) {
  const reveal = profile.reveal ?? 1;
  particles.points.rotation.y += 0.00012 + profile.particles * 0.00018;
  particles.points.rotation.x = Math.sin(time * 0.09) * 0.035;
  particles.material.opacity = (0.08 + profile.particles * 0.34) * reveal;
  particles.material.size = 0.014 + profile.particles * 0.012;
}

function revealStage(progress, start, end) {
  const normalized = THREE.MathUtils.clamp((progress - start) / Math.max(0.001, end - start), 0, 1);
  return THREE.MathUtils.smootherstep(normalized, 0, 1);
}

function withReveal(profile, reveal) {
  return { ...profile, reveal };
}

function fibonacciSphere(count, radius) {
  const points = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let index = 0; index < count; index += 1) {
    const y = 1 - (index / (count - 1)) * 2;
    const radial = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = golden * index;
    const variation = 0.97 + ((index * 37) % 17) / 280;
    points.push(new THREE.Vector3(Math.cos(theta) * radial, y, Math.sin(theta) * radial).multiplyScalar(radius * variation));
  }
  return points;
}

function nearestNeighborEdges(points, neighborCount) {
  const seen = new Set();
  const edges = [];
  points.forEach((point, index) => {
    const nearest = points
      .map((candidate, candidateIndex) => ({ candidateIndex, distance: candidateIndex === index ? Infinity : point.distanceToSquared(candidate) }))
      .sort((a, b) => a.distance - b.distance)
      .slice(0, neighborCount);
    for (const item of nearest) {
      const low = Math.min(index, item.candidateIndex);
      const high = Math.max(index, item.candidateIndex);
      const key = `${low}:${high}`;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push([points[low], points[high]]);
    }
  });
  return edges;
}

function estimateTextEmphasis(text) {
  const value = String(text || "");
  if (!value.trim()) return 0.35;
  const letters = value.match(/[A-Za-z]/g) || [];
  const upper = value.match(/[A-Z]/g) || [];
  const punctuation = value.match(/[!?;:]/g) || [];
  const pauses = value.match(/[,.-]/g) || [];
  const caps = letters.length ? upper.length / letters.length : 0;
  return THREE.MathUtils.clamp(0.28 + punctuation.length * 0.08 + pauses.length * 0.018 + caps * 0.5, 0.22, 1.0);
}

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function fract(value) {
  return value - Math.floor(value);
}
