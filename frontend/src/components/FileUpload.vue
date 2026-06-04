<template>
  <div class="file-upload">
    <div class="upload-bar">
      <label class="collect-label">知识库：</label>
      <select v-model="selectedCollection" class="collect-select">
        <option value="documents">默认库</option>
        <option v-for="c in collections" :key="c.name" :value="c.name">
          {{ c.label }} ({{ c.count }} 条)
        </option>
      </select>
      <input
        v-if="editingNew"
        v-model="newCollectionName"
        class="collect-input"
        placeholder="输入新知识库名"
        @keydown.enter="confirmNewCollection"
        @keydown.escape="editingNew = false"
        @blur="confirmNewCollection"
      />
      <button v-else @click="editingNew = true; newCollectionName = ''" class="collect-add-btn">+ 新建</button>
    </div>
    <div
      class="drop-zone"
      :class="{ dragging, uploading }"
      @dragover.prevent="dragging = true"
      @dragleave="dragging = false"
      @drop.prevent="handleDrop"
      @click="triggerFileInput"
    >
      <input
        ref="fileInput"
        type="file"
        :accept="acceptTypes"
        multiple
        hidden
        @change="handleFileSelect"
      />
      <div v-if="uploading" class="upload-status">
        <div class="spinner"></div>
        <p>{{ uploadStatus }}</p>
      </div>
      <div v-else class="drop-hint">
        <p class="drop-icon">📄</p>
        <p class="drop-text">点击或拖拽文件到此处上传</p>
        <p class="drop-formats">支持: PDF, PPTX, DOCX, XLSX, MD, TXT</p>
      </div>
    </div>

    <!-- 上传结果列表 -->
    <div v-if="results.length" class="upload-results">
      <div
        v-for="(r, i) in results"
        :key="i"
        class="result-item"
        :class="r.status"
      >
        <span class="result-icon">{{ r.status === 'ok' ? '✓' : '✗' }}</span>
        <span class="result-name">{{ r.filename }}</span>
        <span class="result-detail">{{ r.detail }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const emit = defineEmits(['uploaded'])

const fileInput = ref(null)
const dragging = ref(false)
const uploading = ref(false)
const uploadStatus = ref('')
const results = ref([])
const collections = ref([])
const selectedCollection = ref('documents')
const editingNew = ref(false)
const newCollectionName = ref('')

const acceptTypes = '.pdf,.pptx,.docx,.xlsx,.xls,.md,.txt,.markdown'

onMounted(async () => {
  try {
    const res = await fetch('/api/collections')
    const data = await res.json()
    if (data.collections) {
      collections.value = data.collections
        .filter(c => c.name !== 'documents')
        .map(c => ({ name: c.name, label: c.display_name || c.name, count: c.count }))
    }
  } catch (e) { /* ignore */ }
})

function confirmNewCollection() {
  const name = newCollectionName.value.trim()
  if (name && name !== 'documents') {
    selectedCollection.value = name
    if (!collections.value.find(c => c.name === name)) {
      collections.value.push({ name, label: name, count: 0 })
    }
  }
  editingNew.value = false
  newCollectionName.value = ''
}

function triggerFileInput() {
  if (!uploading.value) {
    fileInput.value.click()
  }
}

function handleFileSelect(e) {
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
  uploading.value = true
  results.value = []

  const coll = selectedCollection.value || 'documents'

  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    uploadStatus.value = `上传中 (${i + 1}/${files.length}): ${file.name} → [${coll}]`

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('collection', coll)

      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()

      if (data.error) {
        results.value.push({
          filename: file.name,
          status: 'error',
          detail: data.error,
        })
      } else if (data.task_id) {
        await pollTask(data.task_id, file.name, i, files.length)
      } else {
        results.value.push({
          filename: file.name,
          status: 'ok',
          detail: `${data.chunks} 个文本块已入库 → [${coll}]`,
        })
        emit('uploaded', data)
      }
    } catch (err) {
      results.value.push({
        filename: file.name,
        status: 'error',
        detail: `上传失败: ${err.message}`,
      })
    }
  }

  uploading.value = false
  uploadStatus.value = ''
  loadCollections()
}

