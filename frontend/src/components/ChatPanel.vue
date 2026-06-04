<template>
  <div class="chat-layout">
    <!-- 侧边栏：对话列表 -->
    <aside class="chat-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <button @click="newConversation" class="new-conv-btn" title="新对话">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span v-if="!sidebarCollapsed">新对话</span>
        </button>
        <button @click="sidebarCollapsed = !sidebarCollapsed" class="toggle-sidebar" :title="sidebarCollapsed ? '展开' : '收起'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline :points="sidebarCollapsed ? '9 18 15 12 9 6' : '15 18 9 12 15 6'"/></svg>
        </button>
      </div>

      <div v-if="!sidebarCollapsed" class="conv-list">
        <div v-if="conversations.length === 0" class="no-convs">
          <p>暂无对话</p>
          <p class="hint">点击上方按钮开始</p>
        </div>
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: conv.id === activeConvId }"
          @click="switchConversation(conv.id)"
        >
          <div class="conv-info">
            <span class="conv-title">{{ conv.title }}</span>
            <span class="conv-meta">{{ conv.message_count }} 条 · {{ formatDate(conv.updated_at) }}</span>
          </div>
          <button
            @click.stop="confirmDelete(conv)"
            class="conv-delete"
            title="删除对话"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
          </button>
        </div>
        <div v-if="loadingConvs" class="loading-convs">加载中...</div>
      </div>
    </aside>

    <!-- 主对话区 -->
    <div class="chat-main">
      <div class="messages" ref="messagesRef">
        <div v-if="messages.length === 0 && !loading" class="empty-state">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.4">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
          </div>
          <p>开始新的对话</p>
          <div class="suggestions">
            <button
              v-for="q in suggestedQuestions"
              :key="q"
              @click="sendSuggested(q)"
              class="suggestion-btn"
            >{{ q }}</button>
          </div>
        </div>
        <MessageBubble
          v-for="(msg, i) in messages"
          :key="i"
          :message="msg"
        />
        <div v-if="loading" class="typing-hint">助手正在思考...</div>
      </div>

      <div class="input-area">
        <div class="input-row">
          <textarea
            v-model="input"
            @keydown="handleKeydown"
            placeholder="输入问题... (Enter 发送, Shift+Enter 换行)"
            :disabled="loading"
            rows="1"
            ref="inputRef"
          ></textarea>
          <button
            @click="send"
            :disabled="!input.trim() || loading"
            class="send-btn"
            title="发送"
          >
            <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
            <span v-else class="send-spinner"></span>
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认 -->
    <div v-if="deleteTarget" class="modal-mask" @click.self="deleteTarget = null">
      <div class="modal">
        <p class="modal-title">确认删除</p>
        <p>确定要删除对话「{{ deleteTarget.title }}」吗？此操作不可恢复。</p>
        <div class="modal-actions">
          <button @click="deleteTarget = null">取消</button>
          <button @click="doDelete" class="btn-danger" :disabled="deletingConv">
            {{ deletingConv ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted } from 'vue'
import MessageBubble from './MessageBubble.vue'
import { chatStream, conversations as convApi } from '../api.js'

const props = defineProps({ kbs: Array })

const conversations = ref([])
const activeConvId = ref(null)
const messages = ref([])
const input = ref('')
const loading = ref(false)
const messagesRef = ref(null)
const inputRef = ref(null)
const sidebarCollapsed = ref(false)
const loadingConvs = ref(false)
const deleteTarget = ref(null)
const deletingConv = ref(false)

const suggestedQuestions = [
  '知识库中有哪些文档类型？',
  '如何上传文档到知识库？',
  '这个系统支持哪些功能？',
]

onMounted(() => {
  loadConversations()
})

async function loadConversations() {
  loadingConvs.value = true
  try {
    const data = await convApi.list()
    conversations.value = data.conversations || []
    if (conversations.value.length > 0 && !activeConvId.value) {
      await switchConversation(conversations.value[0].id)
    }
  } catch (e) {
    console.error('加载对话列表失败:', e)
  } finally {
    loadingConvs.value = false
  }
}

async function switchConversation(convId) {
  if (convId === activeConvId.value) return
  activeConvId.value = convId
  messages.value = []
  try {
    const data = await convApi.get(convId)
    messages.value = (data.messages || []).map(normalizeMessage)
    scrollToBottom()
  } catch (e) {
    console.error('加载消息失败:', e)
  }
}

async function newConversation() {
  try {
    const data = await convApi.create()
    conversations.value.unshift({
      id: data.id,
      title: '新对话',
      message_count: 0,
      updated_at: new Date().toISOString(),
    })
    activeConvId.value = data.id
    messages.value = []
  } catch (e) {
    console.error('创建对话失败:', e)
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function sendSuggested(q) {
  input.value = q
  send()
}

function normalizeMessage(msg) {
  if (!msg) return msg
  if (typeof msg.sources === 'string') {
    try {
      return { ...msg, sources: JSON.parse(msg.sources || '[]') }
    } catch {
      return { ...msg, sources: [] }
    }
  }
  return {
    ...msg,
    sources: Array.isArray(msg.sources) ? msg.sources : [],
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return

  if (!activeConvId.value) {
    await newConversation()
  }

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  scrollToBottom()

  const assistantMsg = reactive({ role: 'assistant', content: '', sources: [] })
  messages.value.push(assistantMsg)
  loading.value = true

  try {
    const stream = chatStream(
      [{ role: 'user', content: text }],
      null,
      10,
      activeConvId.value,
    )

    for await (const payload of stream) {
      if (payload.type === 'token') {
        assistantMsg.content += payload.content
        scrollToBottom()
      } else if (payload.type === 'sources') {
        assistantMsg.sources = payload.sources
      } else if (payload.type === 'done') {
        if (payload.conversation_id && payload.conversation_id !== activeConvId.value) {
          activeConvId.value = payload.conversation_id
        }
        refreshConvList()
      }
    }
  } catch (e) {
    assistantMsg.content += `\n[请求失败: ${e.message}]`
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

async function refreshConvList() {
  try {
    const data = await convApi.list()
    conversations.value = data.conversations || []
  } catch (e) { /* ignore */ }
}

function confirmDelete(conv) {
  deleteTarget.value = conv
}

async function doDelete() {
  const conv = deleteTarget.value
  if (!conv) return
  deletingConv.value = true
  try {
    await convApi.delete(conv.id)
    conversations.value = conversations.value.filter(c => c.id !== conv.id)
    if (activeConvId.value === conv.id) {
      activeConvId.value = null
      messages.value = []
      if (conversations.value.length > 0) {
        await switchConversation(conversations.value[0].id)
      }
    }
    deleteTarget.value = null
  } catch (e) {
    alert('删除失败: ' + e.message)
  } finally {
    deletingConv.value = false
  }
}

function formatDate(t) {
  if (!t) return ''
  const d = new Date(t)
  const now = new Date()
  const diff = now - d
  if (diff < 86400000) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.chat-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* ── 侧边栏 ───────────────────────────────────────── */

.chat-sidebar {
  width: 260px;
  background: rgba(250, 246, 239, 0.7);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  transition: width 0.2s;
  flex-shrink: 0;
}

.chat-sidebar.collapsed {
  width: 48px;
}

.sidebar-header {
  display: flex;
  gap: 4px;
  padding: 10px;
  border-bottom: 1px solid var(--color-border-light);
}

.new-conv-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: var(--color-text-inverse);
  font-size: var(--text-sm);
  font-family: var(--font-display);
  letter-spacing: 0.05em;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  transition: all var(--transition-fast);
}

.new-conv-btn:hover {
  background: var(--color-primary-hover);
}

.toggle-sidebar {
  padding: 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}

.toggle-sidebar:hover {
  color: var(--color-text);
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.no-convs {
  text-align: center;
  padding: 30px 16px;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.no-convs .hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: 4px;
  opacity: 0.7;
}

.conv-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
}

.conv-item:hover {
  background: var(--color-surface-secondary);
}

.conv-item.active {
  background: var(--color-primary-light);
  border-color: var(--color-primary-200);
}

.conv-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conv-title {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-meta {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.conv-delete {
  opacity: 0;
  padding: 4px;
  border: none;
  background: none;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  transition: all var(--transition-fast);
}

.conv-item:hover .conv-delete {
  opacity: 1;
}

.conv-delete:hover {
  color: var(--color-danger);
  background: var(--color-danger-light);
}

.loading-convs {
  text-align: center;
  padding: 16px;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

/* ── 主对话区 ─────────────────────────────────────── */

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-muted);
}

.empty-state p {
  font-size: var(--text-base);
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
}

.suggestion-btn {
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  font-size: var(--text-sm);
  font-family: inherit;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.suggestion-btn:hover {
  border-color: var(--color-primary-300);
  color: var(--color-primary);
  background: var(--color-primary-light);
}

.typing-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  padding-left: 4px;
}

/* ── 输入区 ───────────────────────────────────────── */

.input-area {
  padding: 12px 24px 16px;
  background: rgba(250, 246, 239, 0.9);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-top: 1px solid var(--color-border);
}

.input-row {
  display: flex;
  gap: 8px;
}

.input-row textarea {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  resize: none;
  outline: none;
  font-family: inherit;
  line-height: var(--leading-normal);
  min-height: 40px;
  max-height: 120px;
  background: var(--color-surface);
  color: var(--color-text);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.input-row textarea::placeholder {
  color: var(--color-text-muted);
}

.input-row textarea:focus {
  border-color: var(--color-primary-400);
  box-shadow: 0 0 0 2px var(--color-primary-50);
}

.send-btn {
  padding: 8px 14px;
  background: var(--color-primary);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  cursor: pointer;
  white-space: nowrap;
  display: flex;
  align-items: center;
  transition: all var(--transition-fast);
}

.send-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.send-btn:disabled {
  background: var(--color-border);
  cursor: not-allowed;
}

.send-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── 弹窗 ─────────────────────────────────────────── */

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  padding: 24px;
  width: 380px;
  max-width: 90vw;
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-xl);
}

.modal-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  margin-bottom: 8px;
}

.modal p {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.modal-actions button {
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.modal-actions button:hover {
  background: var(--color-bg-alt);
}

.modal-actions .btn-danger {
  border-color: var(--color-danger);
  color: var(--color-danger);
  background: var(--color-danger-bg);
}

.modal-actions .btn-danger:hover:not(:disabled) {
  background: var(--color-danger);
  color: #fff;
}

.modal-actions .btn-danger:disabled {
  opacity: 0.5;
}
</style>
