/**
 * API 客户端 — 统一管理后端请求。
 *
 * - 自动注入 X-User-Id header（Dev Mode）
 * - 统一错误处理
 * - SSE 流式读取
 */

const BASE = ''

let _userId = null
let _userInfo = null

export function setUser(user) {
  _userId = user?.user_id
  _userInfo = user
}

export function getUserId() {
  return _userId
}

export function getUserInfo() {
  return _userInfo
}

function headers(extra = {}) {
  const h = { ...extra }
  if (_userId) h['X-User-Id'] = String(_userId)
  return h
}

export async function apiGet(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, { headers: headers() })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function apiPost(path, body = {}, opts = {}) {
  const isFormData = body instanceof FormData
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: isFormData ? headers() : headers({ 'Content-Type': 'application/json' }),
    body: isFormData ? body : JSON.stringify(body),
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function apiPut(path, body = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function apiPatch(path, body = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function apiDelete(path) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    headers: headers(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

/**
 * SSE 流式请求 — 返回 async generator。
 */
export async function* apiStream(path, body = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6))
        } catch {
          // skip unparseable chunks
        }
      }
    }
  }
}

function openBlankWindow() {
  const opened = window.open('', '_blank')
  if (opened) {
    opened.opener = null
    opened.document.title = '正在打开原文...'
    opened.document.body.innerHTML = '<p style="font:14px sans-serif;padding:16px;color:#666">正在打开原文...</p>'
  }
  return opened
}

/**
 * 打开受保护的原始文件。
 * 普通 a 标签不会携带 X-User-Id，所以这里用 fetch 注入鉴权头后再打开 blob URL。
 */
export async function openProtectedFile(path, filename = '') {
  const hashIndex = path.indexOf('#')
  const cleanPath = hashIndex >= 0 ? path.slice(0, hashIndex) : path
  const hash = hashIndex >= 0 ? path.slice(hashIndex) : ''
  const opened = openBlankWindow()

  try {
    const res = await fetch(`${BASE}${cleanPath}`, { headers: headers() })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }

    const blob = await res.blob()
    const blobUrl = URL.createObjectURL(blob)
    const targetUrl = `${blobUrl}${hash}`

    if (opened) {
      opened.location.href = targetUrl
    } else {
      const a = document.createElement('a')
      a.href = targetUrl
      if (filename) a.download = filename
      a.target = '_blank'
      a.rel = 'noopener noreferrer'
      document.body.appendChild(a)
      a.click()
      a.remove()
    }

    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000)
  } catch (e) {
    if (opened && !opened.closed) opened.close()
    throw e
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function downloadBlob(blob, filename = '') {
  const blobUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = blobUrl
  if (filename) a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000)
}

function previewShell({ title, body }) {
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(title)}</title>
  <style>
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: #f7f3ec;
      color: #2f2b25;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    }
    .bar {
      height: 44px;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 0 14px;
      background: #fffaf2;
      border-bottom: 1px solid #e7dccb;
      font-size: 13px;
      color: #5f574b;
    }
    .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 600;
    }
    .viewer {
      height: calc(100vh - 44px);
      overflow: auto;
    }
    iframe {
      width: 100%;
      height: 100%;
      border: 0;
      background: #fff;
    }
    img {
      display: block;
      max-width: min(100%, 1280px);
      max-height: calc(100vh - 72px);
      margin: 14px auto;
      object-fit: contain;
      box-shadow: 0 10px 30px rgba(36, 29, 20, 0.12);
      background: #fff;
    }
    pre {
      margin: 16px auto;
      width: min(960px, calc(100% - 32px));
      padding: 18px;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.7;
      background: #fff;
      border: 1px solid #e7dccb;
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(36, 29, 20, 0.08);
      font-family: "Cascadia Mono", Consolas, "Microsoft YaHei", monospace;
      font-size: 14px;
    }
  </style>
</head>
<body>
  <div class="bar"><span>原文链接预览</span><span class="name">${escapeHtml(title)}</span></div>
  <main class="viewer">${body}</main>
