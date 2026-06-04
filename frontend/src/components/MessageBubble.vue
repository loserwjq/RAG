<template>
  <div class="bubble" :class="message.role">
    <div class="bubble-avatar" v-if="message.role === 'assistant'">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2a4 4 0 0 1 4 4v4a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/>
        <path d="M8 10H6a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2h1"/>
        <path d="M16 10h2a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-1"/>
        <path d="M12 18v4"/>
        <path d="M10 22h4"/>
      </svg>
    </div>
    <div class="bubble-body">
      <div class="bubble-header">
        <span class="bubble-role">{{ message.role === 'user' ? '你' : 'AI 助手' }}</span>
        <span class="bubble-time" v-if="message.time">{{ message.time }}</span>
      </div>
      <div class="bubble-content">
        <div class="text" v-html="renderedContent"></div>
        <span v-if="message._streaming" class="typing-cursor">|</span>
      </div>
      <SourceCard v-if="showSources" :sources="message.sources" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import SourceCard from './SourceCard.vue'

const props = defineProps({ message: Object })

const showSources = computed(() => {
  return props.message?.role === 'assistant' &&
    Array.isArray(props.message.sources) &&
    props.message.sources.length > 0
})

const renderedContent = computed(() => {
  const text = props.message.content || ''
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
})
</script>

<style scoped>
.bubble {
  display: flex;
  gap: var(--space-3);
  max-width: 85%;
  animation: fadeInUp 0.3s ease-out;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.bubble.user { align-self: flex-end; flex-direction: row-reverse; }
.bubble.assistant { align-self: flex-start; }

.bubble-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--color-primary-50);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
  border: 1px solid var(--color-primary-200);
}

.bubble-body { min-width: 0; }

.bubble-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: 4px;
  padding: 0 4px;
}

.bubble.user .bubble-header { flex-direction: row-reverse; }

.bubble-role {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-weight: var(--font-medium);
  font-family: var(--font-display);
  letter-spacing: 0.05em;
}

.bubble-time { font-size: 10px; color: var(--color-text-muted); }

.bubble-content {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-base);
  line-height: var(--leading-relaxed);
  word-break: break-word;
  position: relative;
  user-select: text;
  -webkit-user-select: text;
}

.bubble.user .bubble-content {
  background: var(--color-primary-50);
  color: var(--color-text);
  border: 1px solid var(--color-primary-200);
  border-bottom-right-radius: var(--radius-sm);
}

.bubble.assistant .bubble-content {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-bottom-left-radius: var(--radius-sm);
}

.text :deep(code) {
  background: rgba(0, 255, 136, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.9em;
  font-family: var(--font-mono);
  color: var(--color-primary);
}

.text :deep(strong) { font-weight: var(--font-semibold); }

.typing-cursor {
  display: inline-block;
  animation: blink 1s step-end infinite;
  font-weight: var(--font-light);
  margin-left: 1px;
  color: var(--color-primary);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
