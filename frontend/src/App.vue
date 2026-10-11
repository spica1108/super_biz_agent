<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import { marked } from 'marked'
import 'highlight.js/styles/github.css'

type ChatMode = 'quick' | 'stream'
type Message = {
  type: 'user' | 'assistant'
  content: string
  timestamp: string
  details?: string[]
  pending?: boolean
}
type ChatHistory = {
  id: string
  title: string
  messages: Message[]
  createdAt: string
  updatedAt: string
}
type Notice = { id: number; text: string; kind: 'info' | 'success' | 'warning' | 'error' }
type ApiEnvelope<T = unknown> = { code?: number; message?: string; data?: T }
type SsePayload = {
  type?: string
  data?: string | null
  message?: string
  report?: string
  response?: string
  plan?: string[]
  current_step?: string
  stage?: string
}

marked.setOptions({ breaks: true, gfm: true })

const sessionId = ref(makeSessionId())
const mode = ref<ChatMode>('quick')
const draft = ref('')
const messages = ref<Message[]>([])
const histories = ref<ChatHistory[]>(loadHistories())
const busy = ref(false)
const toolsOpen = ref(false)
const modeOpen = ref(false)
const uploadName = ref('')
const notices = ref<Notice[]>([])
const scrollArea = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
let noticeId = 0
let noticeTimers: number[] = []

const centered = computed(() => messages.value.length === 0)
const modeLabel = computed(() => (mode.value === 'quick' ? '快速' : '流式'))

function makeSessionId(): string {
  return `session_${Math.random().toString(36).slice(2, 11)}_${Date.now()}`
}

function loadHistories(): ChatHistory[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem('chatHistories') ?? '[]')
    return Array.isArray(parsed) ? (parsed as ChatHistory[]).slice(0, 50) : []
  } catch {
    return []
  }
}

function persistHistories(): void {
  try {
    localStorage.setItem('chatHistories', JSON.stringify(histories.value.slice(0, 50)))
  } catch {
    notify('本地历史记录保存失败', 'warning')
  }
}

function saveCurrentHistory(): void {
  if (!messages.value.length) return
  const firstUser = messages.value.find((item) => item.type === 'user')
  const title = firstUser?.content.slice(0, 30) || '新对话'
  const existing = histories.value.find((item) => item.id === sessionId.value)
  const now = new Date().toISOString()
  if (existing) {
    existing.messages = [...messages.value]
    existing.title = title
    existing.updatedAt = now
  } else {
    histories.value.unshift({
      id: sessionId.value,
      title: title.length === 30 && firstUser && firstUser.content.length > 30 ? `${title}...` : title,
      messages: [...messages.value],
      createdAt: now,
      updatedAt: now,
    })
    histories.value = histories.value.slice(0, 50)
  }
  persistHistories()
}

function notify(text: string, kind: Notice['kind'] = 'info'): void {
  const notice = { id: ++noticeId, text, kind }
  notices.value.push(notice)
  const timer = window.setTimeout(() => {
    notices.value = notices.value.filter((item) => item.id !== notice.id)
    noticeTimers = noticeTimers.filter((item) => item !== timer)
  }, 3200)
  noticeTimers.push(timer)
}

function safeMarkdown(value: string): string {
  const html = marked.parse(value, { async: false })
  const clean = DOMPurify.sanitize(html)
  const fragment = document.createElement('template')
  fragment.innerHTML = clean
  fragment.content.querySelectorAll('pre code').forEach((block) => {
    if (!block.classList.contains('hljs')) hljs.highlightElement(block as HTMLElement)
  })
  return fragment.innerHTML
}

async function scrollToLatest(): Promise<void> {
  await nextTick()
  if (scrollArea.value) scrollArea.value.scrollTop = scrollArea.value.scrollHeight
}

function addMessage(type: Message['type'], content: string, options: Partial<Message> = {}): Message {
  const message: Message = { type, content, timestamp: new Date().toISOString(), ...options }
  messages.value.push(message)
  void scrollToLatest()
  return message
}

function resetChat(): void {
  if (busy.value) {
    notify('请等待当前操作完成', 'warning')
    return
  }
  saveCurrentHistory()
  messages.value = []
  sessionId.value = makeSessionId()
  mode.value = 'quick'
  modeOpen.value = false
  toolsOpen.value = false
}

