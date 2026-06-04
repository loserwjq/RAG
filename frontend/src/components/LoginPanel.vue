<template>
  <div class="login-page">
    <!-- 背景装饰: 水墨笔触 -->
    <div class="login-bg">
      <div class="bg-stroke bg-stroke--1"></div>
      <div class="bg-stroke bg-stroke--2"></div>
      <div class="bg-stroke bg-stroke--3"></div>
    </div>

    <div class="login-inner">
      <!-- 左侧品牌区 -->
      <div class="login-brand">
        <div class="brand-content">
          <div class="brand-seal">墨</div>
          <h1 class="brand-title">雅集</h1>
          <p class="brand-subtitle">知识库问答系统</p>
          <p class="brand-desc">智能文档检索与生成，让企业知识触手可及</p>
          <div class="feature-list">
            <div class="feature-item">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              <span>多格式文档解析 (PDF, PPTX, DOCX)</span>
            </div>
            <div class="feature-item">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              <span>高精度混合检索 (向量 + 关键词)</span>
            </div>
            <div class="feature-item">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              <span>多轮对话与上下文记忆</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧表单区 -->
      <div class="login-form-area">
        <div class="login-card">
          <div class="form-tabs">
            <button
              class="form-tab"
              :class="{ active: !isRegister }"
              @click="isRegister = false; loginError = ''"
            >登录</button>
            <button
              class="form-tab"
              :class="{ active: isRegister }"
              @click="isRegister = true; regError = ''"
            >注册</button>
          </div>

          <!-- 登录表单 -->
          <form v-if="!isRegister" @submit.prevent="login" class="login-form">
            <div class="form-field">
              <label for="login-user">用户名</label>
              <input
                id="login-user"
                v-model="loginForm.username"
                type="text"
                placeholder="请输入用户名"
                required
                autofocus
              />
            </div>
            <div class="form-field">
              <label for="login-pass">密码</label>
              <input
                id="login-pass"
                v-model="loginForm.password"
                type="password"
                placeholder="请输入密码"
                required
              />
            </div>
            <button type="submit" class="btn-submit" :disabled="loginLoading">
              <span v-if="loginLoading" class="spinner"></span>
              {{ loginLoading ? '登录中...' : '登 录' }}
            </button>
            <div v-if="loginError" class="form-error">{{ loginError }}</div>
          </form>

          <!-- 注册表单 -->
          <form v-else @submit.prevent="register" class="reg-form">
            <div class="form-field">
              <label for="reg-user">用户名</label>
              <input
                id="reg-user"
                v-model="reg.username"
                type="text"
                placeholder="请输入用户名"
                required
                autofocus
              />
            </div>
            <div class="form-field">
              <label for="reg-pass">密码</label>
              <input
                id="reg-pass"
                v-model="reg.password"
                type="password"
                placeholder="请输入密码"
                required
              />
            </div>
            <div class="form-field">
              <label for="reg-name">显示名称</label>
              <input
                id="reg-name"
                v-model="reg.displayName"
                type="text"
                placeholder="选填"
              />
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
              {{ regLoading ? '注册中...' : '注册并登录' }}
            </button>
            <div v-if="regError" class="form-error">{{ regError }}</div>
            <div v-if="regOk" class="form-success">注册成功，正在登录...</div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { apiPost, setUser } from '../api.js'

const emit = defineEmits(['logged-in'])

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
    setUser(makeUser(data))
    emit('logged-in', makeUser(data))
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
    setTimeout(() => emit('logged-in', user), 600)
  } catch (e) {
    regError.value = e.message
  } finally {
    regLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  position: relative;
  z-index: 5;
  overflow: hidden;
}

/* ═══ Background — 水墨笔触 ═══════════════════════════════ */

.login-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.bg-stroke {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
}

.bg-stroke--1 {
  width: 700px;
  height: 400px;
  background: radial-gradient(ellipse, rgba(100, 90, 70, 0.07) 0%, transparent 70%);
  top: -120px;
  right: -180px;
  transform: rotate(-15deg);
}

.bg-stroke--2 {
  width: 500px;
  height: 300px;
  background: radial-gradient(ellipse, rgba(140, 120, 90, 0.05) 0%, transparent 70%);
  bottom: -80px;
  left: -100px;
  transform: rotate(10deg);
}

