/* global React, THREE */
const { useRef, useEffect, useMemo } = React;

/* ============================================================
   Bed3D — WebGL bed preview using Three.js
   Parametric bed with PBR materials, dynamic lighting,
   and live updates from wizard state.
   ============================================================ */

/* --- Material PBR profiles ---------------------------------- */
const MAT_PROFILES = {
  boucle:   { roughness: 0.92, metalness: 0.0,  bumpScale: 0.8,  bumpFreq: 60  },
  velvet:   { roughness: 0.75, metalness: 0.02, bumpScale: 0.3,  bumpFreq: 120 },
  linen:    { roughness: 0.88, metalness: 0.0,  bumpScale: 0.6,  bumpFreq: 40  },
  weave:    { roughness: 0.82, metalness: 0.0,  bumpScale: 0.4,  bumpFreq: 50  },
  chenille: { roughness: 0.85, metalness: 0.01, bumpScale: 0.5,  bumpFreq: 70  },
  leather:  { roughness: 0.35, metalness: 0.05, bumpScale: 0.15, bumpFreq: 20  },
};

/* --- Time-of-day lighting presets --------------------------- */
const LIGHT_PRESETS = {
  morning_cool: { key: 0xD6E4F0, fill: 0x8AACC8, amb: 0x9AAFCA, intensity: 1.1, keyY: 4, keyZ: 3 },
  noon_neutral: { key: 0xFFFAF0, fill: 0xD4D0C8, amb: 0xE8E4DC, intensity: 1.3, keyY: 6, keyZ: 1 },
  golden_hour:  { key: 0xFFD4A0, fill: 0xE8B878, amb: 0xF0D8B0, intensity: 1.4, keyY: 2, keyZ: 4 },
  evening_lamp: { key: 0xFFBF70, fill: 0x887050, amb: 0x605040, intensity: 0.9, keyY: 3, keyZ: 2 },
};

/* --- Shadow presets ----------------------------------------- */
const SHADOW_PRESETS = {
  soft_diffuse:  { bias: -0.002, radius: 8, mapSize: 1024 },
  directional_4: { bias: -0.001, radius: 3, mapSize: 2048 },
  hard_studio_5: { bias: -0.0005, radius: 1, mapSize: 2048 },
};

/* --- Procedural bump texture -------------------------------- */
function createBumpTexture(freq, size = 256) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(size, size);
  for (let i = 0; i < size * size; i++) {
    const x = i % size, y = (i / size) | 0;
    const n1 = Math.sin(x * freq / size) * Math.cos(y * freq / size);
    const n2 = Math.sin((x + y) * freq * 0.7 / size);
    const n3 = Math.cos((x - y * 0.5) * freq * 1.3 / size);
    const v = ((n1 + n2 + n3) / 3 + 1) * 0.5;
    const byte = (v * 255) | 0;
    img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = byte;
    img.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(2, 2);
  return tex;
}

/* --- Leg geometry builders ---------------------------------- */
function createLegs(legType, bedW, bedD, frameH) {
  const group = new THREE.Group();
  const legH = 0.15;
  const inset = 0.06;

  const positions = [
    [-bedW / 2 + inset, 0, -bedD / 2 + inset],
    [bedW / 2 - inset, 0, -bedD / 2 + inset],
    [-bedW / 2 + inset, 0, bedD / 2 - inset],
    [bedW / 2 - inset, 0, bedD / 2 - inset],
  ];

  const woodColor = 0x9B7048;
  const metalColor = 0x7A7770;
  const darkColor = 0x1A1B19;

  if (legType === "hidden") {
    const plinth = new THREE.Mesh(
      new THREE.BoxGeometry(bedW - 0.04, 0.06, bedD - 0.04),
      new THREE.MeshStandardMaterial({ color: darkColor, roughness: 0.9 })
    );
    plinth.position.y = frameH + 0.03;
    plinth.castShadow = true;
    group.add(plinth);
    return group;
  }

  if (legType === "swivel") {
    const pole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.015, 0.015, legH * 0.6, 8),
      new THREE.MeshStandardMaterial({ color: metalColor, roughness: 0.3, metalness: 0.7 })
    );
    pole.position.y = frameH + legH * 0.3;
    pole.castShadow = true;
    const base = new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.14, 0.03, 16),
      new THREE.MeshStandardMaterial({ color: metalColor, roughness: 0.3, metalness: 0.7 })
    );
    base.position.y = frameH + legH * 0.6 + 0.015;
    base.castShadow = true;
    group.add(pole, base);
    return group;
  }

  positions.forEach(([px, , pz]) => {
    let leg;
    if (legType === "wood" || legType === "keep") {
      leg = new THREE.Mesh(
        new THREE.CylinderGeometry(0.018, 0.013, legH, 8),
        new THREE.MeshStandardMaterial({ color: woodColor, roughness: 0.6 })
      );
    } else if (legType === "metal") {
      const g = new THREE.Group();
      const rod1 = new THREE.Mesh(
        new THREE.CylinderGeometry(0.006, 0.006, legH, 6),
        new THREE.MeshStandardMaterial({ color: metalColor, roughness: 0.25, metalness: 0.8 })
      );
      rod1.position.x = -0.015;
      const rod2 = rod1.clone();
      rod2.position.x = 0.015;
      const cross = new THREE.Mesh(
        new THREE.CylinderGeometry(0.004, 0.004, 0.04, 6),
        new THREE.MeshStandardMaterial({ color: metalColor, roughness: 0.25, metalness: 0.8 })
      );
      cross.rotation.z = Math.PI / 2;
      cross.position.y = legH * 0.3;
      g.add(rod1, rod2, cross);
      g.position.set(px, frameH + legH / 2, pz);
      g.traverse(c => { if (c.isMesh) c.castShadow = true; });
      group.add(g);
      return;
    } else if (legType === "block") {
      leg = new THREE.Mesh(
        new THREE.BoxGeometry(0.05, legH, 0.05),
        new THREE.MeshStandardMaterial({ color: woodColor, roughness: 0.55 })
      );
    } else {
      return;
    }
    leg.position.set(px, frameH + legH / 2, pz);
    leg.castShadow = true;
    group.add(leg);
  });

  return group;
}