async function readEventStream(response: Response, onData: (payload: SsePayload | string) => boolean | void): Promise<void> {
  if (!response.body) throw new Error('服务器未返回流式内容')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let stopped = false
  try {
    while (!stopped) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (!raw || raw === '[DONE]') continue
        let parsed: SsePayload | string
        try {
          parsed = JSON.parse(raw) as SsePayload
        } catch {
          parsed = raw
        }
        stopped = onData(parsed) === true
        if (stopped) break
      }
      if (done) {
        if (buffer.startsWith('data:')) {
          const raw = buffer.slice(5).trim()
          if (raw && raw !== '[DONE]') {
            let parsed: SsePayload | string
            try { parsed = JSON.parse(raw) as SsePayload } catch { parsed = raw }
            onData(parsed)
          }
        }
        break
      }
    }
  } finally {
    reader.releaseLock()
  }
}

async function sendMessage(): Promise<void> {
  const question = draft.value.trim()
  if (!question) {
    notify('请输入消息内容', 'warning')
    return
  }
  if (busy.value) return
  draft.value = ''
  addMessage('user', question)
  busy.value = true
  try {
    if (mode.value === 'quick') await sendQuick(question)
    else await sendStream(question)
  } catch (error) {
    addMessage('assistant', `抱歉，请求失败：${errorMessage(error)}`)
  } finally {
    busy.value = false
    saveCurrentHistory()
  }
}

async function sendQuick(question: string): Promise<void> {
  const pending = addMessage('assistant', '正在思考...', { pending: true })
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ Id: sessionId.value, Question: question }),
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const envelope = (await response.json()) as ApiEnvelope<{ success?: boolean; answer?: string; errorMessage?: string }>
    messages.value = messages.value.filter((item) => item !== pending)
    const result = envelope.data
    if ((envelope.code === 200 || envelope.message === 'success') && result?.success) {
      addMessage('assistant', result.answer || '（无回复内容）')
      return
    }
    throw new Error(result?.errorMessage || envelope.message || '请求失败')
  } catch (error) {
    messages.value = messages.value.filter((item) => item !== pending)
    throw error
  }
}

async function sendStream(question: string): Promise<void> {
  const response = await fetch('/api/chat_stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ Id: sessionId.value, Question: question }),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const message = addMessage('assistant', '', { pending: true })
  let content = ''
  await readEventStream(response, (event) => {
    if (typeof event === 'string') content += event
    else if (event.type === 'content') content += event.data || ''
    else if (event.type === 'error') throw new Error(event.data || event.message || '流式请求失败')
    else if (event.type === 'done') return true
    message.content = content
    void scrollToLatest()
  })
  message.pending = false
  if (!content) message.content = '（无回复内容）'
}

async function loadHistory(history: ChatHistory): Promise<void> {
  if (busy.value) return
  saveCurrentHistory()
  sessionId.value = history.id
  messages.value = [...history.messages]
  try {
    const response = await fetch(`/api/chat/session/${encodeURIComponent(history.id)}`)
    if (response.ok) {
      const payload = (await response.json()) as { history?: Array<{ role: string; content: string; timestamp?: string }> }
      if (payload.history?.length) {
        messages.value = payload.history.map((item) => ({
          type: item.role === 'user' ? 'user' : 'assistant',
          content: item.content,
          timestamp: item.timestamp || new Date().toISOString(),
        }))
      }
    }
  } catch {
    notify('无法从服务端读取会话，已显示本地记录', 'warning')
  }
  void scrollToLatest()
}

async function deleteHistory(history: ChatHistory): Promise<void> {
  if (busy.value) return
  try {
    const response = await fetch('/api/chat/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: history.id }),
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = (await response.json()) as { status?: string; message?: string }
    if (result.status !== 'success') throw new Error(result.message || '清空会话失败')
    histories.value = histories.value.filter((item) => item.id !== history.id)
    persistHistories()
    if (sessionId.value === history.id) {
      messages.value = []
      sessionId.value = makeSessionId()
    }
    notify('会话已清空', 'success')
  } catch (error) {
    notify(`删除失败：${errorMessage(error)}`, 'error')
  }
}

function chooseFile(): void {
  toolsOpen.value = false
  fileInput.value?.click()
}

async function uploadFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!/\.(txt|md|markdown)$/i.test(file.name)) {
    notify('只支持 TXT 或 Markdown 文件', 'error')
    input.value = ''
    return
  }
  if (file.size > 50 * 1024 * 1024) {
    notify('文件大小不能超过 50 MB', 'error')
    input.value = ''
    return
  }
  busy.value = true
  uploadName.value = file.name
  try {
    const body = new FormData()
    body.append('file', file)
    const response = await fetch('/api/upload', { method: 'POST', body })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const envelope = (await response.json()) as ApiEnvelope
    if (envelope.code !== 200 && envelope.message !== 'success') throw new Error(envelope.message || '上传失败')
    addMessage('assistant', `${file.name} 上传到知识库成功`)
    saveCurrentHistory()
  } catch (error) {
    notify(`文件上传失败：${errorMessage(error)}`, 'error')
  } finally {
    input.value = ''
    uploadName.value = ''
    busy.value = false
  }
}

