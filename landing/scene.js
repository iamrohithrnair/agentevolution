import * as THREE from 'three';

const APP_URL = 'http://localhost:3000';

// ── Renderer ──
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2.5));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
(document.getElementById('root') ?? document.body).appendChild(renderer.domElement);
renderer.domElement.style.position = 'fixed';
renderer.domElement.style.top = '0';
renderer.domElement.style.left = '0';
renderer.domElement.style.zIndex = '1';

// ── Global State ──
const STATE = {
  scrollY: 0,
  scrollProgress: 0,
  mouseX: 0,
  mouseY: 0,
  mouseNX: 0,
  mouseNY: 0,
  soundEnabled: true,
  reducedMotion: true,
  currentDrone: 0,
  flightMode: 1,
  launched: false,
  launchTime: 0,
  dogfightActive: false,
  stormActive: false,
  autopilotActive: false,
  section: 0
};

// ── Audio Engine — DISABLED (no-op stubs; landing page is silent) ──
let audioCtx = null;
const ambientLayers = { started: false, hum: null };
function ensureAudio() {}
function setMasterVolume() {}
function createPanner() { return null; }
function playTone() {}
function playNoiseBurst() {}
function playHover() {}
function playHoverSoft() {}
function playHoverDeep() {}
function playHoverBright() {}
function playHoverWarm() {}
function playClick() {}
function playClickSoft() {}
function playClickDeep() {}
function playClickBright() {}
function playClickNav() {}
function playClickToggle() {}
function playInputFocus() {}
function playInputBlur() {}
function playRipple() {}
function playLaser() {}
function playSwirl() {}
function playMorph() {}
function playLaunch() {}
function playThunder() {}
function playCinematicWhoosh() {}
function playScrollTick() {}
function playScrollWhoosh() {}
function playSectionReveal() {}
function startAmbientLayers() {}
function muteAmbientLayers() {}
function updateAmbientMix() {}
function startStormAmbient() {}
function stopStormAmbient() {}
function updateStormAmbient() {}
function startPropellerHum() {}
function updateHumPitch() {}

// ── CSS Overlay ──
const overlay = document.createElement('div');
overlay.id = 'ui-overlay';
document.body.appendChild(overlay);