/* --- Pillow geometry ---------------------------------------- */
function createPillow(w, h, d) {
  const shape = new THREE.Shape();
  const r = Math.min(w, d) * 0.3;
  shape.moveTo(-w / 2 + r, -d / 2);
  shape.lineTo(w / 2 - r, -d / 2);
  shape.quadraticCurveTo(w / 2, -d / 2, w / 2, -d / 2 + r);
  shape.lineTo(w / 2, d / 2 - r);
  shape.quadraticCurveTo(w / 2, d / 2, w / 2 - r, d / 2);
  shape.lineTo(-w / 2 + r, d / 2);
  shape.quadraticCurveTo(-w / 2, d / 2, -w / 2, d / 2 - r);
  shape.lineTo(-w / 2, -d / 2 + r);
  shape.quadraticCurveTo(-w / 2, -d / 2, -w / 2 + r, -d / 2);

  const extrudeSettings = { depth: h, bevelEnabled: true, bevelThickness: h * 0.35, bevelSize: r * 0.5, bevelSegments: 6 };
  const geom = new THREE.ExtrudeGeometry(shape, extrudeSettings);
  geom.computeVertexNormals();
  geom.rotateX(-Math.PI / 2);
  geom.translate(0, h / 2, 0);
  return geom;
}

/* ============================================================
   React component
   ============================================================ */
