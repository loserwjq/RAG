<template>
  <div class="docs-panel">
    <!-- KB 选择 -->
    <div class="panel-toolbar">
      <div class="kb-select-row">
        <label class="form-label">知识库：</label>
        <select v-model="selectedKbId" @change="loadDocuments" class="form-select">
          <option :value="null" disabled>请选择知识库...</option>
          <option v-for="kb in kbs" :key="kb.id" :value="kb.id">
            {{ kb.name }} ({{ kb.doc_count || 0 }} 文档)
          </option>
        </select>
        <button @click="$emit('refresh-kbs')" class="icon-btn" title="刷新">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.36-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
        </button>
      </div>
    </div>

    <!-- 未选择 KB -->
    <div v-if="!selectedKbId" class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
      </svg>
      <p>请选择一个知识库来管理文档</p>
    </div>

    <!-- 已选择 KB -->
    <template v-else>
      <!-- 上传区域 -->
      <div
        class="drop-zone"
        :class="{ dragging, uploading }"
        @dragover.prevent="dragging = true"
        @dragleave="dragging = false"
        @drop.prevent="handleDrop"
        @click="triggerInput"
      >
        <input
          ref="fileInput"
          type="file"
          :accept="acceptTypes"
          multiple
          hidden
          @change="handleSelect"
        />
        <div v-if="uploading" class="zone-uploading">
          <div class="spinner"></div>
          <p class="upload-text">{{ uploadStatus }}</p>
          <p class="upload-sub">请勿关闭页面</p>
        </div>
        <div v-else class="zone-idle">
          <div class="zone-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          </div>
          <p class="zone-text">点击或拖拽文件到此处上传</p>
          <p class="zone-formats">支持 PDF, PPTX, DOCX, XLSX, MD, TXT</p>
        </div>
      </div>

      <!-- 上传结果 -->
      <div v-if="results.length" class="upload-results">
        <div v-for="(r, i) in results" :key="i" class="result-item" :class="r.status">
          <span class="result-icon">
            <svg v-if="r.status === 'ok'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-success)" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-danger)" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </span>
          <span class="result-name">{{ r.filename }}</span>
          <span class="result-detail">{{ r.detail }}</span>
        </div>
      </div>

      <!-- 文档列表 -->
      <div class="doc-section">
        <div class="section-header">
          <h4>已上传文档</h4>
          <button @click="loadDocuments" class="text-btn" :disabled="loadingDocs">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.36-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            刷新
          </button>
        </div>

        <!-- Loading -->
        <div v-if="loadingDocs" class="loading-state">
          <div class="skeleton" v-for="i in 3" :key="i">
            <div class="skeleton-line skeleton-line--title"></div>
            <div class="skeleton-line skeleton-line--detail"></div>
          </div>
        </div>

        <!-- 空列表 -->
        <div v-else-if="documents.length === 0" class="empty-small">
          <p>暂无文档，请上传文件</p>
        </div>

        <!-- 文档列表 -->
        <div v-else class="doc-list">
          <div v-for="doc in documents" :key="doc.id" class="doc-item">
            <div class="doc-icon" :class="'doc-type--' + (doc.file_type || 'unknown')">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </div>
            <div class="doc-info">
              <span class="doc-name">{{ doc.file_name }}</span>
              <span class="doc-meta">
                <span class="meta-chip">{{ doc.file_type?.toUpperCase() }}</span>
                <span>{{ doc.chunk_count }} chunks</span>
                <span>{{ formatSize(doc.file_size) }}</span>
                <span class="doc-status" :class="'status--' + doc.status">
                  {{ doc.deleted_at ? '已删除' : statusLabel(doc.status) }}
                </span>
              </span>
            </div>
            <span class="doc-time">{{ formatTime(doc.uploaded_at) }}</span>
            <button
              v-if="!doc.deleted_at"
              @click="confirmDelete(doc)"
              class="icon-btn icon-btn--danger"
              :disabled="deleting === doc.id"
              title="删除文档"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
            </button>
          </div>
        </div>
      </div>
    </template>

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
          <h3 class="modal-title">确认删除文档</h3>
          <p class="modal-desc">确定要删除「{{ deleteTarget.file_name }}」吗？此操作将删除所有相关向量数据。</p>
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
import { ref, watch } from 'vue'
import { kb as kbApi, pollUploadTask } from '../api.js'

const props = defineProps({ kbs: Array })
const emit = defineEmits(['refresh-kbs'])

const acceptTypes = '.pdf,.pptx,.docx,.xlsx,.xls,.md,.txt,.markdown'

const selectedKbId = ref(null)
const fileInput = ref(null)
const dragging = ref(false)
const uploading = ref(false)
const uploadStatus = ref('')
const results = ref([])
const documents = ref([])
const loadingDocs = ref(false)
const deleting = ref(null)
const deleteTarget = ref(null)

// 默认选择第一个 KB
watch(() => props.kbs, (val) => {
  if (val?.length && !selectedKbId.value) {
    selectedKbId.value = val[0].id
    loadDocuments()
  }
}, { immediate: true })

function statusLabel(s) {
  const map = {
    uploading: '上传中',
    processing: '处理中',
    parsing: '解析中',
    vectorizing: '向量化',
    done: '已完成',
    error: '失败',
  }
  return map[s] || s
}

function triggerInput() {
  if (!uploading.value) fileInput.value.click()
}

function handleSelect(e) {
  const files = Array.from(e.target.files)
  if (files.length) uploadFiles(files)
  e.target.value = ''
}

function handleDrop(e) {
  dragging.value = false
  const files = Array.from(e.dataTransfer.files)
  if (files.length) uploadFiles(files)
}

