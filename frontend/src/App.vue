<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import {
  ArrowRight,
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
const pageRoot = ref<HTMLElement | null>(null)
type ModuleKey = 'home' | 'work'
const activeModule = ref<ModuleKey>('home')
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
let pointerFrame = 0
let pointerX = 0
let pointerY = 0
let motionEnabled = false

function applyPointerEffect() {
  pointerFrame = 0
  const root = pageRoot.value
  if (!root) return

  const normalizedX = pointerX / window.innerWidth - 0.5
  const normalizedY = pointerY / window.innerHeight - 0.5
  root.style.setProperty('--pointer-x', `${pointerX}px`)
  root.style.setProperty('--pointer-y', `${pointerY}px`)
  root.style.setProperty('--pointer-opacity', '1')
  root.style.setProperty('--hero-shift-x', `${normalizedX * 16}px`)
  root.style.setProperty('--hero-shift-y', `${normalizedY * 12}px`)
  root.style.setProperty('--hero-rotate-x', `${normalizedY * -3}deg`)
  root.style.setProperty('--hero-rotate-y', `${normalizedX * 4}deg`)
}

function handlePointerMove(event: PointerEvent) {
  if (!motionEnabled) return
  pointerX = event.clientX
  pointerY = event.clientY
  if (!pointerFrame) pointerFrame = window.requestAnimationFrame(applyPointerEffect)
}

function resetPointerEffect() {
  const root = pageRoot.value
  if (!root) return
  root.style.setProperty('--pointer-opacity', '0')
  root.style.setProperty('--hero-shift-x', '0px')
  root.style.setProperty('--hero-shift-y', '0px')
  root.style.setProperty('--hero-rotate-x', '0deg')
  root.style.setProperty('--hero-rotate-y', '0deg')
}

onMounted(() => {
  window.addEventListener('keydown', handleEscape)

  const savedTheme = window.localStorage.getItem('portfolio-theme')
  darkMode.value = savedTheme ? savedTheme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  syncThemeColor()

  const initialModule = window.location.hash.replace('#', '')
  if (initialModule === 'work') activeModule.value = 'work'
  if (initialModule === 'about' || initialModule === 'stack' || initialModule === 'profile' || initialModule === 'contact') activeModule.value = 'home'

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  motionEnabled = !reduceMotion && window.matchMedia('(pointer: fine)').matches
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
    { threshold: 0.12, rootMargin: '0px 0px -7% 0px' },
  )
  revealElements.forEach((element) => revealObserver?.observe(element))
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleEscape)
  revealObserver?.disconnect()
  if (pointerFrame) window.cancelAnimationFrame(pointerFrame)
  document.documentElement.classList.remove('motion-ready')
  document.body.classList.remove('demo-is-open')
})

function toggleTheme() {
  darkMode.value = !darkMode.value
  window.localStorage.setItem('portfolio-theme', darkMode.value ? 'dark' : 'light')
  syncThemeColor()
}

function syncThemeColor() {
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', darkMode.value ? '#080b18' : '#eef3ff')
}

function switchModule(module: ModuleKey) {
  activeModule.value = module
  window.history.replaceState(null, '', module === 'home' ? window.location.pathname : `#${module}`)
}
</script>

