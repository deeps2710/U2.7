import * as THREE from "./vendor/three.module.min.js";

const simplexNoise3D = `
  vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 permute(vec4 x) { return mod289(((x*34.0)+1.0)*x); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
  float snoise(vec3 v) {
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod289(i);
    vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
    p0 *= norm.x;
    p1 *= norm.y;
    p2 *= norm.z;
    p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
  }
`;

const STATE_PROFILES = {
  idle: { scale: 1, shaderTime: 1, ringSpeed: 1, autoRotate: 0.5, light: 2.7, lightPulse: 0.35, exposure: 1.04, energy: 1, opacity: 1, particleSpeed: 0.05, particleEnergy: 1, flicker: 0.05 },
  listening: { scale: 0.68, shaderTime: 0.42, ringSpeed: 0.34, autoRotate: 0.12, light: 1.42, lightPulse: 0.04, exposure: 0.9, energy: 0.58, opacity: 0.96, particleSpeed: 0.018, particleEnergy: 0.5, flicker: 0.008 },
  thinking: { scale: 0.5, shaderTime: 1.35, ringSpeed: 2.25, autoRotate: 1.08, light: 3.1, lightPulse: 0.82, exposure: 1, energy: 1.16, opacity: 1, particleSpeed: 0.085, particleEnergy: 1.08, flicker: 0.16 },
  transcribing: { scale: 0.74, shaderTime: 0.82, ringSpeed: 1, autoRotate: 0.55, light: 2.35, lightPulse: 0.38, exposure: 0.98, energy: 0.92, opacity: 1, particleSpeed: 0.05, particleEnergy: 0.8, flicker: 0.08 },
  waiting_for_wake_word: { scale: 0.86, shaderTime: 0.62, ringSpeed: 0.55, autoRotate: 0.34, light: 2.05, lightPulse: 0.28, exposure: 0.96, energy: 0.78, opacity: 0.94, particleSpeed: 0.035, particleEnergy: 0.68, flicker: 0.045 },
  inactive: { scale: 0.12, shaderTime: 0.18, ringSpeed: 0.035, autoRotate: 0.02, light: 0.12, lightPulse: 0, exposure: 0.5, energy: 0.08, opacity: 0.18, particleSpeed: 0.012, particleEnergy: 0.05, flicker: 0 },
};

