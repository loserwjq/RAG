<template>
  <div class="splash-scene" ref="sceneRef">
    <!-- 粒子爆发层 -->
    <div class="particle-burst" ref="burstRef">
      <div v-for="i in 24" :key="i" class="spark" :ref="el => { if (el) sparks[i-1] = el }"></div>
    </div>

    <!-- 绿色方块 / 登录卡片 -->
    <div class="cube-card" ref="cubeRef">
      <!-- 方块阶段：绿色霓虹方块 -->
      <div class="cube-face" ref="cubeFaceRef">
        <div class="cube-inner">
          <div class="cube-glow"></div>
          <div class="cube-lines">
            <span class="cube-line cube-line--top"></span>
            <span class="cube-line cube-line--right"></span>
            <span class="cube-line cube-line--bottom"></span>
            <span class="cube-line cube-line--left"></span>
          </div>
          <div class="cube-corner cube-corner--tl"></div>
          <div class="cube-corner cube-corner--tr"></div>
          <div class="cube-corner cube-corner--bl"></div>
          <div class="cube-corner cube-corner--br"></div>
        </div>
      </div>

      <!-- 登录卡片阶段：隐藏的登录表单 -->
      <div class="card-content" ref="cardContentRef">
        <!-- 标题 -->
        <div class="card-header">
          <div class="card-logo">
            <div class="logo-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="3"/>
                <rect x="7" y="7" width="10" height="10" rx="1.5"/>
                <circle cx="12" cy="12" r="3" fill="currentColor" opacity="0.3"/>
              </svg>
            </div>
            <h1 class="logo-title">NEURAL<span class="logo-accent">KB</span></h1>
          </div>
          <p class="card-subtitle">智能知识库问答系统</p>
        </div>

        <!-- 登录表单 -->
        <div class="form-tabs">
          <button class="form-tab" :class="{ active: !isRegister }" @click="isRegister = false; loginError = ''">
            登 录
          </button>
          <button class="form-tab" :class="{ active: isRegister }" @click="isRegister = true; regError = ''">
            注 册
          </button>
        </div>

        <form v-if="!isRegister" @submit.prevent="login" class="login-form">
          <div class="form-field">
            <label for="login-user">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              用户名
            </label>
            <input id="login-user" v-model="loginForm.username" type="text" placeholder="请输入用户名" required autofocus />
          </div>
          <div class="form-field">
            <label for="login-pass">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              密码
            </label>
            <input id="login-pass" v-model="loginForm.password" type="password" placeholder="请输入密码" required />
          </div>
          <button type="submit" class="btn-submit" :disabled="loginLoading">
            <span v-if="loginLoading" class="spinner"></span>
            <span v-else class="btn-content">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 10 4 15 9 20"/><path d="M20 4v7a4 4 0 0 1-4 4H4"/></svg>
              登 录
            </span>
          </button>
          <div v-if="loginError" class="form-error">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
            {{ loginError }}
          </div>
        </form>

        <form v-else @submit.prevent="register" class="reg-form">
          <div class="form-field">
            <label for="reg-user">用户名</label>
            <input id="reg-user" v-model="reg.username" type="text" placeholder="请输入用户名" required autofocus />
          </div>
          <div class="form-field">
            <label for="reg-pass">密码</label>
            <input id="reg-pass" v-model="reg.password" type="password" placeholder="请输入密码" required />
          </div>
          <div class="form-field">
            <label for="reg-name">显示名称</label>
            <input id="reg-name" v-model="reg.displayName" type="text" placeholder="选填" />
          </div>
          <div class="form-field">
            <label for="reg-dept">部门</label>
            <select id="reg-dept" v-model="reg.department" required>
              <option value="">请选择部门</option>
              <option value="dev">开发部</option>
              <option value="test">测试部</option>
              <option value="product">产品部</option>
            </select>
          </div>
          <button type="submit" class="btn-submit" :disabled="regLoading">
            <span v-if="regLoading" class="spinner"></span>
            <span v-else class="btn-content">注册并登录</span>
          </button>
          <div v-if="regError" class="form-error">{{ regError }}</div>
          <div v-if="regOk" class="form-success">注册成功，正在登录...</div>
        </form>

        <!-- 特性列表 -->
        <div class="feature-strip">
          <div class="feature-chip">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            多格式解析
          </div>
          <div class="feature-chip">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            混合检索
          </div>
          <div class="feature-chip">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            多轮对话
          </div>
        </div>
      </div>
    </div>

    <!-- 跳过按钮 -->
    <button class="skip-btn" ref="skipRef" @click="skipAnimation">跳过动画 →</button>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import gsap from 'gsap'
