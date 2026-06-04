<template>
  <!-- ═══ 背景诗文 ═══ -->
  <BackgroundPoems />

  <!-- ═══ 水墨画布特效 ═══ -->
  <InkWashCanvas />

  <!-- ═══ 未登录 ═══ -->
  <LoginPanel v-if="!user" @logged-in="onLogin" />

  <!-- ═══ 已登录 ═══ -->
  <div v-else class="app-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-brand">
        <div class="brand-icon">墨</div>
        <span class="brand-name">雅集 · 知识库</span>
      </div>

      <nav class="sidebar-nav">
        <button class="nav-item" :class="{ active: activeTab === 'chat' }" @click="activeTab = 'chat'">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          <span>对话</span>
        </button>
        <button class="nav-item" :class="{ active: activeTab === 'docs' }" @click="activeTab = 'docs'">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
          <span>文档</span>
        </button>
        <button class="nav-item" :class="{ active: activeTab === 'kb' }" @click="activeTab = 'kb'">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <span>知识库</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <div class="user-card">
          <div class="user-avatar">{{ user.display_name?.charAt(0) || 'U' }}</div>
          <div class="user-details">
            <div class="user-name">{{ user.display_name }}</div>
            <div class="user-role">
              <span class="dept-badge">{{ deptName(user.department) }}</span>
              <span v-if="user.role === 'admin'" class="role-badge">管理员</span>
            </div>
          </div>
          <button @click="logout" class="logout-btn" title="退出登录">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="main-area">
      <header class="top-bar">
        <h2 class="page-title">{{ pageTitle }}</h2>
        <div class="top-bar-actions">
          <div v-if="kbs.length" class="kb-selector">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <select v-model="activeKbId" class="quick-kb-select">
              <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
            </select>
          </div>
        </div>
      </header>

      <main class="content-area">
        <ChatPanel v-show="activeTab === 'chat'" :key="'chat-' + kbsKey" :kbs="kbs" />
        <DocumentsPanel v-show="activeTab === 'docs'" :key="'docs-' + kbsKey" :kbs="kbs" @refresh-kbs="loadKbs" />
        <KBPanel v-show="activeTab === 'kb'" :key="'kb-' + kbsKey" :user-info="user" @refresh-kbs="loadKbs" />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import LoginPanel from './components/LoginPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import DocumentsPanel from './components/DocumentsPanel.vue'
import KBPanel from './components/KBPanel.vue'
import BackgroundPoems from './components/BackgroundPoems.vue'
import InkWashCanvas from './components/InkWashCanvas.vue'
import { setUser, getUserInfo, kb as kbApi } from './api.js'

const user = ref(null)
const activeTab = ref('chat')
const activeKbId = ref(null)
const kbs = ref([])
const kbsKey = ref(0)

const deptMap = { dev: '开发部', test: '测试部', product: '产品部' }
function deptName(d) { return deptMap[d] || d }

const pageTitle = computed(() => {
  const titles = { chat: '知识库问答', docs: '文档管理', kb: '知识库管理' }
  return titles[activeTab.value] || ''
})

async function onLogin(userData) {
  user.value = userData
  await loadKbs()
}

async function loadKbs() {
  try {
    const data = await kbApi.list()
    kbs.value = data.knowledge_bases || []
    kbsKey.value++
    if (kbs.value.length && !activeKbId.value) {
      activeKbId.value = kbs.value[0].id
    }
  } catch (e) {
    console.error('加载知识库失败:', e)
  }
}

function logout() {
  user.value = null
  kbs.value = []
  setUser(null)
}
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════════
   App Layout — 水墨画风
   ═══════════════════════════════════════════════════════════ */

.app-layout {
  position: relative;
  z-index: 5;
  height: 100vh;
  display: flex;
  background: transparent;
}

/* ═══ Sidebar ═════════════════════════════════════════════ */

.sidebar {
  width: var(--sidebar-width);
  background: rgba(250, 246, 239, 0.92);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  z-index: var(--z-sidebar);
}

.sidebar-brand {
  height: var(--header-height);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-light);
}

.brand-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: var(--color-text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: var(--font-bold);
  flex-shrink: 0;
}

.brand-name {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  white-space: nowrap;
  font-family: var(--font-display);
  letter-spacing: 0.05em;
}

/* ═══ Navigation ══════════════════════════════════════════ */

.sidebar-nav {
  flex: 1;
  padding: var(--space-3) var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
  width: 100%;
}

.nav-item:hover {
  background: var(--color-surface-secondary);
  color: var(--color-text);
  border-color: var(--color-border-light);
}

.nav-item.active {
  background: var(--color-primary-light);
  color: var(--color-primary);
  border-color: var(--color-primary-200);
}

.nav-item.active svg {
  stroke: var(--color-primary);
}

/* ═══ Sidebar Footer ══════════════════════════════════════ */

.sidebar-footer {
  padding: var(--space-3);
  border-top: 1px solid var(--color-border-light);
}

.user-card {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border-radius: var(--radius-md);
  background: var(--color-bg-alt);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  color: var(--color-text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  font-family: var(--font-display);
  flex-shrink: 0;
}

.user-details {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-role {
  display: flex;
  gap: 4px;
  margin-top: 2px;
}

.dept-badge {
  font-size: 10px;
  padding: 1px 5px;
  background: var(--color-primary-light);
  color: var(--color-primary-600);
  border-radius: 3px;
  font-weight: var(--font-medium);
}

.role-badge {
  font-size: 10px;
  padding: 1px 5px;
  background: var(--color-accent-light);
  color: var(--color-accent);
  border-radius: 3px;
  font-weight: var(--font-medium);
}

.logout-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.logout-btn:hover {
  background: var(--color-danger-light);
  color: var(--color-danger);
}

/* ═══ Main Area ═══════════════════════════════════════════ */

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.top-bar {
  height: var(--header-height);
  padding: 0 var(--space-6);
  background: rgba(250, 246, 239, 0.85);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.page-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  font-family: var(--font-display);
  letter-spacing: 0.08em;
}

.top-bar-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.kb-selector {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 4px 10px;
  background: var(--color-bg-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.quick-kb-select {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
  min-width: 120px;
  outline: none;
}

.content-area {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ═══ Responsive ══════════════════════════════════════════ */

@media (max-width: 768px) {
  .sidebar {
    width: 56px;
  }

  .brand-name,
  .nav-item span,
  .user-details,
  .user-card .logout-btn {
    display: none;
  }

  .user-card {
    justify-content: center;
    padding: var(--space-2);
  }

  .nav-item {
    justify-content: center;
    padding: var(--space-3);
  }

  .top-bar {
    padding: 0 var(--space-4);
  }
}
</style>