.bg-stroke--3 {
  width: 400px;
  height: 500px;
  background: radial-gradient(ellipse, rgba(196, 58, 49, 0.03) 0%, transparent 70%);
  top: 40%;
  right: 10%;
  transform: rotate(25deg);
}

.login-inner {
  display: flex;
  align-items: center;
  gap: 80px;
  position: relative;
  z-index: 1;
}

/* ═══ Left Brand — 品牌区 ══════════════════════════════════ */

.login-brand {
  flex-shrink: 0;
}

.brand-content {
  width: 360px;
  max-width: 90vw;
  text-align: center;
}

.brand-seal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  border: 2.5px solid var(--color-accent);
  border-radius: var(--radius-md);
  color: var(--color-accent);
  font-family: var(--font-display);
  font-size: 36px;
  font-weight: var(--font-bold);
  margin-bottom: var(--space-6);
  transform: rotate(4deg);
  opacity: 0.85;
}

.brand-title {
  font-family: var(--font-display);
  font-size: 2.8rem;
  font-weight: var(--font-bold);
  color: var(--color-text);
  letter-spacing: 0.3em;
  margin-bottom: var(--space-1);
}

.brand-subtitle {
  font-family: var(--font-display);
  font-size: var(--text-lg);
  color: var(--color-text-secondary);
  letter-spacing: 0.15em;
  margin-bottom: var(--space-6);
}

.brand-desc {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  line-height: var(--leading-relaxed);
  margin-bottom: var(--space-8);
}

.feature-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  text-align: left;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: rgba(250, 246, 239, 0.5);
}

.feature-item svg {
  color: var(--color-primary-400);
  flex-shrink: 0;
}

/* ═══ Right Form — 表单区 ══════════════════════════════════ */

.login-form-area {
  flex-shrink: 0;
}

.login-card {
  width: 400px;
  max-width: 90vw;
  background: rgba(250, 246, 239, 0.95);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: var(--radius-lg);
  padding: var(--space-10);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-lg);
}

.form-tabs {
  display: flex;
  background: var(--color-bg-alt);
  border-radius: var(--radius-md);
  padding: 3px;
  margin-bottom: var(--space-8);
}

.form-tab {
  flex: 1;
  padding: var(--space-2) var(--space-4);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  font-family: var(--font-display);
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.form-tab.active {
  background: var(--color-surface);
  color: var(--color-text);
  box-shadow: var(--shadow-xs);
  border: 1px solid var(--color-border-light);
}

.form-field {
  margin-bottom: var(--space-4);
}

.form-field label {
  display: block;
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-1);
}

.form-field input,
.form-field select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-surface);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  outline: none;
}

.form-field input::placeholder {
  color: var(--color-text-muted);
}

.form-field input:focus,
.form-field select:focus {
  border-color: var(--color-primary-400);
  box-shadow: 0 0 0 3px var(--color-primary-50);
}

.btn-submit {
  width: 100%;
  padding: var(--space-2) var(--space-4);
  background: var(--color-primary);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  font-family: var(--font-display);
  letter-spacing: 0.2em;
  cursor: pointer;
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  margin-top: var(--space-6);
}

.btn-submit:hover:not(:disabled) {
  background: var(--color-primary-hover);
  box-shadow: var(--shadow-md);
}

.btn-submit:disabled {
  background: var(--color-text-muted);
  cursor: not-allowed;
}

.form-error {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
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

/* ═══ Spinner ══════════════════════════════════════════════ */

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ═══ Responsive ════════════════════════════════════════════ */

@media (max-width: 768px) {
  .login-inner {
    flex-direction: column;
    gap: var(--space-8);
    padding: var(--space-4);
  }

  .login-brand {
    text-align: center;
  }

  .brand-content {
    width: auto;
  }

  .brand-seal {
    width: 56px;
    height: 56px;
    font-size: 24px;
    margin-bottom: var(--space-4);
  }

  .brand-title {
    font-size: 2rem;
  }

  .login-brand .feature-list {
    display: none;
  }

  .login-card {
    padding: var(--space-6);
  }
}
</style>
