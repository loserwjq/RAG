<template>
  <div class="kb-panel">
    <!-- 新建知识库按钮 -->
    <div class="panel-toolbar">
      <button @click="showCreate = !showCreate" class="btn btn--primary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ showCreate ? '取消' : '新建知识库' }}
      </button>
    </div>

    <!-- 新建表单 -->
    <div v-if="showCreate" class="create-card">
      <form @submit.prevent="createKb" class="create-form">
        <div class="form-row">
          <div class="form-field">
            <label for="kb-name">知识库名称</label>
            <input id="kb-name" v-model="form.name" type="text" placeholder="例如：开发部文档库" required />
          </div>
          <div class="form-field">
            <label for="kb-dept">归属部门</label>
            <select id="kb-dept" v-model="form.department">
              <option value="dev">开发部</option>
              <option value="test">测试部</option>
              <option value="product">产品部</option>
            </select>
          </div>
        </div>
        <div class="form-field">
          <label for="kb-desc">描述</label>
          <input id="kb-desc" v-model="form.description" type="text" placeholder="选填，简要描述知识库用途" />
        </div>
        <div class="create-actions">
          <button type="submit" class="btn btn--primary" :disabled="creating">
            {{ creating ? '创建中...' : '创建知识库' }}
          </button>
          <span v-if="error" class="form-error">{{ error }}</span>
        </div>
      </form>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <div class="skeleton" v-for="i in 3" :key="i">
        <div class="skeleton-line skeleton-line--title"></div>
        <div class="skeleton-line skeleton-line--detail"></div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="kbs.length === 0" class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
      </svg>
      <p>暂无知识库</p>
      <p class="hint">点击「新建知识库」创建第一个知识库</p>
    </div>

    <!-- 知识库卡片列表 -->
    <div v-else class="kb-grid">
      <div
        v-for="kb in kbs"
        :key="kb.id"
        class="kb-card"
        :class="{ expanded: expandedKb === kb.id }"
      >
        <!-- 卡片头部 -->
        <div class="kb-card-header" @click="expandedKb = expandedKb === kb.id ? null : kb.id">
          <div class="kb-card-left">
            <div class="kb-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <div class="kb-card-info">
              <h3 class="kb-name">{{ kb.name }}</h3>
              <span class="kb-collection">{{ kb.collection_name }}</span>
            </div>
          </div>
          <div class="kb-card-meta">
            <span class="meta-badge" title="文档数">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
              {{ kb.doc_count || 0 }}
            </span>
            <span class="meta-badge" title="成员数">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
              {{ kb.member_count || 0 }}
            </span>
            <span class="dept-tag">{{ deptName(kb.department) }}</span>
          </div>
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            class="expand-icon"
            :class="{ rotated: expandedKb === kb.id }"
          >
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>

        <!-- 展开详情 -->
        <div v-if="expandedKb === kb.id" class="kb-card-detail">
          <!-- 描述和操作 -->
          <div class="detail-section">
            <div class="detail-info">
              <span v-if="kb.description" class="kb-desc">{{ kb.description }}</span>
              <span class="kb-ctime">创建于 {{ kb.created_at?.substring(0, 10) }}</span>
            </div>
            <button
              @click="confirmDelete(kb)"
              class="btn btn--danger-sm"
              :disabled="deleting === kb.id"
            >{{ deleting === kb.id ? '删除中...' : '删除知识库' }}</button>
          </div>

          <div class="divider"></div>

          <!-- 成员管理 -->
          <div class="members-section">
            <h4>成员管理</h4>
            <div class="member-list">
              <div v-for="m in kb._members" :key="m.id" class="member-item">
                <div class="member-avatar">{{ (m.display_name || m.username).charAt(0) }}</div>
                <span class="member-name">{{ m.display_name || m.username }}</span>
                <span class="member-dept">{{ deptName(m.department) }}</span>
                <span class="perm-tag" :class="'perm--' + m.permission">{{ m.permission }}</span>
                <button
                  v-if="m.id !== kb.owner_id && (userInfo.role === 'admin' || kb.owner_id === userInfo.user_id)"
                  @click="removeMember(kb, m.id)"
                  class="icon-btn icon-btn--sm"
                  :disabled="removingMember === m.id"
                  title="移除成员"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>

            <!-- 添加成员 -->
            <div class="add-member">
              <select
                :value="getAddForm(kb.id, 'userId')"
                @change="e => setAddForm(kb.id, 'userId', e.target.value ? Number(e.target.value) : null)"
                class="form-select form-select--sm"
              >
                <option :value="null">选择用户...</option>
                <option
                  v-for="u in allUsers"
                  :key="u.id"
                  :value="u.id"
                  :disabled="kb._members?.some(m => m.id === u.id)"
                >{{ u.display_name || u.username }} ({{ deptName(u.department) }})</option>
              </select>
              <select
                :value="getAddForm(kb.id, 'permission')"
                @change="e => setAddForm(kb.id, 'permission', e.target.value)"
                class="form-select form-select--sm"
              >
                <option value="read">只读</option>
                <option value="write">可写</option>
                <option value="admin">管理</option>
              </select>
              <button
                @click="addMember(kb)"
                :disabled="!getAddForm(kb.id, 'userId') || addingMember === kb.id"
                class="btn btn--primary-sm"
              >{{ addingMember === kb.id ? '...' : '添加' }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 删除确认 Modal -->
    <Teleport to="body">
      <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
        <div class="modal-card">
          <div class="modal-icon modal-icon--danger">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
          </div>
          <h3 class="modal-title">确认删除知识库</h3>
          <p class="modal-desc">确定要删除「{{ deleteTarget.name }}」吗？此操作将同时删除所有文档和向量数据，不可恢复！</p>
          <div class="modal-actions">
            <button @click="deleteTarget = null" class="btn btn--secondary">取消</button>
            <button @click="doDelete" class="btn btn--danger" :disabled="deleting === deleteTarget.id">
              {{ deleting === deleteTarget.id ? '删除中...' : '确认删除' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { kb as kbApi, users as usersApi, getUserInfo } from '../api.js'

const props = defineProps({ userInfo: Object })
const emit = defineEmits(['refresh-kbs'])

const kbs = ref([])
const loading = ref(true)
const showCreate = ref(false)
const creating = ref(false)
const error = ref('')
const expandedKb = ref(null)
const deleting = ref(null)
const deleteTarget = ref(null)
const allUsers = ref([])
const addingMember = ref(null)
const removingMember = ref(null)

const form = reactive({ name: '', department: 'dev', description: '' })
const addMemberForm = reactive({})

const deptMap = { dev: '开发部', test: '测试部', product: '产品部' }
function deptName(d) { return deptMap[d] || d }

async function loadKbs() {
  loading.value = true
  try {
    const data = await kbApi.list()
    kbs.value = (data.knowledge_bases || []).map(kb => ({
      ...kb,
      _members: kb.members || [],
    }))
  } catch (e) {
    error.value = '加载知识库失败: ' + e.message
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  try {
    const data = await usersApi.list()
    allUsers.value = data.users || []
  } catch (e) { /* ignore */ }
}

onMounted(() => {
  loadKbs()
  loadUsers()
})

async function createKb() {
  creating.value = true
  error.value = ''
  try {
    await kbApi.create(form.name, form.department, form.description)
    showCreate.value = false
    form.name = ''
    form.description = ''
    await loadKbs()
    emit('refresh-kbs')
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

function confirmDelete(kb) {
  deleteTarget.value = kb
}

async function doDelete() {
  const kb = deleteTarget.value
  if (!kb) return
  deleting.value = kb.id
  try {
    await kbApi.delete(kb.id)
    deleteTarget.value = null
    expandedKb.value = null
    await loadKbs()
    emit('refresh-kbs')
  } catch (e) {
    error.value = '删除失败: ' + e.message
  } finally {
    deleting.value = null
  }
}

async function addMember(kb) {
  const f = addMemberForm[kb.id]
  if (!f?.userId) return
  addingMember.value = kb.id
  try {
    await kbApi.addMember(kb.id, f.userId, f.permission || 'read')
    f.userId = null
    f.permission = 'read'
    await loadKbDetail(kb.id)
  } catch (e) {
    error.value = '添加成员失败: ' + e.message
  } finally {
    addingMember.value = null
  }
}

async function removeMember(kb, userId) {
  removingMember.value = userId
  try {
    await kbApi.removeMember(kb.id, userId)
    await loadKbDetail(kb.id)
  } catch (e) {
    error.value = '移除成员失败: ' + e.message
  } finally {
    removingMember.value = null
  }
}

async function loadKbDetail(kbId) {
  try {
    const data = await kbApi.get(kbId)
    const idx = kbs.value.findIndex(k => k.id === kbId)
    if (idx >= 0) {
      kbs.value[idx] = {
        ...kbs.value[idx],
        ...data,
        _members: data.members || [],
      }
    }
  } catch (e) { /* ignore */ }
}

function ensureForm(kbId) {
  if (!addMemberForm[kbId]) {
    addMemberForm[kbId] = reactive({ userId: null, permission: 'read' })
  }
  return addMemberForm[kbId]
}

function getAddForm(kbId, field) {
  return ensureForm(kbId)[field]
}

function setAddForm(kbId, field, value) {
  const f = ensureForm(kbId)
  f[field] = value
}
</script>

<style scoped>
.kb-panel {
  height: 100%;
  overflow-y: auto;
  padding: var(--space-4) var(--space-6);
  max-width: var(--content-max-width);
  margin: 0 auto;
  width: 100%;
}

/* ═══ Toolbar ═════════════════════════════════════════════ */

.panel-toolbar {
  margin-bottom: var(--space-4);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
}

.btn--primary {
  background: var(--color-primary);
  color: #fff;
}

.btn--primary:hover {
  background: var(--color-primary-hover);
}

.btn--primary:disabled {
  background: var(--color-text-muted);
  cursor: not-allowed;
}

.btn--primary-sm {
  padding: 4px 10px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: inherit;
  cursor: pointer;
}

.btn--primary-sm:disabled {
  background: var(--color-text-muted);
  cursor: not-allowed;
}

.btn--danger-sm {
  padding: 4px 10px;
  background: var(--color-surface);
  color: var(--color-danger);
  border: 1px solid var(--color-danger-light);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn--danger-sm:hover:not(:disabled) {
  background: var(--color-danger-bg);
}

.btn--danger-sm:disabled {
  opacity: 0.5;
}

.btn--secondary {
  background: var(--color-surface);
  border-color: var(--color-border);
  color: var(--color-text-secondary);
}

.btn--secondary:hover {
  background: var(--color-bg-alt);
}

.btn--danger {
  background: var(--color-danger);
  color: #fff;
}

.btn--danger:hover:not(:disabled) {
  background: var(--color-seal-red, #a03028);
}

.btn--danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ═══ Create Card ═════════════════════════════════════════ */

.create-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  margin-bottom: var(--space-4);
  animation: slideDown 0.2s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.form-row {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.form-row .form-field {
  flex: 1;
}

.form-field {
  margin-bottom: var(--space-3);
}

.form-field label {
  display: block;
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-1);
}

.form-field input,
.form-field select,
.form-select {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.form-field input:focus,
.form-field select:focus,
.form-select:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-100);
}

.form-select--sm {
  padding: 4px 6px;
  font-size: var(--text-xs);
  border-radius: var(--radius-sm);
}

.create-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.form-error {
  font-size: var(--text-xs);
  color: var(--color-danger);
}

/* ═══ Loading / Empty ════════════════════════════════════ */

.loading-state {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.skeleton {
  padding: var(--space-4);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
}

.skeleton-line {
  height: 12px;
  background: var(--color-border);
  border-radius: 3px;
  animation: shimmer 1.5s ease-in-out infinite;
}

.skeleton-line--title {
  width: 40%;
  margin-bottom: 8px;
}

.skeleton-line--detail {
  width: 60%;
}

@keyframes shimmer {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-12);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.empty-state svg {
  margin-bottom: var(--space-3);
}

.empty-state .hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

/* ═══ KB Card Grid ═══════════════════════════════════════ */

.kb-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.kb-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: all var(--transition-fast);
}

.kb-card:hover {
  box-shadow: var(--shadow-sm);
}

.kb-card-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.kb-card-header:hover {
  background: var(--color-bg-alt);
}

.kb-card-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex: 1;
  min-width: 0;
}

.kb-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--color-primary-light);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kb-card-info {
  min-width: 0;
}

.kb-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-collection {
  font-size: 10px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.kb-card-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.meta-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.dept-tag {
  font-size: 10px;
  padding: 1px 6px;
  background: var(--color-primary-light);
  color: var(--color-primary-600);
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
}

.expand-icon {
  color: var(--color-text-muted);
  transition: transform var(--transition-fast);
  flex-shrink: 0;
}

.expand-icon.rotated {
  transform: rotate(180deg);
}

/* ═══ KB Detail ══════════════════════════════════════════ */

.kb-card-detail {
  border-top: 1px solid var(--color-border-light);
  background: var(--color-bg-alt);
  padding: var(--space-4);
  animation: slideDown 0.2s ease-out;
}

.detail-section {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.detail-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kb-desc {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.kb-ctime {
  font-size: 10px;
  color: var(--color-text-muted);
}

.divider {
  height: 1px;
  background: var(--color-border-light);
  margin: var(--space-3) 0;
}

/* Members */
.members-section h4 {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
}

.member-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: var(--space-3);
}

.member-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
}

.member-avatar {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-full);
  background: var(--color-primary-light);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: var(--font-semibold);
  flex-shrink: 0;
}

.member-name {
  font-weight: var(--font-medium);
  color: var(--color-text);
}

.member-dept {
  color: var(--color-text-muted);
  font-size: 10px;
}

.perm-tag {
  margin-left: auto;
  font-size: 9px;
  padding: 1px 5px;
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
}

.perm--read { background: var(--color-surface-secondary); color: var(--color-text-muted); }
.perm--write { background: var(--color-warning-light); color: #6b5010; }
.perm--admin { background: var(--color-danger-light); color: var(--color-danger); }

.icon-btn--sm {
  width: 22px;
  height: 22px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}

.icon-btn--sm:hover:not(:disabled) {
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.icon-btn--sm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.add-member {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

/* ═══ Modal ═══════════════════════════════════════════════ */

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(26, 24, 20, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  padding: var(--space-4);
}

.modal-card {
  background: var(--color-surface);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  width: 400px;
  max-width: 90vw;
  box-shadow: var(--shadow-xl);
  text-align: center;
}

.modal-icon--danger {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--color-danger-bg);
  color: var(--color-danger);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto var(--space-4);
}

.modal-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.modal-desc {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: var(--leading-relaxed);
  margin-bottom: var(--space-6);
}

.modal-actions {
  display: flex;
  justify-content: center;
  gap: var(--space-3);
}
</style>
