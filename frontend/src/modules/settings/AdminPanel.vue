<template>
  <div class="admin-panel">
    <!-- ===== 注册限制 ===== -->
    <section class="admin-card">
      <div class="card-header">
        <h3>注册限制</h3>
      </div>
      <div class="card-body">
        <div class="stat-row">
          <div class="stat-box">
            <span class="stat-value">{{ userCountData.total_users }}</span>
            <span class="stat-label">当前用户</span>
          </div>
          <div class="stat-box">
            <span class="stat-value">{{ maxUsers }}</span>
            <span class="stat-label">最大限制</span>
          </div>
          <div class="stat-box">
            <span class="stat-value" :class="remainingUsers < 0 ? 'text-danger' : ''">
              {{ remainingUsers }}
            </span>
            <span class="stat-label">剩余名额</span>
          </div>
        </div>
        <div class="form-row">
          <label>最大用户数（0 = 不限制）</label>
          <div class="input-row">
            <input
              v-model.number="maxUsersInput"
              type="number"
              min="0"
              class="admin-input"
              placeholder="0"
            />
            <button
              class="btn-save"
              :disabled="savingMaxUsers || maxUsersInput === maxUsers"
              @click="saveMaxUsers"
            >
              {{ savingMaxUsers ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
        <p v-if="maxUsersSaved" class="hint success">已保存</p>
      </div>
    </section>

    <!-- ===== 聊天记录 ===== -->
    <section class="admin-card">
      <div class="card-header">
        <h3>聊天记录</h3>
        <div class="filter-row">
          <input
            v-model="msgKeyword"
            type="text"
            class="admin-input search-input"
            placeholder="搜索关键词..."
            @keyup.enter="msgOffset = 0; loadMessages()"
          />
          <select v-model.number="msgUserFilter" class="admin-select" @change="msgOffset = 0; loadMessages()">
            <option :value="0">全部用户</option>
            <option v-for="u in userList" :key="u.id" :value="u.id">
              {{ u.username }}
            </option>
          </select>
          <select v-model.number="msgLimit" class="admin-select" @change="loadMessages">
            <option :value="20">20 条</option>
            <option :value="50">50 条</option>
            <option :value="100">100 条</option>
            <option :value="200">200 条</option>
          </select>
          <button class="btn-refresh" @click="msgOffset = 0; loadMessages()">搜索</button>
        </div>
      </div>
      <div class="card-body">
        <div v-if="loadingMessages" class="loading">加载中...</div>
        <div v-else-if="messages.length === 0" class="empty">暂无消息</div>
        <div v-else class="message-list">
          <div v-for="msg in messages" :key="msg.id" class="message-row">
            <div class="msg-meta">
              <span class="msg-user">{{ msg.username }}</span>
              <span class="msg-role" :class="msg.role">{{ msg.role === 'user' ? '用户' : 'AI' }}</span>
              <span class="msg-time">{{ formatTime(msg.created_at) }}</span>
            </div>
            <div class="msg-content">{{ msg.content }}</div>
          </div>
        </div>
        <div v-if="messages.length > 0" class="pagination">
          <button :disabled="msgOffset === 0" @click="prevPage">上一页</button>
          <span>第 {{ pageNum }} / {{ totalPages }} 页</span>
          <button :disabled="msgOffset + msgLimit >= msgTotal" @click="nextPage">下一页</button>
        </div>
      </div>
    </section>

    <!-- ===== 流量监控 ===== -->
    <section class="admin-card">
      <div class="card-header">
        <h3>流量监控</h3>
        <div class="filter-row">
          <select v-model.number="trafficUserFilter" class="admin-select" @change="loadTraffic">
            <option :value="0">全部用户</option>
            <option v-for="u in userList" :key="u.id" :value="u.id">
              {{ u.username }}
            </option>
          </select>
          <select v-model.number="trafficDays" class="admin-select" @change="loadTraffic">
            <option :value="7">最近 7 天</option>
            <option :value="30">最近 30 天</option>
            <option :value="90">最近 90 天</option>
            <option :value="365">全部</option>
          </select>
          <button class="btn-refresh" @click="loadTraffic">刷新</button>
        </div>
      </div>
      <div class="card-body">
        <div v-if="loadingTraffic" class="loading">加载中...</div>
        <div v-else-if="trafficByUser.length === 0" class="empty">暂无流量数据</div>
        <div v-else>
          <!-- 总计 -->
          <div class="stat-row">
            <div class="stat-box">
              <span class="stat-value">{{ formatBytes(trafficTotals.total_bytes) }}</span>
              <span class="stat-label">总流量</span>
            </div>
            <div class="stat-box">
              <span class="stat-value">{{ formatBytes(trafficTotals.upload_bytes) }}</span>
              <span class="stat-label">上传</span>
            </div>
            <div class="stat-box">
              <span class="stat-value">{{ formatBytes(trafficTotals.download_bytes) }}</span>
              <span class="stat-label">下载</span>
            </div>
            <div class="stat-box">
              <span class="stat-value">{{ trafficTotals.request_count }}</span>
              <span class="stat-label">请求数</span>
            </div>
          </div>

          <!-- 按用户 -->
          <table class="traffic-table">
            <thead>
              <tr>
                <th>用户</th>
                <th>上传</th>
                <th>下载</th>
                <th>总流量</th>
                <th>请求数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in trafficByUser" :key="u.user_id">
                <td>{{ u.username }}</td>
                <td>{{ formatBytes(u.upload_bytes) }}</td>
                <td>{{ formatBytes(u.download_bytes) }}</td>
                <td><strong>{{ formatBytes(u.total_bytes) }}</strong></td>
                <td>{{ u.request_count }}</td>
                <td>
                  <button
                    class="btn-text text-danger"
                    :disabled="deletingUserId === u.user_id"
                    @click="showDeleteConfirm(u.user_id, u.username)"
                  >
                    {{ deletingUserId === u.user_id ? '删除中...' : '删除' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- 确认删除弹窗 -->
    <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
      <div class="modal-box">
        <div class="modal-header">
          <h4>确认删除</h4>
        </div>
        <div class="modal-body">
          <p>确定要删除用户 <strong>{{ deleteTarget.username }}</strong> 吗？</p>
          <p class="text-danger">此操作不可恢复，该用户的所有数据将被清除。</p>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="deleteTarget = null">取消</button>
          <button class="btn-danger" :disabled="deletingUserId !== null" @click="confirmDeleteUser">
            {{ deletingUserId !== null ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { adminAPI, authAPI } from '@/api/endpoints'
import { useToast } from '@/composables/useToast'

const toast = useToast()

// ============================================================
// 注册限制
// ============================================================

const maxUsers = ref(0)
const maxUsersInput = ref(0)
const savingMaxUsers = ref(false)
const maxUsersSaved = ref(false)
const userCountData = ref({ total_users: 0, active_users: 0 })

const remainingUsers = computed(() => maxUsers.value - userCountData.value.total_users)

async function loadSettings() {
  try {
    const [settings, count] = await Promise.all([
      adminAPI.getSettings(),
      adminAPI.getUserCount(),
    ])
    maxUsers.value = settings.max_users
    maxUsersInput.value = settings.max_users
    userCountData.value = count
  } catch (e: any) {
    toast.error('加载设置失败: ' + (e.response?.data?.detail || '未知错误'))
  }
}

async function saveMaxUsers() {
  savingMaxUsers.value = true
  maxUsersSaved.value = false
  try {
    const res = await adminAPI.saveSettings({ max_users: maxUsersInput.value })
    maxUsers.value = res.max_users
    maxUsersSaved.value = true
    toast.success('注册限制已更新')
    await loadSettings()
  } catch (e: any) {
    toast.error('保存失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    savingMaxUsers.value = false
  }
}

// ============================================================
// 聊天记录
// ============================================================

const messages = ref<Array<any>>([])
const msgTotal = ref(0)
const msgOffset = ref(0)
const msgLimit = ref(50)
const msgUserFilter = ref(0) // 0 = all
const msgKeyword = ref('')
const loadingMessages = ref(false)
const userList = ref<Array<{ id: number; username: string }>>([])

const pageNum = computed(() => Math.floor(msgOffset.value / msgLimit.value) + 1)
const totalPages = computed(() => Math.max(1, Math.ceil(msgTotal.value / msgLimit.value)))

async function loadMessages() {
  loadingMessages.value = true
  try {
    const params: any = {
      user_id: msgUserFilter.value > 0 ? msgUserFilter.value : undefined,
      limit: msgLimit.value,
      offset: msgOffset.value,
    }
    if (msgKeyword.value.trim()) {
      params.keyword = msgKeyword.value.trim()
    }
    const res = await adminAPI.getMessages(params)
    messages.value = res.messages
    msgTotal.value = res.total
  } catch (e: any) {
    toast.error('加载消息失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    loadingMessages.value = false
  }
}

function prevPage() {
  if (msgOffset.value > 0) {
    msgOffset.value = Math.max(0, msgOffset.value - msgLimit.value)
    loadMessages()
  }
}

function nextPage() {
  if (msgOffset.value + msgLimit.value < msgTotal.value) {
    msgOffset.value += msgLimit.value
    loadMessages()
  }
}

// ============================================================
// 流量监控
// ============================================================

const trafficByUser = ref<Array<any>>([])
const trafficTotals = ref({ upload_bytes: 0, download_bytes: 0, total_bytes: 0, request_count: 0 })
const trafficDaily = ref<Array<any>>([])
const trafficUserFilter = ref(0)
const trafficDays = ref(7)
const loadingTraffic = ref(false)
const deletingUserId = ref<number | null>(null)
const deleteTarget = ref<{ user_id: number; username: string } | null>(null)

function showDeleteConfirm(userId: number, username: string) {
  deleteTarget.value = { user_id: userId, username }
}

async function confirmDeleteUser() {
  if (!deleteTarget.value) return
  const t = deleteTarget.value
  deleteTarget.value = null
  deletingUserId.value = t.user_id
  try {
    await authAPI.deleteUser(t.user_id)
    toast.success('用户已删除')
    await Promise.all([loadTraffic(), loadSettings()])
  } catch (e: any) {
    toast.error('删除失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    deletingUserId.value = null
  }
}

async function loadTraffic() {
  loadingTraffic.value = true
  try {
    const res = await adminAPI.getTraffic({
      user_id: trafficUserFilter.value > 0 ? trafficUserFilter.value : undefined,
      days: trafficDays.value,
    })
    trafficByUser.value = res.by_user
    trafficTotals.value = res.totals
    trafficDaily.value = res.daily
  } catch (e: any) {
    toast.error('加载流量数据失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    loadingTraffic.value = false
  }
}

async function handleDeleteUser(userId: number, username: string) {
  if (!confirm('确定要删除用户 ' + username + ' 吗？此操作不可恢复。')) return
  deletingUserId.value = userId
  try {
    await authAPI.deleteUser(userId)
    toast.success(`用户「${username}」已删除`)
    await Promise.all([loadTraffic(), loadSettings()])
  } catch (e: any) {
    toast.error('删除失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    deletingUserId.value = null
  }
}

// ============================================================
// 工具函数
// ============================================================

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i]
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

// ============================================================
// 初始化
// ============================================================

onMounted(async () => {
  await Promise.all([
    loadSettings(),
    loadMessages(),
    loadTraffic(),
  ])
  // 加载用户列表
  try {
    const users = await authAPI.listUsers()
    userList.value = users
  } catch {
    // 忽略
  }
})
</script>

<style scoped>
.admin-panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 960px;
}

.admin-card {
  background: var(--bg-secondary, #f8fafc);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-tertiary, #f1f5f9);
  border-bottom: 1px solid var(--border-color, #e2e8f0);
}

.card-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.card-body {
  padding: 16px;
}

.stat-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.stat-box {
  flex: 1;
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  padding: 12px;
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 24px;
  font-weight: 700;
}

.stat-label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  margin-top: 4px;
}

.form-row {
  margin-bottom: 8px;
}

.form-row label {
  display: block;
  font-size: 13px;
  margin-bottom: 6px;
  color: var(--text-secondary, #64748b);
}

.input-row {
  display: flex;
  gap: 8px;
}

.admin-input {
  flex: 1;
  max-width: 160px;
  padding: 6px 10px;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 4px;
  font-size: 14px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #1e293b);
}

.admin-select {
  padding: 5px 8px;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #1e293b);
}

.btn-save {
  padding: 6px 16px;
  background: var(--color-primary, #3b82f6);
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}

.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-refresh {
  padding: 5px 12px;
  background: var(--bg-tertiary, #f1f5f9);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}

.filter-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.search-input {
  min-width: 140px;
}

.loading, .empty {
  padding: 32px;
  text-align: center;
  color: var(--text-secondary, #64748b);
}

.message-list {
  max-height: 400px;
  overflow-y: auto;
}

.message-row {
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
}

.message-row:last-child {
  border-bottom: none;
}

.msg-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 4px;
  font-size: 12px;
}

.msg-user {
  font-weight: 600;
}

.msg-role {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
}

.msg-role.user {
  background: #dbeafe;
  color: #1d4ed8;
}

.msg-role.assistant {
  background: #dcfce7;
  color: #15803d;
}

.msg-time {
  color: var(--text-secondary, #94a3b8);
}

.msg-content {
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-primary, #1e293b);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  font-size: 13px;
}

.pagination button {
  padding: 4px 12px;
  background: var(--bg-tertiary, #f1f5f9);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.pagination button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.traffic-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.traffic-table th {
  text-align: left;
  padding: 8px 6px;
  border-bottom: 2px solid var(--border-color, #e2e8f0);
  font-weight: 600;
  white-space: nowrap;
}

.traffic-table td {
  padding: 8px 6px;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
}

.btn-text {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 6px;
}

.text-danger {
  color: #ef4444;
}

.text-danger:hover {
  text-decoration: underline;
}

.text-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.text-danger {
  color: #ef4444 !important;
}

.hint {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  margin-top: 4px;
}

.hint.success {
  color: #16a34a;
}

[data-theme="dark"] .admin-card {
  background: var(--bg-secondary, #1e293b);
  border-color: var(--border-color, #334155);
}

[data-theme="dark"] .card-header {
  background: var(--bg-tertiary, #0f172a);
  border-color: var(--border-color, #334155);
}

[data-theme="dark"] .stat-box {
  background: var(--bg-primary, #0f172a);
  border-color: var(--border-color, #334155);
}

[data-theme="dark"] .admin-input,
[data-theme="dark"] .admin-select {
  background: var(--bg-primary, #0f172a);
  border-color: var(--border-color, #334155);
  color: var(--text-primary, #f1f5f9);
}

/* 确认弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-box {
  background: var(--bg-primary, #fff);
  border-radius: 8px;
  padding: 0;
  min-width: 360px;
  max-width: 440px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
}

.modal-header {
  padding: 16px 20px 0;
}

.modal-header h4 {
  margin: 0;
  font-size: 16px;
}

.modal-body {
  padding: 12px 20px;
  font-size: 14px;
  line-height: 1.6;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px 16px;
}

.btn-cancel {
  padding: 6px 16px;
  background: var(--bg-tertiary, #f1f5f9);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.btn-danger {
  padding: 6px 16px;
  background: #ef4444;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>