function Bed3DViewer({ color, material, legs, tod, shadow, size, bedding, env }) {
  const mountRef = useRef(null);
  const sceneRef = useRef({});

  const colorHex = color || "#6F8C68";
  const matId = material || "boucle";
  const legType = legs || "wood";
  const todId = tod || "noon_neutral";
  const shadowId = shadow || "soft_diffuse";

  const bedWidth = useMemo(() => {
    const cm = parseInt(size) || 160;
    return cm / 100 * 0.6;
  }, [size]);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, container.clientWidth / container.clientHeight, 0.1, 50);
    camera.position.set(2.2, 1.5, 2.2);
    camera.lookAt(0, 0.3, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    if (renderer.outputColorSpace !== undefined) {
      renderer.outputColorSpace = THREE.SRGBColorSpace;
    } else {
      renderer.outputEncoding = THREE.sRGBEncoding;
    }
    container.appendChild(renderer.domElement);

    // Floor
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(8, 8),
      new THREE.ShadowMaterial({ opacity: 0.18 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    // Ambient
    const ambient = new THREE.AmbientLight(0xE8E4DC, 0.5);
    scene.add(ambient);

    // Key light
    const keyLight = new THREE.DirectionalLight(0xFFFAF0, 1.3);
    keyLight.position.set(3, 6, 3);
    keyLight.castShadow = true;
    keyLight.shadow.camera.left = -3;
    keyLight.shadow.camera.right = 3;
    keyLight.shadow.camera.top = 3;
    keyLight.shadow.camera.bottom = -3;
    keyLight.shadow.mapSize.width = 2048;
    keyLight.shadow.mapSize.height = 2048;
    scene.add(keyLight);

    // Fill
    const fillLight = new THREE.DirectionalLight(0xD4D0C8, 0.4);
    fillLight.position.set(-2, 3, -1);
    scene.add(fillLight);

    // Rim
    const rimLight = new THREE.DirectionalLight(0xFFFFFF, 0.2);
    rimLight.position.set(0, 2, -4);
    scene.add(rimLight);

    // Orbit controls (manual)
    let isDragging = false;
    let prevX = 0, prevY = 0;
    let theta = Math.PI / 4, phi = Math.PI / 5;
    let radius = 3.2;

    function updateCamera() {
      camera.position.x = radius * Math.sin(theta) * Math.cos(phi);
      camera.position.y = radius * Math.sin(phi) + 0.3;
      camera.position.z = radius * Math.cos(theta) * Math.cos(phi);
      camera.lookAt(0, 0.25, 0);
    }
    updateCamera();

    const onPointerDown = (e) => { isDragging = true; prevX = e.clientX; prevY = e.clientY; };
    const onPointerMove = (e) => {
      if (!isDragging) return;
      const dx = e.clientX - prevX;
      const dy = e.clientY - prevY;
      theta -= dx * 0.006;
      phi = Math.max(0.05, Math.min(Math.PI / 2.2, phi + dy * 0.006));
      prevX = e.clientX; prevY = e.clientY;
      updateCamera();
    };
    const onPointerUp = () => { isDragging = false; };
    const onWheel = (e) => {
      e.preventDefault();
      radius = Math.max(1.5, Math.min(6, radius + e.deltaY * 0.003));
      updateCamera();
    };

    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    renderer.domElement.addEventListener("wheel", onWheel, { passive: false });

    // Store refs for updates
    sceneRef.current = {
      scene, camera, renderer, keyLight, fillLight, ambient, rimLight,
      bedGroup: null, legsGroup: null, updateCamera,
      theta: () => theta, phi: () => phi, radius: () => radius,
    };

    // Animation loop
    let raf;
    function animate() {
      raf = requestAnimationFrame(animate);
      renderer.render(scene, camera);
    }
    animate();

    // Resize
    const ro = new ResizeObserver(() => {
      const w = container.clientWidth, h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    ro.observe(container);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("wheel", onWheel);
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, []);

  // Rebuild bed when params change
  useEffect(() => {
    const s = sceneRef.current;
    if (!s.scene) return;

    // Remove old bed
    if (s.bedGroup) { s.scene.remove(s.bedGroup); }
    if (s.legsGroup) { s.scene.remove(s.legsGroup); }

    const bedD = 1.2; // depth (front-to-back) fixed at 200cm scale
    const bedW = bedWidth;
    const frameH = 0.0;
    const platformH = 0.08;
    const mattressH = 0.16;
    const headboardH = 0.5;

    const profile = MAT_PROFILES[matId] || MAT_PROFILES.boucle;
    const bumpTex = createBumpTexture(profile.bumpFreq);
    const fabricColor = new THREE.Color(colorHex);

    const fabricMat = new THREE.MeshStandardMaterial({
      color: fabricColor,
      roughness: profile.roughness,
      metalness: profile.metalness,
      bumpMap: bumpTex,
      bumpScale: profile.bumpScale * 0.02,
    });

    const frameMat = new THREE.MeshStandardMaterial({
      color: fabricColor.clone().multiplyScalar(0.7),
      roughness: 0.8,
    });

    const bedGroup = new THREE.Group();

    // Platform
    const platform = new THREE.Mesh(
      new THREE.BoxGeometry(bedW, platformH, bedD),
      frameMat
    );
    platform.position.y = frameH + platformH / 2 + 0.15;
    platform.castShadow = true;
    platform.receiveShadow = true;
    bedGroup.add(platform);

    // Mattress
    const mattressGeom = new THREE.BoxGeometry(bedW - 0.04, mattressH, bedD - 0.06);
    mattressGeom.translate(0, 0, 0.01);
    // Round the mattress edges via scale trick (bevel approximation)
    const mattress = new THREE.Mesh(mattressGeom, new THREE.MeshStandardMaterial({
      color: 0xF5F0E8,
      roughness: 0.9,
      bumpMap: createBumpTexture(30),
      bumpScale: 0.005,
    }));
    mattress.position.y = frameH + platformH + mattressH / 2 + 0.15;
    mattress.castShadow = true;
    mattress.receiveShadow = true;
    bedGroup.add(mattress);

    // Headboard
    const hbGeom = new THREE.BoxGeometry(bedW + 0.04, headboardH, 0.08);
    const headboard = new THREE.Mesh(hbGeom, fabricMat);
    headboard.position.set(0, frameH + platformH + headboardH / 2 + 0.15, -bedD / 2 + 0.02);
    headboard.castShadow = true;
    bedGroup.add(headboard);

    // Headboard top cap (rounded look)
    const capGeom = new THREE.CylinderGeometry(0.04, 0.04, bedW + 0.04, 16, 1, false, 0, Math.PI);
    capGeom.rotateZ(Math.PI / 2);
    capGeom.rotateY(Math.PI / 2);
    const cap = new THREE.Mesh(capGeom, fabricMat);
    cap.position.set(0, frameH + platformH + headboardH + 0.15, -bedD / 2 + 0.02);
    cap.castShadow = true;
    bedGroup.add(cap);

    // Bedding / duvet
    const beddingColor = getBeddingColor(bedding);
    const duvetGeom = new THREE.BoxGeometry(bedW - 0.06, 0.06, bedD * 0.65);
    const duvet = new THREE.Mesh(duvetGeom, new THREE.MeshStandardMaterial({
      color: new THREE.Color(beddingColor),
      roughness: 0.92,
      bumpMap: createBumpTexture(25),
      bumpScale: 0.008,
    }));
    duvet.position.set(0, frameH + platformH + mattressH + 0.03 + 0.15, bedD * 0.1);
    duvet.castShadow = true;
    bedGroup.add(duvet);

    // Pillows
    const pillowCount = parseInt(size) >= 160 ? 3 : parseInt(size) >= 120 ? 2 : 1;
    const pillowW = (bedW - 0.12) / pillowCount - 0.02;
    for (let i = 0; i < pillowCount; i++) {
      const px = -((pillowCount - 1) * (pillowW + 0.02)) / 2 + i * (pillowW + 0.02);
      const pillowGeom = createPillow(pillowW, 0.06, 0.18);
      const pillow = new THREE.Mesh(pillowGeom, new THREE.MeshStandardMaterial({
        color: 0xFAF6F0,
        roughness: 0.88,
        bumpMap: createBumpTexture(35),
        bumpScale: 0.004,
      }));
      pillow.position.set(px, frameH + platformH + mattressH + 0.15, -bedD / 2 + 0.22);
      pillow.castShadow = true;
      bedGroup.add(pillow);
    }

    s.scene.add(bedGroup);
    s.bedGroup = bedGroup;

    // Legs
    const legsGroup = createLegs(legType, bedW, bedD, frameH);
    s.scene.add(legsGroup);
    s.legsGroup = legsGroup;

    return () => {
      fabricMat.dispose();
      frameMat.dispose();
      bumpTex.dispose();
    };
  }, [colorHex, matId, legType, bedWidth, bedding, size]);

  // Update lighting
  useEffect(() => {
    const s = sceneRef.current;
    if (!s.keyLight) return;

    const lp = LIGHT_PRESETS[todId] || LIGHT_PRESETS.noon_neutral;
    s.keyLight.color.setHex(lp.key);
    s.keyLight.intensity = lp.intensity;
    s.keyLight.position.y = lp.keyY;
    s.keyLight.position.z = lp.keyZ;
    s.fillLight.color.setHex(lp.fill);
    s.ambient.color.setHex(lp.amb);

    const sp = SHADOW_PRESETS[shadowId] || SHADOW_PRESETS.soft_diffuse;
    s.keyLight.shadow.bias = sp.bias;
    s.keyLight.shadow.radius = sp.radius;
    s.keyLight.shadow.mapSize.width = sp.mapSize;
    s.keyLight.shadow.mapSize.height = sp.mapSize;
  }, [todId, shadowId]);

  // Update background based on environment
  useEffect(() => {
    const s = sceneRef.current;
    if (!s.scene) return;
    const envBg = getEnvBackground(env);
    s.scene.background = new THREE.Color(envBg);
  }, [env]);

  return React.createElement("div", {
    ref: mountRef,
    style: {
      width: "100%",
      height: "100%",
      cursor: "grab",
      touchAction: "none",
    },
  });
}

/* --- Helpers ------------------------------------------------ */
function getBeddingColor(beddingId) {
  const map = {
    linen_white: "#F5F0E8",
    linen_natural: "#E8DCC8",
    linen_grey: "#C8C4BC",
    linen_sage: "#C8D4BC",
    cotton_white: "#FEFEFE",
    jersey_warm: "#E8D8C4",
  };
  return map[beddingId] || "#F5F0E8";
}

function getEnvBackground(envId) {
  const map = {
    cyclorama_warm: "#F4F0E5",
    cyclorama_neutral: "#FAFAFA",
    cyclorama_grey: "#DCDCDC",
    cyclorama_architectural: "#F7F3EA",
    cyclorama_softlight: "#FAF8F6",
    cyclorama_paperwhite: "#FCFAF7",
    scandi: "#EFE8D6",
    loft: "#C9B79C",
    japandi: "#E9DDC4",
    boho: "#E5C6A0",
    dark_moody: "#3D3A33",
    garden: "#C8D4B6",
    showroom: "#EAE2CE",
    studio_white: "#F4F0E5",
    studio_grey: "#DEDED9",
  };
  return map[envId] || "#EDE9DF";
}
