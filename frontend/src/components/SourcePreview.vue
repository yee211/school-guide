<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{ source: string }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const title = ref('资料原文')
const content = ref('')
const pending = ref(true)
const error = ref('')
const truncated = ref(false)
const controller = new AbortController()
const html = computed(() => DOMPurify.sanitize(marked.parse(content.value, { gfm: true, breaks: true }) as string))

onMounted(async () => {
  dialog.value?.showModal()
  try {
    const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
    const response = await fetch(`${base}/knowledge/source?source=${encodeURIComponent(props.source)}`, { signal: controller.signal })
    const data = await response.json().catch(() => null)
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : '资料暂时无法预览')
    const labels: Record<string, string> = { school_overview: '学校概况', school_life: '校园生活', library: '图书馆服务' }
    title.value = labels[data.title] ?? data.title
    content.value = data.content
    truncated.value = data.truncated
  } catch (cause) {
    if (!controller.signal.aborted) error.value = cause instanceof Error ? cause.message : '资料暂时无法预览'
  } finally {
    pending.value = false
  }
})
onUnmounted(() => controller.abort())
</script>

<template>
  <dialog ref="dialog" class="source-preview" aria-labelledby="source-preview-title" @close="emit('close')">
    <header>
      <h2 id="source-preview-title">{{ title }}</h2>
      <button type="button" autofocus aria-label="关闭资料预览" @click="dialog?.close()">关闭</button>
    </header>
    <p class="source-path">{{ source }}</p>
    <p v-if="pending" role="status">正在读取资料…</p>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <template v-else>
      <p v-if="truncated" role="status">资料较长，当前展示前 60,000 个字符。</p>
      <article class="markdown-body" v-html="html"></article>
    </template>
  </dialog>
</template>

<style scoped>
.source-preview { width: min(860px, calc(100vw - 32px)); max-height: 85vh; box-sizing: border-box; padding: 24px; border: 1px solid #dce5ed; border-radius: 14px; color: #263b4f; background: #fff; overflow: auto; }
.source-preview::backdrop { background: rgb(20 35 50 / 45%); }
header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
h2 { margin: 0; font-size: 20px; overflow-wrap: anywhere; }
button { padding: 8px 14px; flex-shrink: 0; border: 1px solid #cad8e4; border-radius: 8px; background: #f2f6fa; cursor: pointer; }
button:focus-visible { outline: 3px solid #58a9e8; outline-offset: 3px; }
.source-path { color: #586d80; font-size: 12px; overflow-wrap: anywhere; }
article { overflow-wrap: anywhere; }
article :deep(table) { display: block; max-width: 100%; overflow-x: auto; }
</style>
