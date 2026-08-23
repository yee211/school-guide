<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import {
  ArrowUp,
  BookOpen,
  Bot,
  Building2,
  Check,
  Copy,
  GraduationCap,
  Menu,
  MessageCircleQuestion,
  Plus,
  RotateCcw,
  Sparkles,
  Square,
  Trash2,
  X,
} from 'lucide-vue-next'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { askSchoolAssistantStream } from '../services/chat'
import type { ChatMessage, HistoryTurn } from '../types/chat'

defineOptions({ name: 'SchoolAssistant' })

marked.setOptions({
  gfm: true,
  breaks: true,
})

function renderMarkdown(content: string): string {
  if (!content) return ''
  try {
    const rawHtml = marked.parse(content) as string
    return DOMPurify.sanitize(rawHtml)
  } catch {
    return content
  }
}

const suggestions = [
  { icon: Building2, label: '学校概况', prompt: '请介绍一下长沙工业学院的基本情况' },
  { icon: GraduationCap, label: '专业设置', prompt: '学校目前有哪些特色专业？' },
  { icon: BookOpen, label: '校园资源', prompt: '学校的教学资源和校园条件怎么样？' },
  { icon: Sparkles, label: '办学特色', prompt: '学校在产教融合方面有哪些特色？' },
]

const STORAGE_KEY = 'school_assistant_chat_history'

const messages = ref<ChatMessage[]>([])
const input = ref('')
const loading = ref(false)
const mobileMenuOpen = ref(false)
const messageList = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const abortController = ref<AbortController | null>(null)
const copiedId = ref<number | null>(null)
let copyTimer: number | undefined
let id = 0

// 每次请求携带的对话历史条数上限（约 5 轮），控制 token 用量
const MAX_HISTORY = 10

onMounted(() => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved) as ChatMessage[]
      if (Array.isArray(parsed) && parsed.length > 0) {
        messages.value = parsed
        id = Math.max(...parsed.map((m) => m.id), 0)
        scrollToBottom()
      }
    }
  } catch {
    // ignore
  }
})

watch(
  messages,
  (newMessages) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newMessages))
    } catch {
      // ignore
    }
  },
  { deep: true },
)

function scrollToBottom() {
  nextTick(() => messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'smooth' }))
}