import { apiPost, setUser } from '../api.js'

const emit = defineEmits(['logged-in'])

const sceneRef = ref(null)
const cubeRef = ref(null)
const cubeFaceRef = ref(null)
const cardContentRef = ref(null)
const burstRef = ref(null)
const skipRef = ref(null)
const sparks = ref([])

const isRegister = ref(false)

const loginForm = ref({ username: '', password: '' })
const loginError = ref('')
const loginLoading = ref(false)

const reg = ref({ username: '', password: '', displayName: '', department: '' })
const regError = ref('')
const regOk = ref(false)
const regLoading = ref(false)

function makeUser(data) {
  return {
    user_id: data.user_id,
    username: data.username,
    display_name: data.display_name,
    department: data.department,
    role: data.role,
  }
}

async function login() {
  loginError.value = ''
  loginLoading.value = true
  try {
    const data = await apiPost('/api/auth/login', {
      username: loginForm.value.username,
      password: loginForm.value.password,
    })
    const user = makeUser(data)
    setUser(user)
    await exitAnimation()
    emit('logged-in', user)
  } catch (e) {
    loginError.value = e.message
  } finally {
    loginLoading.value = false
  }
}

async function register() {
  regError.value = ''
  regOk.value = false
  regLoading.value = true
  try {
    const data = await apiPost('/api/auth/register', {
      username: reg.value.username,
      password: reg.value.password,
      display_name: reg.value.displayName || reg.value.username,
      department: reg.value.department,
    })
    regOk.value = true
    const user = makeUser(data)
    setUser(user)
    setTimeout(async () => {
      await exitAnimation()
      emit('logged-in', user)
    }, 600)
  } catch (e) {
    regError.value = e.message
  } finally {
    regLoading.value = false
  }
}

/* ═══════════════════════════════════════════════════════════
   GSAP Animation
   ═══════════════════════════════════════════════════════════ */
let tl = null
let isSkipped = false

function skipAnimation() {
  if (isSkipped) return
  isSkipped = true
  if (tl) tl.progress(1)
}

function particleBurst() {
  const sps = sparks.value.filter(Boolean)
  sps.forEach((el, i) => {
    const angle = (i / sps.length) * Math.PI * 2
    const distance = 60 + Math.random() * 100
    gsap.fromTo(el, {
      x: 0, y: 0, scale: 1, opacity: 1
    }, {
      x: Math.cos(angle) * distance,
      y: Math.sin(angle) * distance,
      scale: 0,
      opacity: 0,
      duration: 0.6 + Math.random() * 0.4,
      ease: 'power2.out',
    })
  })
}

async function exitAnimation() {
  // 卡片收拢动画
  await gsap.to(cubeRef.value, {
    scale: 1.05,
    opacity: 0,
    filter: 'blur(8px)',
    duration: 0.4,
    ease: 'power2.in',
  })
}

onMounted(async () => {
  await nextTick()

  const cube = cubeRef.value
  const cubeFace = cubeFaceRef.value
  const cardContent = cardContentRef.value
  const skip = skipRef.value

  if (!cube || !cubeFace || !cardContent) return

  // 初始状态
  gsap.set(cube, { y: -300, scale: 0.6, opacity: 0 })
  gsap.set(cubeFace, { opacity: 1, scale: 1 })
  gsap.set(cardContent, { opacity: 0 })
  gsap.set(skip, { opacity: 0 })

  tl = gsap.timeline({ paused: false })

  // 1. 方块从上方掉落，弹跳
  tl.to(cube, {
    y: window.innerHeight * 0.08,
    scale: 1,
    opacity: 1,
    duration: 1.0,
    ease: 'bounce.out',
  })

  // 2. 弹跳微调
  tl.to(cube, {
    y: window.innerHeight * 0.05,
    duration: 0.25,
    ease: 'power1.inOut',
  })

  // 3. 方块旋转 + 发光增强
  tl.to(cubeFace, {
    rotation: 45,
    scale: 1.1,
    duration: 0.4,
    ease: 'power2.inOut',
  })

  // 4. 方块扩大成卡片形状
  tl.to(cubeFace, {
    scale: 2.5,
    rotation: 0,
    borderWidth: 0,
    duration: 0.5,
    ease: 'power3.inOut',
  }, '-=0.15')

  // 5. 粒子爆发
  tl.call(() => particleBurst(), null, '-=0.2')

  // 6. 卡片内容淡入
  tl.to(cardContent, {
    opacity: 1,
    duration: 0.4,
    ease: 'power2.out',
  }, '-=0.1')

  // 7. 出现跳过按钮
  tl.to(skip, {
    opacity: 0.5,
    duration: 0.5,
    ease: 'power2.out',
  }, '+=0.3')
})
</script>