async function loadCollections() {
  try {
    const res = await fetch('/api/collections')
    const data = await res.json()
    if (data.collections) {
      const list = data.collections
        .filter(c => c.name !== 'documents')
        .map(c => ({ name: c.name, label: c.display_name || c.name, count: c.count }))
      collections.value = list
      // 如果当前选的还是临时中文名，映射为后端返回的内部名
      const sel = selectedCollection.value
      if (sel && !list.find(c => c.name === sel)) {
        const match = list.find(c => c.label === sel)
        if (match) selectedCollection.value = match.name
      }
    }
  } catch (e) { /* ignore */ }
}

async function pollTask(taskId, filename, index, total) {
  const statusLabels = {
    processing: '排队中',
    parsing: '正在解析文档',
    vectorizing: '正在向量化',
  }

  for (let attempt = 0; attempt < 450; attempt++) {
    await new Promise(r => setTimeout(r, 2000))

    try {
      const res = await fetch(`/api/upload/${taskId}`)
      const task = await res.json()

      if (task.error && task.status === 'error') {
        results.value.push({
          filename,
          status: 'error',
          detail: task.error,
        })
        return
      }

      if (task.status === 'done') {
        const coll = task.collection || selectedCollection.value || 'documents'
        results.value.push({
          filename,
          status: 'ok',
          detail: `${task.chunks} 个文本块已入库 → [${coll}]`,
        })
        emit('uploaded', task)
        return
      }

      // 更新进度提示
      const label = statusLabels[task.status] || task.status
      uploadStatus.value = `处理中 (${index + 1}/${total}): ${filename} — ${label}`
    } catch (err) {
      // 网络错误时继续重试
      if (attempt > 5) {
        results.value.push({
          filename,
          status: 'error',
          detail: `状态查询失败: ${err.message}`,
        })
        return
      }
    }
  }

  results.value.push({
    filename,
    status: 'error',
    detail: '处理超时（超过 15 分钟）',
  })
}
</script>

<style scoped>
.file-upload {
  padding: 16px 24px;
}

.upload-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.collect-label {
  font-size: 13px;
  color: #666;
  white-space: nowrap;
}

.collect-select {
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 13px;
  background: #fff;
  min-width: 140px;
}

.collect-input {
  padding: 4px 8px;
  border: 1px solid #4096ff;
  border-radius: 4px;
  font-size: 13px;
  width: 150px;
}

.collect-add-btn {
  padding: 4px 10px;
  border: 1px dashed #d9d9d9;
  border-radius: 4px;
  background: none;
  color: #999;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.collect-add-btn:hover {
  border-color: #4096ff;
  color: #4096ff;
}

.drop-zone {
  border: 2px dashed #d9d9d9;
  border-radius: 12px;
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #fafafa;
}

.drop-zone:hover,
.drop-zone.dragging {
  border-color: #4096ff;
  background: #f0f7ff;
}

.drop-zone.uploading {
  border-color: #faad14;
  background: #fffbe6;
  cursor: wait;
}

.drop-hint .drop-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.drop-hint .drop-text {
  font-size: 14px;
  color: #333;
  margin-bottom: 4px;
}

.drop-hint .drop-formats {
  font-size: 12px;
  color: #999;
}

.upload-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.upload-status p {
  font-size: 14px;
  color: #d48806;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #faad14;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.upload-results {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}

.result-item.ok {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
}

.result-item.error {
  background: #fff2f0;
  border: 1px solid #ffccc7;
}

.result-icon {
  font-weight: bold;
}

.result-item.ok .result-icon { color: #52c41a; }
.result-item.error .result-icon { color: #ff4d4f; }

.result-name {
  font-weight: 500;
  color: #333;
}

.result-detail {
  color: #666;
  margin-left: auto;
}
</style>
