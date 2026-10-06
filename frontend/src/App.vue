<script setup>
import { ref, nextTick, onUnmounted } from 'vue'

// ---------- 常量 ----------
const BACKEND_HTTP = 'http://127.0.0.1:8000'
const BACKEND_WS = 'ws://127.0.0.1:8000/ws/chat'
const POLL_INTERVAL = 3000   // 轮询间隔：3 秒

// ---------- 响应式变量 ----------
const toolDialog = ref(null)
const input = ref('')
const messages = ref([])
const currentReply = ref('')
const connected = ref(false)
const listEl = ref(null)

// ---------- 模块级状态（不需要响应式） ----------
let ws = null
let pollTimer = null

// ---------- 建立 WS 连接 ----------
function connectWS() {
  // 防止重复建连接：已经有 CONNECTING 或 OPEN 状态的 ws，就不重建
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return
  }

  console.log('[ws] connecting')
  ws = new WebSocket(BACKEND_WS)
  window.ws = ws   // 调试用

  ws.onopen = () => {
    console.log('[ws] open')
    connected.value = true
    stopPolling()   // 连上了，停止轮询
  }

  ws.onclose = (e) => {
    console.log('[ws] close', e.code, e.reason)
    connected.value = false
    ws = null
    startPolling()  // 断开，重新开始轮询
  }

  ws.onerror = (e) => {
    console.log('[ws] error', e)
  }

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)

    if (msg.type === 'delta') {
      currentReply.value += msg.content
      scrollToBottom()
    } else if (msg.type === 'done') {
      if (currentReply.value) {
        messages.value.push({ role: 'assistant', content: currentReply.value })
        currentReply.value = ''
      }
      scrollToBottom()
    } else if (msg.type === 'tool_request') {
      toolDialog.value = {
        id: msg.id,
        command: msg.command,
        reason: msg.reason,
      }
    } else if (msg.type === 'tool_result') {
      const status = msg.rejected ? '被拒绝'
                   : msg.denied   ? '被规则拦截'
                   : msg.timeout  ? '超时'
                   : `退出码 ${msg.exit_code}`
      const out = msg.stdout || msg.stderr || '(无输出)'
      messages.value.push({
        role: 'system',
        content: `[工具执行] ${msg.command}\n状态：${status}\n输出：${out}`,
      })
      scrollToBottom()
    }
  }
}

// ---------- 轮询后端 ----------
async function pollOnce() {
  try {
    const res = await fetch(`${BACKEND_HTTP}/`, { cache: 'no-store' })
    if (res.ok) {
      console.log('[poll] backend alive, trying ws')
      connectWS()
      // 不在这里停轮询，等 onopen 时再停
    }
  } catch (e) {
    // 后端还没起来，继续等下次
    console.log('[poll] backend not reachable')
  }
}

function startPolling() {
  if (pollTimer) return   // 已经在轮询，不重复启动
  console.log('[poll] start')
  pollOnce()              // 立即探一次，不用等 3 秒
  pollTimer = setInterval(pollOnce, POLL_INTERVAL)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
    console.log('[poll] stop')
  }
}

// ---------- 用户交互 ----------
function respondTool(approved) {
  if (!toolDialog.value) return
  ws.send(JSON.stringify({
    type: 'tool_confirm',
    id: toolDialog.value.id,
    approved,
  }))
  toolDialog.value = null
}

function send() {
  const text = input.value.trim()
  if (!text || !connected.value) return

  messages.value.push({ role: 'user', content: text })
  ws.send(JSON.stringify({ type: 'chat', content: text }))
  input.value = ''
  scrollToBottom()
}

function scrollToBottom() {
  nextTick(() => {
    if (listEl.value) {
      listEl.value.scrollTop = listEl.value.scrollHeight
    }
  })
}

// ---------- 启动 & 清理 ----------
startPolling()   // 页面一加载就开始轮询

onUnmounted(() => {
  stopPolling()
  if (ws) ws.close()
})
</script>

