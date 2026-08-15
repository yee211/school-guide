<script setup lang="ts">
import { nextTick, ref } from 'vue'
import {
  ArrowUp,
  BookOpen,
  Bot,
  Building2,
  GraduationCap,
  Menu,
  MessageCircleQuestion,
  Sparkles,
  X,
} from 'lucide-vue-next'
import { askSchoolAssistant } from './services/chat'
import type { ChatMessage } from './types/chat'

const suggestions = [
  { icon: Building2, label: '学校概况', prompt: '请介绍一下长沙工业学院的基本情况' },
  { icon: GraduationCap, label: '专业设置', prompt: '学校目前有哪些特色专业？' },
  { icon: BookOpen, label: '校园资源', prompt: '学校的教学资源和校园条件怎么样？' },
  { icon: Sparkles, label: '办学特色', prompt: '学校在产教融合方面有哪些特色？' },
]

const messages = ref<ChatMessage[]>([])
const input = ref('')
const loading = ref(false)
const mobileMenuOpen = ref(false)
const messageList = ref<HTMLElement | null>(null)
let id = 0

function scrollToBottom() {
  nextTick(() => messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'smooth' }))
}

async function sendMessage(text = input.value) {
  const question = text.trim()
  if (!question || loading.value) return

  messages.value.push({ id: ++id, role: 'user', content: question })
  input.value = ''
  mobileMenuOpen.value = false
  loading.value = true
  scrollToBottom()

  try {
    const result = await askSchoolAssistant(question)
    messages.value.push({
      id: ++id,
      role: 'assistant',
      content: result.answer,
      sources: result.sources,
    })
  } catch (error) {
    messages.value.push({
      id: ++id,
      role: 'assistant',
      content: error instanceof Error ? error.message : '抱歉，回答生成失败，请稍后重试。',
    })
  } finally {
    loading.value = false
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
            <strong>校园介绍助手</strong>
            <span><i></i> 在线</span>
          </div>
        </div>
        <div class="topbar-tag"><Sparkles :size="14" /> AI 智能问答</div>
      </header>

      <div ref="messageList" class="messages">
        <section v-if="messages.length === 0" class="welcome">
          <div class="welcome-icon">
            <MessageCircleQuestion :size="30" />
          </div>
          <p class="eyebrow">你好，欢迎来到长沙工业学院</p>
          <h2>今天想了解学校的什么？</h2>
          <p class="welcome-copy">我会基于学校资料，为你解答校园概况、专业建设、办学特色等问题。</p>
          <div class="suggestion-grid">
            <button v-for="item in suggestions" :key="item.prompt" @click="sendMessage(item.prompt)">
              <component :is="item.icon" :size="20" />
              <span>{{ item.prompt }}</span>
            </button>
          </div>
        </section>

        <template v-else>
          <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
            <div v-if="message.role === 'assistant'" class="message-avatar"><Bot :size="18" /></div>
            <div class="message-body">
              <div class="bubble">{{ message.content }}</div>
              <div v-if="message.sources?.length" class="sources">
                <span>参考资料</span>
                <div v-for="source in message.sources" :key="source.source" class="source-chip">
                  <BookOpen :size="13" /> {{ source.title }}
                </div>
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
            v-model="input"
            rows="1"
            maxlength="5000"
            placeholder="输入你想了解的问题…"
            aria-label="向校园介绍助手提问"
            @keydown="handleKeydown"
          ></textarea>
          <button class="send-button" :disabled="!input.trim() || loading" aria-label="发送消息" @click="sendMessage()">
            <ArrowUp :size="20" />
          </button>
        </div>
        <p>内容由 AI 生成，重要信息请以学校官方发布为准</p>
      </footer>
    </section>
  </main>
</template>
