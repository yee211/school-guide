<script setup lang="ts">
import { computed } from 'vue'
import { knowledgeModules, type KnowledgeModuleId } from '../data/knowledgeModules'

const props = defineProps<{ activeId: KnowledgeModuleId; disabled: boolean; hasConversation: boolean }>()
defineEmits<{
  select: [id: KnowledgeModuleId]
  ask: [question: string]
  resume: []
  preview: [source: string]
}>()
const activeModule = computed(() => knowledgeModules.find((item) => item.id === props.activeId) ?? knowledgeModules[0])

function sourceTitle(source: string): string {
  const filename = source.split('/').pop() ?? source
  const titles: Record<string, string> = {
    'school_overview.md': '学校概况',
    'school_life.txt': '校园生活',
    'library.md': '图书馆服务',
  }
  return titles[filename] ?? filename.replace(/\.[^.]+$/, '')
}
</script>

<template>
  <section class="welcome knowledge-explorer" aria-labelledby="knowledge-heading">
    <div class="welcome-icon"><component :is="activeModule.icon" :size="30" /></div>
    <p class="eyebrow">长沙工业学院 · 知识库导览</p>
    <h2 id="knowledge-heading">{{ activeModule.label }}</h2>
    <nav class="knowledge-tabs" aria-label="知识模块">
      <button v-for="item in knowledgeModules" :key="item.id" type="button"
        :aria-pressed="item.id === activeId" @click="$emit('select', item.id)">{{ item.label }}</button>
    </nav>
    <p class="welcome-copy">{{ activeModule.description }}</p>
    <div class="suggestion-grid">
      <button v-for="question in activeModule.questions" :key="question" type="button"
        :disabled="disabled" @click="$emit('ask', question)">
        <component :is="activeModule.icon" :size="20" />
        <span>{{ question }}</span>
      </button>
    </div>
    <p class="knowledge-hint">{{ disabled ? '正在回答中，请返回对话查看或停止生成。' : '点击问题即可提问，也可以在下方输入具体问题。' }}</p>
    <details class="knowledge-sources">
      <summary>本模块资料（{{ activeModule.sources.length }} 份）</summary>
      <ul><li v-for="source in activeModule.sources" :key="source" :title="source"><button type="button" class="source-link" @click="$emit('preview', source)">{{ sourceTitle(source) }}</button><br /><small>{{ source }}</small></li></ul>
    </details>
    <button v-if="hasConversation" class="resume-chat" type="button" @click="$emit('resume')">返回当前对话</button>
  </section>
</template>