<template>
  <div class="chat">
    <!-- 顶部连接状态 -->
    <div class="status">
      {{ connected ? '已连接' : '未连接' }}
    </div>

    <!-- 消息列表，ref="listEl" 绑定上面的 DOM 引用 -->
    <div class="list" ref="listEl">
      <!-- 遍历历史消息，按角色加不同样式 -->
      <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
        {{ m.content }}
      </div>
      <!-- 正在流式接收的回复，实时显示 -->
      <div v-if="currentReply" class="msg assistant">
        {{ currentReply }}
      </div>
    </div>

    <!-- 底部输入栏 -->
    <div class="input-bar">
      <!-- v-model 双向绑定，回车触发 send -->
      <input
        v-model="input"
        @keyup.enter="send"
        placeholder="说点什么..."
      />
      <button @click="send">发送</button>
    </div>
    <div v-if="toolDialog" class="modal-mask">
  
      <div class="modal">
    <div class="modal-title">工具执行确认</div>
    <div class="modal-reason">{{ toolDialog.reason }}</div>
    <pre class="modal-cmd">{{ toolDialog.command }}</pre>
    <div class="modal-actions">
      <button class="btn-reject" @click="respondTool(false)">拒绝</button>
      <button class="btn-approve" @click="respondTool(true)">同意</button>
    </div>
  </div>
</div>
  </div>
</template>

<style>
/* 全局重置 */
body { margin: 0; font-family: sans-serif; }

/* 聊天容器：纵向排列，占满整屏 */
.chat { display: flex; flex-direction: column; height: 100vh; }

/* 顶部状态栏 */
.status { padding: 8px; font-size: 12px; color: #666; border-bottom: 1px solid #eee; }

/* 消息列表：占满剩余空间，内容多了自己滚 */
.list { flex: 1; overflow-y: auto; padding: 16px; }

/* 单条消息气泡 */
.msg { margin: 8px 0; padding: 8px 12px; border-radius: 8px; max-width: 70%; white-space: pre-wrap; }

/* 用户消息：靠右，蓝色 */
.msg.user { background: #d1e7ff; margin-left: auto; }

/* 助手消息：靠左，灰色 */
.msg.assistant { background: #f1f1f1; }

/* 底部输入栏 */
.input-bar { display: flex; padding: 12px; border-top: 1px solid #eee; }
.input-bar input { flex: 1; padding: 8px; font-size: 16px; }
.input-bar button { margin-left: 8px; padding: 8px 16px; }

/* 弹窗 */
.modal-mask {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
  animation: fadeIn 0.15s ease;
}
@keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }

.modal {
  background: #fff;
  border-radius: 14px;
  padding: 22px 24px;
  min-width: 360px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
  animation: pop 0.18s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes pop {
  from { transform: scale(0.92); opacity: 0 }
  to   { transform: scale(1);    opacity: 1 }
}

.modal-title { font-size: 15px; font-weight: 600; color: #111; margin-bottom: 10px; }
.modal-reason { font-size: 13px; color: #666; margin-bottom: 12px; }
.modal-cmd {
  background: #f6f6f8;
  border: 1px solid #ececf0;
  border-radius: 8px;
  padding: 10px 12px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12.5px;
  color: #333;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0 0 16px;
}
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
.modal-actions button {
  padding: 8px 18px; border-radius: 8px;
  font-size: 14px; font-weight: 500;
  border: none; cursor: pointer;
  transition: transform 0.08s ease, filter 0.12s ease;
}
.modal-actions button:active { transform: scale(0.96); }

.btn-reject { background: #f0f0f3; color: #444; }
.btn-reject:hover { filter: brightness(0.96); }

.btn-approve {
  background: linear-gradient(135deg, #4c8bf5, #3a6ff0);
  color: #fff;
  box-shadow: 0 2px 8px rgba(76, 139, 245, 0.35);
}
.btn-approve:hover { filter: brightness(1.05); }

/* 系统消息 */
.msg.system {
  background: #fff5d6;
  border-left: 3px solid #f0b400;
  font-size: 13px;
  color: #5a4400;
  max-width: 85%;
}

</style>