export function createArmillaryCore({ scene, camera, renderer }) {
  camera.position.set(0, 1.05, 13.4);
  camera.lookAt(0, 0, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.04;

  const root = new THREE.Group();
  root.position.y = 4.15;
  root.rotation.x = -0.06;
  scene.add(root);

  const shared = { coreTime: { value: 0 }, energy: { value: 1 }, opacity: { value: 1 } };
  const nucleus = makeNucleus(shared);
  const core = makePlasmaCore(shared);
  const aura = makeAura(shared);
  const coreLight = new THREE.PointLight(0x00ff66, 2.7, 5.8, 2.0);
  root.add(nucleus, core, aura, coreLight);

  const rings = [];
  const createRing = (...args) => {
    const ring = makeArmillaryRing(...args);
    root.add(ring.mesh);
    rings.push(ring);
  };

  createRing(2.0, 0.45, 0, 0, 0, 2.0, 1.0, 0.0, 0.002, 0.0);
  createRing(1.85, 0.06, 0.05, 0, -0.05, 5.0, 1.5, 0.0, 0.003, 0.0);
  createRing(2.15, 0.18, Math.PI / 2, 0, 0, 3.0, 1.2, 0.003, 0.0, 0.001);
  createRing(2.25, 0.14, Math.PI / 2, Math.PI / 3, 0, 4.0, 0.8, 0.002, 0.002, 0.0);
  createRing(2.35, 0.14, Math.PI / 2, -Math.PI / 3, 0, 3.5, 1.4, 0.001, 0.0, 0.003);
  createRing(2.5, 0.08, Math.PI / 4, Math.PI / 4, 0, 6.0, 1.8, -0.002, 0.001, 0.002);
  createRing(2.6, 0.08, -Math.PI / 4, Math.PI / 6, 0, 5.0, 1.1, 0.002, -0.001, 0.001);
  createRing(2.75, 0.05, 0.1, Math.PI / 2, 0.1, 8.0, 2.0, 0.0, -0.002, 0.0);
  createRing(1.5, 0.06, Math.PI / 3, 0, Math.PI / 6, 2.0, 2.5, 0.004, 0.004, 0.0);
  createRing(2.05, 0.05, 0.34, 0.0, 0.0, 7.0, 1.65, 0.0, 0.0015, 0.0);
  createRing(2.05, 0.05, -0.34, 0.0, 0.0, 7.5, 1.35, 0.0, -0.0014, 0.0);

  const particles = makeParticles();
  scene.add(particles.points);

  const current = { ...STATE_PROFILES.idle };
  let visualState = "idle";
  let stateStartedAt = 0;
  let speechStartedAt = 0;
  let speechText = "";
  let textEmphasis = 0.35;
  let voiceProfile = { pitch: 0.72, rate: 0.92, volume: 0.95 };
  let targetRootY = 4.15;

  return {
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
      targetRootY = mode === "compact" ? 0.55 : 4.15;
    },
    update(time, state = visualState) {
      if (STATE_PROFILES[state] && state !== visualState) {
        visualState = state;
        stateStartedAt = time;
      }
      const desired = dynamicProfile(visualState, time - stateStartedAt, time - speechStartedAt, speechText, textEmphasis, voiceProfile);
      for (const key of Object.keys(current)) current[key] = THREE.MathUtils.lerp(current[key], desired[key], 0.055);

      const flicker = 1 + (Math.sin(time * 11.0) * 0.45 + Math.sin(time * 23.0 + 0.8) * 0.18) * current.flicker;
      const scale = current.scale * flicker;
      const shaderTime = time * current.shaderTime;

      root.position.y = THREE.MathUtils.lerp(root.position.y, targetRootY, 0.08);
      shared.coreTime.value = shaderTime;
      shared.energy.value = current.energy;
      shared.opacity.value = current.opacity;
      nucleus.scale.setScalar(scale * (1 + Math.sin(time * 7.6) * 0.035 * current.energy));
      core.scale.setScalar(scale * (1 + Math.sin(time * 3.1) * 0.012 * current.energy));
      aura.scale.setScalar(scale * (1 + Math.sin(time * 3.2) * 0.02 * current.energy));
      coreLight.intensity = Math.max(0.02, (current.light + Math.sin(time * 5.2) * current.lightPulse) * flicker);
      renderer.toneMappingExposure = current.exposure;

      root.rotation.y += 0.003 * current.autoRotate;
      root.rotation.x = -0.06 + Math.sin(time * 0.28) * 0.025 * current.energy;

      for (const ring of rings) {
        ring.material.uniforms.uTime.value = shaderTime;
        ring.material.uniforms.uEnergy.value = current.energy;
        ring.material.uniforms.uOpacity.value = current.opacity;
        const ringBreath = 1 + Math.sin(time * 3.0 + ring.baseRotX * 0.7 + ring.baseRotY * 0.5) * (0.004 + current.flicker * 0.018);
        ring.mesh.scale.setScalar(scale * ringBreath);
        ring.mesh.rotation.x += ring.mechSpdX * current.ringSpeed;
        ring.mesh.rotation.y += ring.mechSpdY * current.ringSpeed;
        ring.mesh.rotation.z += ring.mechSpdZ * current.ringSpeed;
      }

      particles.material.uniforms.uTime.value = time;
      particles.material.uniforms.uEnergy.value = current.particleEnergy;
      particles.material.uniforms.uOpacity.value = current.opacity;
      particles.points.rotation.y += current.particleSpeed * 0.006;
      particles.points.rotation.x = Math.sin(time * 0.11) * 0.035 * current.particleEnergy;
    },
  };
}