function autoResize() {
  nextTick(() => {
    const el = textareaRef.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(Math.max(el.scrollHeight, 32), 140)}px`
  })
}

function stopGeneration() {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  loading.value = false
}

function clearChat() {
  if (loading.value) {
    stopGeneration()
  }
  messages.value = []
  localStorage.removeItem(STORAGE_KEY)
  mobileMenuOpen.value = false
}

async function copyMessage(content: string, msgId: number) {
  try {
    await navigator.clipboard.writeText(content)
    copiedId.value = msgId
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = window.setTimeout(() => {
      copiedId.value = null
    }, 2000)
  } catch {
    // fallback
  }
}

async function regenerateLast() {
  if (loading.value || messages.value.length === 0) return
  const lastUserIndex = [...messages.value].reverse().findIndex((m) => m.role === 'user')
  if (lastUserIndex === -1) return
  const actualIndex = messages.value.length - 1 - lastUserIndex
  const lastQuestion = messages.value[actualIndex].content
  messages.value = messages.value.slice(0, actualIndex)
  sendMessage(lastQuestion)
}

async function sendMessage(text = input.value) {
  const question = text.trim()
  if (!question || loading.value) return

  // 截取最近的对话历史（不含本条），供后端做多轮上下文
  const history: HistoryTurn[] = messages.value
    .slice(-MAX_HISTORY)
    .map((m) => ({ role: m.role, content: m.content }))

  messages.value.push({ id: ++id, role: 'user', content: question })
  input.value = ''
  autoResize()
  mobileMenuOpen.value = false
  loading.value = true
  scrollToBottom()

  const assistantId = ++id
  let started = false
  abortController.value = new AbortController()

  try {
    await askSchoolAssistantStream(
      question,
      history,
      {
        onDelta: (delta) => {
          if (!started) {
            messages.value.push({ id: assistantId, role: 'assistant', content: delta })
            started = true
          } else {
            const msg = messages.value.find((m) => m.id === assistantId)
            if (msg) msg.content += delta
          }
          scrollToBottom()
        },
        onDone: (sources) => {
          const msg = messages.value.find((m) => m.id === assistantId)
          if (msg) msg.sources = sources
        },
        onError: (err) => {
          const msg = messages.value.find((m) => m.id === assistantId)
          if (msg) {
            if (!msg.content) msg.content = err
          } else {
            messages.value.push({ id: assistantId, role: 'assistant', content: err })
          }
        },
      },
      abortController.value.signal,
    )
  } catch (error: any) {
    if (error?.name === 'AbortError') {
      return
    }
    const fallback = error instanceof Error ? error.message : '抱歉，回答生成失败，请稍后重试。'
    const msg = messages.value.find((m) => m.id === assistantId)
    if (msg) {
      if (!msg.content) msg.content = fallback
    } else {
      messages.value.push({ id: assistantId, role: 'assistant', content: fallback })
    }
  } finally {
    loading.value = false
    abortController.value = null
    scrollToBottom()
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}
</script>

<template>
  <main class="app-shell">
    <aside class="sidebar" :class="{ open: mobileMenuOpen }">
      <button class="mobile-close" aria-label="关闭菜单" @click="mobileMenuOpen = false">
        <X :size="20" />
      </button>

      <div class="brand">
        <img src="/school-logo.png" alt="长沙工业学院校徽与校名" />
      </div>

      <div class="sidebar-actions">
        <button class="new-chat-btn" type="button" @click="clearChat">
          <Plus :size="16" /> 新建对话
        </button>
      </div>

      <section class="side-intro">
        <p class="eyebrow">CAMPUS AI GUIDE</p>
        <h1>校园智答</h1>
        <p>关于长沙工业学院，你想了解的，都可以在这里找到答案。</p>
      </section>

      <section class="quick-section">
        <p class="section-label">快速了解</p>
        <button
          v-for="item in suggestions"
          :key="item.label"
          class="quick-link"
          @click="sendMessage(item.prompt)"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
          <span class="quick-arrow">↗</span>
        </button>
      </section>

      <div class="sidebar-footer">
        <span class="status-dot"></span>
        <span>校园知识库已连接</span>
      </div>
    </aside>

    <div v-if="mobileMenuOpen" class="overlay" @click="mobileMenuOpen = false"></div>

    <section class="chat-panel">
      <header class="topbar">
        <button class="menu-button" aria-label="打开菜单" @click="mobileMenuOpen = true">
          <Menu :size="21" />
        </button>
        <div class="assistant-title">
          <div class="avatar"><Bot :size="21" /></div>
          <div>
            <strong>长工小助手</strong>
            <span><i></i> 在线</span>
          </div>
        </div>
        <div class="topbar-right">
          <button
            v-if="messages.length > 0"
            class="topbar-action-btn"
            title="清空对话"
            aria-label="清空对话"
            @click="clearChat"
          >
            <Trash2 :size="15" /> 清空
          </button>
          <div class="topbar-tag"><Sparkles :size="14" /> AI 智能问答</div>
        </div>
      </header>

      <div ref="messageList" class="messages">
        <section v-if="messages.length === 0" class="welcome">
          <div class="welcome-icon">
            <MessageCircleQuestion :size="30" />
          </div>
          <p class="eyebrow">你好，欢迎来到长沙工业学院</p>
          <h2>今天想了解学校的什么？</h2>
          <p class="welcome-copy">我会基于学校资料，为你解答校园概况、录取分数线、专业计划、学费及校园生活等问题。</p>
          <div class="suggestion-grid">
            <button v-for="item in suggestions" :key="item.prompt" @click="sendMessage(item.prompt)">
              <component :is="item.icon" :size="20" />
              <span>{{ item.prompt }}</span>
            </button>
          </div>
        </section>

        <template v-else>
          <article v-for="(message, index) in messages" :key="message.id" class="message" :class="message.role">
            <div v-if="message.role === 'assistant'" class="message-avatar"><Bot :size="18" /></div>
            <div class="message-body">
              <!-- 用户消息展示纯文本，助手消息展示 Markdown 富文本 -->
              <div v-if="message.role === 'user'" class="bubble user-bubble">{{ message.content }}</div>
              <div
                v-else
                class="bubble assistant-bubble markdown-body"
                v-html="renderMarkdown(message.content)"
              ></div>

              <!-- 参考资料卡片 -->
              <div v-if="message.sources?.length" class="sources">
                <span>参考资料</span>
                <div v-for="source in message.sources" :key="source.source" class="source-chip">
                  <BookOpen :size="13" /> {{ source.title }}
                </div>
              </div>

              <!-- 助手消息底部操作栏（复制、重新生成） -->
              <div v-if="message.role === 'assistant'" class="message-actions">
                <button
                  class="action-btn"
                  type="button"
                  :title="copiedId === message.id ? '已复制' : '复制回答'"
                  @click="copyMessage(message.content, message.id)"
                >
                  <Check v-if="copiedId === message.id" :size="13" />
                  <Copy v-else :size="13" />
                  <span>{{ copiedId === message.id ? '已复制' : '复制' }}</span>
                </button>

                <button
                  v-if="index === messages.length - 1 && !loading"
                  class="action-btn"
                  type="button"
                  title="重新生成回答"
                  @click="regenerateLast"
                >
                  <RotateCcw :size="13" />
                  <span>重新生成</span>
                </button>
              </div>
            </div>
          </article>

          <article v-if="loading" class="message assistant">
            <div class="message-avatar"><Bot :size="18" /></div>
            <div class="bubble typing"><span></span><span></span><span></span></div>
          </article>
        </template>
      </div>

      <footer class="composer-wrap">
        <div class="composer">
          <textarea
            ref="textareaRef"
            v-model="input"
            rows="1"
            maxlength="5000"
            placeholder="输入你想了解的问题…（Shift+Enter 换行）"
            aria-label="向长工小助手提问"
            @input="autoResize"
            @keydown="handleKeydown"
          ></textarea>

          <!-- 流式生成中显示停止按钮，否则显示发送按钮 -->
          <button
            v-if="loading"
            class="stop-button"
            type="button"
            aria-label="停止生成"
            title="停止生成"
            @click="stopGeneration"
          >
            <Square :size="16" />
          </button>
          <button
            v-else
            class="send-button"
            :disabled="!input.trim()"
            type="button"
            aria-label="发送消息"
            title="发送消息"
            @click="sendMessage()"
          >
            <ArrowUp :size="20" />
          </button>
        </div>
        <p>内容由 AI 生成，重要信息请以学校官方发布为准</p>
      </footer>
    </section>
  </main>
</template>