<style scoped>
.splash-scene {
  position: fixed;
  inset: 0;
  z-index: var(--z-splash);
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(ellipse at center, rgba(0,255,136,0.03) 0%, transparent 60%);
  pointer-events: all;
}

/* ═══ Particle Burst ═══════════════════════════════════════ */

.particle-burst {
  position: absolute;
  top: 50%;
  left: 50%;
  pointer-events: none;
}

.spark {
  position: absolute;
  width: 3px;
  height: 3px;
  background: var(--color-primary);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--glow-green), 0 0 12px var(--glow-green);
}

/* ═══ Cube Card ════════════════════════════════════════════ */

.cube-card {
  position: relative;
  width: 420px;
  min-height: 520px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* --- Cube Face --- */
.cube-face {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  z-index: 1;
}

.cube-inner {
  width: 100px;
  height: 100px;
  position: relative;
  background: linear-gradient(135deg, #00ff88 0%, #00cc6a 100%);
  border-radius: 12px;
  box-shadow:
    0 0 30px rgba(0, 255, 136, 0.6),
    0 0 80px rgba(0, 255, 136, 0.3),
    0 0 120px rgba(0, 255, 136, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.cube-glow {
  position: absolute;
  inset: -8px;
  border-radius: 18px;
  background: radial-gradient(circle at center, rgba(0,255,136,0.15) 0%, transparent 70%);
  animation: cubePulse 2s ease-in-out infinite;
}

@keyframes cubePulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.cube-lines {
  position: absolute;
  inset: 0;
}

.cube-line {
  position: absolute;
  background: rgba(255, 255, 255, 0.4);
}

.cube-line--top {
  top: 4px; left: 12px; right: 12px;
  height: 1px;
}

.cube-line--bottom {
  bottom: 4px; left: 12px; right: 12px;
  height: 1px;
}

.cube-line--left {
  left: 4px; top: 12px; bottom: 12px;
  width: 1px;
}

.cube-line--right {
  right: 4px; top: 12px; bottom: 12px;
  width: 1px;
}

.cube-corner {
  position: absolute;
  width: 8px;
  height: 8px;
  border-color: rgba(255, 255, 255, 0.7);
  border-style: solid;
}

.cube-corner--tl { top: 3px; left: 3px; border-width: 1.5px 0 0 1.5px; border-radius: 3px 0 0 0; }
.cube-corner--tr { top: 3px; right: 3px; border-width: 1.5px 1.5px 0 0; border-radius: 0 3px 0 0; }
.cube-corner--bl { bottom: 3px; left: 3px; border-width: 0 0 1.5px 1.5px; border-radius: 0 0 0 3px; }
.cube-corner--br { bottom: 3px; right: 3px; border-width: 0 1.5px 1.5px 0; border-radius: 0 0 3px 0; }

/* --- Card Content --- */
.card-content {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 420px;
  padding: var(--space-8);
  background: var(--color-surface);
  border: 1px solid var(--color-border-glow);
  border-radius: var(--radius-2xl);
  box-shadow:
    var(--shadow-xl),
    0 0 30px rgba(0, 255, 136, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(20px);
}

.card-header {
  text-align: center;
  margin-bottom: var(--space-6);
}

.card-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.logo-icon {
  color: var(--color-primary);
  filter: drop-shadow(0 0 8px var(--glow-green));
}

.logo-title {
  font-family: var(--font-display);
  font-size: 1.8rem;
  font-weight: var(--font-black);
  color: var(--color-text);
  letter-spacing: 0.1em;
}

.logo-accent {
  color: var(--color-primary);
  text-shadow: 0 0 12px var(--glow-green);
}

.card-subtitle {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  letter-spacing: 0.2em;
  font-family: var(--font-display);
  font-weight: var(--font-medium);
}

/* ═══ Form Tabs ════════════════════════════════════════════ */

.form-tabs {
  display: flex;
  background: var(--color-bg-alt);
  border-radius: var(--radius-md);
  padding: 3px;
  margin-bottom: var(--space-6);
  border: 1px solid var(--color-border);
}

.form-tab {
  flex: 1;
  padding: var(--space-2) var(--space-4);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  font-family: var(--font-display);
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.form-tab.active {
  background: var(--color-surface);
  color: var(--color-primary);
  box-shadow: 0 0 12px rgba(0, 255, 136, 0.15);
  border: 1px solid var(--color-border-glow);
}

.form-tab:hover:not(.active) {
  color: var(--color-text-secondary);
}

/* ═══ Form Fields ══════════════════════════════════════════ */

.form-field {
  margin-bottom: var(--space-4);
}

.form-field label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-1);
  font-family: var(--font-display);
  letter-spacing: 0.05em;
}

.form-field input,
.form-field select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-family: var(--font-family);
  color: var(--color-text);
  background: var(--color-bg-alt);
  transition: all var(--transition-fast);
  outline: none;
}

.form-field input::placeholder {
  color: var(--color-text-muted);
}

.form-field input:focus,
.form-field select:focus {
  border-color: var(--color-primary-400);
  box-shadow: 0 0 12px rgba(0, 255, 136, 0.1), inset 0 0 0 1px rgba(0, 255, 136, 0.05);
}

.form-field select {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23556680' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 30px;
}

/* ═══ Submit Button ════════════════════════════════════════ */

.btn-submit {
  width: 100%;
  padding: var(--space-3) var(--space-6);
  background: transparent;
  color: var(--color-primary);
  border: 1px solid var(--color-primary-400);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  font-family: var(--font-display);
  letter-spacing: 0.2em;
  cursor: pointer;
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  margin-top: var(--space-6);
  position: relative;
  overflow: hidden;
}

.btn-submit::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--color-primary-50) 0%, transparent 50%);
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.btn-submit:hover:not(:disabled)::before {
  opacity: 1;
}

.btn-submit:hover:not(:disabled) {
  border-color: var(--color-primary);
  box-shadow: 0 0 20px rgba(0, 255, 136, 0.2), 0 0 40px rgba(0, 255, 136, 0.08);
  color: var(--color-text-glow);
}

.btn-submit:disabled {
  border-color: var(--color-border);
  color: var(--color-text-muted);
  cursor: not-allowed;
}

.btn-content {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(0, 255, 136, 0.2);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ═══ Messages ═════════════════════════════════════════════ */

.form-error {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  display: flex;
  align-items: center;
  gap: var(--space-1);
  background: var(--color-danger-bg);
  color: var(--color-danger);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  border: 1px solid var(--color-danger-light);
}

.form-success {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--color-success-bg);
  color: var(--color-success);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  border: 1px solid var(--color-success-light);
}

/* ═══ Feature Strip ════════════════════════════════════════ */

.feature-strip {
  display: flex;
  gap: var(--space-2);
  justify-content: center;
  margin-top: var(--space-6);
  flex-wrap: wrap;
}

.feature-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  font-size: 10px;
  color: var(--color-text-muted);
  font-family: var(--font-display);
  letter-spacing: 0.05em;
}

.feature-chip svg {
  color: var(--color-primary-400);
}

/* ═══ Skip Button ══════════════════════════════════════════ */

.skip-btn {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: var(--space-2) var(--space-4);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  font-family: var(--font-display);
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: all var(--transition-fast);
  z-index: var(--z-splash);
}

.skip-btn:hover {
  border-color: var(--color-primary-400);
  color: var(--color-primary);
  box-shadow: 0 0 8px rgba(0, 255, 136, 0.1);
}
</style>
