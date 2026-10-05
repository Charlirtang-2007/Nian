<script setup>
// 从 Vue 引入 ref（响应式变量）和 nextTick（DOM 更新后执行）
import { ref, nextTick } from 'vue'

// 建立 WebSocket 连接，指向本地 FastAPI 后端
const ws = new WebSocket('ws://127.0.0.1:8000/ws/chat')

const input = ref('')          // 输入框内容，双向绑定
const messages = ref([])       // 消息列表，每条 {role, content}，role 是 user 或 assistant
const currentReply = ref('')   // 当前正在流式接收的回复（还没拼完）
const connected = ref(false)   // 连接状态，用来显示"已连接/未连接"
const listEl = ref(null)       // 消息列表 DOM 引用，用来自动滚到底部

// WebSocket 连接成功时触发
ws.onopen = () => {
  connected.value = true
}

// WebSocket 断开时触发
ws.onclose = () => {
  connected.value = false
}

// 收到后端消息时触发
ws.onmessage = (e) => {
  // 后端发来的是 JSON 字符串，解析成对象
  const msg = JSON.parse(e.data)

  if (msg.type === 'delta') {
    // 流式片段：逐块拼接，实现"打字机"效果
    currentReply.value += msg.content
    scrollToBottom()
  } else if (msg.type === 'done') {
    // 本轮结束：把拼好的完整回复推进消息列表
    messages.value.push({ role: 'assistant', content: currentReply.value })
    currentReply.value = ''   // 清空临时变量，准备下一轮
    scrollToBottom()
  }
}

// 发送消息
function send() {
  const text = input.value.trim()
  // 空内容或未连接时，直接返回，不发送
  if (!text || !connected.value) return

  // 先把自己发的消息显示在界面上
  messages.value.push({ role: 'user', content: text })

  // 通过 WebSocket 发给后端（约定格式：{type, content}）
  ws.send(JSON.stringify({ type: 'chat', content: text }))

  input.value = ''   // 清空输入框
  scrollToBottom()
}

// 自动滚动到消息列表底部
function scrollToBottom() {
  // nextTick：等 Vue 把新消息渲染到 DOM 之后再滚动
  // 否则 scrollHeight 还是旧的，滚不到最新位置
  nextTick(() => {
    if (listEl.value) {
      listEl.value.scrollTop = listEl.value.scrollHeight
    }
  })
}
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
</style>