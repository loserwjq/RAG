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
      <div class="empty-icon-glow">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.5">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
      </div>
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
        :ref="el => setCardRef(kb.id, el)"
        @mousemove="e => onCardMouseMove(kb.id, e)"
        @mouseenter="e => onCardMouseEnter(kb.id, e)"
        @mouseleave="e => onCardMouseLeave(kb.id, e)"
        @click="e => onCardClick(kb.id, e)"
      >
        <!-- 卡片头部 -->
        <div class="kb-card-header" @click="expandedKb = expandedKb === kb.id ? null : kb.id">
          <div class="kb-card-left">
            <div class="kb-icon" :ref="el => setIconRef(kb.id, el)">
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

        <!-- 光晕 overlay -->
        <div class="card-glow-overlay" :ref="el => setGlowRef(kb.id, el)"></div>

        <!-- 涟漪容器 -->
        <div class="ripple-container" :ref="el => setRippleRef(kb.id, el)"></div>
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
import { ref, reactive, onMounted, onUnmounted, nextTick, watch } from 'vue'
import gsap from 'gsap'
import { kb as kbApi, users as usersApi } from '../api.js'

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

// ── 交互引用 ──
const cardRefs = {}
const iconRefs = {}
const glowRefs = {}
const rippleRefs = {}
const floatTweens = {}
const idleFloatTimers = {}

function setCardRef(id, el) { if (el) cardRefs[id] = el }
function setIconRef(id, el) { if (el) iconRefs[id] = el }
function setGlowRef(id, el) { if (el) glowRefs[id] = el }
function setRippleRef(id, el) { if (el) rippleRefs[id] = el }

const deptMap = { dev: '开发部', test: '测试部', product: '产品部' }
function deptName(d) { return deptMap[d] || d }