function dynamicProfile(state, stateAge, speechAge, text, textEmphasis, voiceProfile) {
  const base = { ...(STATE_PROFILES[state] || STATE_PROFILES.idle) };
  if (state === "waiting_for_wake_word") {
    const boot = THREE.MathUtils.smootherstep(Math.min(stateAge / 2.4, 1), 0, 1);
    base.scale = THREE.MathUtils.lerp(0.18, base.scale, boot);
    base.energy = THREE.MathUtils.lerp(0.12, base.energy, boot);
    base.opacity = THREE.MathUtils.lerp(0.18, base.opacity, boot);
    base.light = THREE.MathUtils.lerp(0.18, base.light, boot);
  }
  if (state === "inactive") {
    const shutdown = THREE.MathUtils.smootherstep(Math.min(stateAge / 3.4, 1), 0, 1);
    base.scale = THREE.MathUtils.lerp(1.0, base.scale, shutdown);
    base.opacity = THREE.MathUtils.lerp(1.0, base.opacity, shutdown);
    base.energy = THREE.MathUtils.lerp(1.0, base.energy, shutdown);
    base.light = THREE.MathUtils.lerp(2.7, base.light, shutdown);
  }
  if (state !== "speaking") return base;

  const phraseWave = 0.5 + 0.5 * Math.sin(speechAge * 0.55 + 0.35 * Math.sin(speechAge * 0.18));
  const sentenceIntent = 0.5 + 0.5 * Math.sin(speechAge * 0.21 + 1.2);
  const syllableA = Math.max(0, Math.sin(speechAge * 2.9 + 0.9 * Math.sin(speechAge * 0.63)));
  const syllableB = Math.max(0, Math.sin(speechAge * 4.7 + 1.4 + 0.4 * Math.sin(speechAge * 0.91)));
  const syllableC = Math.max(0, Math.sin(speechAge * 6.6 + 2.1));
  const wordAccent = Math.pow(Math.max(syllableA * 0.85, syllableB * 0.7), 1.1);
  const pitch = THREE.MathUtils.clamp(Number(voiceProfile.pitch || 0.72), 0, 1.4);
  const rate = THREE.MathUtils.clamp(Number(voiceProfile.rate || 0.92), 0.55, 1.6);
  const volume = THREE.MathUtils.clamp(Number(voiceProfile.volume || 0.95), 0, 1);
  const prosody = THREE.MathUtils.clamp(textEmphasis * 0.45 + pitch * 0.28 + volume * 0.22 + rate * 0.08, 0.25, 1.25);
  const emphasis = Math.pow(Math.max(wordAccent, syllableC * 0.52) * (0.72 + sentenceIntent * 0.28), 1.0) * prosody;
  const speechEnvelope = THREE.MathUtils.clamp(phraseWave * 0.3 + wordAccent * 0.44 + syllableC * 0.1 + sentenceIntent * 0.16, 0, 1);
  const microFlutter = 0.5 + 0.5 * Math.sin(speechAge * 9.5 + emphasis * 3.4);
  const hasText = text.trim().length > 0 ? 1 : 0.68;

  base.scale = THREE.MathUtils.lerp(0.96, 1.18, speechEnvelope * hasText) + emphasis * 0.025;
  base.shaderTime = 1.0 + emphasis * 0.28;
  base.ringSpeed = 1.22 + speechEnvelope * 0.64 + emphasis * 0.1;
  base.autoRotate = 0.6 + speechEnvelope * 0.22 + emphasis * 0.05;
  base.light = 2.9 + speechEnvelope * 1.08 + emphasis * 0.42 + microFlutter * 0.28;
  base.lightPulse = 0.72 + emphasis * 0.42;
  base.exposure = 1.02 + speechEnvelope * 0.12;
  base.energy = 1.28 + speechEnvelope * 0.52 + emphasis * 0.18;
  base.opacity = 1;
  base.particleSpeed = 0.05 + emphasis * 0.018;
  base.particleEnergy = 1.05 + speechEnvelope * 0.28;
  base.flicker = 0.18 + speechEnvelope * 0.17 + emphasis * 0.12;
  return base;
}