function appendAIOpsEvent(current: string, event: SsePayload): string {
  switch (event.type) {
    case 'content': return current + (event.data || '')
    case 'plan': return `${current}\n\n## 执行计划\n${event.message || (event.plan || []).join('\n')}\n`
    case 'step_complete': return `${current}\n- ${event.message || event.current_step || '步骤完成'}\n`
    case 'status': return `${current}\n${event.message || event.stage || ''}\n`
    case 'report': return `${current}\n\n## 诊断报告\n\n${event.report || ''}\n`
    case 'complete': return event.response ? `${current}\n\n${event.response}` : current
    default: return current
  }
}

async function triggerAIOps(): Promise<void> {
  if (busy.value) return
  resetChat()
  const pending = addMessage('assistant', '正在分析告警与运行状态…', { pending: true })
  busy.value = true
  try {
    const response = await fetch('/api/aiops', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId.value }),
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    let content = ''
    await readEventStream(response, (event) => {
      if (typeof event === 'string') {
        content += event
      } else {
        if (event.type === 'error') throw new Error(event.message || String(event.data || '分析失败'))
        content = appendAIOpsEvent(content, event)
      }
      pending.content = content || '正在分析告警与运行状态…'
      if (typeof event !== 'string' && (event.type === 'complete' || event.type === 'done')) return true
      void scrollToLatest()
    })
    pending.content = content || '诊断流程已完成，但服务未返回报告内容。'
    pending.pending = false
    saveCurrentHistory()
  } catch (error) {
    pending.content = `智能运维分析失败：${errorMessage(error)}`
    pending.pending = false
  } finally {
    busy.value = false
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function onDocumentClick(event: MouseEvent): void {
  const target = event.target
  if (target instanceof Element && !target.closest('.popover-anchor')) {
    toolsOpen.value = false
    modeOpen.value = false
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    toolsOpen.value = false
    modeOpen.value = false
  }
}

watch(messages, saveCurrentHistory, { deep: true })
onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
  noticeTimers.forEach(window.clearTimeout)
})
</script>