</body>
</html>`
}

function openPreviewHtml(opened, html) {
  const previewBlob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const previewUrl = URL.createObjectURL(previewBlob)
  if (opened) {
    opened.location.href = previewUrl
  } else {
    const a = document.createElement('a')
    a.href = previewUrl
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
    document.body.appendChild(a)
    a.click()
    a.remove()
  }
  window.setTimeout(() => URL.revokeObjectURL(previewUrl), 10 * 60_000)
}

/**
 * 打开统一预览页：PDF/TXT/图片预览，Office 转 PDF 成功则预览，失败则下载。
 */
export async function openProtectedPreview(path, filename = '') {
  const hashIndex = path.indexOf('#')
  const cleanPath = hashIndex >= 0 ? path.slice(0, hashIndex) : path
  const hash = hashIndex >= 0 ? path.slice(hashIndex) : ''
  const opened = openBlankWindow()

  try {
    const res = await fetch(`${BASE}${cleanPath}`, { headers: headers() })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }

    const mode = res.headers.get('X-Preview-Mode')
    const contentType = res.headers.get('content-type') || ''
    const blob = await res.blob()

    if (mode === 'download') {
      if (opened && !opened.closed) opened.close()
      downloadBlob(blob, filename)
      return
    }

    const fileUrl = URL.createObjectURL(blob)
    const title = filename || '原文'
    let body = ''

    if (contentType.includes('application/pdf')) {
      body = `<iframe src="${fileUrl}${hash}" title="${escapeHtml(title)}"></iframe>`
    } else if (contentType.startsWith('image/')) {
      body = `<img src="${fileUrl}" alt="${escapeHtml(title)}">`
    } else if (contentType.startsWith('text/') || /\.(txt|md|markdown)$/i.test(title)) {
      const text = await blob.text()
      body = `<pre>${escapeHtml(text)}</pre>`
      URL.revokeObjectURL(fileUrl)
    } else {
      if (opened && !opened.closed) opened.close()
      downloadBlob(blob, filename)
      URL.revokeObjectURL(fileUrl)
      return
    }

    openPreviewHtml(opened, previewShell({ title, body }))
    if (!contentType.startsWith('text/')) {
      window.setTimeout(() => URL.revokeObjectURL(fileUrl), 10 * 60_000)
    }
  } catch (e) {
    if (opened && !opened.closed) opened.close()
    throw e
  }
}

// ── 认证 ────────────────────────────────────────────────

export const auth = {
  login: (username, password) =>
    apiPost('/api/auth/login', { username, password }),

  register: (username, password, displayName, department) =>
    apiPost('/api/auth/register', {
      username,
      password,
      display_name: displayName,
      department,
    }),
}

// ── 知识库 ──────────────────────────────────────────────

export const kb = {
  list: () => apiGet('/api/kb'),

  get: (id) => apiGet(`/api/kb/${id}`),

  create: (name, department, description = '') =>
    apiPost('/api/kb', { name, department, description }),

  update: (id, data) => apiPut(`/api/kb/${id}`, data),

  delete: (id) => apiDelete(`/api/kb/${id}`),

  members: (id) => apiGet(`/api/kb/${id}/members`),

  addMember: (id, userId, permission = 'read') =>
    apiPost(`/api/kb/${id}/members`, { user_id: userId, permission }),

  removeMember: (id, userId) =>
    apiDelete(`/api/kb/${id}/members/${userId}`),

  // 文档
  documents: (id, limit = 100) =>
    apiGet(`/api/kb/${id}/documents?limit=${limit}`),

  upload: (id, file) => {
    const form = new FormData()
    form.append('file', file)
    return apiPost(`/api/kb/${id}/upload`, form)
  },

  deleteDocument: (docId) => apiDelete(`/api/documents/${docId}`),
}

// ── 对话 ────────────────────────────────────────────────

export function chatStream(messages, kbId = null, topK = 10, conversationId = null) {
  return apiStream('/api/chat', { messages, kb_id: kbId, top_k: topK, conversation_id: conversationId })
}

export const conversations = {
  list: (limit = 50) => apiGet(`/api/conversations?limit=${limit}`),

  create: (kbId = null, title = '新对话') =>
    apiPost('/api/conversations', { kb_id: kbId, title }),

  get: (id) => apiGet(`/api/conversations/${id}`),

  update: (id, data) => apiPatch(`/api/conversations/${id}`, data),

  delete: (id) => apiDelete(`/api/conversations/${id}`),

  messages: (id, before = null, limit = 50) =>
    apiGet(`/api/conversations/${id}/messages?limit=${limit}${before ? '&before=' + before : ''}`),
}

// ── 用户 ────────────────────────────────────────────────

export const users = {
  list: (department = null) =>
    apiGet(`/api/users${department ? `?department=${department}` : ''}`),

  me: () => apiGet('/api/users/me'),
}

// ── 系统 ────────────────────────────────────────────────

export const system = {
  info: () => apiGet('/api/info'),
  health: () => apiGet('/api/health'),
  departments: () => apiGet('/api/departments'),
  formats: () => apiGet('/api/supported-formats'),
  stats: () => apiGet('/api/stats'),
}

// ── 上传任务轮询 ────────────────────────────────────────

export async function pollUploadTask(taskId, timeout = 900) {
  const statusLabels = {
    processing: '排队中',
    parsing: '正在解析文档',
    vectorizing: '正在向量化',
  }
  for (let i = 0; i < timeout; i++) {
    await new Promise(r => setTimeout(r, 2000))
    try {
      const res = await apiGet(`/api/upload/${taskId}`)
      if (res.status === 'done') return { ...res, done: true }
      if (res.status === 'error') return { ...res, done: true, error: res.error }
      res._label = statusLabels[res.status] || res.status
      if (i % 5 === 0) console.log(`[poll] ${taskId}: ${res._label}`)
    } catch (e) {
      if (i > 5) throw e
    }
  }
  throw new Error('处理超时（超过 30 分钟）')
}