function estimateTextEmphasis(text) {
  const value = String(text || "");
  if (!value.trim()) return 0.35;
  const letters = value.match(/[A-Za-z]/g) || [];
  const upper = value.match(/[A-Z]/g) || [];
  const punch = value.match(/[!?;:]/g) || [];
  const commas = value.match(/[,.-]/g) || [];
  const caps = letters.length ? upper.length / letters.length : 0;
  return THREE.MathUtils.clamp(0.28 + punch.length * 0.08 + commas.length * 0.018 + caps * 0.5, 0.22, 1.0);
}

function makeNucleus(shared) {
  return new THREE.Mesh(
    new THREE.SphereGeometry(0.46, 56, 56),
    new THREE.ShaderMaterial({
      uniforms: shared,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
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
        uniform float coreTime;
        uniform float energy;
        uniform float opacity;
        varying vec3 vNormal;
        varying vec3 vWorld;
        void main() {
          vec3 V = normalize(cameraPosition - vWorld);
          float facing = pow(max(dot(normalize(vNormal), V), 0.0), 0.28);
          float rim = pow(1.0 - max(dot(normalize(vNormal), V), 0.0), 3.4);
          float pulse = 0.88 + 0.12 * sin(coreTime * 8.0);
          float alpha = clamp((facing * 0.92 + rim * 0.24) * pulse * opacity, 0.0, 1.0);
          vec3 color = vec3(0.76, 1.0, 0.84) * 1.35 + vec3(0.0, 1.0, 0.25) * rim;
          gl_FragColor = vec4(color * alpha * 1.45 * energy, alpha);
        }
      `,
    })
  );
}

function makePlasmaCore(shared) {
  return new THREE.Mesh(
    new THREE.SphereGeometry(1.05, 80, 80),
    new THREE.ShaderMaterial({
      uniforms: shared,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      vertexShader: `
        varying vec2 vUv;
        varying vec3 vPos;
        varying vec3 vNormal;
        varying vec3 vWorld;
        uniform float coreTime;
        uniform float energy;
        ${simplexNoise3D}
        void main() {
          vUv = uv;
          vPos = position;
          vNormal = normalize(normalMatrix * normal);
          float pressure = snoise(position * 3.1 + vec3(coreTime * 1.4, -coreTime * 0.8, coreTime * 0.55));
          float fine = snoise(position * 8.0 + vec3(-coreTime * 2.1, coreTime * 1.2, 0.0));
          float displacement = (pressure * 0.042 + fine * 0.014) * (0.75 + energy * 0.25);
          vec3 newPosition = position + normal * displacement;
          vec4 world = modelMatrix * vec4(newPosition, 1.0);
          vWorld = world.xyz;
          gl_Position = projectionMatrix * viewMatrix * world;
        }
      `,
      fragmentShader: `
        varying vec2 vUv;
        varying vec3 vPos;
        varying vec3 vNormal;
        varying vec3 vWorld;
        uniform float coreTime;
        uniform float energy;
        uniform float opacity;
        ${simplexNoise3D}
        void main() {
          vec3 p = normalize(vPos);
          float n1 = snoise(p * 3.6 + vec3(coreTime * 1.85, -coreTime * 1.20, coreTime * 0.65));
          float n2 = snoise(p * 7.4 + vec3(-coreTime * 2.7, coreTime * 2.05, coreTime * 1.2));
          float n3 = snoise(p * 17.5 + vec3(coreTime * 4.5, -coreTime * 2.8, coreTime * 1.9));
          float ridgeA = pow(1.0 - abs(n1), 4.6);
          float ridgeB = pow(1.0 - abs(n2), 7.0);
          float micro = pow(1.0 - abs(n3), 11.0);
          float veins = clamp(ridgeA * 0.80 + ridgeB * 0.75 + micro * 0.55, 0.0, 1.45);
          vec3 V = normalize(cameraPosition - vWorld);
          float fresnel = pow(1.0 - max(dot(normalize(vNormal), V), 0.0), 2.4);
          float pressurePulse = 0.88 + 0.12 * sin(coreTime * 6.2 + ridgeA * 5.0);
          float frontHotspot = pow(max(dot(p, normalize(vec3(-0.25, 0.12, 1.0))), 0.0), 10.0);
          vec3 deep = vec3(0.0, 0.035, 0.008);
          vec3 neon = vec3(0.0, 1.0, 0.27);
          vec3 lime = vec3(0.25, 1.0, 0.42);
          vec3 whiteHot = vec3(0.74, 1.0, 0.84);
          vec3 finalColor = deep + neon * veins * 1.45 + lime * ridgeB * 0.80 + whiteHot * (micro * 0.85 + frontHotspot * 0.55) + neon * fresnel * 0.25;
          float alpha = clamp((0.24 + veins * 0.82 + fresnel * 0.16 + frontHotspot * 0.25) * opacity, 0.0, 0.96);
          gl_FragColor = vec4(finalColor * pressurePulse * energy, alpha);
        }
      `,
    })
  );
}

function makeAura(shared) {
  return new THREE.Mesh(
    new THREE.SphereGeometry(1.18, 80, 80),
    new THREE.ShaderMaterial({
      uniforms: shared,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.BackSide,
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
        uniform float coreTime;
        uniform float energy;
        uniform float opacity;
        varying vec3 vNormal;
        varying vec3 vWorld;
        void main() {
          vec3 V = normalize(cameraPosition - vWorld);
          float rim = pow(1.0 - abs(dot(normalize(vNormal), V)), 3.8);
          float pulse = 0.78 + 0.22 * sin(coreTime * 3.2);
          float alpha = rim * pulse * 0.11 * opacity * (0.7 + energy * 0.3);
          gl_FragColor = vec4(vec3(0.0, 1.0, 0.25) * alpha * 1.4 * energy, alpha);
        }
      `,
    })
  );
}

