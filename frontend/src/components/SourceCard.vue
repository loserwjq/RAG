<template>
  <div class="sources">
    <button class="sources-toggle" @click="expanded = !expanded">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 15l-6-6-6 6"/>
      </svg>
      <span>参考来源 ({{ sources.length }})</span>
      <svg
        width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
        class="chevron" :class="{ rotated: expanded }"
      >
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>

    <div v-if="expanded" class="sources-list">
      <div v-for="(s, i) in sources" :key="i" class="source-item">
        <div class="source-header">
          <span class="source-idx">[{{ i + 1 }}]</span>
          <span class="source-doc">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
            {{ s.file_name || s.metadata?.file_name || s.metadata?.doc_name || '未知文档' }}
          </span>
          <span class="source-meta" v-if="pageLabel(s)">{{ pageLabel(s) }}</span>
          <span class="source-meta" v-if="chunkLabel(s)">{{ chunkLabel(s) }}</span>
          <span class="source-meta" v-if="s.metadata?.type">{{ s.metadata.type }}</span>
          <span class="source-spacer"></span>
          <a
            v-if="sourceTarget(s)"
            class="source-open"
            :href="sourceTarget(s)"
            target="_blank"
            rel="noopener noreferrer"
            :title="openTitle(s)"
            @click.prevent.stop="openSource(s)"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/>
              <line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
            原文链接
          </a>
          <span class="source-score" v-if="s.rerank_score != null" title="Rerank 分数">
            {{ s.rerank_score.toFixed(3) }}
          </span>
          <span class="source-score" v-else-if="s.score != null" title="相似度分数">
            {{ s.score > 0 ? '+' : '' }}{{ s.score.toFixed(3) }}
          </span>
        </div>
        <div class="source-text">{{ s.content?.substring(0, 300) }}{{ s.content?.length > 300 ? '...' : '' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { openProtectedPreview } from '../api.js'

defineProps({ sources: Array })

const expanded = ref(false)

function toInt(value) {
  const n = Number(value)
  return Number.isFinite(n) ? Math.trunc(n) : null
}

function pageLabel(source) {
  const direct = toInt(source?.page_number)
  if (direct && direct > 0) return `第${direct}页`

  const pageIdx = toInt(source?.metadata?.page_idx)
  if (pageIdx === null || pageIdx < 0) return ''
  return `第${pageIdx + 1}页`
}

function chunkLabel(source) {
  const chunkIdx = toInt(source?.metadata?.chunk_idx)
  if (chunkIdx === null || chunkIdx < 0) return ''
  return `Chunk ${chunkIdx + 1}`
}

function openTitle(source) {
  const location = [pageLabel(source), chunkLabel(source)].filter(Boolean).join(' / ')
  return location ? `打开原文链接：${location}` : '打开原文链接'
}

function sourceTarget(source) {
  return source?.preview_url || source?.file_url || ''
}

async function openSource(source) {
  const target = sourceTarget(source)
  if (!target) return
  try {
    await openProtectedPreview(
      target,
      source.file_name || source.metadata?.file_name || source.metadata?.doc_name || '',
    )
  } catch (e) {
    console.error('预览原文失败:', e)
    alert('预览原文失败: ' + (e?.message || e))
  }
}
</script>

<style scoped>
.sources {
  margin-top: var(--space-2);
  border-top: 1px solid var(--color-border-light);
  padding-top: var(--space-2);
}

.sources-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  border: none;
  background: none;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: inherit;
  cursor: pointer;
  padding: 2px 0;
  transition: color var(--transition-fast);
  width: 100%;
  text-align: left;
}

.sources-toggle:hover {
  color: var(--color-primary);
}

.chevron {
  margin-left: auto;
  transition: transform var(--transition-fast);
}

.chevron.rotated {
  transform: rotate(180deg);
}

.sources-list {
  margin-top: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-height: 320px;
  overflow-y: auto;
}

.source-item {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-alt);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
}

.source-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 11px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.source-idx {
  color: var(--color-accent);
  font-weight: var(--font-semibold);
}

.source-doc {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--color-text-secondary);
  font-weight: var(--font-medium);
}

.source-meta {
  color: var(--color-text-muted);
  background: var(--color-surface-secondary);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
}

.source-spacer {
  flex: 1 1 auto;
}

.source-open {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--color-primary);
  background: var(--color-primary-light);
  border: 1px solid var(--color-primary-200);
  border-radius: 3px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: var(--font-medium);
  text-decoration: none;
  transition: all var(--transition-fast);
}

.source-open:hover {
  background: var(--color-primary);
  color: var(--color-text-inverse);
  border-color: var(--color-primary);
}

.source-score {
  color: var(--color-primary-400);
  font-weight: var(--font-semibold);
  font-size: 10px;
}

.source-text {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: var(--leading-relaxed);
}
</style>
