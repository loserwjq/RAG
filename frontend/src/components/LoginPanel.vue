<template>
  <!-- LoginPanel is no longer used directly; SplashScreen contains the full login experience.
       This component is kept as a minimal standalone fallback. -->
  <div class="login-page">
    <div class="login-card">
      <div class="card-header">
        <h1 class="logo-title">NEURAL<span class="logo-accent">KB</span></h1>
        <p class="card-subtitle">智能知识库问答系统</p>
      </div>

      <div class="form-tabs">
        <button class="form-tab" :class="{ active: !isRegister }" @click="isRegister = false; loginError = ''">登录</button>
        <button class="form-tab" :class="{ active: isRegister }" @click="isRegister = true; regError = ''">注册</button>
      </div>

      <form v-if="!isRegister" @submit.prevent="login" class="login-form">
        <div class="form-field">
          <label for="login-user">用户名</label>
          <input id="login-user" v-model="loginForm.username" type="text" placeholder="请输入用户名" required autofocus />
        </div>
        <div class="form-field">
          <label for="login-pass">密码</label>
          <input id="login-pass" v-model="loginForm.password" type="password" placeholder="请输入密码" required />
        </div>
        <button type="submit" class="btn-submit" :disabled="loginLoading">
          <span v-if="loginLoading" class="spinner"></span>
          {{ loginLoading ? '登录中...' : '登 录' }}
        </button>
        <div v-if="loginError" class="form-error">{{ loginError }}</div>
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
          {{ regLoading ? '注册中...' : '注册并登录' }}
        </button>
        <div v-if="regError" class="form-error">{{ regError }}</div>
        <div v-if="regOk" class="form-success">注册成功，正在登录...</div>
      </form>
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
    const data = await apiPost('/api/auth/login', { username: loginForm.value.username, password: loginForm.value.password })
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
}

.login-card {
  width: 400px;
  max-width: 90vw;
  background: var(--color-surface);
  border: 1px solid var(--color-border-glow);
  border-radius: var(--radius-2xl);
  padding: var(--space-10);
  box-shadow: var(--shadow-xl), 0 0 30px rgba(0, 255, 136, 0.05);
}

.card-header { text-align: center; margin-bottom: var(--space-6); }

.logo-title {
  font-family: var(--font-display);
  font-size: 1.8rem;
  font-weight: var(--font-black);
  color: var(--color-text);
  letter-spacing: 0.1em;
  margin-bottom: var(--space-1);
}

.logo-accent { color: var(--color-primary); text-shadow: 0 0 12px var(--glow-green); }

.card-subtitle {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  letter-spacing: 0.2em;
  font-family: var(--font-display);
}

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

.form-field { margin-bottom: var(--space-4); }

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
  font-family: var(--font-family);
  color: var(--color-text);
  background: var(--color-bg-alt);
  transition: all var(--transition-fast);
  outline: none;
}

.form-field input::placeholder { color: var(--color-text-muted); }
.form-field input:focus,
.form-field select:focus {
  border-color: var(--color-primary-400);
  box-shadow: 0 0 12px rgba(0, 255, 136, 0.1);
}

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
}

.btn-submit:hover:not(:disabled) {
  border-color: var(--color-primary);
  box-shadow: 0 0 20px rgba(0, 255, 136, 0.2);
}
.btn-submit:disabled { border-color: var(--color-border); color: var(--color-text-muted); cursor: not-allowed; }

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(0, 255, 136, 0.2);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.form-error { margin-top: var(--space-3); padding: var(--space-2) var(--space-3); background: var(--color-danger-bg); color: var(--color-danger); border-radius: var(--radius-sm); font-size: var(--text-xs); border: 1px solid var(--color-danger-light); }
.form-success { margin-top: var(--space-3); padding: var(--space-2) var(--space-3); background: var(--color-success-bg); color: var(--color-success); border-radius: var(--radius-sm); font-size: var(--text-xs); border: 1px solid var(--color-success-light); }
</style>