async function uploadFiles(files) {
  if (!selectedKbId.value) return
  uploading.value = true
  results.value = []

  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    uploadStatus.value = `上传中 (${i + 1}/${files.length}): ${file.name}`

    try {
      const data = await kbApi.upload(selectedKbId.value, file)
      if (data.task_id) {
        try {
          const result = await pollUploadTask(data.task_id)
          if (result.error) {
            results.value.push({ filename: file.name, status: 'error', detail: result.error })
          } else {
            results.value.push({
              filename: file.name,
              status: 'ok',
              detail: `${result.chunks} 个文本块已入库`,
            })
          }
        } catch (e) {
          results.value.push({ filename: file.name, status: 'error', detail: e.message })
        }
      } else {
        results.value.push({
          filename: file.name,
          status: 'ok',
          detail: '已入库',
        })
      }
    } catch (e) {
      results.value.push({ filename: file.name, status: 'error', detail: e.message })
    }
  }

  uploading.value = false
  uploadStatus.value = ''
  loadDocuments()
  setTimeout(() => emit('refresh-kbs'), 500)
}

async function loadDocuments() {
  if (!selectedKbId.value) return
  loadingDocs.value = true
  try {
    const data = await kbApi.documents(selectedKbId.value)
    documents.value = data.documents || []
  } catch (e) {
    console.error('加载文档列表失败:', e)
  } finally {
    loadingDocs.value = false
  }
}

function confirmDelete(doc) {
  deleteTarget.value = doc
}

async function doDelete() {
  const doc = deleteTarget.value
  if (!doc) return
  deleting.value = doc.id
  try {
    await kbApi.deleteDocument(doc.id)
    deleteTarget.value = null
    await loadDocuments()
    setTimeout(() => emit('refresh-kbs'), 500)
  } catch (e) {
    alert('删除失败: ' + e.message)
  } finally {
    deleting.value = null
  }
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatTime(t) {
  if (!t) return '-'
  return t.replace('T', ' ').substring(0, 16)
}
</script>

<style scoped>
.docs-panel {
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

.kb-select-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.form-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-medium);
  white-space: nowrap;
}

.form-select {
  flex: 1;
  padding: 7px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-surface);
  cursor: pointer;
  outline: none;
}

.form-select:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-100);
}

.icon-btn {
  width: 32px;
  height: 32px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.icon-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.icon-btn--danger:hover:not(:disabled) {
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ═══ Empty ═══════════════════════════════════════════════ */

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

/* ═══ Drop Zone ═══════════════════════════════════════════ */

.drop-zone {
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-8);
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-base);
  background: var(--color-bg-alt);
  margin-bottom: var(--space-3);
}

.drop-zone:hover,
.drop-zone.dragging {
  border-color: var(--color-primary);
  background: var(--color-primary-50);
}

.drop-zone.uploading {
  border-color: var(--color-accent);
  background: var(--color-warning-bg);
  cursor: wait;
}

.zone-icon svg {
  stroke: var(--color-text-muted);
  margin-bottom: var(--space-3);
}

.zone-text {
  font-size: var(--text-sm);
  color: var(--color-text);
  font-weight: var(--font-medium);
}

.zone-formats {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

.zone-uploading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.upload-text {
  font-size: var(--text-sm);
  color: var(--color-accent);
  font-weight: var(--font-medium);
}

.upload-sub {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-accent);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ═══ Upload Results ══════════════════════════════════════ */

.upload-results {
  margin-bottom: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.result-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.result-item.ok {
  background: var(--color-success-bg);
  border: 1px solid var(--color-success-light);
}

.result-item.error {
  background: var(--color-danger-bg);
  border: 1px solid var(--color-danger-light);
}

.result-name {
  font-weight: var(--font-medium);
  color: var(--color-text);
}

.result-detail {
  margin-left: auto;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

/* ═══ Document List ═══════════════════════════════════════ */

.doc-section {
  margin-top: var(--space-6);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.section-header h4 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text);
}

.text-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 0;
  border: none;
  background: none;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: inherit;
  cursor: pointer;
  transition: color var(--transition-fast);
}

.text-btn:hover:not(:disabled) {
  color: var(--color-primary);
}

.text-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Skeleton Loading */
.loading-state {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.skeleton {
  padding: var(--space-3);
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

.empty-small {
  text-align: center;
  padding: var(--space-8);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

/* Doc Items */
.doc-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  transition: all var(--transition-fast);
}

.doc-item:hover {
  border-color: var(--color-border);
  box-shadow: var(--shadow-xs);
}

.doc-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.doc-type--pdf { background: var(--color-danger-light); color: var(--color-danger); }
.doc-type--pptx { background: var(--color-warning-light); color: #8a6a20; }
.doc-type--docx { background: var(--color-primary-light); color: var(--color-primary-600); }
.doc-type--xlsx { background: var(--color-success-light); color: var(--color-success); }
.doc-type--xls { background: var(--color-success-light); color: var(--color-success); }
.doc-type--md { background: #f0ebe0; color: var(--color-primary-500); }
.doc-type--txt { background: var(--color-surface-secondary); color: var(--color-text-muted); }
.doc-type--unknown { background: var(--color-surface-secondary); color: var(--color-text-muted); }

.doc-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.doc-name {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 2px;
}

.meta-chip {
  padding: 0 4px;
  background: var(--color-surface-secondary);
  border-radius: 3px;
  font-weight: var(--font-medium);
  font-size: 10px;
}

.doc-status {
  font-weight: var(--font-medium);
}

.status--done { color: var(--color-success); }
.status--error { color: var(--color-danger); }
.status--uploading,
.status--processing,
.status--parsing,
.status--vectorizing { color: var(--color-accent); }

.doc-time {
  font-size: 11px;
  color: var(--color-text-muted);
  white-space: nowrap;
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

.btn {
  padding: var(--space-2) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
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
</style>