// ── 数据加载 ──
async function loadKbs() {
  loading.value = true
  try {
    const data = await kbApi.list()
    kbs.value = (data.knowledge_bases || []).map(kb => ({
      ...kb,
      _members: kb.members || [],
    }))
    await nextTick()
    startIdleFloats()
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

// ── 新建表单动画 ──
watch(showCreate, async (val) => {
  await nextTick()
  const formEl = document.querySelector('.create-card')
  if (!formEl) return
  if (val) {
    gsap.fromTo(formEl,
      { y: -30, opacity: 0, scale: 0.95, filter: 'blur(4px)' },
      { y: 0, opacity: 1, scale: 1, filter: 'blur(0px)', duration: 0.35, ease: 'back.out(1.4)' }
    )
  } else {
    gsap.to(formEl, { y: -15, opacity: 0, scale: 0.95, duration: 0.2, ease: 'power2.in' })
  }
})

onUnmounted(() => {
  // 清理所有 GSAP 动画
  Object.values(floatTweens).forEach(t => t?.kill())
  Object.values(idleFloatTimers).forEach(t => clearTimeout(t))
})

// ── ═══════════════════════════════════════════════════════
//   GSAP 交互效果
// ═══════════════════════════════════════════════════════════

/* --- 空闲浮动动画 --- */
function startIdleFloats() {
  kbs.value.forEach((kb, i) => {
    const card = cardRefs[kb.id]
    if (!card) return
    // 先清除旧动画
    floatTweens[kb.id]?.kill()
    // 轻微浮动
    floatTweens[kb.id] = gsap.to(card, {
      y: 'random(-3, 3)',
      x: 'random(-2, 2)',
      duration: 'random(2.5, 4)',
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut',
      delay: i * 0.08,
    })
  })
}

/* --- 鼠标进入卡片 --- */
function onCardMouseEnter(kbId, e) {
  const card = cardRefs[kbId]
  const icon = iconRefs[kbId]
  const glow = glowRefs[kbId]
  if (!card) return

  // 停止浮动
  floatTweens[kbId]?.kill()
  gsap.to(card, { x: 0, y: 0, duration: 0.2 })

  // 卡片发光
  gsap.to(card, {
    borderColor: 'rgba(0,255,136,0.4)',
    boxShadow: '0 0 20px rgba(0,255,136,0.1), 0 0 40px rgba(0,255,136,0.04)',
    scale: 1.015,
    duration: 0.3,
    ease: 'power2.out',
  })

  // 图标旋转 + 发光
  if (icon) {
    gsap.to(icon, {
      rotation: 12,
      scale: 1.1,
      boxShadow: '0 0 16px rgba(0,255,136,0.3)',
      duration: 0.3,
      ease: 'back.out(1.7)',
    })
  }

  // 光晕 overlay
  if (glow) {
    gsap.to(glow, { opacity: 1, duration: 0.3 })
  }
}

/* --- 鼠标在卡片上移动 — 3D 倾斜 + 光晕跟随 --- */
function onCardMouseMove(kbId, e) {
  const card = cardRefs[kbId]
  const glow = glowRefs[kbId]
  if (!card) return

  const rect = card.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  const centerX = rect.width / 2
  const centerY = rect.height / 2

  // 3D 倾斜
  const rotateX = ((y - centerY) / centerY) * -5
  const rotateY = ((x - centerX) / centerX) * 5

  gsap.to(card, {
    rotateX: rotateX,
    rotateY: rotateY,
    duration: 0.4,
    ease: 'power2.out',
  })

  // 光晕跟随鼠标
  if (glow) {
    const percentX = (x / rect.width) * 100
    const percentY = (y / rect.height) * 100
    glow.style.background = `radial-gradient(circle at ${percentX}% ${percentY}%, rgba(0,255,136,0.12) 0%, transparent 50%)`
  }
}

/* --- 鼠标离开卡片 --- */
function onCardMouseLeave(kbId, e) {
  const card = cardRefs[kbId]
  const icon = iconRefs[kbId]
  const glow = glowRefs[kbId]
  if (!card) return

  // 恢复
  gsap.to(card, {
    borderColor: 'var(--color-border)',
    boxShadow: 'none',
    scale: 1,
    rotateX: 0,
    rotateY: 0,
    duration: 0.4,
    ease: 'power2.out',
  })

  if (icon) {
    gsap.to(icon, {
      rotation: 0,
      scale: 1,
      boxShadow: 'none',
      duration: 0.3,
      ease: 'power2.out',
    })
  }

  if (glow) {
    gsap.to(glow, { opacity: 0, duration: 0.4 })
  }

  // 重新开始浮动 (延迟一下)
  idleFloatTimers[kbId] = setTimeout(() => {
    if (cardRefs[kbId]) {
      floatTweens[kbId] = gsap.to(cardRefs[kbId], {
        y: 'random(-3, 3)',
        x: 'random(-2, 2)',
        duration: 'random(3, 5)',
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
      })
    }
  }, 500)
}

/* --- 点击涟漪 --- */
function onCardClick(kbId, e) {
  const ripple = rippleRefs[kbId]
  if (!ripple) return

  const rect = ripple.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top

  const dot = document.createElement('div')
  dot.className = 'ripple-dot'
  dot.style.left = x + 'px'
  dot.style.top = y + 'px'
  ripple.appendChild(dot)

  gsap.fromTo(dot,
    { scale: 0, opacity: 1 },
    {
      scale: 3,
      opacity: 0,
      duration: 0.6,
      ease: 'power2.out',
      onComplete: () => dot.remove(),
    }
  )

  // 小粒子爆发
  for (let i = 0; i < 8; i++) {
    const spark = document.createElement('div')
    spark.className = 'ripple-spark'
    spark.style.left = x + 'px'
    spark.style.top = y + 'px'
    ripple.appendChild(spark)

    const angle = (i / 8) * Math.PI * 2
    const dist = 15 + Math.random() * 20

    gsap.fromTo(spark,
      { x: 0, y: 0, scale: 1, opacity: 0.8 },
      {
        x: Math.cos(angle) * dist,
        y: Math.sin(angle) * dist,
        scale: 0,
        opacity: 0,
        duration: 0.4 + Math.random() * 0.3,
        ease: 'power2.out',
        onComplete: () => spark.remove(),
      }
    )
  }
}

// ── KB 操作 ──
async function createKb() {
  creating.value = true
  error.value = ''
  try {
    const result = await kbApi.create(form.name, form.department, form.description)
    showCreate.value = false
    form.name = ''
    form.description = ''
    await loadKbs()
    emit('refresh-kbs')

    // 庆祝动画 — 找到新卡片并播放入场特效
    await nextTick()
    const newCard = document.querySelector('.kb-card:first-child')
    if (newCard) {
      // 粒子爆发
      spawnCelebration(newCard)
      // 卡片滑入 + 光晕脉冲
      gsap.fromTo(newCard,
        { y: -60, opacity: 0, scale: 0.9, boxShadow: '0 0 40px rgba(0,255,136,0.5)' },
        {
          y: 0, opacity: 1, scale: 1,
          duration: 0.6,
          ease: 'back.out(1.4)',
          onComplete: () => {
            gsap.to(newCard, {
              boxShadow: '0 0 0px rgba(0,255,136,0)',
              duration: 0.8,
              ease: 'power2.out',
            })
          }
        }
      )
      // 图标脉冲
      const icon = newCard.querySelector('.kb-icon')
      if (icon) {
        gsap.fromTo(icon,
          { scale: 0, rotation: -180 },
          { scale: 1, rotation: 0, duration: 0.5, delay: 0.2, ease: 'back.out(2)' }
        )
      }
    }
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

// ── 庆祝粒子 ──
function spawnCelebration(targetEl) {
  const rect = targetEl.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  const count = 30

  for (let i = 0; i < count; i++) {
    const spark = document.createElement('div')
    spark.style.cssText = `
      position: fixed;
      left: ${cx}px;
      top: ${cy}px;
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: ${i % 3 === 0 ? '#00d4ff' : '#00ff88'};
      box-shadow: 0 0 6px ${i % 3 === 0 ? 'rgba(0,212,255,0.8)' : 'rgba(0,255,136,0.8)'};
      pointer-events: none;
      z-index: 100;
    `
    document.body.appendChild(spark)

    const angle = (i / count) * Math.PI * 2
    const dist = 40 + Math.random() * 120
    const duration = 0.5 + Math.random() * 0.8

    gsap.fromTo(spark,
      { x: 0, y: 0, scale: 1, opacity: 1 },
      {
        x: Math.cos(angle) * dist,
        y: Math.sin(angle) * dist - 30,
        scale: 0,
        opacity: 0,
        duration,
        ease: 'power2.out',
        onComplete: () => spark.remove(),
      }
    )
  }

  // 中心光环
  const ring = document.createElement('div')
  ring.style.cssText = `
    position: fixed;
    left: ${cx}px;
    top: ${cy}px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 2px solid rgba(0,255,136,0.6);
    pointer-events: none;
    z-index: 100;
    transform: translate(-50%, -50%);
  `
  document.body.appendChild(ring)

  gsap.fromTo(ring,
    { width: 10, height: 10, marginLeft: -5, marginTop: -5, opacity: 1 },
    {
      width: 300, height: 300, marginLeft: -150, marginTop: -150,
      opacity: 0, duration: 0.8, ease: 'power2.out',
      onComplete: () => ring.remove(),
    }
  )
}

function confirmDelete(kb) { deleteTarget.value = kb }

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
      kbs.value[idx] = { ...kbs.value[idx], ...data, _members: data.members || [] }
    }
  } catch (e) { /* ignore */ }
}

function ensureForm(kbId) {
  if (!addMemberForm[kbId]) {
    addMemberForm[kbId] = reactive({ userId: null, permission: 'read' })
  }
  return addMemberForm[kbId]
}

function getAddForm(kbId, field) { return ensureForm(kbId)[field] }
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

.panel-toolbar { margin-bottom: var(--space-4); }

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  font-family: var(--font-family);
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
}

