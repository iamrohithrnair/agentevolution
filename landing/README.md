# Dronan — Landing Page

A standalone marketing landing page for **Dronan**, the self-evolving medical drone fleet built for the MongoDB Agentic Evolution Hackathon (London 2026).

This folder is **fully decoupled** from the actual Dronan application (the rebuild specified under `prompts/`). The app runs without the landing page, and the landing page runs without the app.

The landing page links into the actual app at `http://localhost:3000` via the nav **Open App** link, footer **Mission Console** link, and the hero **Dispatch Mission** CTA after a short launch animation.

## Stack

- Three.js (cinematic 3D scene, drone morphing, ripple physics)
- Vite (zero-config dev server + bundler)
- Pure light-mode CSS, no audio

## Run

```bash
npm install
npm run dev   # http://localhost:5173
```

## Build

```bash
npm run build
npm run preview
```

## Credits

3D scene assets and motion design adapted from a cinematic drone-launch template; all copy, branding, agent fleet, and information architecture rewritten for Dronan.
