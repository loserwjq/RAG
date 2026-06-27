<template>
  <canvas ref="canvas" class="cyber-canvas"></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvas = ref(null)
let ctx = null
let W = 0, H = 0, dpr = 1
let rafId = null

/* ═══════════════════════════════════════════════════════════
   Mouse state
   ═══════════════════════════════════════════════════════════ */
const mouse = { x: -100, y: -100, onScreen: false }

/* ═══════════════════════════════════════════════════════════
   Grid — 电路网格
   ═══════════════════════════════════════════════════════════ */
const gridSize = 48
const gridPoints = []

function buildGrid() {
  gridPoints.length = 0
  for (let x = gridSize; x < W; x += gridSize) {
    for (let y = gridSize; y < H; y += gridSize) {
      gridPoints.push({ x, y, baseAlpha: 0.03 + Math.random() * 0.04 })
    }
  }
}

function drawGrid(t) {
  ctx.strokeStyle = 'rgba(0,255,136,0.06)'
  ctx.lineWidth = 0.5

  ctx.beginPath()
  for (let x = gridSize; x < W; x += gridSize) {
    ctx.moveTo(x, 0)
    ctx.lineTo(x, H)
  }
  for (let y = gridSize; y < H; y += gridSize) {
    ctx.moveTo(0, y)
    ctx.lineTo(W, y)
  }
  ctx.stroke()

  // Glowing grid points
  for (const pt of gridPoints) {
    const dx = mouse.x - pt.x
    const dy = mouse.y - pt.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    const glowRadius = 120
    let alpha = pt.baseAlpha

    if (mouse.onScreen && dist < glowRadius) {
      alpha += (1 - dist / glowRadius) * 0.25
    }

    // Subtle pulse
    alpha += Math.sin(t * 0.002 + pt.x * 0.01 + pt.y * 0.01) * 0.015

    if (alpha > 0.01) {
      ctx.fillStyle = `rgba(0,255,136,${alpha})`
      ctx.beginPath()
      ctx.arc(pt.x, pt.y, 0.8, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

/* ═══════════════════════════════════════════════════════════
   Floating particles
   ═══════════════════════════════════════════════════════════ */
const particles = []

function initParticles() {
  particles.length = 0
  const count = Math.floor((W * H) / 15000)
  for (let i = 0; i < count; i++) {
    particles.push({
      x: Math.random() * W,
      y: Math.random() * H,
      r: 0.3 + Math.random() * 1.2,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      alpha: 0.1 + Math.random() * 0.3,
      color: Math.random() < 0.7 ? '0,255,136' : '0,212,255',
      pulseSpeed: 0.005 + Math.random() * 0.015,
    })
  }
}

function drawParticles(t) {
  for (const p of particles) {
    p.x += p.vx
    p.y += p.vy

    if (p.x < 0) p.x = W
    if (p.x > W) p.x = 0
    if (p.y < 0) p.y = H
    if (p.y > H) p.y = 0

    const alpha = p.alpha + Math.sin(t * p.pulseSpeed) * 0.15

    // Draw particle
    ctx.fillStyle = `rgba(${p.color},${Math.max(0, Math.min(1, alpha))})`
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
    ctx.fill()

    // Glow for brighter particles
    if (p.r > 0.7) {
      ctx.fillStyle = `rgba(${p.color},${Math.max(0, Math.min(1, alpha * 0.3))})`
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.r * 2.5, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

/* ═══════════════════════════════════════════════════════════
   Cursor glow
   ═══════════════════════════════════════════════════════════ */
const trailPoints = []

function drawCursorGlow() {
  if (!mouse.onScreen) return

  // Fade trail
  for (let i = trailPoints.length - 1; i >= 0; i--) {
    const p = trailPoints[i]
    p.life -= 0.02
    if (p.life <= 0) {
      trailPoints.splice(i, 1)
      continue
    }
    const r = p.size * p.life
    const a = p.life * 0.15
    ctx.fillStyle = `rgba(0,255,136,${a})`
    ctx.beginPath()
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2)
    ctx.fill()
  }

  // Core dot
  const coreGrad = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 12)
  coreGrad.addColorStop(0, 'rgba(0,255,136,0.4)')
  coreGrad.addColorStop(0.3, 'rgba(0,255,136,0.15)')
  coreGrad.addColorStop(1, 'rgba(0,255,136,0)')
  ctx.fillStyle = coreGrad
  ctx.beginPath()
  ctx.arc(mouse.x, mouse.y, 12, 0, Math.PI * 2)
  ctx.fill()
}

/* ═══════════════════════════════════════════════════════════
   Animation loop
   ═══════════════════════════════════════════════════════════ */
function animate(t) {
  ctx.clearRect(0, 0, W, H)
  drawGrid(t)
  drawParticles(t)
  drawCursorGlow()
  rafId = requestAnimationFrame(animate)
}

/* ═══════════════════════════════════════════════════════════
   Resize
   ═══════════════════════════════════════════════════════════ */
function resize() {
  W = window.innerWidth
  H = window.innerHeight
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.value.width = W * dpr
  canvas.value.height = H * dpr
  canvas.value.style.width = W + 'px'
  canvas.value.style.height = H + 'px'
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.scale(dpr, dpr)
  buildGrid()
  initParticles()
}

/* ═══════════════════════════════════════════════════════════
   Events
   ═══════════════════════════════════════════════════════════ */
function onMouseMove(e) {
  mouse.x = e.clientX
  mouse.y = e.clientY
  const prevOnScreen = mouse.onScreen
  mouse.onScreen = true

  if (prevOnScreen) {
    trailPoints.push({ x: e.clientX, y: e.clientY, size: 2 + Math.random() * 3, life: 1 })
    if (trailPoints.length > 30) trailPoints.shift()
  }
}

function onMouseLeave() { mouse.onScreen = false }
function onMouseEnter(e) { mouse.x = e.clientX; mouse.y = e.clientY; mouse.onScreen = true }

/* ═══════════════════════════════════════════════════════════
   Lifecycle
   ═══════════════════════════════════════════════════════════ */
onMounted(() => {
  ctx = canvas.value.getContext('2d')
  resize()
  window.addEventListener('resize', resize)
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseleave', onMouseLeave)
  window.addEventListener('mouseenter', onMouseEnter)
  rafId = requestAnimationFrame(animate)
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  window.removeEventListener('resize', resize)
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseleave', onMouseLeave)
  window.removeEventListener('mouseenter', onMouseEnter)
})
</script>

<style scoped>
.cyber-canvas {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
</style>