.btn--primary {
  background: var(--color-primary-100);
  color: var(--color-primary);
  border-color: var(--color-primary-200);
}

.btn--primary:hover {
  background: var(--color-primary-200);
  box-shadow: 0 0 12px rgba(0, 255, 136, 0.15);
}

.btn--primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn--primary-sm {
  padding: 4px 10px;
  background: var(--color-primary-100);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-200);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: var(--font-family);
  cursor: pointer;
}

.btn--primary-sm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn--danger-sm {
  padding: 4px 10px;
  background: transparent;
  color: var(--color-danger);
  border: 1px solid var(--color-danger-light);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: var(--font-family);
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
  background: transparent;
  border-color: var(--color-border);
  color: var(--color-text-secondary);
}

.btn--secondary:hover {
  border-color: var(--color-border-light);
  color: var(--color-text);
}

.btn--danger {
  background: var(--color-danger);
  color: #fff;
}

.btn--danger:hover:not(:disabled) {
  box-shadow: 0 0 12px rgba(255, 51, 85, 0.3);
}

.btn--danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ═══ Create Card ═════════════════════════════════════════ */

.create-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border-glow);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  margin-bottom: var(--space-4);
  animation: slideDown 0.2s ease-out;
}

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.form-row {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.form-row .form-field { flex: 1; }
.form-field { margin-bottom: var(--space-3); }

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
  font-family: var(--font-family);
  color: var(--color-text);
  background: var(--color-bg-alt);
  outline: none;
  transition: all var(--transition-fast);
}