<template>
  <main class="workspace">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark">S</span><div><strong>SuperBizAgent</strong><small>智能 OnCall 助手</small></div></div>
      <button class="new-chat" type="button" :disabled="busy" @click="resetChat"><span aria-hidden="true">＋</span>新建对话</button>
      <div class="history-heading"><span>近期对话</span><span>{{ histories.length }}</span></div>
      <nav class="history-list" aria-label="近期对话">
        <div v-for="item in histories" :key="item.id" class="history-row" :class="{ selected: item.id === sessionId }">
          <button class="history-select" type="button" :title="item.title" @click="loadHistory(item)">{{ item.title }}</button>
          <button class="history-delete" type="button" :aria-label="`删除${item.title}`" title="删除会话" @click="deleteHistory(item)">×</button>
        </div>
        <p v-if="!histories.length" class="empty-history">暂无历史对话</p>
      </nav>
      <div class="sidebar-foot"><span class="status-dot"></span>服务工作区</div>
    </aside>

    <section class="main-panel">
      <header class="topbar">
        <div class="topbar-title"><span class="online-dot"></span><span>智能运维工作台</span></div>
        <button class="aiops-button" type="button" :disabled="busy" @click="triggerAIOps">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.2 5.1L20 10l-5.8 1.9L12 17l-2.2-5.1L4 10l5.8-1.9L12 3Zm6 12 .9 2.1L21 18l-2.1.9L18 21l-.9-2.1L15 18l2.1-.9L18 15Z" /></svg>
          AI Ops 分析
        </button>
      </header>

      <div class="conversation" :class="{ centered }" ref="scrollArea" aria-live="polite">
        <div v-if="centered" class="welcome">
          <div class="welcome-icon"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 4 19 12l9 4-9 4-3 8-3-8-9-4 9-4 3-8Z" /></svg></div>
          <p class="eyebrow">ON-CALL ASSISTANT</p>
          <h1>你好，需要排查什么问题？</h1>
          <p class="welcome-copy">提问、检索知识库，或启动 AI Ops 诊断。</p>
        </div>
        <article v-for="(message, index) in messages" :key="`${message.timestamp}-${index}`" class="message" :class="message.type">
          <div v-if="message.type === 'assistant'" class="assistant-mark" aria-hidden="true">✦</div>
          <div class="message-body">
            <div v-if="message.pending && !message.content" class="message-text pending-text">正在生成回答…</div>
            <div v-else-if="message.type === 'assistant'" class="message-text markdown" :class="{ streaming: message.pending }" v-html="safeMarkdown(message.content)" />
            <div v-else class="message-text">{{ message.content }}</div>
            <time>{{ new Date(message.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time>
          </div>
        </article>
      </div>

      <div class="composer-wrap">
        <form class="composer" @submit.prevent="sendMessage">
          <textarea v-model="draft" rows="1" maxlength="1000" :disabled="busy" placeholder="问问智能 OnCall 助手" @keydown.enter.exact.prevent="sendMessage" />
          <div class="composer-toolbar">
            <div class="popover-anchor">
              <button class="icon-button" type="button" :aria-expanded="toolsOpen" title="附件和工具" @click.stop="toolsOpen = !toolsOpen">＋</button>
              <div v-if="toolsOpen" class="popover tools-popover">
                <button class="popover-item" type="button" @click="chooseFile"><span class="file-symbol">↥</span>上传知识文件</button>
              </div>
            </div>
            <div class="composer-actions">
              <div class="popover-anchor">
                <button class="mode-button" type="button" :aria-expanded="modeOpen" @click.stop="modeOpen = !modeOpen">{{ modeLabel }}模式 <span>⌄</span></button>
                <div v-if="modeOpen" class="popover mode-popover">
                  <button class="popover-item" :class="{ active: mode === 'quick' }" type="button" @click="mode = 'quick'; modeOpen = false">快速回答<small>普通请求响应</small></button>
                  <button class="popover-item" :class="{ active: mode === 'stream' }" type="button" @click="mode = 'stream'; modeOpen = false">流式回答<small>实时接收生成内容</small></button>
                </div>
              </div>
              <button class="send-button" type="submit" :disabled="busy || !draft.trim()" title="发送消息" aria-label="发送消息">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12 20 4l-5.5 16-3-6-7.5-2Zm7.5 2L20 4" /></svg>
              </button>
            </div>
          </div>
        </form>
        <p class="composer-note">{{ uploadName ? `正在上传 ${uploadName}` : 'AI 生成内容请结合实际情况核验' }}</p>
        <input ref="fileInput" class="file-input" type="file" accept=".txt,.md,.markdown" @change="uploadFile" />
      </div>
    </section>

    <TransitionGroup name="notice" tag="div" class="notice-stack" aria-live="polite">
      <div v-for="notice in notices" :key="notice.id" class="notice" :class="notice.kind">{{ notice.text }}</div>
    </TransitionGroup>
  </main>
</template>

<style>
:root { font-family: 'DM Sans', 'Noto Sans SC', sans-serif; color: #182230; background: #f7f8fa; font-synthesis: none; text-rendering: optimizeLegibility; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; min-height: 100vh; }
button, textarea { font: inherit; }
button { cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .55; }
.workspace { display: flex; width: 100%; height: 100vh; min-height: 560px; overflow: hidden; background: #fff; }
.sidebar { display: flex; flex: 0 0 264px; flex-direction: column; padding: 22px 14px 14px; color: #d6dbe3; background: #19232d; }
.brand { display: flex; align-items: center; gap: 11px; min-height: 45px; padding: 0 8px; }
.brand-mark { display: grid; width: 34px; height: 34px; place-items: center; border-radius: 9px; color: #fff; background: #247b69; font-weight: 700; }
.brand strong, .brand small { display: block; }
.brand strong { color: #fff; font-size: 14px; }
.brand small { margin-top: 3px; color: #8e9aa8; font-size: 11px; }
.new-chat { display: flex; align-items: center; gap: 10px; height: 40px; margin: 28px 2px 24px; padding: 0 12px; border: 1px solid #42505f; border-radius: 6px; color: #eef2f5; background: transparent; text-align: left; font-size: 13px; }
.new-chat span { font-size: 20px; line-height: 1; }
.new-chat:hover { background: #263541; }
.history-heading { display: flex; justify-content: space-between; padding: 0 9px 10px; color: #93a0ad; font-size: 11px; }
.history-heading span + span { color: #768594; }
.history-list { flex: 1; overflow-y: auto; }
.history-row { display: flex; align-items: center; gap: 4px; margin: 2px 0; padding: 2px 4px; border-radius: 5px; }
.history-row:hover, .history-row.selected { background: #283744; }
.history-select { min-width: 0; flex: 1; overflow: hidden; padding: 7px 6px; border: 0; color: #d4dbe2; background: transparent; text-align: left; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.history-delete { width: 27px; height: 27px; border: 0; border-radius: 4px; color: #9ba7b2; background: transparent; font-size: 18px; opacity: 0; }
.history-row:hover .history-delete, .history-delete:focus-visible { opacity: 1; }
.history-delete:hover { color: #fff; background: #44515d; }
.empty-history { padding: 8px; color: #798694; font-size: 12px; }
.sidebar-foot { display: flex; align-items: center; gap: 8px; padding: 13px 9px 2px; border-top: 1px solid #34414d; color: #93a0ad; font-size: 11px; }
.status-dot, .online-dot { width: 7px; height: 7px; border-radius: 50%; background: #52b788; }
.main-panel { display: flex; min-width: 0; flex: 1; flex-direction: column; background: #fff; }
.topbar { display: flex; height: 62px; flex: 0 0 62px; align-items: center; justify-content: space-between; padding: 0 28px; border-bottom: 1px solid #e9edf0; }
.topbar-title { display: flex; align-items: center; gap: 9px; color: #536170; font-size: 12px; font-weight: 600; }
.aiops-button { display: flex; height: 34px; align-items: center; gap: 8px; padding: 0 12px; border: 1px solid #d8e5df; border-radius: 5px; color: #216b59; background: #f7fbf9; font-size: 12px; font-weight: 600; }
.aiops-button:hover { background: #edf7f2; }
.aiops-button svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-linejoin: round; stroke-width: 1.6; }
.conversation { display: flex; min-height: 0; flex: 1; flex-direction: column; gap: 25px; overflow: auto; padding: 34px max(24px, calc((100% - 820px) / 2)) 24px; scroll-behavior: smooth; }
.conversation.centered { justify-content: center; }
.welcome { margin: auto 0; padding-bottom: 24px; text-align: center; }
.welcome-icon { display: grid; width: 46px; height: 46px; margin: 0 auto 22px; place-items: center; border: 1px solid #d7e8e1; border-radius: 13px; color: #297963; background: #f1f8f5; }
.welcome-icon svg { width: 24px; fill: currentColor; }
.eyebrow { color: #75838f; font-size: 10px; font-weight: 700; }
.welcome h1 { margin: 10px 0; color: #25323d; font-size: 22px; font-weight: 600; }
.welcome-copy { color: #7b8792; font-size: 13px; }
.message { display: flex; width: 100%; align-items: flex-start; gap: 11px; }
.message.user { justify-content: flex-end; }
.assistant-mark { display: grid; width: 27px; height: 27px; flex: 0 0 27px; place-items: center; border-radius: 8px; color: #246f5c; background: #eaf4ef; }
.message-body { min-width: 0; max-width: min(720px, 88%); }
.message.user .message-body { max-width: min(600px, 82%); }
.message-text { padding: 11px 14px; border: 1px solid #e8edf0; border-radius: 5px 12px 12px; color: #26333d; background: #fbfcfc; line-height: 1.65; font-size: 13px; overflow-wrap: anywhere; }
.message.user .message-text { border-color: #dce8e3; border-radius: 12px 5px 12px 12px; background: #eff6f2; }
.message-body time { display: block; margin: 5px 3px 0; color: #a1aab2; font-size: 10px; }
.message.user time { text-align: right; }
.pending-text { color: #7c8994; }
.streaming::after { content: '▋'; margin-left: 2px; color: #297963; animation: blink 1s steps(2, start) infinite; }
@keyframes blink { to { visibility: hidden; } }
.markdown :first-child { margin-top: 0; }
.markdown :last-child { margin-bottom: 0; }
.markdown h1, .markdown h2, .markdown h3 { margin: 18px 0 8px; font-size: 15px; }
.markdown p, .markdown ul, .markdown ol, .markdown blockquote { margin: 8px 0; }
.markdown ul, .markdown ol { padding-left: 22px; }
.markdown code { padding: 2px 4px; border-radius: 3px; background: #eff2f3; font-family: Consolas, monospace; font-size: .92em; }
.markdown pre { overflow: auto; margin: 10px 0; padding: 12px; border: 1px solid #e4e9ec; border-radius: 5px; background: #f7f9fa; }
.markdown pre code { padding: 0; background: transparent; }
.markdown blockquote { padding-left: 12px; border-left: 3px solid #91b7a8; color: #66747e; }
.markdown table { width: 100%; border-collapse: collapse; }
.markdown th, .markdown td { padding: 6px 8px; border: 1px solid #dfe5e8; text-align: left; }
.markdown a { color: #236e5a; }
.composer-wrap { width: min(820px, calc(100% - 48px)); margin: 0 auto; padding: 10px 0 12px; }
.composer { padding: 10px 12px 8px; border: 1px solid #dce3e7; border-radius: 8px; background: #fff; box-shadow: 0 3px 12px #1822300a; }
.composer:focus-within { border-color: #81aa9b; box-shadow: 0 0 0 3px #26765e12; }
.composer textarea { display: block; width: 100%; min-height: 34px; max-height: 140px; resize: vertical; padding: 5px 4px; border: 0; outline: 0; color: #23313a; background: transparent; font-size: 13px; line-height: 1.5; }
.composer textarea::placeholder { color: #9aa4ac; }
.composer-toolbar, .composer-actions { display: flex; align-items: center; justify-content: space-between; }
.composer-actions { gap: 12px; }
.icon-button { width: 30px; height: 30px; border: 0; border-radius: 5px; color: #586771; background: transparent; font-size: 22px; }
.icon-button:hover { background: #f1f4f5; }
.mode-button { display: flex; align-items: center; gap: 8px; padding: 6px 4px; border: 0; color: #697680; background: transparent; font-size: 11px; }
.mode-button span { font-size: 16px; }
.send-button { display: grid; width: 32px; height: 32px; place-items: center; border: 0; border-radius: 5px; color: #fff; background: #26745f; }
.send-button:hover:not(:disabled) { background: #1d624f; }
.send-button:disabled { background: #c8d3cf; }
.send-button svg { width: 17px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.7; }
.composer-note { min-height: 15px; margin: 7px 2px 0; color: #9aa4ab; text-align: center; font-size: 10px; }
.file-input { display: none; }
.popover-anchor { position: relative; }
.popover { position: absolute; z-index: 5; bottom: calc(100% + 9px); min-width: 190px; padding: 5px; border: 1px solid #e0e6e9; border-radius: 6px; background: white; box-shadow: 0 8px 24px #1822301c; }
.tools-popover { left: 0; }
.mode-popover { right: 0; }
.popover-item { display: flex; width: 100%; flex-direction: column; gap: 3px; padding: 9px; border: 0; border-radius: 4px; color: #33414b; background: transparent; text-align: left; font-size: 12px; }
.popover-item:hover, .popover-item.active { background: #f0f6f3; }
.popover-item small { color: #89949c; font-size: 10px; }
.file-symbol { display: inline; margin-right: 5px; color: #26745f; }
.notice-stack { position: fixed; z-index: 10; top: 16px; right: 16px; display: flex; width: min(340px, calc(100vw - 32px)); flex-direction: column; gap: 8px; }
.notice { padding: 11px 14px; border: 1px solid #dce5e1; border-left: 3px solid #367f68; border-radius: 5px; color: #27353d; background: white; box-shadow: 0 8px 24px #18223018; font-size: 12px; }
.notice.warning { border-left-color: #cb922f; }
.notice.error { border-left-color: #c34d4d; }
.notice.success { border-left-color: #3f936e; }
.notice-enter-active, .notice-leave-active { transition: opacity .18s, transform .18s; }
.notice-enter-from, .notice-leave-to { opacity: 0; transform: translateX(12px); }
@media (max-width: 720px) {
  .sidebar { flex-basis: 62px; align-items: center; padding: 14px 6px; }
  .brand { justify-content: center; padding: 0; }
  .brand > div, .history-heading, .history-list, .sidebar-foot { display: none; }
  .new-chat { width: 42px; height: 40px; justify-content: center; margin: 20px 0; padding: 0; overflow: hidden; font-size: 0; }
  .new-chat span { font-size: 21px; }
  .topbar { height: 54px; flex-basis: 54px; padding: 0 14px; }
  .conversation { padding: 24px 14px; }
  .welcome h1 { font-size: 19px; }
  .composer-wrap { width: calc(100% - 24px); }
  .message-body { max-width: 90%; }
}
</style>