const style = document.createElement('style');
style.textContent = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700&family=Sora:wght@300;400;500;600;700&family=General+Sans:wght@400;500;600;700&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  body { overflow-x:hidden; background:#ffffff; color:#111118; font-family:'Outfit',sans-serif; cursor:default; }
  ::selection { background:rgba(56,120,255,0.3); }
  #ui-overlay { position:absolute; top:0; left:0; width:100%; pointer-events:none; z-index:10; }
  #ui-overlay * { pointer-events:auto; }

  /* ── NAV ── */
  .nav { position:fixed; top:0; left:0; width:100%; z-index:100; padding:20px 48px;
    display:flex; align-items:center; justify-content:space-between;
    background:rgba(255,255,255,0.75);
    backdrop-filter:blur(40px); -webkit-backdrop-filter:blur(40px); transition:all 0.5s;
    border-bottom:1px solid rgba(0,0,0,0.06); }
  .nav-logo { font-family:'Sora',sans-serif; font-weight:700; font-size:20px;
    letter-spacing:1.5px; display:flex; align-items:center; gap:10px; color:#0a0a12; }
  .nav-logo svg { width:28px; height:28px; }
  .nav-links { display:flex; gap:32px; align-items:center; }
  .nav-link { color:rgba(0,0,0,0.5); font-size:13px; font-family:'Outfit',sans-serif; font-weight:500; letter-spacing:0.4px;
    text-decoration:none; transition:color 0.4s; position:relative; cursor:pointer; padding:4px 0; }
  .nav-link:hover { color:rgba(0,0,0,0.85); }
  .nav-link::after { content:''; position:absolute; bottom:-2px; left:0; width:0; height:1px;
    background:rgba(0,0,0,0.3); transition:width 0.4s; }
  .nav-link:hover::after { width:100%; }
  .nav-actions { display:flex; gap:16px; align-items:center; }
  .nav-btn { padding:8px 20px; border-radius:6px; font-size:13px; font-family:'Outfit',sans-serif; font-weight:500;
    cursor:pointer; transition:all 0.3s; border:none; letter-spacing:0.4px; text-decoration:none;
    display:inline-flex; align-items:center; justify-content:center; }
  .btn-ghost { background:transparent; color:rgba(0,0,0,0.55); border:1px solid rgba(0,0,0,0.14); }
  .btn-ghost:hover { border-color:rgba(0,0,0,0.28); color:rgba(0,0,0,0.85); }
  .btn-primary { background:rgba(0,0,0,0.07); color:rgba(0,0,0,0.8); border:1px solid rgba(0,0,0,0.12); }
  .btn-primary:hover { background:rgba(0,0,0,0.12); border-color:rgba(0,0,0,0.22); color:#000; }
  .sound-toggle { width:36px; height:36px; border-radius:50%; background:rgba(0,0,0,0.04);
    border:1px solid rgba(0,0,0,0.08); display:flex; align-items:center; justify-content:center;
    cursor:pointer; transition:all 0.3s; color:rgba(0,0,0,0.4); font-size:16px; }
  .sound-toggle:hover { background:rgba(0,0,0,0.08); color:rgba(0,0,0,0.8); }

  /* ── HERO ── */
  .hero { height:100vh; display:flex; align-items:center; padding:0 48px; position:relative; }
  .hero-content { max-width:560px; z-index:2; }
  .hero-badge { display:inline-flex; align-items:center; gap:8px; padding:6px 16px; border-radius:100px;
    background:rgba(0,0,0,0.04); border:1px solid rgba(0,0,0,0.1);
    font-family:'Outfit',sans-serif; font-size:11px; color:rgba(0,0,0,0.48); font-weight:600; letter-spacing:1.5px; margin-bottom:28px;
    text-transform:uppercase; }
  .hero-badge .dot { width:5px; height:5px; border-radius:50%; background:rgba(0,0,0,0.3);
    animation:pulse-dot 3s ease-in-out infinite; }
  @keyframes pulse-dot { 0%,100%{opacity:0.6;transform:scale(1)} 50%{opacity:0.2;transform:scale(0.7)} }
  .hero-title { font-family:'Sora',sans-serif; font-size:60px; font-weight:700;
    line-height:1.1; letter-spacing:-1.5px; margin-bottom:22px; color:rgba(0,0,0,0.92); }
  .hero-title .gradient { background:linear-gradient(135deg,rgba(0,0,0,0.92) 0%,rgba(0,0,0,0.55) 100%);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
  .hero-sub { font-family:'Outfit',sans-serif; font-size:17px; color:rgba(0,0,0,0.52); line-height:1.85;
    margin-bottom:40px; font-weight:400; max-width:440px; letter-spacing:0.15px; }
  .hero-ctas { display:flex; gap:14px; align-items:center; }
  .cta-launch { padding:14px 34px; border-radius:100px; background:#0a0a12; color:#ffffff; font-family:'Outfit',sans-serif; font-size:14px;
    font-weight:600; border:none; cursor:pointer; transition:all 0.4s; position:relative; overflow:hidden;
    letter-spacing:0.5px; }
  .cta-launch:hover { background:#1a1a28; transform:translateY(-1px); }
  .cta-launch .ripple { position:absolute; border-radius:50%; background:rgba(255,255,255,0.15);
    transform:scale(0); animation:ripple-anim 0.6s ease-out; pointer-events:none; }
  @keyframes ripple-anim { to { transform:scale(4); opacity:0; } }
  .cta-explore { padding:14px 28px; border-radius:100px; background:transparent; color:rgba(0,0,0,0.55);
    font-family:'Outfit',sans-serif; font-size:14px; font-weight:500; border:1px solid rgba(0,0,0,0.14); cursor:pointer;
    transition:all 0.4s; display:flex; align-items:center; gap:8px; letter-spacing:0.4px; }
  .cta-explore:hover { border-color:rgba(0,0,0,0.28); color:rgba(0,0,0,0.8); }
  .cta-explore svg { transition:transform 0.3s; opacity:0.4; }
  .cta-explore:hover svg { transform:translateX(3px); opacity:0.7; }

  /* ── HERO STATS ── */
  .hero-stats { position:absolute; right:48px; bottom:80px; display:flex; gap:40px; z-index:2; }
  .stat { text-align:right; }
  .stat-value { font-family:'Sora',sans-serif; font-size:28px; font-weight:700; color:rgba(0,0,0,0.82); letter-spacing:-0.5px; }
  .stat-label { font-family:'Outfit',sans-serif; font-size:10px; color:rgba(0,0,0,0.4); text-transform:uppercase;
    letter-spacing:2.5px; margin-top:6px; font-weight:500; }

  /* ── SCROLL SECTIONS ── */
  .scroll-section { min-height:100vh; padding:120px 48px; position:relative;
    display:flex; align-items:center; opacity:0; transform:translateY(40px);
    transition:opacity 0.8s, transform 0.8s; }
  .scroll-section.visible { opacity:1; transform:translateY(0); }
  .section-content { max-width:480px; z-index:2; }
  .section-label { font-family:'Outfit',sans-serif; font-size:11px; color:rgba(0,0,0,0.42); text-transform:uppercase;
    letter-spacing:3.5px; font-weight:600; margin-bottom:20px; }
  .section-title { font-family:'Sora',sans-serif; font-size:44px; font-weight:700;
    line-height:1.12; letter-spacing:-1.2px; margin-bottom:18px; color:rgba(0,0,0,0.88); }
  .section-desc { font-family:'Outfit',sans-serif; font-size:16px; color:rgba(0,0,0,0.5); line-height:1.85;
    margin-bottom:36px; font-weight:400; letter-spacing:0.15px; }

  /* ── FLOATING PANELS ── */
  .float-panels { display:flex; flex-wrap:wrap; gap:10px; }
  .float-panel { padding:10px 18px; border-radius:8px;
    background:rgba(0,0,0,0.03); border:1px solid rgba(0,0,0,0.09);
    backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
    font-family:'Outfit',sans-serif; font-size:13px; font-weight:500; color:rgba(0,0,0,0.52);
    letter-spacing:0.3px; transition:all 0.5s; cursor:default; position:relative; overflow:hidden; }
  .float-panel:hover { background:rgba(0,0,0,0.06); border-color:rgba(0,0,0,0.16);
    color:rgba(0,0,0,0.78); transform:translateY(-1px); }
  .float-panel .panel-icon { margin-right:8px; opacity:0.5; }

  /* ── DRONE SELECTOR ── */
  .drone-selector { min-height:100vh; padding:120px 48px; }
  .drone-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
    gap:16px; margin-top:40px; }
  .drone-card { padding:24px; border-radius:12px; background:rgba(0,0,0,0.018);
    border:1px solid rgba(0,0,0,0.07); cursor:pointer; transition:all 0.5s;
    text-align:center; position:relative; overflow:hidden; }
  .drone-card:hover { background:rgba(0,0,0,0.045); border-color:rgba(0,0,0,0.14);
    transform:translateY(-2px); }
  .drone-card.active { border-color:rgba(0,0,0,0.2); background:rgba(0,0,0,0.055); }
  .drone-card .drone-icon { font-size:32px; margin-bottom:12px; display:block; opacity:0.55; }
  .drone-card .drone-name { font-family:'Sora',sans-serif; font-size:14px; font-weight:600; margin-bottom:4px; color:rgba(0,0,0,0.78); letter-spacing:0.1px; }
  .drone-card .drone-type { font-family:'Outfit',sans-serif; font-size:11px; color:rgba(0,0,0,0.4); letter-spacing:1px; text-transform:uppercase; font-weight:500; }

  /* ── ACTION BAR ── */
  .action-bar { position:fixed; bottom:24px; left:50%; transform:translateX(-50%); z-index:100;
    display:flex; gap:6px; padding:6px; border-radius:100px;
    background:rgba(255,255,255,0.8); border:1px solid rgba(0,0,0,0.08);
    backdrop-filter:blur(40px); -webkit-backdrop-filter:blur(40px); }
  .action-btn { padding:7px 18px; border-radius:100px; font-family:'Outfit',sans-serif; font-size:12px; font-weight:500;
    border:1px solid rgba(0,0,0,0.09); background:transparent; color:rgba(0,0,0,0.5);
    cursor:pointer; transition:all 0.4s; white-space:nowrap; letter-spacing:0.5px; }
  .action-btn:hover { background:rgba(0,0,0,0.06); color:rgba(0,0,0,0.72); border-color:rgba(0,0,0,0.16); }
  .action-btn.active { background:rgba(0,0,0,0.08); border-color:rgba(0,0,0,0.18); color:rgba(0,0,0,0.82); }
  .action-btn.danger { border-color:rgba(0,0,0,0.07); color:rgba(0,0,0,0.38); }
  .action-btn.danger:hover { background:rgba(0,0,0,0.05); color:rgba(0,0,0,0.65); }
  .action-btn.danger.active { background:rgba(200,40,40,0.06); border-color:rgba(200,40,40,0.14); color:rgba(180,40,40,0.7); }

  /* ── FOOTER ── */
  .site-footer { position:relative; z-index:20; background:#fafafa; border-top:1px solid rgba(0,0,0,0.06);
    padding:0 48px; margin-top:0; }
  .footer-top { display:flex; gap:80px; padding:72px 0 56px; border-bottom:1px solid rgba(0,0,0,0.06); }
  .footer-brand { max-width:280px; flex-shrink:0; }
  .footer-logo { font-family:'Sora',sans-serif; font-weight:700; font-size:18px; letter-spacing:1.5px;
    display:flex; align-items:center; gap:10px; color:#0a0a12; margin-bottom:16px; }
  .footer-logo svg { width:24px; height:24px; }
  .footer-tagline { font-family:'Outfit',sans-serif; font-size:14px; color:rgba(0,0,0,0.45); line-height:1.8;
    font-weight:400; margin-bottom:28px; }
  .footer-social { display:flex; gap:8px; }
  .social-link { width:36px; height:36px; border-radius:50%; border:1px solid rgba(0,0,0,0.08);
    background:transparent; display:flex; align-items:center; justify-content:center;
    color:rgba(0,0,0,0.3); transition:all 0.3s; text-decoration:none; }
  .social-link:hover { border-color:rgba(0,0,0,0.2); color:rgba(0,0,0,0.6); background:rgba(0,0,0,0.03); }
  .footer-columns { display:flex; gap:56px; flex:1; }
  .footer-col { display:flex; flex-direction:column; gap:12px; }
  .footer-col-title { font-family:'Sora',sans-serif; font-size:11px; font-weight:700; letter-spacing:2px;
    text-transform:uppercase; color:rgba(0,0,0,0.62); margin-bottom:6px; }
  .footer-link { font-family:'Outfit',sans-serif; font-size:14px; color:rgba(0,0,0,0.42); text-decoration:none;
    transition:color 0.3s; font-weight:400; letter-spacing:0.1px; }
  .footer-link:hover { color:rgba(0,0,0,0.75); }
  .footer-newsletter { display:flex; align-items:center; justify-content:space-between; gap:40px;
    padding:40px 0; border-bottom:1px solid rgba(0,0,0,0.06); }
  .newsletter-title { font-family:'Sora',sans-serif; font-size:16px; font-weight:700; color:rgba(0,0,0,0.78);
    margin-bottom:4px; letter-spacing:-0.2px; }
  .newsletter-desc { font-family:'Outfit',sans-serif; font-size:14px; color:rgba(0,0,0,0.42); font-weight:400; }
  .newsletter-form { display:flex; gap:8px; }
  .newsletter-input { padding:10px 18px; border-radius:100px; border:1px solid rgba(0,0,0,0.12);
    background:rgba(0,0,0,0.02); font-family:'Outfit',sans-serif; font-size:14px; color:rgba(0,0,0,0.7);
    width:260px; outline:none; transition:all 0.3s; }
  .newsletter-input::placeholder { color:rgba(0,0,0,0.32); }
  .newsletter-input:focus { border-color:rgba(0,0,0,0.22); background:white; }
  .newsletter-btn { padding:10px 24px; border-radius:100px; background:#0a0a12; color:#fff;
    font-family:'Outfit',sans-serif; font-size:13px; font-weight:500; border:none; cursor:pointer;
    transition:all 0.3s; letter-spacing:0.3px; }
  .newsletter-btn:hover { background:#1a1a28; }
  .footer-bottom { display:flex; align-items:center; justify-content:space-between; padding:24px 0 32px; }
  .footer-legal { display:flex; align-items:center; gap:24px; }
  .footer-legal span { font-family:'Outfit',sans-serif; font-size:12px; color:rgba(0,0,0,0.38); font-weight:400; }
  .footer-legal-links { display:flex; gap:20px; }
  .legal-link { font-family:'Outfit',sans-serif; font-size:12px; color:rgba(0,0,0,0.38); text-decoration:none;
    transition:color 0.3s; font-weight:400; }
  .legal-link:hover { color:rgba(0,0,0,0.62); }
  .footer-locale { display:flex; align-items:center; gap:6px; font-family:'Outfit',sans-serif; font-size:12px;
    color:rgba(0,0,0,0.38); }
  .footer-locale svg { opacity:0.4; }

  @media(max-width:768px) {
    .site-footer { padding:0 20px; }
    .footer-top { flex-direction:column; gap:40px; padding:48px 0 40px; }
    .footer-brand { max-width:100%; }
    .footer-columns { flex-wrap:wrap; gap:32px; }
    .footer-col { min-width:140px; }
    .footer-newsletter { flex-direction:column; align-items:flex-start; gap:16px; padding:32px 0; }
    .newsletter-form { flex-direction:column; width:100%; }
    .newsletter-input { width:100%; }
    .footer-bottom { flex-direction:column; gap:12px; align-items:flex-start; }
    .footer-legal { flex-direction:column; gap:8px; }
  }

  /* ── SCROLL INDICATOR ── */
  .scroll-hint { position:fixed; bottom:100px; left:50%; transform:translateX(-50%); z-index:20;
    display:flex; flex-direction:column; align-items:center; gap:8px;
    animation:float-hint 2s ease-in-out infinite; opacity:0.4; transition:opacity 1s; }
  .scroll-hint.hidden { opacity:0; pointer-events:none; }
  .scroll-hint span { font-family:'Outfit',sans-serif; font-size:10px; text-transform:uppercase; letter-spacing:4px;
    color:rgba(0,0,0,0.35); font-weight:500; }
  .scroll-line { width:1px; height:28px; background:linear-gradient(180deg,rgba(0,0,0,0.12),transparent); }
  @keyframes float-hint { 0%,100%{transform:translateX(-50%) translateY(0)} 50%{transform:translateX(-50%) translateY(6px)} }

  /* ── HUD TELEMETRY ── */
  .hud { position:fixed; top:80px; right:48px; z-index:50; display:flex; flex-direction:column;
    gap:6px; opacity:0; transition:opacity 0.5s; }
  .hud.visible { opacity:1; }
  .hud-item { padding:6px 14px; border-radius:6px; background:rgba(255,255,255,0.82);
    border:1px solid rgba(0,0,0,0.09); font-size:11px; font-family:'Sora',sans-serif;
    color:rgba(0,0,0,0.45); display:flex; justify-content:space-between; gap:20px;
    backdrop-filter:blur(24px); letter-spacing:0.5px; font-weight:500; }
  .hud-item .hud-val { color:rgba(0,0,0,0.7); font-weight:600; font-variant-numeric:tabular-nums; }

  /* ── SECTION DOT INDICATORS ── */
  .section-dots { position:fixed; right:24px; top:50%; transform:translateY(-50%); z-index:80;
    display:flex; flex-direction:column; align-items:center; gap:18px;
    opacity:0; transition:opacity 0.6s ease; pointer-events:none; }
  .section-dots.visible { opacity:1; pointer-events:auto; }
  .section-dot { width:10px; height:10px; border-radius:50%; background:rgba(0,0,0,0.1);
    border:1.5px solid rgba(0,0,0,0.15); cursor:pointer; position:relative;
    transition:all 0.4s cubic-bezier(0.4,0,0.2,1); }
  .section-dot:hover { background:rgba(0,0,0,0.25); border-color:rgba(0,0,0,0.3); transform:scale(1.3); }
  .section-dot.active { background:rgba(0,0,0,0.55); border-color:rgba(0,0,0,0.55);
    box-shadow:0 0 0 4px rgba(0,0,0,0.06); transform:scale(1.15); }
  .section-dot-label { position:absolute; right:22px; top:50%; transform:translateY(-50%);
    font-family:'Outfit',sans-serif; font-size:11px; color:rgba(0,0,0,0.5); letter-spacing:0.5px;
    font-weight:500; white-space:nowrap; opacity:0; pointer-events:none;
    transition:opacity 0.25s ease, transform 0.25s ease; transform:translateY(-50%) translateX(6px);
    background:rgba(255,255,255,0.9); backdrop-filter:blur(12px); padding:4px 10px; border-radius:6px;
    border:1px solid rgba(0,0,0,0.08); }
  .section-dot:hover .section-dot-label { opacity:1; transform:translateY(-50%) translateX(0); }

  /* Responsive */
  @media(max-width:768px) {
    .nav { padding:16px 20px; }
    .nav-links { display:none; }
    .hero { padding:0 20px; }
    .hero-title { font-size:36px; }
    .hero-stats { display:none; }
    .scroll-section { padding:80px 20px; }
    .section-title { font-size:30px; }
    .action-bar { bottom:12px; padding:6px; gap:6px; }
    .action-btn { padding:6px 12px; font-size:11px; }
    .drone-grid { grid-template-columns:repeat(2,1fr); }
    .section-dots { right:12px; gap:14px; }
    .section-dot { width:8px; height:8px; }
    .section-dot-label { display:none; }
  }

  /* ── CONTRAST PASS: preserve original composition, darken text only ── */
  .nav-link { color:rgba(0,0,0,0.72); font-weight:600; }
  .hero-badge { color:rgba(0,0,0,0.68); }
  .hero-title,
  .section-title { color:rgba(0,0,0,0.96); }
  .hero-title .gradient {
    background:linear-gradient(135deg,rgba(0,0,0,0.98) 0%,rgba(0,0,0,0.72) 100%);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
  }
  .hero-sub,
  .section-desc { color:rgba(0,0,0,0.72); font-weight:500; }
  .section-label { color:rgba(0,0,0,0.68); }
  .cta-explore { color:rgba(0,0,0,0.76); font-weight:600; }
  .stat-label,
  .float-panel,
  .drone-card .drone-type,
  .footer-tagline,
  .footer-link,
  .newsletter-desc { color:rgba(0,0,0,0.62); }
  .drone-card .drone-name,
  .newsletter-title,
  .footer-col-title { color:rgba(0,0,0,0.86); }
`;
document.head.appendChild(style);

// ── Build HTML ──
overlay.innerHTML = `
  <nav class="nav">
    <div class="nav-logo">
      <svg viewBox="0 0 28 28" fill="none"><path d="M14 2L26 8v12l-12 6L2 20V8l12-6z" stroke="rgba(0,0,0,0.2)" stroke-width="1" fill="rgba(0,0,0,0.04)"/><circle cx="14" cy="14" r="3" fill="rgba(0,0,0,0.4)"/></svg>
      DRONAN
    </div>
    <div class="nav-links">
      <a class="nav-link" href="#section1">Self-Evolving Memory</a>
      <a class="nav-link" href="#section2">Voice Copilot</a>
      <a class="nav-link" href="#section3">Recoverable Agents</a>
      <a class="nav-link" href="#section4">Agent Fleet</a>
      <a class="nav-link" href="https://www.mongodb.com/atlas" target="_blank" rel="noopener">Built on Atlas</a>
    </div>
    <div class="nav-actions">
      <a class="nav-btn btn-primary" href="${APP_URL}">Open App</a>
    </div>
  </nav>

  <div class="section-dots" id="sectionDots">
    <div class="section-dot active" data-section="0"><span class="section-dot-label">Mission Brief</span></div>
    <div class="section-dot" data-section="1"><span class="section-dot-label">Self-Evolving Memory</span></div>
    <div class="section-dot" data-section="2"><span class="section-dot-label">Voice Copilot</span></div>
    <div class="section-dot" data-section="3"><span class="section-dot-label">Recoverable Agents</span></div>
    <div class="section-dot" data-section="4"><span class="section-dot-label">Agent Fleet</span></div>
  </div>

  <section class="hero" id="heroSection">
    <div class="hero-content">
      <div class="hero-badge"><span class="dot"></span> MONGODB AGENTIC EVOLUTION HACKATHON · LONDON 2026</div>
      <h1 class="hero-title">The first<br>self-evolving<br><span class="gradient">medical drone fleet.</span></h1>
      <p class="hero-sub">Dronan is a voice-piloted, multi-agent medical-delivery platform whose entire memory, recovery, and skill registry runs on MongoDB Atlas. Seventeen LangGraph agents reflect after every flight, embed lessons with Voyage AI, and get measurably faster &mdash; Take 3 finishes 30% sooner than Take 1.</p>
      <div class="hero-ctas">
        <button class="cta-launch" id="launchBtn">Dispatch Mission</button>
        <button class="cta-explore" id="exploreBtn">See How It Works <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
      </div>
    </div>
    <div class="hero-stats">
      <div class="stat"><div class="stat-value">17</div><div class="stat-label">LangGraph Agents</div></div>
      <div class="stat"><div class="stat-value">21</div><div class="stat-label">Atlas Collections</div></div>
      <div class="stat"><div class="stat-value">44k</div><div class="stat-label">Synthetic Emergencies</div></div>
    </div>
  </section>

  <section class="scroll-section" id="section1">
    <div class="section-content">
      <div class="section-label">01 &mdash; Self-Evolving Memory</div>
      <h2 class="section-title">Every mission teaches the next one.</h2>
      <p class="section-desc">After each delivery, the Reflection agent distils what went well and what didn&rsquo;t, embeds the lesson with Voyage <code>voyage-3-large</code>, and writes it to the <code>mission_memory</code> collection. The Planner retrieves matching lessons via Atlas <code>$vectorSearch</code> on the very next mission &mdash; and the fleet provably improves, take after take.</p>
      <div class="float-panels">
        <div class="float-panel"><span class="panel-icon">&#9670;</span> mission_memory</div>
        <div class="float-panel"><span class="panel-icon">&#9673;</span> Voyage Embeddings</div>
        <div class="float-panel"><span class="panel-icon">&#9674;</span> Atlas $vectorSearch</div>
        <div class="float-panel"><span class="panel-icon">&#9635;</span> reflection_eval</div>
      </div>
    </div>
  </section>

  <section class="scroll-section" id="section2" style="justify-content:flex-end;">
    <div class="section-content">
      <div class="section-label">02 &mdash; Voice Copilot</div>
      <h2 class="section-title">Speak the mission. Watch it fly.</h2>
      <p class="section-desc">A LiveKit room streams operator speech through Deepgram Nova-3, into a LangGraph supervisor, and back out as ElevenLabs Turbo v2.5 narration &mdash; under 2.5 seconds round-trip. The Narrator agent reads every state change aloud while drones reroute, recover, and deliver.</p>
      <div class="float-panels">
        <div class="float-panel"><span class="panel-icon">&#9678;</span> LiveKit Agents</div>
        <div class="float-panel"><span class="panel-icon">&#9790;</span> Deepgram Nova-3</div>
        <div class="float-panel"><span class="panel-icon">&#8853;</span> ElevenLabs Turbo</div>
        <div class="float-panel"><span class="panel-icon">&#9637;</span> Silero VAD</div>
      </div>
    </div>
  </section>

  <section class="scroll-section" id="section3">
    <div class="section-content">
      <div class="section-label">03 &mdash; Recoverable Agents</div>
      <h2 class="section-title">Pull the plug.<br>Resume the mission.</h2>
      <p class="section-desc">Every LangGraph node is checkpointed to MongoDB via <code>langgraph-checkpoint-mongodb</code>. Every tool call carries an idempotency key in <code>tool_call_log</code>. Crash mid-flight, restart the server, and the mission picks up at the exact next node &mdash; no duplicate dispatches, no orphaned drones.</p>
      <div class="float-panels">
        <div class="float-panel"><span class="panel-icon">&#9694;</span> MongoDBSaver</div>
        <div class="float-panel"><span class="panel-icon">&#9708;</span> Idempotency Keys</div>
        <div class="float-panel"><span class="panel-icon">&#9697;</span> Saga Compensation</div>
        <div class="float-panel"><span class="panel-icon">&#9670;</span> A2A Replay</div>
      </div>
    </div>
  </section>

  <section class="drone-selector scroll-section" id="section4" style="flex-direction:column;align-items:flex-start;justify-content:center;">
    <div class="section-content" style="max-width:100%;">
      <div class="section-label">04 &mdash; Agent Fleet</div>
      <h2 class="section-title">Seventeen specialists. One supervisor.</h2>
      <p class="section-desc">Each agent advertises its capabilities as a Voyage-embedded skill card in <code>agent_skills</code>. The Supervisor runs a vector search to pick the right peer for every sub-task. Inter-agent messages persist in <code>agent_messages</code> for full replay.</p>
    </div>
    <div class="drone-grid" id="droneGrid"></div>
  </section>

  <div class="scroll-hint" id="scrollHint">
    <span>Scroll to explore</span>
    <div class="scroll-line"></div>
  </div>

  <div class="hud" id="hud">
    <div class="hud-item"><span>MISSION</span><span class="hud-val" id="hudAlt">MED-0398</span></div>
    <div class="hud-item"><span>ETA</span><span class="hud-val" id="hudSpd">10.2 min</span></div>
    <div class="hud-item"><span>TAKE</span><span class="hud-val" id="hudBat">3 / 3</span></div>
    <div class="hud-item"><span>ATLAS</span><span class="hud-val" id="hudGps">LIVE</span></div>
    <div class="hud-item"><span>NODE</span><span class="hud-val" id="hudMode">PLANNER</span></div>
  </div>

  <div class="action-bar">
    <button class="action-btn" id="btnStorm">&#9889; Inject Storm</button>
    <button class="action-btn" id="btnDogfight">&#9876; Pull the Plug</button>
    <button class="action-btn" id="btnAutopilot">&#9678; Self-Evolve</button>
  </div>

  <footer class="site-footer" id="siteFooter">
    <div class="footer-top">
      <div class="footer-brand">
        <div class="footer-logo">
          <svg viewBox="0 0 28 28" fill="none"><path d="M14 2L26 8v12l-12 6L2 20V8l12-6z" stroke="rgba(0,0,0,0.15)" stroke-width="1" fill="rgba(0,0,0,0.03)"/><circle cx="14" cy="14" r="3" fill="rgba(0,0,0,0.25)"/></svg>
          DRONAN
        </div>
        <p class="footer-tagline">A voice-piloted, self-evolving medical drone fleet built on MongoDB Atlas, LangChain, LiveKit, and Voyage AI for the MongoDB Agentic Evolution Hackathon.</p>
        <div class="footer-social">
          <a href="javascript:void(0)" class="social-link" aria-label="GitHub">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
          </a>
          <a href="javascript:void(0)" class="social-link" aria-label="X">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4l11.733 16h4.267l-11.733 -16z"/><path d="M4 20l6.768 -6.768m2.46 -2.46l6.772 -6.772"/></svg>
          </a>
          <a href="javascript:void(0)" class="social-link" aria-label="LinkedIn">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="3"/><path d="M8 11v5"/><path d="M8 8v.01"/><path d="M12 16v-5c0-1.5 1-2 2-2s2 .5 2 2v5"/></svg>
          </a>
        </div>
      </div>
      <div class="footer-columns">
        <div class="footer-col">
          <h4 class="footer-col-title">Platform</h4>
          <a href="${APP_URL}" class="footer-link">Mission Console</a>
          <a href="javascript:void(0)" class="footer-link">Voice Copilot</a>
          <a href="javascript:void(0)" class="footer-link">Reflection Feed</a>
          <a href="javascript:void(0)" class="footer-link">Agent Skill Registry</a>
          <a href="javascript:void(0)" class="footer-link">Audit Trail</a>
          <a href="javascript:void(0)" class="footer-link">Trace Replay</a>
        </div>
        <div class="footer-col">
          <h4 class="footer-col-title">Built With</h4>
          <a href="https://www.mongodb.com/atlas" target="_blank" rel="noopener" class="footer-link">MongoDB Atlas</a>
          <a href="https://www.langchain.com/langgraph" target="_blank" rel="noopener" class="footer-link">LangChain &middot; LangGraph</a>
          <a href="https://www.voyageai.com/" target="_blank" rel="noopener" class="footer-link">Voyage AI</a>
          <a href="https://livekit.io/" target="_blank" rel="noopener" class="footer-link">LiveKit Agents</a>
          <a href="https://elevenlabs.io/" target="_blank" rel="noopener" class="footer-link">ElevenLabs</a>
          <a href="https://nextjs.org/" target="_blank" rel="noopener" class="footer-link">Next.js 15</a>
        </div>
        <div class="footer-col">
          <h4 class="footer-col-title">Use Cases</h4>
          <a href="javascript:void(0)" class="footer-link">NHS Blood Logistics</a>
          <a href="javascript:void(0)" class="footer-link">Disaster Response</a>
          <a href="javascript:void(0)" class="footer-link">Remote Clinics</a>
          <a href="javascript:void(0)" class="footer-link">Mass-Casualty Triage</a>
          <a href="javascript:void(0)" class="footer-link">Cold-Chain Plasma</a>
        </div>
        <div class="footer-col">
          <h4 class="footer-col-title">Hackathon</h4>
          <a href="javascript:void(0)" class="footer-link">Live Demo Script</a>
          <a href="javascript:void(0)" class="footer-link">Architecture</a>
          <a href="javascript:void(0)" class="footer-link">Acceptance Tests</a>
          <a href="javascript:void(0)" class="footer-link">Self-Evolution Proof</a>
          <a href="javascript:void(0)" class="footer-link">Judge Q&amp;A</a>
        </div>
      </div>
    </div>
    <div class="footer-newsletter">
      <div class="newsletter-text">
        <h4 class="newsletter-title">Get the demo invite</h4>
        <p class="newsletter-desc">We&rsquo;re running live judge demos at MongoDB.local London. Drop your email for a private invite and the post-event recording.</p>
      </div>
      <div class="newsletter-form">
        <input type="email" class="newsletter-input" placeholder="you@company.com" />
        <button class="newsletter-btn">Request Invite</button>
      </div>
    </div>
    <div class="footer-bottom">
      <div class="footer-legal">
        <span>&copy; 2026 Dronan &middot; Built for the MongoDB Agentic Evolution Hackathon</span>
        <div class="footer-legal-links">
          <a href="javascript:void(0)" class="legal-link">Privacy</a>
          <a href="javascript:void(0)" class="legal-link">Terms</a>
          <a href="javascript:void(0)" class="legal-link">Compliance</a>
        </div>
      </div>
      <div class="footer-locale">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        <span>London &middot; United Kingdom</span>
      </div>
    </div>
  </footer>
`;

// ── Drone Data ──
const DRONES = [
  { name:'Supervisor Agent',     type:'Routing & Orchestration',    icon:'◈', color:0x1e293b, accent:0x4F46E5 },
  { name:'Reflection Agent',     type:'Self-Evolution Loop',         icon:'◉', color:0x8888aa, accent:0x10B981 },
  { name:'Anomaly Agent',        type:'Telemetry & Recovery',        icon:'◊', color:0x2a2a2a, accent:0xDC2626 },
  { name:'Dispatch Agent',       type:'Cold-Chain Logistics',        icon:'▣', color:0xddaa44, accent:0xF59E0B },
  { name:'Replanner Agent',      type:'Adaptive VRP & Reroute',      icon:'◬', color:0x111111, accent:0xEC4899 },
  { name:'Vision Agent',         type:'Obstacle & Landing-Pad CV',   icon:'⊞', color:0x555566, accent:0x0EA5E9 },
  { name:'Narrator Agent',       type:'Voice & Operator Comms',      icon:'⊡', color:0x222233, accent:0x14B8A6 }
];

// Build drone grid
const droneGrid = document.getElementById('droneGrid');
DRONES.forEach((d, i) => {
  const card = document.createElement('div');
  card.className = 'drone-card' + (i === 0 ? ' active' : '');
  card.innerHTML = `<span class="drone-icon">${d.icon}</span><div class="drone-name">${d.name}</div><div class="drone-type">${d.type}</div>`;
  card.addEventListener('click', () => {
    playMorph();
    STATE.currentDrone = i;
    document.querySelectorAll('.drone-card').forEach((c, j) => c.classList.toggle('active', j === i));
    switchDrone(i);
  });
  droneGrid.appendChild(card);
});

// ── Launch Button ──
document.getElementById('launchBtn').addEventListener('click', function(e) {
  const rect = this.getBoundingClientRect();
  const ripple = document.createElement('span');
  ripple.className = 'ripple';
  ripple.style.left = (e.clientX - rect.left) + 'px';
  ripple.style.top = (e.clientY - rect.top) + 'px';
  ripple.style.width = ripple.style.height = '10px';
  this.appendChild(ripple);
  setTimeout(() => ripple.remove(), 600);
  playLaunch();
  STATE.launched = true;
  STATE.launchTime = performance.now() / 1000;
  startPropellerHum();
  startAmbientLayers();
  setTimeout(() => {
    window.location.href = APP_URL;
  }, 650);
});

document.getElementById('exploreBtn').addEventListener('click', () => {
  playClick();
  window.scrollTo({ top: window.innerHeight, behavior: 'smooth' });
});

// ── Action Buttons ──
document.getElementById('btnStorm').addEventListener('click', function() {
  STATE.stormActive = !STATE.stormActive;
  this.classList.toggle('active');
  if (STATE.stormActive) {
    playThunder();
    startStormAmbient();
  } else playClick();
});
document.getElementById('btnDogfight').addEventListener('click', function() {
  STATE.dogfightActive = !STATE.dogfightActive;
  this.classList.toggle('active');
  this.classList.toggle('danger');
  playClick();
});
document.getElementById('btnAutopilot').addEventListener('click', function() {
  STATE.autopilotActive = !STATE.autopilotActive;
  this.classList.toggle('active');
  playClick();
});

// ── Double-click Easter Egg ──
renderer.domElement.addEventListener('dblclick', () => {
  STATE.flightMode = STATE.flightMode === 1 ? 2 : 1;
  playMorph();
  document.getElementById('hudMode').textContent = STATE.flightMode === 1 ? 'HOVER' : 'CINEMATIC';
});

// ── 3D Click Interaction — raycast to objects and apply forces ──
renderer.domElement.addEventListener('click', (e) => {
  interact3D.pointer.set(
    (e.clientX / window.innerWidth) * 2 - 1,
    -(e.clientY / window.innerHeight) * 2 + 1
  );
  interact3D.raycaster.setFromCamera(interact3D.pointer, camera);

  // Collect all interactive meshes
  const testObjects = [];
  mainDrone.traverse(c => { if (c.isMesh) testObjects.push(c); });
  enemyDrones.forEach(ed => ed.traverse(c => { if (c.isMesh) testObjects.push(c); }));
  obstacles.forEach(ob => { if (ob.isMesh) testObjects.push(ob); });
  windmills.forEach(wm => wm.traverse(c => { if (c.isMesh) testObjects.push(c); }));
  // holo rings, energy beam etc
  [holoRing1, holoRing2, holoRing3, scanGrid, energyBeam, contactShadow, forceRing].forEach(m => {
    if (m.isMesh) testObjects.push(m);
  });

  const hits = interact3D.raycaster.intersectObjects(testObjects, false);
  if (hits.length > 0) {
    const hit = hits[0];
    interact3D.clickedObject = hit.object;
    interact3D.clickForce = 1.5;
    interact3D.clickOrigin.copy(hit.point);
    interact3D.clickDir.copy(interact3D.raycaster.ray.direction);

    // Spatial sound varies by what was clicked
    const name = hit.object.name || '';
    const hp = hit.point;
    if (name.includes('drone') || name.includes('Drone')) {
      playTone(300, 0.15, 0.03, 'triangle', { spatial: true, x: hp.x, y: hp.y, z: hp.z });
      playTone(600, 0.2, 0.02, 'sine', { spatial: true, x: hp.x, y: hp.y, z: hp.z });
      playNoiseBurst(0.15, 0.015, 800, 3, 'bandpass');
    } else if (name.includes('windmill')) {
      playTone(200, 0.25, 0.025, 'sine', { spatial: true, x: hp.x, y: hp.y, z: hp.z });
      playNoiseBurst(0.2, 0.01, 400, 2, 'lowpass');
    } else {
      playTone(400, 0.12, 0.02, 'sine', { spatial: true, x: hp.x, y: hp.y, z: hp.z });
    }

    // Spawn 3D impact ripple rings at click point — more for the drone
    const hitNormal = hit.face ? hit.face.normal : new THREE.Vector3(0, 1, 0);
    const name2 = hit.object.name || '';
    if (name2.includes('drone') || name2.includes('Drone')) {
      spawnMultiRipple(hit.point, hitNormal, 4);
    } else {
      spawnMultiRipple(hit.point, hitNormal, 2);
    }
  }
});

// ── Impact Ripple Ring — expanding torus at click point ──
function spawnImpactRipple(point, normal) {
  const rippleGeo = new THREE.TorusGeometry(0.05, 0.008, 16, 64);
  const rippleMat = new THREE.MeshBasicMaterial({
    color: 0x8899bb, transparent: true, opacity: 0.6, depthWrite: false,
    blending: THREE.AdditiveBlending, side: THREE.DoubleSide
  });
  const ring = new THREE.Mesh(rippleGeo, rippleMat);
  ring.position.copy(point);
  // Orient ring to face along the hit normal
  const up = new THREE.Vector3(0, 0, 1);
  const quat = new THREE.Quaternion().setFromUnitVectors(up, normal.clone().normalize());
  ring.quaternion.copy(quat);
  scene.add(ring);
  interact3D.impactRipples.push({ mesh: ring, age: 0, maxAge: 0.8 });
}

// ── Spawn multiple concentric ripples for stronger hits ──
function spawnMultiRipple(point, normal, count = 3) {
  for (let i = 0; i < count; i++) {
    setTimeout(() => spawnImpactRipple(point.clone(), normal), i * 60);
  }
}

// ── Scroll tracking with sound ──
let lastScrollY = 0;
let scrollTickAccum = 0;
let lastSectionTriggered = -1;
let scrollVelocity = 0;
let lastScrollTime = 0;
let whooshCooldown = 0;

window.addEventListener('scroll', () => {
  // Start ambient audio on first interaction
  if (!ambientLayers.started && STATE.soundEnabled) startAmbientLayers();

  STATE.scrollY = window.scrollY;
  const maxScroll = document.body.scrollHeight - window.innerHeight;
  STATE.scrollProgress = maxScroll > 0 ? STATE.scrollY / maxScroll : 0;


  // Scroll velocity for whoosh
  const now = performance.now();
  const timeDelta = (now - lastScrollTime) / 1000;
  lastScrollTime = now;
  const scrollDelta = STATE.scrollY - lastScrollY;
  const direction = scrollDelta > 0 ? 1 : -1;
  scrollVelocity = timeDelta > 0 ? Math.abs(scrollDelta) / timeDelta : 0;

  // Tick sound — every ~80px of scrolling
  scrollTickAccum += Math.abs(scrollDelta);
  if (scrollTickAccum > 80) {
    playScrollTick(STATE.scrollProgress);
    scrollTickAccum = 0;
  }

  // Whoosh on fast scroll
  whooshCooldown -= timeDelta;
  if (scrollVelocity > 1200 && whooshCooldown <= 0) {
    playScrollWhoosh(direction);
    whooshCooldown = 0.4;
  }

  lastScrollY = STATE.scrollY;

  // Section visibility with reveal sound
  document.querySelectorAll('.scroll-section').forEach((s, i) => {
    const rect = s.getBoundingClientRect();
    if (rect.top < window.innerHeight * 0.75) {
      if (!s.classList.contains('visible')) {
        s.classList.add('visible');
        if (i !== lastSectionTriggered) {
          playSectionReveal(i);
          lastSectionTriggered = i;
        }
      }
    }
  });

  // Scroll hint
  document.getElementById('scrollHint').classList.toggle('hidden', STATE.scrollY > 100);

  // HUD
  document.getElementById('hud').classList.toggle('visible', STATE.scrollY > window.innerHeight * 0.3);

  // Section index
  STATE.section = Math.floor(STATE.scrollY / window.innerHeight);

  // Update dot indicators
  const dotsContainer = document.getElementById('sectionDots');
  if (dotsContainer) {
    // Show dots once scrolled past initial fold
    dotsContainer.classList.toggle('visible', STATE.scrollY > 50);
    // Determine active section from all major sections
    const allSections = [
      document.getElementById('heroSection'),
      document.getElementById('section1'),
      document.getElementById('section2'),
      document.getElementById('section3'),
      document.getElementById('section4')
    ];
    let activeIdx = 0;
    const mid = window.innerHeight * 0.5;
    allSections.forEach((sec, i) => {
      if (sec) {
        const rect = sec.getBoundingClientRect();
        if (rect.top < mid && rect.bottom > 0) activeIdx = i;
      }
    });
    dotsContainer.querySelectorAll('.section-dot').forEach((dot, i) => {
      dot.classList.toggle('active', i === activeIdx);
    });
  }
});

// ── Section Dot Click Navigation ──
const dotSectionTargets = ['heroSection', 'section1', 'section2', 'section3', 'section4'];
document.querySelectorAll('.section-dot').forEach((dot, i) => {
  dot.addEventListener('click', () => {
    const target = document.getElementById(dotSectionTargets[i]);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth' });
      if (typeof playClick === 'function') playClick();
    }
  });
  dot.addEventListener('mouseenter', () => {
    if (typeof playHoverBright === 'function') playHoverBright();
  });
});

// ── Mouse ──
window.addEventListener('mousemove', e => {
  STATE.mouseX = e.clientX;
  STATE.mouseY = e.clientY;
  STATE.mouseNX = (e.clientX / window.innerWidth) * 2 - 1;
  STATE.mouseNY = -(e.clientY / window.innerHeight) * 2 + 1;
});

// ── Force Field State ──
const forceField = {
  worldPos: new THREE.Vector3(),
  raycaster: new THREE.Raycaster(),
  pointer: new THREE.Vector2(),
  strength: 0,
  targetStrength: 0,
  radius: 4.0,
  influenceMap: new Map() // tracks per-object displacement
};

// ── 3D Interaction State ──
const interact3D = {
  raycaster: new THREE.Raycaster(),
  pointer: new THREE.Vector2(),
  hoveredObject: null,
  clickedObject: null,
  clickForce: 0,          // decays over time after click
  clickOrigin: new THREE.Vector3(),
  clickDir: new THREE.Vector3(),
  hoverGlow: 0,           // smooth hover intensity
  lastHoverName: '',
  impactRipples: [],       // radial shockwave rings spawned on click
  dragActive: false,
  dragStart: new THREE.Vector2(),
  dragVelocity: new THREE.Vector2(),
  mouseDown: false,
  // Highlight materials cache
  highlightMeshes: new Map()
};

// Track mouse state for drag-force
window.addEventListener('mousedown', (e) => {
  interact3D.mouseDown = true;
  interact3D.dragStart.set(e.clientX, e.clientY);
  interact3D.dragActive = false;
});
window.addEventListener('mouseup', () => {
  if (interact3D.dragActive && interact3D.hoveredObject) {
    // Fling force on release
    const flingMag = interact3D.dragVelocity.length() * 0.003;
    if (flingMag > 0.05) {
      interact3D.clickForce = Math.min(flingMag, 3);
      interact3D.clickOrigin.copy(forceField.worldPos);
      const fwp = forceField.worldPos;
      playTone(150 + flingMag * 200, 0.2, 0.02, 'triangle', { spatial: true, x: fwp.x, y: fwp.y, z: fwp.z });
      playNoiseBurst(0.12, 0.01, 500, 2, 'bandpass');
    }
  }
  interact3D.mouseDown = false;
  interact3D.dragActive = false;
  interact3D.dragVelocity.set(0, 0);
});
window.addEventListener('mousemove', (e) => {
  if (interact3D.mouseDown) {
    interact3D.dragVelocity.set(e.movementX, e.movementY);
    const dragDist = Math.hypot(e.clientX - interact3D.dragStart.x, e.clientY - interact3D.dragStart.y);
    if (dragDist > 8) interact3D.dragActive = true;
  }
});

// Force-reactive objects registry: { mesh, restPos, restRot, mass, displacement }
const forceReactiveObjects = [];

function registerForceReactive(mesh, opts = {}) {
  forceReactiveObjects.push({
    mesh,
    restPos: mesh.position.clone(),
    restRot: mesh.rotation.clone(),
    mass: opts.mass || 1.0,
    damping: opts.damping || 0.92,
    stiffness: opts.stiffness || 0.08,
    maxDisplace: opts.maxDisplace || 1.2,
    vel: new THREE.Vector3(),
    rotVel: new THREE.Vector3(),
    affectedByWind: opts.affectedByWind !== false
  });
}

// ── Global Interactive Sound System ──
// (Individual element bindings are added after DOM is built, see bottom of file)

// ── THREE.js Scene ──
const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0xffffff, 0.04);
scene.background = new THREE.Color(0xffffff);

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 200);
camera.position.set(0, 2, 8);

// ── Lighting ──
const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
scene.add(ambientLight);

const keyLight = new THREE.DirectionalLight(0xffffff, 1.4);
keyLight.position.set(5, 10, 5);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(2048, 2048);
keyLight.shadow.camera.near = 0.5;
keyLight.shadow.camera.far = 50;
keyLight.shadow.camera.left = -10;
keyLight.shadow.camera.right = 10;
keyLight.shadow.camera.top = 10;
keyLight.shadow.camera.bottom = -10;
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0xdde0e8, 0.6);
fillLight.position.set(-5, 3, -5);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0xccccdd, 0.4);
rimLight.position.set(0, 5, -8);
scene.add(rimLight);

// Volumetric god-ray light cones
const coneGeo = new THREE.ConeGeometry(3, 12, 64, 4, true);
const coneMat = new THREE.ShaderMaterial({
  uniforms: { uTime: { value: 0 }, uOpacity: { value: 0.04 } },
  vertexShader: `
    varying vec2 vUv;
    varying float vY;
    void main() {
      vUv = uv;
      vY = position.y;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    uniform float uTime;
    uniform float uOpacity;
    varying vec2 vUv;
    varying float vY;
    void main() {
      float fade = smoothstep(0.0, 0.5, vUv.y) * smoothstep(1.0, 0.6, vUv.y);
      float flicker = 0.7 + 0.3 * sin(uTime * 1.5 + vY * 2.0);
      float edge = smoothstep(0.0, 0.15, vUv.x) * smoothstep(1.0, 0.85, vUv.x);
      gl_FragColor = vec4(0.85, 0.88, 0.95, fade * flicker * edge * uOpacity);
    }
  `,
  transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending
});
const godRay1 = new THREE.Mesh(coneGeo, coneMat);
godRay1.name = 'godRay1';
godRay1.position.set(6, 8, -3);
godRay1.rotation.z = -0.3;
scene.add(godRay1);
const godRay2 = new THREE.Mesh(coneGeo, coneMat.clone());
godRay2.name = 'godRay2';
godRay2.position.set(-5, 9, 2);
godRay2.rotation.z = 0.25;
godRay2.rotation.x = 0.1;
scene.add(godRay2);

const pointLight1 = new THREE.PointLight(0x99aacc, 0.5, 15);
pointLight1.position.set(3, 2, 3);
scene.add(pointLight1);

const pointLight2 = new THREE.PointLight(0x8899bb, 0.4, 12);
pointLight2.position.set(-3, 1, -3);
scene.add(pointLight2);

// ── Ground Plane ──
const groundGeo = new THREE.PlaneGeometry(100, 100);
const groundMat = new THREE.MeshStandardMaterial({
  color: 0xf0f0f4, roughness: 0.9, metalness: 0.0
});
const ground = new THREE.Mesh(groundGeo, groundMat);
ground.name = 'ground';
ground.rotation.x = -Math.PI / 2;
ground.position.y = -1;
ground.receiveShadow = true;
scene.add(ground);

// ── Grid ──
const gridHelper = new THREE.GridHelper(40, 80, 0xccccdd, 0xdddde8);
gridHelper.name = 'gridHelper';
gridHelper.position.y = -0.99;
gridHelper.material.transparent = true;
gridHelper.material.opacity = 0.5;
scene.add(gridHelper);

// ── Holographic Ring Platform ──
const holoRingGeo = new THREE.TorusGeometry(2.8, 0.015, 32, 256);
const holoRingMat = new THREE.ShaderMaterial({
  uniforms: { uTime: { value: 0 }, uOpacity: { value: 0.5 } },
  vertexShader: `
    varying float vAngle;
    void main() {
      vAngle = atan(position.x, position.z);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    uniform float uTime;
    uniform float uOpacity;
    varying float vAngle;
    void main() {
      float sweep = sin(vAngle * 3.0 - uTime * 2.0) * 0.5 + 0.5;
      float pulse = 0.4 + 0.6 * sweep;
      gl_FragColor = vec4(0.5, 0.6, 0.8, pulse * uOpacity);
    }
  `,
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending
});
const holoRing1 = new THREE.Mesh(holoRingGeo, holoRingMat);
holoRing1.name = 'holoRing1';
holoRing1.rotation.x = -Math.PI / 2;
holoRing1.position.y = -0.95;
scene.add(holoRing1);

const holoRing2Geo = new THREE.TorusGeometry(3.4, 0.008, 32, 256);
const holoRing2 = new THREE.Mesh(holoRing2Geo, holoRingMat.clone());
holoRing2.name = 'holoRing2';
holoRing2.rotation.x = -Math.PI / 2;
holoRing2.position.y = -0.96;
scene.add(holoRing2);

const holoRing3Geo = new THREE.TorusGeometry(1.6, 0.012, 32, 192);
const holoRing3 = new THREE.Mesh(holoRing3Geo, holoRingMat.clone());
holoRing3.name = 'holoRing3';
holoRing3.rotation.x = -Math.PI / 2;
holoRing3.position.y = -0.94;
scene.add(holoRing3);

// ── Floating Holographic Tick Marks ──
const tickGroup = new THREE.Group();
tickGroup.name = 'holoTicks';
const tickGeo = new THREE.BoxGeometry(0.005, 0.15, 0.005, 1, 4, 1);
const tickMat = new THREE.MeshBasicMaterial({ color: 0x6688aa, transparent: true, opacity: 0.25 });
for (let i = 0; i < 60; i++) {
  const angle = (i / 60) * Math.PI * 2;
  const r = 2.8;
  const tick = new THREE.Mesh(tickGeo, tickMat.clone());
  tick.position.set(Math.cos(angle) * r, -0.88, Math.sin(angle) * r);
  tick.lookAt(0, -0.88, 0);
  tick.scale.y = i % 5 === 0 ? 1.4 : 0.6;
  tickGroup.add(tick);
}
scene.add(tickGroup);

// ── Floating 3D Data Orbiting Rings ──
const orbitDataGroup = new THREE.Group();
orbitDataGroup.name = 'orbitData';
// Orbiting spheres on tilted ring paths
  for (let ring = 0; ring < 3; ring++) {
    const ringGroup = new THREE.Group();
    ringGroup.rotation.x = 0.3 + ring * 0.4;
    ringGroup.rotation.z = ring * 0.6;
    // Ring path
    const pathGeo = new THREE.TorusGeometry(3.2 + ring * 0.8, 0.003, 16, 256);
  const pathMat = new THREE.MeshBasicMaterial({
    color: 0x5577aa, transparent: true, opacity: 0.08, depthWrite: false
  });
  const pathMesh = new THREE.Mesh(pathGeo, pathMat);
  ringGroup.add(pathMesh);
  // Orbiting nodes
  const nodeCount = 3 + ring;
  for (let n = 0; n < nodeCount; n++) {
    const nodeGeo = new THREE.OctahedronGeometry(0.04 + ring * 0.01, 2);
    const nodeMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color().setHSL(0.55 + ring * 0.08, 0.3, 0.6),
      transparent: true, opacity: 0.5
    });
    const node = new THREE.Mesh(nodeGeo, nodeMat);
    node.userData.angle = (n / nodeCount) * Math.PI * 2;
    node.userData.radius = 3.2 + ring * 0.8;
    node.userData.speed = 0.15 + ring * 0.05;
    node.userData.ringIdx = ring;
    ringGroup.add(node);
  }
  orbitDataGroup.add(ringGroup);
}
orbitDataGroup.position.y = 2;
scene.add(orbitDataGroup);

// ── Energy Pillar / Vertical Beam ──
const beamGeo = new THREE.CylinderGeometry(0.02, 0.02, 20, 24, 8, true);
const beamMat = new THREE.ShaderMaterial({
  uniforms: { uTime: { value: 0 }, uOpacity: { value: 0.12 } },
  vertexShader: `
    varying float vY;
    void main() {
      vY = (position.y + 10.0) / 20.0;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    uniform float uTime;
    uniform float uOpacity;
    varying float vY;
    void main() {
      float beam = smoothstep(0.0, 0.3, vY) * smoothstep(1.0, 0.7, vY);
      float scan = smoothstep(0.0, 0.02, fract(vY * 20.0 - uTime * 3.0));
      float pulse = 0.5 + 0.5 * sin(uTime * 2.0 + vY * 10.0);
      gl_FragColor = vec4(0.5, 0.65, 0.9, beam * (0.3 + scan * 0.4 + pulse * 0.3) * uOpacity);
    }
  `,
  transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending
});
const energyBeam = new THREE.Mesh(beamGeo, beamMat);
energyBeam.name = 'energyBeam';
energyBeam.position.y = 5;
scene.add(energyBeam);

// ── Scanning Grid Plane (beneath drone) ──
const scanGridGeo = new THREE.PlaneGeometry(8, 8, 80, 80);
const scanGridMat = new THREE.ShaderMaterial({
  uniforms: { uTime: { value: 0 }, uDronePos: { value: new THREE.Vector3() }, uOpacity: { value: 0.25 } },
  vertexShader: `
    varying vec2 vUv;
    varying vec3 vWorldPos;
    void main() {
      vUv = uv;
      vec4 wp = modelMatrix * vec4(position, 1.0);
      vWorldPos = wp.xyz;
      gl_Position = projectionMatrix * viewMatrix * wp;
    }
  `,
  fragmentShader: `
    uniform float uTime;
    uniform vec3 uDronePos;
    uniform float uOpacity;
    varying vec2 vUv;
    varying vec3 vWorldPos;
    void main() {
      vec2 gridUv = fract(vUv * 20.0);
      float gridLine = step(0.94, gridUv.x) + step(0.94, gridUv.y);
      gridLine = min(gridLine, 1.0);
      float dist = length(vWorldPos.xz - uDronePos.xz);
      float ring = smoothstep(0.02, 0.0, abs(fract(dist * 0.8 - uTime * 0.5) - 0.5) - 0.45);
      float fade = smoothstep(4.5, 1.5, dist);
      float alpha = (gridLine * 0.3 + ring * 0.6) * fade * uOpacity;
      gl_FragColor = vec4(0.4, 0.55, 0.8, alpha);
    }
  `,
  transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending
});
const scanGrid = new THREE.Mesh(scanGridGeo, scanGridMat);
scanGrid.name = 'scanGrid';
scanGrid.rotation.x = -Math.PI / 2;
scanGrid.position.y = -0.97;
scene.add(scanGrid);

// ── Floating Glyphs / HUD Markers around drone ──
const glyphGroup = new THREE.Group();
glyphGroup.name = 'floatingGlyphs';
const glyphData = [
  { text: '+', dist: 2.0, hAngle: 0, vOff: 0.5 },
  { text: '◇', dist: 2.5, hAngle: Math.PI * 0.4, vOff: 1.0 },
  { text: '○', dist: 1.8, hAngle: Math.PI * 0.8, vOff: -0.3 },
  { text: '▵', dist: 2.2, hAngle: Math.PI * 1.2, vOff: 0.8 },
  { text: '///', dist: 2.6, hAngle: Math.PI * 1.6, vOff: 0.2 },
  { text: '◁', dist: 2.1, hAngle: Math.PI * 0.6, vOff: 1.3 },
];
glyphData.forEach((g, i) => {
  const canvas = document.createElement('canvas');
  canvas.width = 64; canvas.height = 64;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgba(100,130,170,0.6)';
  ctx.font = '28px monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(g.text, 32, 32);
  const tex = new THREE.CanvasTexture(canvas);
  const spriteMat = new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0.4, depthWrite: false, blending: THREE.AdditiveBlending });
  const sprite = new THREE.Sprite(spriteMat);
  sprite.scale.set(0.35, 0.35, 1);
  sprite.userData.baseAngle = g.hAngle;
  sprite.userData.dist = g.dist;
  sprite.userData.vOff = g.vOff;
  sprite.userData.idx = i;
  glyphGroup.add(sprite);
});
scene.add(glyphGroup);

// ── Afterimage Trail (ghosting effect for drone motion) ──
const GHOST_COUNT = 8;
const ghosts = [];
for (let i = 0; i < GHOST_COUNT; i++) {
  const ghostDrone = buildDrone(DRONES[0]);
  ghostDrone.scale.setScalar(2.2);
  ghostDrone.visible = false;
  ghostDrone.traverse(child => {
    if (child.isMesh && child.material) {
      child.material = child.material.clone();
      child.material.transparent = true;
      child.material.opacity = 0;
      child.material.depthWrite = false;
    }
  });
  scene.add(ghostDrone);
  ghosts.push({ mesh: ghostDrone, pos: new THREE.Vector3(), rot: new THREE.Euler(), age: 0 });
}
let ghostTimer = 0;
let ghostIndex = 0;

// ── Procedural Drone Builder ──
function buildDrone(config) {
  const group = new THREE.Group();
  const bodyColor = config.color;
  const accentColor = config.accent;

  // Body
  // Main fuselage — smooth rounded body
  const bodyGeo = new THREE.CapsuleGeometry(0.22, 0.5, 32, 48);
  bodyGeo.rotateZ(Math.PI / 2);
  const bodyMat = new THREE.MeshStandardMaterial({
    color: bodyColor, roughness: 0.28, metalness: 0.72, envMapIntensity: 1.2
  });
  const body = new THREE.Mesh(bodyGeo, bodyMat);
  body.name = 'droneBody_' + config.name.replace(/\s/g,'');
  body.castShadow = true;
  group.add(body);

  // Top shell — wider dome canopy
  const shellGeo = new THREE.SphereGeometry(0.38, 64, 32, 0, Math.PI * 2, 0, Math.PI / 2);
  const shellMat = new THREE.MeshStandardMaterial({
    color: bodyColor, roughness: 0.18, metalness: 0.82, envMapIntensity: 1.4
  });
  const shell = new THREE.Mesh(shellGeo, shellMat);
  shell.name = 'droneShell';
  shell.position.y = 0.08;
  shell.scale.set(1.2, 0.55, 0.9);
  shell.castShadow = true;
  group.add(shell);

  // Ventral plate — thin bottom with beveled edges
  const ventralGeo = new THREE.BoxGeometry(0.65, 0.04, 0.45, 8, 2, 8);
  const ventralMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color(bodyColor).offsetHSL(0, 0, -0.08), roughness: 0.4, metalness: 0.6
  });
  const ventral = new THREE.Mesh(ventralGeo, ventralMat);
  ventral.name = 'droneVentral';
  ventral.position.y = -0.12;
  ventral.castShadow = true;
  group.add(ventral);

  // Camera gimbal — two-axis mount
  const gimbalArmGeo = new THREE.CylinderGeometry(0.012, 0.012, 0.12, 16);
  const gimbalArmMat = new THREE.MeshStandardMaterial({ color: 0x444444, roughness: 0.3, metalness: 0.8 });
  const gimbalArm = new THREE.Mesh(gimbalArmGeo, gimbalArmMat);
  gimbalArm.position.set(0, -0.2, 0.15);
  group.add(gimbalArm);

  const gimbalGeo = new THREE.SphereGeometry(0.09, 48, 32);
  const gimbalMat = new THREE.MeshStandardMaterial({
    color: 0x1a1a1a, roughness: 0.05, metalness: 0.95, envMapIntensity: 1.5
  });
  const gimbal = new THREE.Mesh(gimbalGeo, gimbalMat);
  gimbal.name = 'droneGimbal';
  gimbal.position.set(0, -0.28, 0.15);
  group.add(gimbal);

  // Camera lens — glass ring + inner
  const lensRingGeo = new THREE.TorusGeometry(0.055, 0.012, 32, 64);
  const lensRingMat = new THREE.MeshStandardMaterial({
    color: 0x333333, roughness: 0.08, metalness: 0.95, envMapIntensity: 1.6
  });
  const lensRing = new THREE.Mesh(lensRingGeo, lensRingMat);
  lensRing.rotation.y = Math.PI / 2;
  lensRing.position.set(0, -0.28, 0.24);
  group.add(lensRing);

  const lensGeo = new THREE.CircleGeometry(0.045, 48);
  const lensMat = new THREE.MeshStandardMaterial({
    color: 0x060618, roughness: 0.02, metalness: 0.98,
    emissive: accentColor, emissiveIntensity: 0.15
  });
  const lens = new THREE.Mesh(lensGeo, lensMat);
  lens.name = 'droneLens';
  lens.position.set(0, -0.28, 0.241);
  group.add(lens);

  // Accent strips on body sides
  const stripGeo = new THREE.BoxGeometry(0.42, 0.015, 0.015, 12, 1, 1);
  const stripMat = new THREE.MeshStandardMaterial({
    color: accentColor, emissive: accentColor, emissiveIntensity: 0.4,
    roughness: 0.2, metalness: 0.8
  });
  [-0.18, 0.18].forEach((z, si) => {
    const strip = new THREE.Mesh(stripGeo, stripMat);
    strip.name = 'droneStrip_' + si;
    strip.position.set(0, 0.02, z);
    group.add(strip);
  });

  // Arms and propellers
  const armPositions = [
    { x: 0.55, z: 0.4 }, { x: -0.55, z: 0.4 },
    { x: 0.55, z: -0.4 }, { x: -0.55, z: -0.4 }
  ];

  const propellers = [];

  armPositions.forEach((pos, ai) => {
    // Tapered arm with rounded profile
    const armLength = Math.sqrt(pos.x * pos.x + pos.z * pos.z) * 0.55;
    const armGeo = new THREE.CapsuleGeometry(0.028, armLength, 24, 32);
    armGeo.rotateZ(Math.PI / 2);
    const armMat = new THREE.MeshStandardMaterial({
      color: bodyColor, roughness: 0.25, metalness: 0.7, envMapIntensity: 1.1
    });
    const arm = new THREE.Mesh(armGeo, armMat);
    arm.name = 'droneArm_' + ai;
    arm.position.set(pos.x * 0.5, 0.02, pos.z * 0.8);
    arm.lookAt(pos.x, 0.02, pos.z);
    arm.castShadow = true;
    group.add(arm);

    // Motor housing — detailed cylinder + ring
    const motorGeo = new THREE.CylinderGeometry(0.055, 0.065, 0.1, 48, 4);
    const motorMat = new THREE.MeshStandardMaterial({
      color: 0x2a2a2a, roughness: 0.12, metalness: 0.92, envMapIntensity: 1.3
    });
    const motor = new THREE.Mesh(motorGeo, motorMat);
    motor.name = 'droneMotor_' + ai;
    motor.position.set(pos.x, 0.07, pos.z);
    group.add(motor);

    const motorRingGeo = new THREE.TorusGeometry(0.065, 0.008, 24, 64);
    const motorRingMat = new THREE.MeshStandardMaterial({
      color: accentColor, emissive: accentColor, emissiveIntensity: 0.4,
      roughness: 0.1, metalness: 0.9, envMapIntensity: 1.4
    });
    const motorRing = new THREE.Mesh(motorRingGeo, motorRingMat);
    motorRing.rotation.x = Math.PI / 2;
    motorRing.position.set(pos.x, 0.12, pos.z);
    group.add(motorRing);

    // Propeller guard ring
    const guardGeo = new THREE.TorusGeometry(0.24, 0.006, 24, 96);
    const guardMat = new THREE.MeshStandardMaterial({
      color: bodyColor, roughness: 0.3, metalness: 0.6, transparent: true, opacity: 0.35, envMapIntensity: 1.1
    });
    const guard = new THREE.Mesh(guardGeo, guardMat);
    guard.rotation.x = Math.PI / 2;
    guard.position.set(pos.x, 0.13, pos.z);
    group.add(guard);

    // Propeller — 3 blades, smooth high-res teardrop shape
    const propGroup = new THREE.Group();
    propGroup.position.set(pos.x, 0.14, pos.z);

    for (let b = 0; b < 3; b++) {
      const bladeShape = new THREE.Shape();
      bladeShape.moveTo(0, 0);
      bladeShape.bezierCurveTo(0.04, 0.022, 0.12, 0.028, 0.22, 0.008);
      bladeShape.bezierCurveTo(0.22, 0.003, 0.22, -0.003, 0.22, -0.005);
      bladeShape.bezierCurveTo(0.12, -0.018, 0.04, -0.012, 0, 0);
      const bladeGeo = new THREE.ShapeGeometry(bladeShape, 24);
      const bladeMat = new THREE.MeshStandardMaterial({
        color: 0x3a3a3a, roughness: 0.3, metalness: 0.5,
        transparent: true, opacity: 0.65, side: THREE.DoubleSide, envMapIntensity: 0.8
      });
      const blade = new THREE.Mesh(bladeGeo, bladeMat);
      blade.rotation.set(-Math.PI / 2, 0, (Math.PI * 2 / 3) * b);
      propGroup.add(blade);
    }

    // Hub cap
    const hubGeo = new THREE.CylinderGeometry(0.018, 0.018, 0.02, 32, 2);
    const hubMat = new THREE.MeshStandardMaterial({ color: 0x555555, metalness: 0.95, roughness: 0.05, envMapIntensity: 1.5 });
    const hub = new THREE.Mesh(hubGeo, hubMat);
    propGroup.add(hub);

    // Spinning disc (motion blur halo)
    const discGeo = new THREE.RingGeometry(0.06, 0.22, 64);
    const discMat = new THREE.MeshStandardMaterial({
      color: bodyColor, transparent: true, opacity: 0.04, side: THREE.DoubleSide, roughness: 0.5
    });
    const disc = new THREE.Mesh(discGeo, discMat);
    disc.rotation.x = -Math.PI / 2;
    disc.position.y = 0.005;
    propGroup.add(disc);

    group.add(propGroup);
    propellers.push(propGroup);

    // LED indicators — front and rear per arm
    const ledGeo = new THREE.SphereGeometry(0.018, 24, 16);
    const isFront = pos.z > 0;
    const ledColor = isFront ? accentColor : 0xff2200;
    const ledMat = new THREE.MeshStandardMaterial({
      color: ledColor, emissive: ledColor, emissiveIntensity: 0.9, roughness: 0.1
    });
    const led = new THREE.Mesh(ledGeo, ledMat);
    led.name = 'droneLed_' + ai;
    led.position.set(pos.x * 0.92, 0.0, pos.z * 0.92);
    group.add(led);
  });

  // Landing gear — angled struts with foot pads
  const legMat = new THREE.MeshStandardMaterial({ color: 0x3a3a3a, roughness: 0.2, metalness: 0.8, envMapIntensity: 1.2 });
  [-0.22, 0.22].forEach((z, li) => {
    [-0.18, 0.18].forEach((x, lj) => {
      // Angled strut
      const strutGeo = new THREE.CylinderGeometry(0.01, 0.014, 0.25, 24);
      const strut = new THREE.Mesh(strutGeo, legMat);
      strut.name = 'droneStrut_' + li + '_' + lj;
      strut.position.set(x, -0.22, z);
      strut.rotation.z = x > 0 ? -0.15 : 0.15;
      strut.rotation.x = z > 0 ? -0.1 : 0.1;
      group.add(strut);
    });
    // Skid rail
    const skidGeo = new THREE.CapsuleGeometry(0.008, 0.4, 16, 32);
    skidGeo.rotateZ(Math.PI / 2);
    const skid = new THREE.Mesh(skidGeo, legMat);
    skid.name = 'droneSkid_' + li;
    skid.position.set(0, -0.34, z);
    group.add(skid);
    // Foot pads
    [-0.2, 0.2].forEach(fx => {
      const padGeo = new THREE.SphereGeometry(0.016, 24, 16);
      const pad = new THREE.Mesh(padGeo, legMat);
      pad.position.set(fx, -0.35, z);
      group.add(pad);
    });
  });

  // Rear antenna
  const antennaGeo = new THREE.CylinderGeometry(0.004, 0.004, 0.18, 16);
  const antennaMat = new THREE.MeshStandardMaterial({ color: 0x555555, metalness: 0.85, roughness: 0.15, envMapIntensity: 1.3 });
  const antenna = new THREE.Mesh(antennaGeo, antennaMat);
  antenna.name = 'droneAntenna';
  antenna.position.set(0, 0.18, -0.18);
  antenna.rotation.x = 0.15;
  group.add(antenna);
  const antennaTipGeo = new THREE.SphereGeometry(0.008, 24, 16);
  const antennaTipMat = new THREE.MeshStandardMaterial({
    color: accentColor, emissive: accentColor, emissiveIntensity: 0.6
  });
  const antennaTip = new THREE.Mesh(antennaTipGeo, antennaTipMat);
  antennaTip.position.set(0, 0.27, -0.2);
  group.add(antennaTip);

  group.userData.propellers = propellers;
  group.userData.config = config;
  return group;
}

// ── Main Drone ──
let mainDrone = buildDrone(DRONES[0]);
mainDrone.position.set(0, 2, 0);
mainDrone.scale.setScalar(2.2);
scene.add(mainDrone);

// ── Enemy Drones (for dogfight) ──
const enemyDrones = [];
for (let i = 0; i < 2; i++) {
  const enemy = buildDrone({ name: 'Enemy_' + i, color: 0x440000, accent: 0xff0000 });
  enemy.scale.setScalar(1.3);
  enemy.visible = false;
  enemy.position.set((i === 0 ? -4 : 4), 3, -3);
  scene.add(enemy);
  enemyDrones.push(enemy);
}

function switchDrone(index) {
  const config = DRONES[index];
  scene.remove(mainDrone);
  mainDrone = buildDrone(config);
  mainDrone.position.set(0, 2, 0);
  mainDrone.scale.setScalar(2.2);
  scene.add(mainDrone);
  // Rebuild ghost drones with new model
  ghosts.forEach(g => {
    scene.remove(g.mesh);
    const newGhost = buildDrone(config);
    newGhost.scale.setScalar(2.2);
    newGhost.visible = false;
    newGhost.traverse(child => {
      if (child.isMesh && child.material) {
        child.material = child.material.clone();
        child.material.transparent = true;
        child.material.opacity = 0;
        child.material.depthWrite = false;
      }
    });
    scene.add(newGhost);
    g.mesh = newGhost;
    g.age = 0;
  });
}

// ── Particles ──
const PARTICLE_COUNT = 5000;
const particleGeo = new THREE.BufferGeometry();
const particlePositions = new Float32Array(PARTICLE_COUNT * 3);
const particleSpeeds = new Float32Array(PARTICLE_COUNT);
const particleSizes = new Float32Array(PARTICLE_COUNT);

for (let i = 0; i < PARTICLE_COUNT; i++) {
  particlePositions[i * 3] = (Math.random() - 0.5) * 30;
  particlePositions[i * 3 + 1] = Math.random() * 15;
  particlePositions[i * 3 + 2] = (Math.random() - 0.5) * 30;
  particleSpeeds[i] = 0.005 + Math.random() * 0.02;
  particleSizes[i] = 0.5 + Math.random() * 2;
}
particleGeo.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
particleGeo.setAttribute('size', new THREE.BufferAttribute(particleSizes, 1));

const particleMat = new THREE.ShaderMaterial({
  uniforms: {
    uTime: { value: 0 },
    uColor: { value: new THREE.Color(0x9999aa) },
    uStorm: { value: 0 },
    uCursorPos: { value: new THREE.Vector3() },
    uCursorStrength: { value: 0 }
  },
  vertexShader: `
    attribute float size;
    uniform float uTime;
    uniform float uStorm;
    uniform vec3 uCursorPos;
    uniform float uCursorStrength;
    varying float vAlpha;
    void main() {
      vec3 pos = position;
      pos.y = mod(pos.y - uTime * (0.1 + uStorm * 0.5), 15.0);
      pos.x += sin(uTime * 0.3 + pos.z * 0.5) * (0.2 + uStorm * 1.5);
      pos.z += cos(uTime * 0.2 + pos.x * 0.3) * (0.1 + uStorm * 1.0);

      // Cursor force field repulsion
      vec3 toCursor = pos - uCursorPos;
      float cursorDist = length(toCursor);
      float forceRadius = 4.0;
      if (cursorDist < forceRadius && cursorDist > 0.01) {
        float repelForce = (1.0 - cursorDist / forceRadius) * uCursorStrength * 1.5;
        pos += normalize(toCursor) * repelForce;
      }

      vAlpha = smoothstep(0.0, 2.0, pos.y) * smoothstep(15.0, 12.0, pos.y);
      vAlpha *= (0.15 + uStorm * 0.3);

      // Brighten particles near cursor
      vAlpha += uCursorStrength * (1.0 - smoothstep(0.0, forceRadius, cursorDist)) * 0.15;

      vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
      gl_PointSize = size * (200.0 / -mvPos.z);
      gl_Position = projectionMatrix * mvPos;
    }
  `,
  fragmentShader: `
    uniform vec3 uColor;
    uniform float uCursorStrength;
    varying float vAlpha;
    void main() {
      float d = length(gl_PointCoord - 0.5) * 2.0;
      float a = smoothstep(1.0, 0.0, d) * vAlpha;
      // Slightly warm tint near cursor interaction
      vec3 col = mix(uColor, vec3(0.6, 0.65, 0.75), uCursorStrength * 0.3);
      gl_FragColor = vec4(col, a);
    }
  `,
  transparent: true,
  depthWrite: false,
  blending: THREE.AdditiveBlending
});
const particles = new THREE.Points(particleGeo, particleMat);
scene.add(particles);

// ── Propeller Airflow Particles ──
const AIRFLOW_COUNT = 1000;
const airflowGeo = new THREE.BufferGeometry();
const airflowPos = new Float32Array(AIRFLOW_COUNT * 3);
const airflowVel = new Float32Array(AIRFLOW_COUNT * 3);
const airflowLife = new Float32Array(AIRFLOW_COUNT);
for (let i = 0; i < AIRFLOW_COUNT; i++) {
  airflowPos[i * 3] = 0;
  airflowPos[i * 3 + 1] = -10;
  airflowPos[i * 3 + 2] = 0;
  airflowLife[i] = Math.random();
}
airflowGeo.setAttribute('position', new THREE.BufferAttribute(airflowPos, 3));

const airflowMat = new THREE.PointsMaterial({
  color: 0x99aabb, size: 0.025, transparent: true, opacity: 0.2,
  blending: THREE.AdditiveBlending, depthWrite: false
});
const airflowParticles = new THREE.Points(airflowGeo, airflowMat);
scene.add(airflowParticles);

// ── Obstacle environment (for Section 3) ──
const obstacles = [];
function createObstacles() {
  // Trees
  for (let i = 0; i < 6; i++) {
    const trunkGeo = new THREE.CylinderGeometry(0.18, 0.26, 3.2, 24);
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x3a2a1a, roughness: 0.9 });
    const trunk = new THREE.Mesh(trunkGeo, trunkMat);
    const x = (Math.random() - 0.5) * 12;
    const z = -8 - Math.random() * 8;
    trunk.position.set(x, -0.25, z);
    trunk.castShadow = true;
    scene.add(trunk);
    obstacles.push(trunk);

    const foliageGeo = new THREE.SphereGeometry(0.9 + Math.random() * 0.5, 32, 24);
    const foliageMat = new THREE.MeshStandardMaterial({ color: 0x0a3a0a, roughness: 0.8 });
    const foliage = new THREE.Mesh(foliageGeo, foliageMat);
    foliage.position.set(x, 1.8, z);
    foliage.castShadow = true;
    scene.add(foliage);
    obstacles.push(foliage);
  }
  // Rocks
  for (let i = 0; i < 4; i++) {
    const rockGeo = new THREE.DodecahedronGeometry(0.7 + Math.random() * 0.6, 3);
    const rockMat = new THREE.MeshStandardMaterial({ color: 0x2a2a2a, roughness: 0.9, metalness: 0.1 });
    const rock = new THREE.Mesh(rockGeo, rockMat);
    rock.position.set((Math.random() - 0.5) * 10, -0.7, -6 - Math.random() * 6);
    rock.rotation.set(Math.random(), Math.random(), Math.random());
    rock.castShadow = true;
    scene.add(rock);
    obstacles.push(rock);
  }
  // Buildings
  for (let i = 0; i < 3; i++) {
    const h = 5 + Math.random() * 6;
    const buildGeo = new THREE.BoxGeometry(1.8, h, 1.8, 4, 8, 4);
    const buildMat = new THREE.MeshStandardMaterial({
      color: 0x1a1a2e, roughness: 0.5, metalness: 0.3
    });
    const building = new THREE.Mesh(buildGeo, buildMat);
    building.position.set(-6 + i * 6, h / 2 - 1, -12);
    building.castShadow = true;
    scene.add(building);
    obstacles.push(building);

    // Window emissives
    const winGeo = new THREE.PlaneGeometry(0.08, 0.1, 2, 2);
    const winMat = new THREE.MeshStandardMaterial({
      emissive: 0x445566, emissiveIntensity: 0.4, color: 0x000000
    });
    for (let wy = 0; wy < h - 0.5; wy += 0.4) {
      for (let wx = -0.25; wx <= 0.25; wx += 0.25) {
        if (Math.random() > 0.4) {
          const win = new THREE.Mesh(winGeo, winMat);
          win.position.set(building.position.x + wx, wy, building.position.z + 0.41);
          scene.add(win);
        }
      }
    }
  }
}
createObstacles();

// Register obstacles as force-reactive (after they've been created)
obstacles.forEach(ob => {
  registerForceReactive(ob, { mass: 2.5, damping: 0.88, stiffness: 0.04, maxDisplace: 0.3 });
});

// ── Windmill Assets ──
const windmills = [];
function buildWindmill(x, z, height, bladeLength) {
  const group = new THREE.Group();
  group.name = 'windmill_' + windmills.length;

  // Tower — tapered cylindrical pole
  const towerGeo = new THREE.CylinderGeometry(0.12, 0.22, height, 24, 8);
  const towerMat = new THREE.MeshStandardMaterial({
    color: 0xe8e8ec, roughness: 0.4, metalness: 0.3, envMapIntensity: 1.0
  });
  const tower = new THREE.Mesh(towerGeo, towerMat);
  tower.name = 'windmillTower_' + windmills.length;
  tower.position.y = height / 2;
  tower.castShadow = true;
  group.add(tower);

  // Nacelle — housing at top
  const nacelleGeo = new THREE.CapsuleGeometry(0.18, 0.45, 24, 32);
  nacelleGeo.rotateZ(Math.PI / 2);
  const nacelleMat = new THREE.MeshStandardMaterial({
    color: 0xf0f0f4, roughness: 0.25, metalness: 0.5, envMapIntensity: 1.2
  });
  const nacelle = new THREE.Mesh(nacelleGeo, nacelleMat);
  nacelle.name = 'windmillNacelle_' + windmills.length;
  nacelle.position.y = height + 0.05;
  nacelle.position.z = 0.12;
  nacelle.castShadow = true;
  group.add(nacelle);

  // Hub — front nose cone
  const hubGeo = new THREE.ConeGeometry(0.12, 0.25, 32);
  hubGeo.rotateX(-Math.PI / 2);
  const hubMat = new THREE.MeshStandardMaterial({
    color: 0xdddddd, roughness: 0.2, metalness: 0.6
  });
  const hub = new THREE.Mesh(hubGeo, hubMat);
  hub.name = 'windmillHub_' + windmills.length;
  hub.position.y = height + 0.05;
  hub.position.z = 0.48;
  group.add(hub);

  // Rotor group — spins around Z axis
  const rotorGroup = new THREE.Group();
  rotorGroup.name = 'windmillRotor_' + windmills.length;
  rotorGroup.position.y = height + 0.05;
  rotorGroup.position.z = 0.52;

  // Three blades — elongated tapered shapes
  for (let b = 0; b < 3; b++) {
    const bladeGroup = new THREE.Group();
    bladeGroup.rotation.z = (Math.PI * 2 / 3) * b;

    // Main blade body — tapered box with twist
    const bladeGeo = new THREE.BoxGeometry(0.08, bladeLength, 0.015, 2, 24, 1);
    const positions = bladeGeo.attributes.position;
    for (let v = 0; v < positions.count; v++) {
      const py = positions.getY(v);
      const normalizedY = (py + bladeLength / 2) / bladeLength;
      // Taper width toward tip
      const taper = 1.0 - normalizedY * 0.7;
      positions.setX(v, positions.getX(v) * taper);
      // Subtle twist along length
      const twist = normalizedY * 0.3;
      const px = positions.getX(v);
      const pz = positions.getZ(v);
      positions.setX(v, px * Math.cos(twist) - pz * Math.sin(twist));
      positions.setZ(v, px * Math.sin(twist) + pz * Math.cos(twist));
    }
    positions.needsUpdate = true;
    bladeGeo.computeVertexNormals();

    const bladeMat = new THREE.MeshStandardMaterial({
      color: 0xf5f5f8, roughness: 0.3, metalness: 0.2, side: THREE.DoubleSide,
      envMapIntensity: 1.0
    });
    const blade = new THREE.Mesh(bladeGeo, bladeMat);
    blade.name = 'windmillBlade_' + windmills.length + '_' + b;
    blade.position.y = bladeLength / 2 + 0.08;
    blade.castShadow = true;
    bladeGroup.add(blade);

    // Blade root fairing
    const fairingGeo = new THREE.CylinderGeometry(0.05, 0.035, 0.15, 16);
    const fairingMat = new THREE.MeshStandardMaterial({
      color: 0xe0e0e4, roughness: 0.3, metalness: 0.4
    });
    const fairing = new THREE.Mesh(fairingGeo, fairingMat);
    fairing.position.y = 0.06;
    bladeGroup.add(fairing);

    rotorGroup.add(bladeGroup);
  }

  // Center hub disc
  const hubDiscGeo = new THREE.CylinderGeometry(0.08, 0.08, 0.04, 32);
  hubDiscGeo.rotateX(Math.PI / 2);
  const hubDiscMat = new THREE.MeshStandardMaterial({
    color: 0xcccccc, roughness: 0.15, metalness: 0.7
  });
  const hubDisc = new THREE.Mesh(hubDiscGeo, hubDiscMat);
  rotorGroup.add(hubDisc);

  group.add(rotorGroup);

  // Base foundation — circular pad
  const baseGeo = new THREE.CylinderGeometry(0.5, 0.6, 0.08, 32);
  const baseMat = new THREE.MeshStandardMaterial({
    color: 0xd0d0d4, roughness: 0.7, metalness: 0.1
  });
  const base = new THREE.Mesh(baseGeo, baseMat);
  base.name = 'windmillBase_' + windmills.length;
  base.position.y = 0.04;
  base.receiveShadow = true;
  group.add(base);

  // Aviation warning light at top
  const warningLightGeo = new THREE.SphereGeometry(0.035, 16, 12);
  const warningLightMat = new THREE.MeshStandardMaterial({
    color: 0xff2200, emissive: 0xff2200, emissiveIntensity: 0.8, roughness: 0.1
  });
  const warningLight = new THREE.Mesh(warningLightGeo, warningLightMat);
  warningLight.name = 'windmillWarningLight_' + windmills.length;
  warningLight.position.y = height + 0.28;
  group.add(warningLight);

  group.position.set(x, -1, z);
  group.userData.rotorGroup = rotorGroup;
  group.userData.warningLight = warningLight;
  group.userData.spinSpeed = 0.3 + Math.random() * 0.4;
  group.userData.height = height;

  scene.add(group);
  windmills.push(group);

  // Register tower for force reactivity
  registerForceReactive(tower, { mass: 8.0, damping: 0.94, stiffness: 0.02, maxDisplace: 0.15 });

  return group;
}

// Place windmills across the landscape
buildWindmill(-8, -6, 6.5, 2.8);
buildWindmill(9, -9, 7.2, 3.2);
buildWindmill(-12, -14, 8.0, 3.5);
buildWindmill(6, -16, 6.0, 2.5);
buildWindmill(14, -4, 7.5, 3.0);

// ── Contact Shadow ──
const contactShadowGeo = new THREE.CircleGeometry(1, 64);
const contactShadowMat = new THREE.MeshBasicMaterial({
  color: 0x000000, transparent: true, opacity: 0.18, depthWrite: false
});
const contactShadow = new THREE.Mesh(contactShadowGeo, contactShadowMat);
contactShadow.name = 'contactShadow';
contactShadow.rotation.x = -Math.PI / 2;
contactShadow.position.y = -0.98;
scene.add(contactShadow);

// ── Force Field Visual Ring ──
const forceRingGeo = new THREE.TorusGeometry(1.2, 0.015, 32, 128);
const forceRingMat = new THREE.MeshBasicMaterial({
  color: 0x667788, transparent: true, opacity: 0, side: THREE.DoubleSide,
  depthWrite: false
});
const forceRing = new THREE.Mesh(forceRingGeo, forceRingMat);
forceRing.name = 'forceFieldRing';
forceRing.rotation.x = Math.PI / 2;
forceRing.visible = false;
scene.add(forceRing);

// Inner ripple ring
const forceRippleGeo = new THREE.RingGeometry(0.3, 1.6, 96);
const forceRippleMat = new THREE.ShaderMaterial({
  uniforms: {
    uOpacity: { value: 0 },
    uTime: { value: 0 },
    uColor: { value: new THREE.Color(0x8899aa) }
  },
  vertexShader: `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    uniform float uOpacity;
    uniform float uTime;
    uniform vec3 uColor;
    varying vec2 vUv;
    void main() {
      float r = length(vUv - 0.5) * 2.0;
      float ring = smoothstep(0.6, 0.7, r) * smoothstep(1.0, 0.85, r);
      float pulse = 0.5 + 0.5 * sin(uTime * 4.0 + r * 8.0);
      float alpha = ring * pulse * uOpacity * 0.35;
      gl_FragColor = vec4(uColor, alpha);
    }
  `,
  transparent: true,
  depthWrite: false,
  side: THREE.DoubleSide
});
const forceRipple = new THREE.Mesh(forceRippleGeo, forceRippleMat);
forceRipple.name = 'forceFieldRipple';
forceRipple.rotation.x = -Math.PI / 2;
forceRipple.visible = false;
scene.add(forceRipple);

// ── Pressure Wave Particles (spawn around force impact) ──
const WAVE_COUNT = 400;
const waveGeo = new THREE.BufferGeometry();
const wavePos = new Float32Array(WAVE_COUNT * 3);
const waveVel = new Float32Array(WAVE_COUNT * 3);
const waveLife = new Float32Array(WAVE_COUNT);
for (let i = 0; i < WAVE_COUNT; i++) {
  wavePos[i * 3 + 1] = -20; // hidden
  waveLife[i] = 0;
}
waveGeo.setAttribute('position', new THREE.BufferAttribute(wavePos, 3));
const waveMat = new THREE.PointsMaterial({
  color: 0x99aabb, size: 0.04, transparent: true, opacity: 0,
  blending: THREE.AdditiveBlending, depthWrite: false
});
const waveParticles = new THREE.Points(waveGeo, waveMat);
waveParticles.visible = false;
scene.add(waveParticles);

// ── Laser trails (dogfight) ──
const laserPool = [];
function fireLaser(origin, direction, color = 0xff3333) {
  const geo = new THREE.CylinderGeometry(0.01, 0.01, 1.5, 12);
  geo.rotateX(Math.PI / 2);
  const mat = new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0.8
  });
  const laser = new THREE.Mesh(geo, mat);
  laser.position.copy(origin);
  laser.lookAt(origin.clone().add(direction));
  laser.userData.vel = direction.clone().normalize().multiplyScalar(0.5);
  laser.userData.life = 1.0;
  scene.add(laser);
  laserPool.push(laser);
  playLaser(origin);
}

// ── Lightning (storm) ──
const lightningGeo = new THREE.BufferGeometry();
const lightningMat = new THREE.LineBasicMaterial({
  color: 0x889aaa, transparent: true, opacity: 0
});
const lightning = new THREE.LineSegments(lightningGeo, lightningMat);
scene.add(lightning);
let lightningTimer = 0;
let lightningFlash = 0;

function triggerLightning() {
  const pts = [];
  let x = (Math.random() - 0.5) * 10;
  let y = 15;
  const segments = 12 + Math.floor(Math.random() * 8);
  for (let i = 0; i < segments; i++) {
    pts.push(x, y, (Math.random() - 0.5) * 6);
    x += (Math.random() - 0.5) * 2;
    y -= (15 / segments) + (Math.random() - 0.5) * 0.5;
    pts.push(x, y, (Math.random() - 0.5) * 6);
  }
  lightningGeo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  lightningMat.opacity = 1;
  lightningFlash = 1;
  playThunder();
}

// ── Animation ──
const clock = new THREE.Clock();
const droneTargetPos = new THREE.Vector3(0, 2, 0);
const droneCurrentPos = new THREE.Vector3(0, 2, 0);
const droneTargetRot = new THREE.Euler(0, 0, 0);
let cameraAngle = 0;

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);
  const time = clock.getElapsedTime();
  const motionScale = STATE.reducedMotion ? 0.15 : 1.0;

  // ── Scroll-based camera & drone position ──
  const scrollSections = STATE.scrollY / window.innerHeight;

  // Camera cinematic orbit — speed changes per section
  const orbitSpeeds = [0.15, 0.08, 0.25, 0.05, 0.12];
  const sectionIdx = Math.min(Math.floor(scrollSections), 4);
  const baseOrbitSpeed = orbitSpeeds[sectionIdx] || 0.15;
  if (STATE.flightMode === 1) {
    cameraAngle += dt * baseOrbitSpeed * motionScale;
  } else {
    cameraAngle += dt * 0.4 * motionScale;
  }

  let camRadius = 8;
  let camHeight = 2.5;
  let camLookY = 1.5;
  let targetFogDensity = 0.04;
  let targetBgColor = new THREE.Color(0xffffff);
  let targetGroundColor = new THREE.Color(0xf0f0f4);
  let targetAmbientIntensity = 1.2;
  let targetKeyIntensity = 1.4;
  let targetGridOpacity = 0.5;

  // Smooth easing helper
  function easeInOut(t) { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; }

  if (scrollSections < 1) {
    // Hero — bright white, wide orbit, gentle fog
    const t = easeInOut(Math.min(scrollSections, 1));
    camRadius = 8 - t * 2;
    camHeight = 2.5 + t * 0.5;
    camLookY = 1.5;
    targetFogDensity = 0.04;
    targetBgColor.set(0xffffff);
    targetGroundColor.set(0xf0f0f4);
    targetAmbientIntensity = 1.2;
    targetKeyIntensity = 1.4;
    targetGridOpacity = 0.5 - t * 0.2;
    droneTargetPos.set(0, 2, 0);
  } else if (scrollSections < 2) {
    // Section 1 — Smart Flight AI: lift up, tighter orbit, slightly warm tint
    const t = easeInOut(scrollSections - 1);
    camRadius = 6 - t * 1;
    camHeight = 3 + t * 3;
    camLookY = 2 + t * 2;
    targetFogDensity = 0.035 + t * 0.01;
    targetBgColor.setRGB(1, 1 - t * 0.01, 1 - t * 0.02);
    targetGroundColor.setRGB(0.94 - t * 0.04, 0.94 - t * 0.02, 0.96 - t * 0.02);
    targetAmbientIntensity = 1.2 + t * 0.3;
    targetKeyIntensity = 1.4 + t * 0.4;
    targetGridOpacity = 0.3 - t * 0.15;
    droneTargetPos.set(t * 0.5, 2.5 + t * 2, -t * 1);
  } else if (scrollSections < 3) {
    // Section 2 — Camera System: zoom in close, cool blue tone, dramatic
    const t = easeInOut(scrollSections - 2);
    camRadius = 5 - t * 2.5;
    camHeight = 2 + t * 0.5;
    camLookY = 2 + t * 0.3;
    targetFogDensity = 0.03 + t * 0.015;
    targetBgColor.setRGB(0.97 - t * 0.04, 0.97 - t * 0.02, 1);
    targetGroundColor.setRGB(0.88 - t * 0.06, 0.90 - t * 0.04, 0.95 - t * 0.02);
    targetAmbientIntensity = 1.0 + t * 0.2;
    targetKeyIntensity = 1.8 + t * 0.5;
    targetGridOpacity = 0.15 - t * 0.1;
    droneTargetPos.set(-t * 0.8, 2 + Math.sin(time * 0.6) * 0.3, -t * 3);
    // Drone rotates to face camera
    mainDrone.rotation.y = THREE.MathUtils.lerp(mainDrone.rotation.y, Math.PI * 0.15 * t, dt * 2);
  } else if (scrollSections < 4) {
    // Section 3 — Obstacle Avoidance: wide, dramatic top-down-ish, darker
    const t = easeInOut(scrollSections - 3);
    camRadius = 7 + t * 3;
    camHeight = 4 + t * 3;
    camLookY = 1 + t * 0.5;
    targetFogDensity = 0.045 + t * 0.025;
    targetBgColor.setRGB(0.95 - t * 0.06, 0.95 - t * 0.06, 0.97 - t * 0.04);
    targetGroundColor.setRGB(0.85 - t * 0.08, 0.85 - t * 0.06, 0.88 - t * 0.04);
    targetAmbientIntensity = 0.9 + t * 0.1;
    targetKeyIntensity = 1.2;
    targetGridOpacity = 0.05;
    droneTargetPos.set(Math.sin(time * 0.5) * 3, 2.5 + Math.sin(time * 0.8) * 0.8, -5 - t * 4);
  } else {
    // Section 4 — Drone Selector: reset to clean, bright, centered
    const t = easeInOut(Math.min(scrollSections - 4, 1));
    camRadius = 10 - t * 2;
    camHeight = 3 + t * 0.5;
    camLookY = 2;
    targetFogDensity = 0.035;
    targetBgColor.set(0xffffff);
    targetGroundColor.set(0xf0f0f4);
    targetAmbientIntensity = 1.3;
    targetKeyIntensity = 1.5;
    targetGridOpacity = 0.4;
    droneTargetPos.set(Math.sin(time * 0.3) * 0.5, 2, 0);
  }

  // ── Smoothly transition environment properties ──
  scene.background.lerp(targetBgColor, dt * 3);
  scene.fog.color.lerp(targetBgColor, dt * 3);
  scene.fog.density = THREE.MathUtils.lerp(scene.fog.density, targetFogDensity, dt * 3);
  groundMat.color.lerp(targetGroundColor, dt * 3);
  ambientLight.intensity = THREE.MathUtils.lerp(ambientLight.intensity, targetAmbientIntensity, dt * 3);
  keyLight.intensity = THREE.MathUtils.lerp(keyLight.intensity, targetKeyIntensity, dt * 3);
  if (gridHelper.material.opacity !== undefined) {
    gridHelper.material.opacity = THREE.MathUtils.lerp(gridHelper.material.opacity, targetGridOpacity, dt * 3);
  }

  // ── Obstacle visibility fades in for section 3 ──
  const obstacleTargetOpacity = (scrollSections > 2.3 && scrollSections < 4.2) ? 1 : 0;
  obstacles.forEach(ob => {
    if (!ob.userData._scrollVis) ob.userData._scrollVis = 0;
    ob.userData._scrollVis = THREE.MathUtils.lerp(ob.userData._scrollVis, obstacleTargetOpacity, dt * 3);
    ob.visible = ob.userData._scrollVis > 0.01;
    if (ob.material) {
      if (!ob.material._origTransparent) {
        ob.material._origTransparent = ob.material.transparent;
        ob.material.transparent = true;
      }
      ob.material.opacity = ob.userData._scrollVis;
    }
  });

  // Launch override
  if (STATE.launched) {
    const launchElapsed = time - STATE.launchTime;
    if (launchElapsed < 4) {
      const liftT = Math.min(launchElapsed / 3, 1);
      const eased = 1 - Math.pow(1 - liftT, 3);
      droneTargetPos.y = 2 + eased * 6;
      camHeight = 2.5 + eased * 4;
      camLookY = 2 + eased * 4;
    }
  }

  // Autopilot: drone follows cursor
  if (STATE.autopilotActive) {
    droneTargetPos.x += (STATE.mouseNX * 3 - droneTargetPos.x) * 0.02;
    droneTargetPos.y += ((STATE.mouseNY * 2 + 3) - droneTargetPos.y) * 0.02;
  }

  // Smooth drone movement
  droneCurrentPos.lerp(droneTargetPos, dt * 2 * motionScale);
  mainDrone.position.copy(droneCurrentPos);

  // Hover bob — amplitude varies by section
  const bobAmplitude = scrollSections < 1 ? 0.08 : scrollSections < 2 ? 0.12 : scrollSections < 3 ? 0.05 : 0.1;
  mainDrone.position.y += Math.sin(time * 1.8) * bobAmplitude * motionScale;

  // ── Drone scale pulses subtly on section transitions ──
  const sectionFrac = scrollSections % 1;
  const transitionPulse = sectionFrac < 0.15 ? 1 + Math.sin(sectionFrac / 0.15 * Math.PI) * 0.04 : 1;
  const baseScale = 2.2 * transitionPulse;
  mainDrone.scale.setScalar(THREE.MathUtils.lerp(mainDrone.scale.x, baseScale, dt * 5));

  // ── Force Field Update ──
  forceField.pointer.set(STATE.mouseNX, STATE.mouseNY);
  forceField.raycaster.setFromCamera(forceField.pointer, camera);
  // Project cursor into 3D at drone depth
  const forcePlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
  const forceIntersect = new THREE.Vector3();
  forceField.raycaster.ray.intersectPlane(forcePlane, forceIntersect);
  if (forceIntersect) {
    forceField.worldPos.lerp(forceIntersect, dt * 8);
  }

  // ── 3D Hover Detection — raycast every frame for live feedback ──
  interact3D.raycaster.setFromCamera(forceField.pointer, camera);
  const hoverTargets = [];
  mainDrone.traverse(c => { if (c.isMesh) hoverTargets.push(c); });
  enemyDrones.forEach(ed => { if (ed.visible) ed.traverse(c => { if (c.isMesh) hoverTargets.push(c); }); });
  obstacles.forEach(ob => { if (ob.visible && ob.isMesh) hoverTargets.push(ob); });
  windmills.forEach(wm => { if (wm.visible) wm.traverse(c => { if (c.isMesh) hoverTargets.push(c); }); });

  const hoverHits = interact3D.raycaster.intersectObjects(hoverTargets, false);
  const prevHover = interact3D.hoveredObject;
  interact3D.hoveredObject = hoverHits.length > 0 ? hoverHits[0].object : null;

  // Hover enter/exit sound
  if (interact3D.hoveredObject && interact3D.hoveredObject !== prevHover) {
    const hName = interact3D.hoveredObject.name || '';
    if (hName !== interact3D.lastHoverName) {
      interact3D.lastHoverName = hName;
      // Spatial hover-enter tone — pitch varies by object type
      const hPos = interact3D.hoveredObject.position || { x: 0, y: 0, z: 0 };
      if (hName.includes('drone') || hName.includes('Drone')) {
        playTone(1400, 0.06, 0.012, 'sine', { spatial: true, x: hPos.x, y: hPos.y, z: hPos.z, pitchVariation: 0.05 });
      } else if (hName.includes('windmill')) {
        playTone(900, 0.08, 0.01, 'triangle', { spatial: true, x: hPos.x, y: hPos.y, z: hPos.z, pitchVariation: 0.04 });
      } else {
        playTone(1100, 0.05, 0.008, 'sine', { spatial: true, x: hPos.x, y: hPos.y, z: hPos.z });
      }
    }
  }
  if (!interact3D.hoveredObject) interact3D.lastHoverName = '';

  // Smooth hover glow intensity
  const hoverTarget = interact3D.hoveredObject ? 1 : 0;
  interact3D.hoverGlow = THREE.MathUtils.lerp(interact3D.hoverGlow, hoverTarget, dt * 10);

  // ── Apply hover highlight — emissive boost on hovered mesh ──
  interact3D.highlightMeshes.forEach((origEmissive, mesh) => {
    if (mesh.material && mesh !== interact3D.hoveredObject) {
      mesh.material.emissiveIntensity = THREE.MathUtils.lerp(
        mesh.material.emissiveIntensity, origEmissive, dt * 8
      );
    }
  });
  if (interact3D.hoveredObject && interact3D.hoveredObject.material) {
    const hm = interact3D.hoveredObject;
    if (!interact3D.highlightMeshes.has(hm)) {
      interact3D.highlightMeshes.set(hm, hm.material.emissiveIntensity || 0);
      if (!hm.material.emissive) hm.material.emissive = new THREE.Color(0x334466);
    }
    hm.material.emissiveIntensity = THREE.MathUtils.lerp(
      hm.material.emissiveIntensity, 0.4 + Math.sin(time * 5) * 0.15, dt * 10
    );
  }

  // ── Click Force Decay & Application ──
  if (interact3D.clickForce > 0.01) {
    interact3D.clickForce *= 0.94; // exponential decay

    // Push the main drone away from click point
    const clickToDrone = new THREE.Vector3().subVectors(mainDrone.position, interact3D.clickOrigin);
    const clickDroneDist = clickToDrone.length();
    if (clickDroneDist < 6 && clickDroneDist > 0.01) {
      const clickPush = (1 - clickDroneDist / 6) * interact3D.clickForce * 0.8 * motionScale;
      const clickPushDir = clickToDrone.normalize();
      mainDrone.position.addScaledVector(clickPushDir, clickPush * dt * 10);
      // Extra tilt from click force
      mainDrone.rotation.z += clickPushDir.x * clickPush * dt * -2;
      mainDrone.rotation.x += clickPushDir.z * clickPush * dt * 2;
    }

    // Push enemy drones
    enemyDrones.forEach(ed => {
      if (!ed.visible) return;
      const toEnemy = new THREE.Vector3().subVectors(ed.position, interact3D.clickOrigin);
      const eDist = toEnemy.length();
      if (eDist < 8 && eDist > 0.01) {
        const ePush = (1 - eDist / 8) * interact3D.clickForce * 1.2;
        ed.position.addScaledVector(toEnemy.normalize(), ePush * dt * 8);
        ed.rotation.z += toEnemy.x * ePush * dt * -3;
      }
    });

    // Push force-reactive objects (obstacles, windmills)
    for (const obj of forceReactiveObjects) {
      const toObj = new THREE.Vector3().subVectors(obj.mesh.position, interact3D.clickOrigin);
      const oDist = toObj.length();
      if (oDist < 6 && oDist > 0.01) {
        const oPush = (1 - oDist / 6) * interact3D.clickForce * 4.0 / obj.mass;
        obj.vel.addScaledVector(toObj.normalize(), oPush * dt * 5);
        obj.rotVel.x += toObj.z * oPush * dt * 1.5;
        obj.rotVel.z -= toObj.x * oPush * dt * 1.5;
      }
    }

    // Boost propeller speed from click impact
    if (mainDrone.userData.propellers) {
      mainDrone.userData.propellers.forEach((p, i) => {
        const dir = (i === 0 || i === 3) ? 1 : -1;
        p.rotation.y += interact3D.clickForce * dir * dt * 25;
      });
    }

    // Push windmill rotors faster from click shockwave
    windmills.forEach(wm => {
      const wmPos = new THREE.Vector3();
      wm.getWorldPosition(wmPos);
      const wDist = wmPos.distanceTo(interact3D.clickOrigin);
      if (wDist < 10) {
        const wPush = (1 - wDist / 10) * interact3D.clickForce;
        wm.userData.rotorGroup.rotation.z += wPush * dt * 8;
      }
    });

    // Push particles outward from click origin via airflow velocity
    const afArr = airflowGeo.attributes.position.array;
    for (let i = 0; i < AIRFLOW_COUNT; i++) {
      const px = afArr[i * 3] - interact3D.clickOrigin.x;
      const py = afArr[i * 3 + 1] - interact3D.clickOrigin.y;
      const pz = afArr[i * 3 + 2] - interact3D.clickOrigin.z;
      const pd = Math.sqrt(px * px + py * py + pz * pz);
      if (pd < 4 && pd > 0.01) {
        const pushAmt = (1 - pd / 4) * interact3D.clickForce * 0.3;
        airflowVel[i * 3] += (px / pd) * pushAmt;
        airflowVel[i * 3 + 1] += (py / pd) * pushAmt;
        airflowVel[i * 3 + 2] += (pz / pd) * pushAmt;
      }
    }
  }

  // ── Update Impact Ripple Rings ──
  for (let i = interact3D.impactRipples.length - 1; i >= 0; i--) {
    const rip = interact3D.impactRipples[i];
    rip.age += dt;
    const t = rip.age / rip.maxAge;
    const scale = 0.1 + t * 4; // expand from 0.1 to 4
    rip.mesh.scale.setScalar(scale);
    rip.mesh.material.opacity = Math.max(0, 0.6 * (1 - t));
    if (rip.age >= rip.maxAge) {
      scene.remove(rip.mesh);
      rip.mesh.geometry.dispose();
      rip.mesh.material.dispose();
      interact3D.impactRipples.splice(i, 1);
    }
  }

  // ── Drag Force — dragging mouse over 3D objects pushes them continuously ──
  if (interact3D.dragActive && interact3D.hoveredObject) {
    const dragForceX = interact3D.dragVelocity.x * 0.0015 * motionScale;
    const dragForceY = -interact3D.dragVelocity.y * 0.0015 * motionScale;
    // Determine if hovering drone, enemy, or obstacle
    let isDrone = false;
    mainDrone.traverse(c => { if (c === interact3D.hoveredObject) isDrone = true; });
    if (isDrone) {
      mainDrone.position.x += dragForceX * 2;
      mainDrone.position.y += dragForceY * 2;
      mainDrone.rotation.z += dragForceX * -0.8;
      mainDrone.rotation.x += dragForceY * 0.5;
    }
    // Push force-reactive objects via drag
    for (const obj of forceReactiveObjects) {
      let isThis = false;
      if (obj.mesh === interact3D.hoveredObject) isThis = true;
      obj.mesh.traverse?.(c => { if (c === interact3D.hoveredObject) isThis = true; });
      if (isThis) {
        obj.vel.x += dragForceX * 3 / obj.mass;
        obj.vel.y += dragForceY * 3 / obj.mass;
      }
    }
  }

  // Distance from cursor to drone
  const cursorDroneDist = forceField.worldPos.distanceTo(mainDrone.position);
  const proximityFactor = Math.max(0, 1 - cursorDroneDist / forceField.radius);
  forceField.targetStrength = proximityFactor;
  forceField.strength = THREE.MathUtils.lerp(forceField.strength, forceField.targetStrength, dt * 5);

  // Cursor force on drone — enhanced with proximity-based push
  const cursorForceX = STATE.mouseNX * 0.12 * motionScale;
  const cursorForceY = STATE.mouseNY * 0.06 * motionScale;

  // Force push direction: drone gets pushed AWAY from cursor
  const pushDir = new THREE.Vector3().subVectors(mainDrone.position, forceField.worldPos).normalize();
  const pushStrength = forceField.strength * 0.6 * motionScale;
  mainDrone.position.x += pushDir.x * pushStrength * dt * 4;
  mainDrone.position.y += pushDir.y * pushStrength * dt * 3;
  mainDrone.position.z += pushDir.z * pushStrength * dt * 2.5;

  // Enhanced tilt based on force proximity
  const tiltMultiplier = 1 + forceField.strength * 3.5;
  mainDrone.rotation.z = THREE.MathUtils.lerp(mainDrone.rotation.z, -cursorForceX * 0.5 * tiltMultiplier, dt * 3);
  mainDrone.rotation.x = THREE.MathUtils.lerp(mainDrone.rotation.x, cursorForceY * 0.3 * tiltMultiplier, dt * 3);

  // Slow yaw + force-induced yaw wobble + scroll-responsive rotation
  const yawWobble = forceField.strength * Math.sin(time * 6) * 0.08;
  const scrollYaw = scrollSections * 0.4; // drone rotates as you scroll
  if (scrollSections < 2 || scrollSections >= 3) {
    // Don't override section 2's special rotation
    mainDrone.rotation.y = THREE.MathUtils.lerp(mainDrone.rotation.y, Math.sin(time * 0.3) * 0.15 + yawWobble + scrollYaw, dt * 2);
  }

  // ── Propeller speed reacts to force proximity + click impact ──
  const forceSpinBoost = forceField.strength * 15 + interact3D.clickForce * 10;

  // Propeller spin — boosted by cursor force proximity
  const propSpeed = (STATE.launched ? 45 : 15) + forceSpinBoost;
  if (mainDrone.userData.propellers) {
    mainDrone.userData.propellers.forEach((p, i) => {
      // Alternate CW/CCW like real quadcopters
      const dir = (i === 0 || i === 3) ? 1 : -1;
      p.rotation.y += dt * propSpeed * dir * motionScale;
      // Subtle wobble under force
      if (forceField.strength > 0.1) {
        p.rotation.x = Math.sin(time * 12 + i * 1.5) * forceField.strength * 0.03;
        p.rotation.z = Math.cos(time * 10 + i * 2) * forceField.strength * 0.03;
      } else {
        p.rotation.x *= 0.9;
        p.rotation.z *= 0.9;
      }
    });
  }

  // LED pulse — emissive intensity breathes
  mainDrone.traverse(child => {
    if (child.name && child.name.startsWith('droneLed_') && child.material) {
      child.material.emissiveIntensity = 0.5 + Math.sin(time * 3 + parseInt(child.name.slice(-1)) * 1.2) * 0.4;
    }
    if (child.name === 'droneAntenna' || (child.name && child.name.startsWith('droneStrip_'))) {
      if (child.material && child.material.emissiveIntensity !== undefined) {
        child.material.emissiveIntensity = 0.25 + Math.sin(time * 2) * 0.15;
      }
    }
  });
  updateHumPitch(STATE.launched ? 0.8 : 0.2);

  // ── Ambient Audio Adaptive Mix ──
  const droneSpeedNorm = Math.min(droneCurrentPos.distanceTo(droneTargetPos) * 5, 1);
  updateAmbientMix(droneSpeedNorm, forceField.strength, STATE.stormActive, STATE.scrollProgress);
  updateStormAmbient(STATE.stormActive);

  // ── Update Audio Listener position to match camera ──
  if (audioCtx && audioCtx.listener) {
    const listener = audioCtx.listener;
    if (listener.positionX) {
      listener.positionX.setValueAtTime(camera.position.x, audioCtx.currentTime);
      listener.positionY.setValueAtTime(camera.position.y, audioCtx.currentTime);
      listener.positionZ.setValueAtTime(camera.position.z, audioCtx.currentTime);
    }
  }

  // Camera position — lerp speed varies per section for cinematic pacing
  const camLerpSpeed = scrollSections < 1 ? 1.5 : scrollSections < 2 ? 1.0 : scrollSections < 3 ? 2.0 : 1.2;
  const cx = Math.sin(cameraAngle) * camRadius;
  const cz = Math.cos(cameraAngle) * camRadius;
  camera.position.lerp(new THREE.Vector3(cx, camHeight, cz), dt * camLerpSpeed);
  const lookTarget = new THREE.Vector3(droneCurrentPos.x, camLookY, droneCurrentPos.z);
  camera.lookAt(lookTarget);

  // ── FOV shifts with scroll for dramatic parallax ──
  const targetFov = scrollSections < 1 ? 50 : scrollSections < 2 ? 45 : scrollSections < 3 ? 55 : scrollSections < 4 ? 40 : 50;
  camera.fov = THREE.MathUtils.lerp(camera.fov, targetFov, dt * 2);
  camera.updateProjectionMatrix();

  // ── Particles — with cursor force repulsion ──
  particleMat.uniforms.uTime.value = time;
  particleMat.uniforms.uCursorPos.value.copy(forceField.worldPos);
  particleMat.uniforms.uCursorStrength.value = THREE.MathUtils.lerp(
    particleMat.uniforms.uCursorStrength.value, forceField.strength, dt * 5
  );
  particleMat.uniforms.uStorm.value = THREE.MathUtils.lerp(
    particleMat.uniforms.uStorm.value, STATE.stormActive ? 1 : 0, dt * 2
  );

  // Airflow particles
  const afPositions = airflowGeo.attributes.position.array;
  for (let i = 0; i < AIRFLOW_COUNT; i++) {
    airflowLife[i] -= dt * 2;
    if (airflowLife[i] <= 0) {
      // Respawn near a propeller
      const propIdx = Math.floor(Math.random() * 4);
      const offsets = [
        [0.55, 0.4], [-0.55, 0.4], [0.55, -0.4], [-0.55, -0.4]
      ];
      const off = offsets[propIdx];
      afPositions[i * 3] = mainDrone.position.x + off[0] * 0.8 + (Math.random() - 0.5) * 0.2;
      afPositions[i * 3 + 1] = mainDrone.position.y + 0.1;
      afPositions[i * 3 + 2] = mainDrone.position.z + off[1] * 0.8 + (Math.random() - 0.5) * 0.2;
      airflowVel[i * 3] = (Math.random() - 0.5) * 0.3;
      airflowVel[i * 3 + 1] = -1 - Math.random() * 2;
      airflowVel[i * 3 + 2] = (Math.random() - 0.5) * 0.3;
      airflowLife[i] = 0.5 + Math.random() * 0.5;
    }
    afPositions[i * 3] += airflowVel[i * 3] * dt;
    afPositions[i * 3 + 1] += airflowVel[i * 3 + 1] * dt;
    afPositions[i * 3 + 2] += airflowVel[i * 3 + 2] * dt;
  }
  airflowGeo.attributes.position.needsUpdate = true;

  // ── Enemy drones (dogfight) ──
  enemyDrones.forEach((enemy, i) => {
    enemy.visible = STATE.dogfightActive;
    if (!STATE.dogfightActive) return;

    const orbitSpeed = 0.6 + i * 0.3;
    const orbitRadius = 4 + i * 1.5;
    const baseAngle = time * orbitSpeed + i * Math.PI;
    const tx = Math.sin(baseAngle) * orbitRadius;
    const tz = Math.cos(baseAngle) * orbitRadius;
    const ty = 2.5 + Math.sin(time * 1.2 + i) * 1.5;

    enemy.position.lerp(new THREE.Vector3(tx, ty, tz), dt * 2);
    enemy.lookAt(mainDrone.position);
    enemy.rotation.z = Math.sin(time * 2 + i) * 0.3;

    if (enemy.userData.propellers) {
      enemy.userData.propellers.forEach((p, j) => {
        p.rotation.y += dt * 30 * (j % 2 === 0 ? 1 : -1);
      });
    }

    // Fire lasers
    if (Math.random() < dt * 0.5) {
      const dir = mainDrone.position.clone().sub(enemy.position).normalize();
      fireLaser(enemy.position.clone(), dir, 0xff3333);
    }

    // Main drone fires back
    if (Math.random() < dt * 0.3) {
      const dir = enemy.position.clone().sub(mainDrone.position).normalize();
      fireLaser(mainDrone.position.clone(), dir, 0x3878ff);
    }
  });

  // Update lasers
  for (let i = laserPool.length - 1; i >= 0; i--) {
    const laser = laserPool[i];
    laser.position.add(laser.userData.vel);
    laser.userData.life -= dt * 2;
    laser.material.opacity = laser.userData.life;
    if (laser.userData.life <= 0) {
      scene.remove(laser);
      laser.geometry.dispose();
      laser.material.dispose();
      laserPool.splice(i, 1);
    }
  }

  // ── Storm ──
  if (STATE.stormActive) {
    lightningTimer += dt;
    if (lightningTimer > 2 + Math.random() * 3) {
      triggerLightning();
      lightningTimer = 0;
    }
    // Storm overrides the scroll-based environment with darker tones
    scene.background.lerp(new THREE.Color(0x1a1a22), dt * 2);
    scene.fog.color.lerp(new THREE.Color(0x1a1a22), dt * 2);
    scene.fog.density = THREE.MathUtils.lerp(scene.fog.density, 0.07 + Math.sin(time * 0.5) * 0.015, dt * 2);
    groundMat.color.lerp(new THREE.Color(0x222230), dt * 2);
    fillLight.intensity = 0.15 + lightningFlash * 2;
    ambientLight.intensity = THREE.MathUtils.lerp(ambientLight.intensity, 0.3, dt * 2);
  } else {
    fillLight.intensity = THREE.MathUtils.lerp(fillLight.intensity, 0.6, dt * 2);
  }

  // Lightning fade
  if (lightningFlash > 0) {
    lightningFlash *= 0.92;
    lightningMat.opacity = lightningFlash;
    ambientLight.intensity = 0.3 + lightningFlash * 1.5;
    if (lightningFlash < 0.01) {
      lightningFlash = 0;
      ambientLight.intensity = 0.3;
    }
  }

  // ── Force-Reactive Objects Physics ──
  for (let i = 0; i < forceReactiveObjects.length; i++) {
    const obj = forceReactiveObjects[i];
    const mesh = obj.mesh;
    if (!mesh.parent) continue; // skip if removed

    // Distance from cursor force field to object
    const toObj = new THREE.Vector3().subVectors(mesh.position, forceField.worldPos);
    const dist = toObj.length();
    const inRange = dist < forceField.radius * 1.5;

    if (inRange && dist > 0.01) {
      // Repulsive force: inversely proportional to distance
      const forceMag = (1 - dist / (forceField.radius * 1.5)) * forceField.strength * 3.5 / obj.mass;
      const forceDir = toObj.normalize();
      obj.vel.addScaledVector(forceDir, forceMag * dt * 8);
      // Torque — spin objects slightly when pushed
      obj.rotVel.x += forceDir.z * forceMag * dt * 2;
      obj.rotVel.z -= forceDir.x * forceMag * dt * 2;
    }

    // Propeller downwash force on nearby objects
    if (obj.affectedByWind) {
      const toDrone = new THREE.Vector3().subVectors(mesh.position, mainDrone.position);
      const droneDist = toDrone.length();
      if (droneDist < 5) {
        const windStrength = (1 - droneDist / 5) * 0.3 * (STATE.launched ? 2.5 : 1.0);
        // Downwash pushes down and outward
        obj.vel.y -= windStrength * dt * 2;
        const outward = new THREE.Vector2(toDrone.x, toDrone.z).normalize();
        obj.vel.x += outward.x * windStrength * dt;
        obj.vel.z += outward.y * windStrength * dt;
      }
    }

    // Storm wind gusts
    if (STATE.stormActive && obj.affectedByWind) {
      const gustX = Math.sin(time * 1.5 + i * 0.7) * 0.15;
      const gustZ = Math.cos(time * 1.1 + i * 0.5) * 0.1;
      obj.vel.x += gustX * dt;
      obj.vel.z += gustZ * dt;
    }

    // Spring back to rest position
    const displacement = new THREE.Vector3().subVectors(mesh.position, obj.restPos);
    const dispLen = displacement.length();
    if (dispLen > 0.001) {
      obj.vel.addScaledVector(displacement, -obj.stiffness);
    }

    // Clamp displacement
    if (dispLen > obj.maxDisplace) {
      const clampDir = displacement.normalize().multiplyScalar(obj.maxDisplace);
      mesh.position.copy(obj.restPos).add(clampDir);
    }

    // Damping
    obj.vel.multiplyScalar(obj.damping);
    obj.rotVel.multiplyScalar(obj.damping);

    // Integrate
    mesh.position.addScaledVector(obj.vel, dt * 60);
    mesh.rotation.x = obj.restRot.x + obj.rotVel.x;
    mesh.rotation.z = obj.restRot.z + obj.rotVel.z;
  }

  // ── Airflow particles react to cursor force ──
  // (already updated above, but add cursor repulsion)
  const afPos = airflowGeo.attributes.position.array;
  for (let i = 0; i < AIRFLOW_COUNT; i++) {
    const px = afPos[i * 3];
    const py = afPos[i * 3 + 1];
    const pz = afPos[i * 3 + 2];
    const dx = px - forceField.worldPos.x;
    const dy = py - forceField.worldPos.y;
    const dz = pz - forceField.worldPos.z;
    const pDist = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (pDist < forceField.radius && pDist > 0.01) {
      const repel = (1 - pDist / forceField.radius) * forceField.strength * 0.15;
      afPos[i * 3] += (dx / pDist) * repel;
      afPos[i * 3 + 1] += (dy / pDist) * repel;
      afPos[i * 3 + 2] += (dz / pDist) * repel;
    }
  }

  // ── Accent lights animation — color shifts per scroll section ──
  const lightPull = forceField.strength * 0.5;

  // Accent light colors evolve with scroll
  const accentColor1 = new THREE.Color();
  const accentColor2 = new THREE.Color();
  if (scrollSections < 1) {
    accentColor1.set(0x99aacc); accentColor2.set(0x8899bb);
  } else if (scrollSections < 2) {
    accentColor1.set(0xaabbdd); accentColor2.set(0x7799cc);
  } else if (scrollSections < 3) {
    accentColor1.set(0x88aadd); accentColor2.set(0x6688bb);
  } else if (scrollSections < 4) {
    accentColor1.set(0x7799aa); accentColor2.set(0x668899);
  } else {
    accentColor1.set(0x99aacc); accentColor2.set(0x8899bb);
  }
  pointLight1.color.lerp(accentColor1, dt * 2);
  pointLight2.color.lerp(accentColor2, dt * 2);

  // Light intensity varies with scroll
  const scrollLightBoost = Math.sin(scrollSections * Math.PI * 0.5) * 0.3;
  pointLight1.intensity = 0.5 + scrollLightBoost;
  pointLight2.intensity = 0.4 + scrollLightBoost * 0.7;

  pointLight1.position.set(
    3 + Math.sin(time * 0.5) * 2 + forceField.worldPos.x * lightPull * 0.3,
    2 + Math.sin(time * 0.8) + forceField.worldPos.y * lightPull * 0.2,
    3 + Math.cos(time * 0.3) * 2
  );
  pointLight2.position.set(
    -3 + Math.cos(time * 0.4) * 2 + forceField.worldPos.x * lightPull * 0.2,
    1 + Math.sin(time * 0.6) + forceField.worldPos.y * lightPull * 0.15,
    -3 + Math.sin(time * 0.7) * 2
  );

  // ── HUD update — values shift with scroll depth ──
  const speed = droneCurrentPos.distanceTo(droneTargetPos) * 10;
  const scrollAlt = droneCurrentPos.y * 10 + scrollSections * 12;
  document.getElementById('hudAlt').textContent = scrollAlt.toFixed(1) + 'm';
  document.getElementById('hudSpd').textContent = (speed + scrollVelocity * 0.002).toFixed(1) + ' m/s';
  document.getElementById('hudBat').textContent = Math.max(62, 98 - Math.floor(time * 0.1) - Math.floor(scrollSections * 3)) + '%';
  document.getElementById('hudGps').textContent = scrollSections > 2 ? 'SCANNING' : 'LOCKED';
  document.getElementById('hudMode').textContent =
    STATE.flightMode === 2 ? 'CINEMATIC' :
    STATE.stormActive ? 'STORM' :
    STATE.dogfightActive ? 'COMBAT' :
    STATE.autopilotActive ? 'AUTO' :
    scrollSections < 1 ? 'HOVER' :
    scrollSections < 2 ? 'ASCEND' :
    scrollSections < 3 ? 'TRACKING' :
    scrollSections < 4 ? 'NAVIGATE' : 'DISPLAY';

  // Cursor proximity still nudges the drone, but the visible force rings and
  // pressure-wave particles stay hidden for a cleaner landing-page feel.
  forceRingMat.opacity = 0;
  forceRippleMat.uniforms.uOpacity.value = 0;
  waveMat.opacity = 0;

  // Force field sound feedback — spatial swirl when cursor is close
  if (forceField.strength > 0.3 && Math.random() < dt * forceField.strength * 2) {
    const fp = forceField.worldPos;
    playTone(200 + forceField.strength * 300, 0.1, 0.008, 'triangle', {
      spatial: true, x: fp.x, y: fp.y, z: fp.z, pitchVariation: 0.06
    });
  }

  // ── God Rays update ──
  coneMat.uniforms.uTime.value = time;
  godRay1.rotation.y = time * 0.05;
  godRay2.rotation.y = -time * 0.04;
  // Dim god rays when storm is active
  const godRayOpacity = STATE.stormActive ? 0.01 : (0.03 + Math.sin(time * 0.8) * 0.015);
  coneMat.uniforms.uOpacity.value = THREE.MathUtils.lerp(coneMat.uniforms.uOpacity.value, godRayOpacity, dt * 2);
  godRay2.material.uniforms.uOpacity.value = THREE.MathUtils.lerp(godRay2.material.uniforms.uOpacity.value, godRayOpacity * 0.7, dt * 2);

  // ── Holographic Rings — react to click force with scale pulse ──
  const clickPulse = 1 + interact3D.clickForce * 0.25;
  holoRingMat.uniforms.uTime.value = time;
  holoRing2.material.uniforms.uTime.value = time + 1.5;
  holoRing3.material.uniforms.uTime.value = time + 3.0;
  holoRing1.position.x = droneCurrentPos.x;
  holoRing1.position.z = droneCurrentPos.z;
  holoRing2.position.x = droneCurrentPos.x;
  holoRing2.position.z = droneCurrentPos.z;
  holoRing3.position.x = droneCurrentPos.x;
  holoRing3.position.z = droneCurrentPos.z;
  holoRing1.rotation.z = time * 0.1 + interact3D.clickForce * 0.3;
  holoRing2.rotation.z = -time * 0.08 - interact3D.clickForce * 0.2;
  holoRing3.rotation.z = time * 0.15 + interact3D.clickForce * 0.15;
  holoRing1.scale.setScalar(THREE.MathUtils.lerp(holoRing1.scale.x, clickPulse, dt * 8));
  holoRing2.scale.setScalar(THREE.MathUtils.lerp(holoRing2.scale.x, clickPulse * 0.95, dt * 7));
  holoRing3.scale.setScalar(THREE.MathUtils.lerp(holoRing3.scale.x, clickPulse * 1.05, dt * 6));
  const holoTargetOp = scrollSections < 1 ? 0.4 : scrollSections < 3 ? 0.2 : scrollSections < 4 ? 0.1 : 0.35;
  const holoForceOp = holoTargetOp + forceField.strength * 0.3 + interact3D.clickForce * 0.4;
  holoRingMat.uniforms.uOpacity.value = THREE.MathUtils.lerp(holoRingMat.uniforms.uOpacity.value, holoForceOp, dt * 3);
  holoRing2.material.uniforms.uOpacity.value = holoRingMat.uniforms.uOpacity.value * 0.6;
  holoRing3.material.uniforms.uOpacity.value = holoRingMat.uniforms.uOpacity.value * 0.8;

  // ── Tick Marks — jitter outward on click force ──
  tickGroup.position.x = droneCurrentPos.x;
  tickGroup.position.z = droneCurrentPos.z;
  tickGroup.rotation.y = -time * 0.12 + interact3D.clickForce * 0.5;
  tickGroup.children.forEach((tick, i) => {
    tick.material.opacity = 0.12 + Math.sin(time * 2 + i * 0.3) * 0.08 + forceField.strength * 0.15 + interact3D.clickForce * 0.3;
    // Radial displacement from click
    const tickAngle = (i / 60) * Math.PI * 2;
    const r = 2.8 + interact3D.clickForce * 0.4 * Math.sin(time * 8 + i * 0.5);
    tick.position.x = Math.cos(tickAngle) * r;
    tick.position.z = Math.sin(tickAngle) * r;
  });

  // ── Orbiting Data Nodes ──
  orbitDataGroup.position.set(droneCurrentPos.x, droneCurrentPos.y, droneCurrentPos.z);
  orbitDataGroup.rotation.y = time * 0.08;
  const orbitOpTarget = STATE.stormActive ? 0.1 : (0.35 + forceField.strength * 0.3);
  orbitDataGroup.children.forEach(ringGroup => {
    ringGroup.children.forEach(child => {
      if (child.userData.angle !== undefined) {
        child.userData.angle += dt * child.userData.speed;
        const a = child.userData.angle;
        const r = child.userData.radius;
        child.position.set(Math.cos(a) * r, Math.sin(a * 0.7) * 0.3, Math.sin(a) * r);
        child.rotation.y = time * 2;
        child.rotation.x = time * 1.5;
        if (child.material) child.material.opacity = orbitOpTarget;
      }
      if (child.geometry && child.geometry.type === 'TorusGeometry' && child.material) {
        child.material.opacity = orbitOpTarget * 0.25;
      }
    });
  });

  // ── Energy Beam — pulse brighter on click ──
  beamMat.uniforms.uTime.value = time;
  energyBeam.position.x = droneCurrentPos.x;
  energyBeam.position.z = droneCurrentPos.z;
  const beamOpTarget = (scrollSections < 1 ? 0.08 : scrollSections < 2 ? 0.14 : 0.06) + forceField.strength * 0.1 + interact3D.clickForce * 0.3;
  beamMat.uniforms.uOpacity.value = THREE.MathUtils.lerp(beamMat.uniforms.uOpacity.value, STATE.stormActive ? 0.02 : beamOpTarget, dt * 3);
  // Scale beam width on click
  const beamScale = 1 + interact3D.clickForce * 0.8;
  energyBeam.scale.x = THREE.MathUtils.lerp(energyBeam.scale.x, beamScale, dt * 6);
  energyBeam.scale.z = THREE.MathUtils.lerp(energyBeam.scale.z, beamScale, dt * 6);

  // ── Scanning Grid — expand rings faster on click ──
  scanGridMat.uniforms.uTime.value = time + interact3D.clickForce * 2; // accelerate scan rings
  scanGridMat.uniforms.uDronePos.value.copy(droneCurrentPos);
  scanGrid.position.x = droneCurrentPos.x;
  scanGrid.position.z = droneCurrentPos.z;
  const scanOpTarget = (scrollSections > 2 && scrollSections < 4 ? 0.35 : 0.12) + forceField.strength * 0.2 + interact3D.clickForce * 0.4;
  scanGridMat.uniforms.uOpacity.value = THREE.MathUtils.lerp(scanGridMat.uniforms.uOpacity.value, scanOpTarget, dt * 3);
  // Scale grid outward on click
  const scanScale = 1 + interact3D.clickForce * 0.3;
  scanGrid.scale.setScalar(THREE.MathUtils.lerp(scanGrid.scale.x, scanScale, dt * 4));

  // ── Floating Glyphs — scatter outward on click ──
  glyphGroup.children.forEach(sprite => {
    const d = sprite.userData;
    const a = d.baseAngle + time * (0.15 + d.idx * 0.02);
    const clickScatter = interact3D.clickForce * 1.2;
    const effectiveDist = d.dist + clickScatter * (0.5 + d.idx * 0.2);
    sprite.position.set(
      droneCurrentPos.x + Math.cos(a) * effectiveDist,
      droneCurrentPos.y + d.vOff + Math.sin(time * 1.2 + d.idx) * 0.15 + clickScatter * Math.sin(d.idx * 2.3) * 0.5,
      droneCurrentPos.z + Math.sin(a) * effectiveDist
    );
    sprite.material.opacity = 0.2 + forceField.strength * 0.25 + interact3D.clickForce * 0.35 + Math.sin(time * 2 + d.idx * 1.5) * 0.08;
    sprite.scale.setScalar(0.35 + interact3D.clickForce * 0.15);
  });

  // ── Windmill Animation ──
  windmills.forEach((wm, wi) => {
    const rotor = wm.userData.rotorGroup;
    const warnLight = wm.userData.warningLight;
    const baseSpeed = wm.userData.spinSpeed;

    // Wind speed factor — faster in storm, affected by cursor proximity
    let windFactor = STATE.stormActive ? 2.5 + Math.sin(time * 0.8 + wi) * 0.8 : 1.0;

    // Cursor proximity boosts spin
    const wmWorldPos = new THREE.Vector3();
    wm.getWorldPosition(wmWorldPos);
    wmWorldPos.y += wm.userData.height;
    const cursorToWm = forceField.worldPos.distanceTo(wmWorldPos);
    if (cursorToWm < 6) {
      windFactor += (1 - cursorToWm / 6) * forceField.strength * 3;
    }

    // Drone downwash proximity boosts spin
    const droneToWm = mainDrone.position.distanceTo(wmWorldPos);
    if (droneToWm < 5) {
      windFactor += (1 - droneToWm / 5) * 1.5 * (STATE.launched ? 2.5 : 1.0);
    }

    // Click impact on windmill — spin boost
    const wmWorldPos2 = new THREE.Vector3();
    wm.getWorldPosition(wmWorldPos2);
    const clickToWm = wmWorldPos2.distanceTo(interact3D.clickOrigin);
    if (clickToWm < 8 && interact3D.clickForce > 0.05) {
      windFactor += (1 - clickToWm / 8) * interact3D.clickForce * 5;
    }

    // Drag interaction on windmill
    if (interact3D.dragActive && interact3D.hoveredObject) {
      let isOnThisWm = false;
      wm.traverse(c => { if (c === interact3D.hoveredObject) isOnThisWm = true; });
      if (isOnThisWm) {
        windFactor += Math.abs(interact3D.dragVelocity.x) * 0.03;
      }
    }

    // Spin the rotor
    rotor.rotation.z += dt * baseSpeed * windFactor * 2.0 * motionScale;

    // Subtle nacelle yaw — windmills face into wind direction
    const windAngle = Math.sin(time * 0.15 + wi * 1.3) * 0.2;
    rotor.parent.children.forEach(child => {
      if (child.name && child.name.startsWith('windmillNacelle')) {
        child.rotation.y = THREE.MathUtils.lerp(child.rotation.y || 0, windAngle, dt * 0.5);
      }
    });

    // Warning light blinks — slow pulse with occasional fast flash
    if (warnLight && warnLight.material) {
      const blinkPhase = (time * 0.8 + wi * 2.1) % 4;
      const blinkIntensity = blinkPhase < 0.3 ? 1.2 : blinkPhase < 0.6 ? 0.6 : 0.05;
      warnLight.material.emissiveIntensity = blinkIntensity;
    }

    // Visibility — fade in/out based on scroll (visible from section 2 onward)
    const wmTargetOpacity = scrollSections > 1.5 ? 1 : scrollSections > 0.8 ? (scrollSections - 0.8) / 0.7 : 0;
    if (!wm.userData._vis) wm.userData._vis = 0;
    wm.userData._vis = THREE.MathUtils.lerp(wm.userData._vis, wmTargetOpacity, dt * 3);
    wm.visible = wm.userData._vis > 0.01;
    wm.traverse(child => {
      if (child.isMesh && child.material) {
        if (!child.material._wmTransparent) {
          child.material._wmTransparent = true;
          child.material.transparent = true;
        }
        child.material.opacity = wm.userData._vis;
      }
    });
  });

  // ── Afterimage Ghost Trail ──
  ghostTimer += dt;
  const droneSpeed = droneCurrentPos.distanceTo(droneTargetPos);
  const ghostInterval = droneSpeed > 0.05 ? 0.04 : 0.12;
  if (ghostTimer > ghostInterval) {
    ghostTimer = 0;
    const g = ghosts[ghostIndex % GHOST_COUNT];
    g.pos.copy(mainDrone.position);
    g.rot.copy(mainDrone.rotation);
    g.age = 1.0;
    ghostIndex++;
  }
  ghosts.forEach(g => {
    if (g.age > 0) {
      g.mesh.visible = true;
      g.mesh.position.copy(g.pos);
      g.mesh.rotation.copy(g.rot);
      g.mesh.scale.setScalar(2.2);
      g.age -= dt * 3;
      const ghostAlpha = Math.max(0, g.age * 0.12);
      g.mesh.traverse(child => {
        if (child.isMesh && child.material) {
          child.material.opacity = ghostAlpha;
        }
      });
      if (g.age <= 0) g.mesh.visible = false;
    }
  });

  // ── Contact Shadow follows drone — pulses on click ──
  contactShadow.position.x = droneCurrentPos.x;
  contactShadow.position.z = droneCurrentPos.z;
  // Scale shrinks + fades as drone rises
  const shadowAlt = droneCurrentPos.y + 1; // height above ground
  const shadowScale = Math.max(0.5, 3.5 - shadowAlt * 0.25) + interact3D.clickForce * 0.8;
  contactShadow.scale.setScalar(THREE.MathUtils.lerp(contactShadow.scale.x, shadowScale, dt * 6));
  contactShadowMat.opacity = Math.max(0, 0.7 - shadowAlt * 0.06 + interact3D.clickForce * 0.15);

  // ── Chromatic Aberration / Distortion near drone on hover ──
  // Simulate via slight camera position jitter when force is strong
  const totalForce = forceField.strength + interact3D.clickForce * 0.5;
  if (totalForce > 0.4) {
    const jitter = (totalForce - 0.4) * 0.018;
    camera.position.x += (Math.random() - 0.5) * jitter;
    camera.position.y += (Math.random() - 0.5) * jitter * 0.5;
  }

  // ── Cursor style reflects 3D hover state ──
  renderer.domElement.style.cursor = interact3D.hoveredObject ? 'pointer' : 'default';

  renderer.render(scene, camera);
}

animate();

// ── Resize ──
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ── Ensure page is scrollable ──
document.body.style.height = (window.innerHeight * 5.5 + 600) + 'px';

// ═══════════════════════════════════════════════════════════
// ── GLOBAL HOVER & CLICK SOUND SYSTEM ──
// Every interactive element gets contextual hover + click sounds
// ═══════════════════════════════════════════════════════════

// Hover ripple visual — subtle radial pulse on hover
function addHoverRippleCSS() {
  const s = document.createElement('style');
  s.textContent = `
    .sound-hover-ring {
      position: absolute; top: 50%; left: 50%; width: 100%; height: 100%;
      transform: translate(-50%, -50%) scale(0.8);
      border-radius: inherit; border: 1px solid rgba(0,0,0,0.06);
      pointer-events: none; opacity: 0;
      animation: hover-ring-expand 0.5s ease-out forwards;
    }
    @keyframes hover-ring-expand {
      0% { transform: translate(-50%, -50%) scale(0.8); opacity: 0.6; }
      100% { transform: translate(-50%, -50%) scale(1.08); opacity: 0; }
    }
    .sound-click-flash {
      position: absolute; top: 50%; left: 50%; width: 120%; height: 120%;
      transform: translate(-50%, -50%) scale(0);
      border-radius: inherit; background: rgba(0,0,0,0.04);
      pointer-events: none; opacity: 0;
      animation: click-flash 0.35s ease-out forwards;
    }
    @keyframes click-flash {
      0% { transform: translate(-50%, -50%) scale(0); opacity: 1; }
      100% { transform: translate(-50%, -50%) scale(1); opacity: 0; }
    }
  `;
  document.head.appendChild(s);
}
addHoverRippleCSS();

function spawnHoverRing(el) {
  if (STATE.reducedMotion) return;
  const ring = document.createElement('div');
  ring.className = 'sound-hover-ring';
  if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
  el.style.overflow = el.style.overflow || 'hidden';
  el.appendChild(ring);
  setTimeout(() => ring.remove(), 500);
}

function spawnClickFlash(el) {
  if (STATE.reducedMotion) return;
  const flash = document.createElement('div');
  flash.className = 'sound-click-flash';
  if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
  el.appendChild(flash);
  setTimeout(() => flash.remove(), 350);
}

// Throttle helper — prevents sound spam on rapid hover
const hoverThrottles = new WeakMap();
function throttledHover(el, fn) {
  const now = Date.now();
  const last = hoverThrottles.get(el) || 0;
  if (now - last < 80) return;
  hoverThrottles.set(el, now);
  fn();
}

// ── Map element selectors to sound functions ──
const SOUND_MAP = {
  hover: [
    // Navigation
    { sel: '.nav-link', fn: playHoverSoft },
    { sel: '.nav-btn', fn: playHoverBright },
    { sel: '.nav-logo', fn: playHoverDeep },
    { sel: '.section-dot', fn: playHoverBright },
    { sel: '.sound-toggle', fn: playHoverWarm },
    // Hero
    { sel: '.cta-launch', fn: playHoverDeep },
    { sel: '.cta-explore', fn: playHoverSoft },
    { sel: '.hero-badge', fn: playHoverBright },
    { sel: '.stat', fn: playHoverSoft },
    // Sections
    { sel: '.float-panel', fn: playHoverWarm },
    { sel: '.section-label', fn: playHoverBright },
    // Drone selector
    { sel: '.drone-card', fn: playHover },
    // Action bar
    { sel: '.action-btn', fn: playHoverSoft },
    // HUD
    { sel: '.hud-item', fn: playHoverBright },
    // Footer
    { sel: '.footer-link', fn: playHoverSoft },
    { sel: '.social-link', fn: playHoverWarm },
    { sel: '.legal-link', fn: playHoverSoft },
    { sel: '.footer-logo', fn: playHoverDeep },
    { sel: '.footer-col-title', fn: playHoverBright },
    { sel: '.newsletter-btn', fn: playHoverDeep },
    { sel: '.newsletter-input', fn: playHoverSoft },
    // Scroll hint
    { sel: '.scroll-hint', fn: playHoverBright },
  ],
  click: [
    // Navigation
    { sel: '.nav-link', fn: playClickNav },
    { sel: '.nav-btn.btn-ghost', fn: playClickSoft },
    { sel: '.nav-btn.btn-primary', fn: playClickBright },
    { sel: '.sound-toggle', fn: () => {} }, // toggle sound is inline
    // Hero
    { sel: '.cta-launch', fn: () => {} }, // launch sound is inline
    { sel: '.cta-explore', fn: () => {} }, // explore sound is inline
    { sel: '.hero-badge', fn: playClickSoft },
    { sel: '.stat', fn: playClickSoft },
    // Sections
    { sel: '.float-panel', fn: playClickSoft },
    // Drone selector — handled separately with playMorph
    { sel: '.drone-card', fn: () => {} }, // morph is inline
    // Action bar — handled separately with toggle logic
    { sel: '.action-btn', fn: () => {} }, // storm/dogfight/autopilot have inline sounds
    // HUD
    { sel: '.hud-item', fn: playClickSoft },
    // Footer
    { sel: '.footer-link', fn: playClickNav },
    { sel: '.social-link', fn: playClickBright },
    { sel: '.legal-link', fn: playClickSoft },
    { sel: '.newsletter-btn', fn: playClickDeep },
    // Scroll hint
    { sel: '.scroll-hint', fn: playClickSoft },
    // Section dots
    { sel: '.section-dot', fn: playClick },
  ]
};

// Bind all hover sounds
SOUND_MAP.hover.forEach(({ sel, fn }) => {
  document.querySelectorAll(sel).forEach(el => {
    el.addEventListener('mouseenter', () => {
      throttledHover(el, () => {
        fn();
        spawnHoverRing(el);
      });
    });
  });
});

// Bind all click sounds
SOUND_MAP.click.forEach(({ sel, fn }) => {
  document.querySelectorAll(sel).forEach(el => {
    el.addEventListener('click', () => {
      fn();
      spawnClickFlash(el);
    });
  });
});

// ── Input focus/blur sounds ──
document.querySelectorAll('input, textarea').forEach(el => {
  el.addEventListener('focus', () => { playInputFocus(); });
  el.addEventListener('blur', () => { playInputBlur(); });
});

// ── Newsletter subscribe with sound ──
document.querySelector('.newsletter-btn')?.addEventListener('click', (e) => {
  e.preventDefault();
  const input = document.querySelector('.newsletter-input');
  if (input && input.value.includes('@')) {
    input.value = '';
    input.placeholder = 'Subscribed ✓';
    // Success chime — ascending triad
    playTone(800, 0.12, 0.03);
    setTimeout(() => playTone(1000, 0.12, 0.025), 80);
    setTimeout(() => playTone(1200, 0.15, 0.02), 160);
    setTimeout(() => { input.placeholder = 'Enter your email'; }, 2000);
  }
});

// ── Catch-all: any element with cursor:pointer that wasn't explicitly mapped ──
// Uses MutationObserver-free approach: delegated events on document
document.addEventListener('mouseenter', (e) => {
  const el = e.target;
  if (!el || !el.matches) return;
  // Skip if already handled by specific bindings
  const handled = SOUND_MAP.hover.some(({ sel }) => el.matches(sel));
  if (handled) return;
  // Check if element looks interactive
  const style = getComputedStyle(el);
  if (style.cursor === 'pointer' || el.tagName === 'A' || el.tagName === 'BUTTON') {
    throttledHover(el, () => {
      playHoverSoft();
      spawnHoverRing(el);
    });
  }
}, true);

document.addEventListener('click', (e) => {
  const el = e.target;
  if (!el || !el.matches) return;
  const handled = SOUND_MAP.click.some(({ sel }) => el.matches(sel));
  if (handled) return;
  const style = getComputedStyle(el);
  if (style.cursor === 'pointer' || el.tagName === 'A' || el.tagName === 'BUTTON') {
    playClickSoft();
    spawnClickFlash(el);
  }
}, true);