.form-field input:focus,
.form-field select:focus,
.form-select:focus {
  border-color: var(--color-primary-400);
  box-shadow: 0 0 8px rgba(0, 255, 136, 0.1);
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

.form-error { font-size: var(--text-xs); color: var(--color-danger); }

/* ═══ Loading / Empty ════════════════════════════════════ */

.loading-state { display: flex; flex-direction: column; gap: var(--space-3); }

.skeleton {
  padding: var(--space-4);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.skeleton-line {
  height: 12px;
  background: var(--color-border-light);
  border-radius: 3px;
  animation: shimmer 1.5s ease-in-out infinite;
}

.skeleton-line--title { width: 40%; margin-bottom: 8px; }
.skeleton-line--detail { width: 60%; }

@keyframes shimmer {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.7; }
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

.empty-icon-glow {
  margin-bottom: var(--space-4);
  filter: drop-shadow(0 0 8px rgba(0, 255, 136, 0.2));
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
  position: relative;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: none; /* GSAP handles transitions */
  transform-style: preserve-3d;
  perspective: 800px;
}

.card-glow-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0;
  z-index: 0;
}

.ripple-container {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;
  overflow: hidden;
  border-radius: var(--radius-lg);
}

.ripple-dot {
  position: absolute;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(0,255,136,0.6) 0%, transparent 70%);
  transform: translate(-50%, -50%);
}

.ripple-spark {
  position: absolute;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--color-primary);
  box-shadow: 0 0 4px var(--glow-green);
  transform: translate(-50%, -50%);
}

.kb-card-header {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  background: var(--color-surface);
  transition: background var(--transition-fast);
}

.kb-card-header:hover {
  background: var(--color-surface-hover);
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
  background: var(--color-primary-50);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: none;
}

.kb-card-info { min-width: 0; }

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
  background: var(--color-primary-50);
  color: var(--color-primary);
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
}

.expand-icon {
  color: var(--color-text-muted);
  transition: transform var(--transition-fast);
  flex-shrink: 0;
}

.expand-icon.rotated { transform: rotate(180deg); }

/* ═══ KB Detail ══════════════════════════════════════════ */

.kb-card-detail {
  position: relative;
  z-index: 1;
  border-top: 1px solid var(--color-border);
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

.kb-desc { font-size: var(--text-xs); color: var(--color-text-secondary); }
.kb-ctime { font-size: 10px; color: var(--color-text-muted); }

.divider {
  height: 1px;
  background: var(--color-border);
  margin: var(--space-3) 0;
}

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
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-accent) 100%);
  color: var(--color-text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: var(--font-bold);
  flex-shrink: 0;
}

.member-name { font-weight: var(--font-medium); color: var(--color-text); }
.member-dept { color: var(--color-text-muted); font-size: 10px; }

.perm-tag {
  margin-left: auto;
  font-size: 9px;
  padding: 1px 5px;
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
}

.perm--read { background: var(--color-surface-secondary); color: var(--color-text-muted); }
.perm--write { background: var(--color-warning-light); color: var(--color-warning); }
.perm--admin { background: var(--color-danger-light); color: var(--color-danger); }

.icon-btn--sm {
  width: 22px;
  height: 22px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: transparent;
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

.icon-btn--sm:disabled { opacity: 0.4; cursor: not-allowed; }

.add-member {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

/* ═══ Modal ═══════════════════════════════════════════════ */

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(4, 4, 10, 0.7);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  padding: var(--space-4);
}

.modal-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border-glow);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  width: 400px;
  max-width: 90vw;
  box-shadow: var(--shadow-xl), 0 0 30px rgba(0, 255, 136, 0.05);
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