function makeArmillaryRing(radius, width, rotX, rotY, rotZ, sweepFreq, sweepSpeed, mechSpdX, mechSpdY, mechSpdZ) {
  const material = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uSweepSpeed: { value: sweepSpeed },
      uFreq: { value: sweepFreq },
      uEnergy: { value: 1 },
      uOpacity: { value: 1 },
    },
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
    vertexShader: `
      varying vec2 vUv;
      varying vec3 vPos;
      void main() {
        vUv = uv;
        vPos = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec2 vUv;
      varying vec3 vPos;
      uniform float uTime;
      uniform float uSweepSpeed;
      uniform float uFreq;
      uniform float uEnergy;
      uniform float uOpacity;
      ${simplexNoise3D}
      void main() {
        float edge = smoothstep(0.0, 0.035, vUv.y) * smoothstep(1.0, 0.965, vUv.y);
        float edgeTop = smoothstep(0.045, 0.0, abs(vUv.y - 0.965));
        float edgeBottom = smoothstep(0.045, 0.0, abs(vUv.y - 0.035));
        float centerSeam = smoothstep(0.018, 0.0, abs(vUv.y - 0.5));
        float crossProfile = smoothstep(1.0, 0.18, abs(vUv.y - 0.5) * 2.0);
        float ticksA = pow(sin(vUv.x * 96.0) * 0.5 + 0.5, 24.0);
        float ticksB = pow(sin(vUv.x * 24.0 + 1.2) * 0.5 + 0.5, 18.0);
        float tickMask = (smoothstep(0.18, 0.0, abs(vUv.y - 0.18)) + smoothstep(0.18, 0.0, abs(vUv.y - 0.82))) * 0.5;
        float etch = (ticksA * 0.45 + ticksB * 0.26) * tickMask;
        float structural = (edgeTop + edgeBottom) * 0.42 + centerSeam * 0.16 + etch;
        float progress = fract(vUv.x * uFreq - uTime * uSweepSpeed * 0.085);
        float d = min(progress, 1.0 - progress);
        float sweep = exp(-d * d * 55.0);
        float phase2 = fract(vUv.x * (uFreq * 0.55 + 1.0) + uTime * uSweepSpeed * 0.045 + 0.37);
        float d2 = min(phase2, 1.0 - phase2);
        sweep += exp(-d2 * d2 * 95.0) * 0.55;
        sweep *= crossProfile;
        float elecNoise = snoise(vec3(vUv.x * 38.0, vUv.y * 11.0, uTime * 2.5));
        float veinNoise = snoise(vec3(vUv.x * 120.0, vUv.y * 28.0, -uTime * 1.6));
        float crackle = smoothstep(0.48, 0.96, abs(elecNoise)) * sweep;
        float microVeins = smoothstep(0.62, 0.98, abs(veinNoise)) * sweep * 0.42;
        vec3 baseBand = vec3(0.0, 0.12, 0.045) * edge + vec3(0.0, 0.24, 0.10) * structural * edge;
        vec3 neonColor = vec3(0.0, 0.95, 0.24);
        vec3 hotColor = vec3(0.72, 1.0, 0.82);
        vec3 finalColor = baseBand + neonColor * (sweep * 0.92 + crackle * 0.80 + microVeins * 0.55) + hotColor * (crackle * 0.85 + edgeTop * sweep * 0.12 + edgeBottom * sweep * 0.12);
        float alpha = edge * (0.20 + structural * 0.18 + sweep * 0.38 + crackle * 0.24 + microVeins * 0.20);
        alpha = clamp(alpha, 0.0, 0.78) * uOpacity;
        gl_FragColor = vec4(finalColor * 1.06 * uEnergy, alpha);
      }
    `,
  });
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, width, 192, 1, true), material);
  mesh.rotation.set(rotX, rotY, rotZ);
  mesh.renderOrder = radius < 2.1 ? 3 : 2;
  return { mesh, material, mechSpdX, mechSpdY, mechSpdZ, baseRotX: rotX, baseRotY: rotY, baseRotZ: rotZ };
}

