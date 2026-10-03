<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Braces,
  Database,
  Github,
  Layers3,
  Mail,
  Moon,
  Sparkles,
  Sun,
  X,
} from 'lucide-vue-next'
import SchoolAssistant from './components/SchoolAssistant.vue'

const demoOpen = ref(false)
const darkMode = ref(false)
const profile = {
  name: '谭锃',
  email: 'yeee6537@gmail.com',
  qqEmail: '2832005374@qq.com',
  github: 'https://github.com/yee211',
  projectSource: 'https://github.com/yee211/SchoolIntroductionAgent',
}

watch(demoOpen, (isOpen) => {
  document.body.classList.toggle('demo-is-open', isOpen)
})

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    demoOpen.value = false
  }
}

let revealObserver: IntersectionObserver | undefined

onMounted(() => {
  window.addEventListener('keydown', handleEscape)

  const savedTheme = window.localStorage.getItem('portfolio-theme')
  darkMode.value = savedTheme ? savedTheme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  syncThemeColor()

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const revealElements = document.querySelectorAll<HTMLElement>('[data-reveal]')

  document.documentElement.classList.add('motion-ready')
  if (reduceMotion || !('IntersectionObserver' in window)) {
    revealElements.forEach((element) => element.classList.add('is-visible'))
    return
  }

  revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return
        entry.target.classList.add('is-visible')
        revealObserver?.unobserve(entry.target)
      })
    },
    { threshold: 0.1, rootMargin: '0px 0px -4% 0px' },
  )
  revealElements.forEach((element) => revealObserver?.observe(element))
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleEscape)
  revealObserver?.disconnect()
  document.documentElement.classList.remove('motion-ready')
  document.body.classList.remove('demo-is-open')
})

function toggleTheme() {
  darkMode.value = !darkMode.value
  window.localStorage.setItem('portfolio-theme', darkMode.value ? 'dark' : 'light')
  syncThemeColor()
}

function syncThemeColor() {
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', darkMode.value ? '#0a0a0f' : '#f4f4f2')
}
</script>

<template>
  <div class="portfolio-page" :class="{ 'dark-mode': darkMode }">
    <header class="site-header">
      <span class="wordmark">TZ<span>.</span></span>
      <p class="header-note">个人主页 · Portfolio</p>
      <button class="theme-toggle" type="button" :aria-label="darkMode ? '切换到浅色模式' : '切换到深色模式'" @click="toggleTheme">
        <Sun v-if="darkMode" :size="17" />
        <Moon v-else :size="17" />
      </button>
    </header>

    <main class="bento-grid">
      <article class="card card-profile" data-reveal style="--reveal-delay: 0ms">
        <div class="profile-top">
          <span class="profile-avatar">TZ</span>
          <span class="profile-status"><i></i> 计算机科学与技术 · 在校</span>
        </div>
        <h1>{{ profile.name }}</h1>
        <p class="profile-intro">
          计算机科学与技术本科生，主要使用 <strong>Python</strong> 构建后端服务、AI 应用与完整 Web 产品。
        </p>
      </article>

      <a class="card card-github" :href="profile.github" target="_blank" rel="noreferrer" data-reveal style="--reveal-delay: 60ms">
        <span class="card-icon"><Github :size="22" /></span>
        <span class="card-github-text">
          <strong>GitHub</strong>
          <small>@yee211</small>
        </span>
        <ArrowUpRight class="card-arrow" :size="18" />
      </a>

      <article class="card card-mail" data-reveal style="--reveal-delay: 120ms">
        <span class="card-label">邮箱 · Contact</span>
        <a :href="`mailto:${profile.email}`"><Mail :size="15" /><strong>Gmail</strong><small>{{ profile.email }}</small></a>
        <a :href="`mailto:${profile.qqEmail}`"><Mail :size="15" /><strong>QQ 邮箱</strong><small>{{ profile.qqEmail }}</small></a>
      </article>

      <article class="card card-stack" data-reveal style="--reveal-delay: 180ms">
        <div class="stack-heading">
          <span class="card-label">技术栈 · Stack</span>
          <Sparkles :size="16" />
        </div>
        <div class="stack-groups">
          <div>
            <Braces :size="17" />
            <div><strong>编程语言</strong><small>Python · TypeScript · SQL</small></div>
          </div>
          <div>
            <Layers3 :size="17" />
            <div><strong>后端框架</strong><small>FastAPI · Pydantic · SSE</small></div>
          </div>
          <div>
            <Database :size="17" />
            <div><strong>数据与检索</strong><small>PostgreSQL · pgvector · Redis</small></div>
          </div>
          <div>
            <Bot :size="17" />
            <div><strong>AI 与工程化</strong><small>RAG · LangChain · Docker</small></div>
          </div>
        </div>
      </article>

      <article id="work" class="card card-project" data-reveal style="--reveal-delay: 240ms">
        <div class="project-info">
          <p class="project-type">SELECTED PROJECT</p>
          <h2>校园智答 <span class="live-badge"><i></i>LIVE</span></h2>
          <p class="project-summary">
            结合结构化查询与 RAG 混合检索，为长沙工业学院校园与招生问题提供准确、可追溯的智能回答。
          </p>
          <ul class="project-tags">
            <li>FastAPI</li><li>Vue 3</li><li>PostgreSQL</li><li>pgvector</li><li>Redis</li>
          </ul>
          <div class="project-actions">
            <button class="project-button" type="button" @click="demoOpen = true">
              在线体验 <ArrowRight :size="15" />
            </button>
            <a class="project-source" :href="profile.projectSource" target="_blank" rel="noreferrer">
              <Github :size="14" /> 查看源码
            </a>
          </div>
        </div>

        <div class="project-visual" aria-hidden="true">
          <div class="mock-window">
            <div class="mock-bar"><span></span><span></span><span></span></div>
            <div class="mock-chat">
              <div class="mock-bot">
                <span class="mock-bot-avatar"><Bot :size="13" /></span>
                <p>你好，我是校园智答，学校与招生信息都可以问我</p>
              </div>
              <p class="mock-user">学校的录取分数线是多少？</p>
              <div class="mock-bot">
                <span class="mock-bot-avatar"><Sparkles :size="13" /></span>
                <p class="mock-typing"><i></i><i></i><i></i></p>
              </div>
            </div>
          </div>
          <span class="visual-badge">LIVE<br />RAG</span>
        </div>
      </article>

      <button class="card card-theme" type="button" data-reveal style="--reveal-delay: 300ms" @click="toggleTheme">
        <Sun v-if="darkMode" :size="26" />
        <Moon v-else :size="26" />
        <strong>{{ darkMode ? '切换浅色模式' : '切换深色模式' }}</strong>
      </button>
    </main>

    <footer class="site-footer">
      <p>© 2026 {{ profile.name }} · Vue 3 构建</p>
      <a :href="profile.github" target="_blank" rel="noreferrer">github.com/yee211</a>
    </footer>

    <Teleport to="body">
      <Transition name="demo">
        <div v-if="demoOpen" class="demo-overlay" role="dialog" aria-modal="true" aria-label="校园智答在线体验">
          <div class="demo-toolbar">
            <div><span></span><strong>校园智答 · 在线体验</strong></div>
            <button type="button" aria-label="关闭在线体验" @click="demoOpen = false"><X :size="20" /></button>
          </div>
          <div class="demo-stage">
            <SchoolAssistant />
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