<template>
  <div
    ref="pageRoot"
    class="portfolio-page"
    :class="{ 'dark-mode': darkMode }"
    @pointermove="handlePointerMove"
    @pointerleave="resetPointerEffect"
  >
    <video class="portfolio-video" autoplay muted loop playsinline preload="metadata" aria-hidden="true" tabindex="-1">
      <source src="/portfolio-background.mp4" type="video/mp4" />
    </video>

    <header class="site-header">
      <button class="wordmark" type="button" aria-label="谭锃首页" @click="switchModule('home')">TZ<span>.</span></button>

      <nav class="module-nav" aria-label="模块切换">
        <button type="button" :class="{ active: activeModule === 'home' }" @click="switchModule('home')">首页</button>
        <button type="button" :class="{ active: activeModule === 'work' }" @click="switchModule('work')">项目</button>
      </nav>

      <button class="theme-toggle" type="button" :aria-label="darkMode ? '切换到浅色模式' : '切换到深色模式'" @click="toggleTheme">
        <Sun v-if="darkMode" :size="17" />
        <Moon v-else :size="17" />
      </button>
    </header>

    <main id="top" class="module-view">
      <Transition name="module" mode="out-in">
        <section v-if="activeModule === 'home'" key="home" class="module-panel profile-panel section-shell">
          <div class="profile-summary-card">
            <div class="profile-intro">
              <p class="section-index">01 / PROFILE</p>
              <h2>{{ profile.name }}</h2>
              <p>计算机科学与技术本科生，主要使用 <strong>Python</strong> 构建后端服务、AI 应用与完整 Web 产品。</p>
              <div class="profile-links home-profile-links">
                <a class="github-profile-link" :href="profile.github" target="_blank" rel="noreferrer" aria-label="访问 GitHub 主页">
                  <Github :size="19" />
                  <span><strong>GitHub</strong><small>@yee211</small></span>
                </a>
                <div class="combined-email-card">
                  <a :href="`mailto:${profile.email}`" aria-label="发送 Gmail 邮件">
                    <Mail :size="19" />
                    <span><strong>Gmail</strong><small>{{ profile.email }}</small></span>
                  </a>
                  <a :href="`mailto:${profile.qqEmail}`" aria-label="发送 QQ 邮件">
                    <Mail :size="19" />
                    <span><strong>QQ 邮箱</strong><small>{{ profile.qqEmail }}</small></span>
                  </a>
                </div>
              </div>
            </div>

            <div class="embedded-stack">
              <div class="embedded-stack-heading">
                <p class="section-index">TECH STACK</p>
                <h3>技术栈</h3>
              </div>
              <div class="stack-groups">
                <article>
                  <Braces :size="20" />
                  <h4>编程语言</h4>
                  <p>Python · TypeScript · SQL · 异步编程 · 类型标注</p>
                </article>
                <article>
                  <Layers3 :size="20" />
                  <h4>后端框架</h4>
                  <p>FastAPI · Pydantic · Uvicorn · REST API · SSE</p>
                </article>
                <article>
                  <Sparkles :size="20" />
                  <h4>数据与检索</h4>
                  <p>PostgreSQL · pgvector · Redis · HNSW · 混合检索</p>
                </article>
                <article>
                  <Database :size="20" />
                  <h4>AI 与工程化</h4>
                  <p>RAG · LangChain · Docker · Nginx · Linux</p>
                </article>
              </div>
            </div>
          </div>
        </section>

        <section v-else key="work" class="module-panel work-panel section-shell">
          <div class="section-heading">
          <div>
            <p class="section-index">02 / SELECTED WORK</p>
            <h2>精选项目</h2>
          </div>
          <p>Python、RAG 与 Web 工程实践。</p>
        </div>

          <article class="featured-project">
            <div class="project-content">
              <span class="project-number">PROJECT / 01</span>
              <div class="project-icon"><Bot :size="27" /></div>
              <p class="project-type">PYTHON · RAG · FULL STACK</p>
              <h3>校园智答</h3>
              <p class="project-summary">结合结构化查询与 RAG 混合检索，为长沙工业学院校园与招生问题提供准确、可追溯的智能回答。</p>
              <ul class="project-tags">
                <li>FastAPI</li><li>Vue 3</li><li>PostgreSQL</li><li>pgvector</li><li>Redis</li>
              </ul>
              <div class="project-actions">
                <button class="project-button" type="button" @click="demoOpen = true">在线体验 <ArrowRight :size="16" /></button>
                <a class="project-source" :href="profile.projectSource" target="_blank" rel="noreferrer"><Github :size="15" /> 查看源码</a>
              </div>
            </div>

            <div class="project-visual" aria-label="校园智答界面预览">
              <div class="browser-frame">
                <div class="browser-bar"><span></span><span></span><span></span><div>campus-assistant.local</div></div>
                <div class="browser-body">
                  <aside class="mock-sidebar">
                    <div class="mock-logo">校园智答</div>
                    <i></i><i></i><i></i><i></i>
                  </aside>
                  <div class="mock-chat">
                    <div class="mock-chat-head"><span>●</span> 校园智能问答</div>
                    <div class="mock-welcome">
                      <div><Bot :size="23" /></div>
                      <strong>你好，我是校园智答</strong>
                      <p>关于学校、专业与招生信息，都可以问我</p>
                      <span></span><span></span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="visual-badge">LIVE<br />RAG</div>
            </div>
          </article>
        </section>

      </Transition>
    </main>

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