function makeParticles() {
  const count = 620;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  const alphas = new Float32Array(count);
  for (let i = 0; i < count; i += 1) {
    const r = 2.4 + Math.random() * 5.3;
    const theta = Math.random() * 2 * Math.PI;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);
    alphas[i] = Math.random();
  }
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("alpha", new THREE.BufferAttribute(alphas, 1));
  const material = new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uEnergy: { value: 1 }, uOpacity: { value: 1 } },
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    vertexShader: `
      attribute float alpha;
      varying float vAlpha;
      void main() {
        vAlpha = alpha;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = 18.0 / -mvPosition.z;
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying float vAlpha;
      uniform float uTime;
      uniform float uEnergy;
      uniform float uOpacity;
      void main() {
        float dist = length(gl_PointCoord - vec2(0.5));
        if (dist > 0.5) discard;
        float twinkle = sin(uTime * 2.0 + vAlpha * 10.0) * 0.5 + 0.5;
        vec3 color = mix(vec3(0.10, 0.45, 0.18), vec3(0.22, 0.95, 0.34), twinkle) * (0.72 + 0.28 * uEnergy);
        gl_FragColor = vec4(color, vAlpha * twinkle * (0.34 + uEnergy * 0.16) * uOpacity);
      }
    `,
  });
  return { points: new THREE.Points(geometry, material), material };
}
