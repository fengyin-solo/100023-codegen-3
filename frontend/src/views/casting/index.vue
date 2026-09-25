<template>
  <section class="page" data-module="casting">
    <header class="page-head">
      <div>
        <h2>试镜排期与定角追踪</h2>
        <p class="page-desc">
          角色在 待试镜 → 试镜中 → 已定角 之间流转（可取消试镜），每次状态变更记录时间与操作人。
        </p>
      </div>
      <div class="page-actions">
        <label class="operator-box">
          <span>操作人</span>
          <input v-model="operator" placeholder="操作人姓名" />
        </label>
        <button class="btn primary" type="button" @click="openCreate">登记角色</button>
        <button class="btn" type="button" @click="exportRows">导出选角清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card" :class="item.tone">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: view === tab.key }"
        type="button"
        @click="view = tab.key"
      >
        {{ tab.label }}
      </button>
      <span v-if="loading" class="loading-hint">读取中…</span>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button class="link" type="button" @click="reload">重试恢复</button>
      </span>
    </div>

    <!-- ============ 选角列表 ============ -->
    <template v-if="view === 'list'">
      <form class="filter-bar" @submit.prevent="reload">
        <label class="filter-item">
          <span>角色编号/名称</span>
          <input v-model="filters.keyword" placeholder="按编号或名称检索" />
        </label>
        <label class="filter-item">
          <span>角色状态</span>
          <select v-model="filters.status">
            <option value="">全部状态</option>
            <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>角色编号</th>
            <th>角色名称</th>
            <th>角色类型</th>
            <th>候选演员</th>
            <th>试镜日期</th>
            <th>当前状态</th>
            <th>定角演员/时间</th>
            <th>最近操作</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td><button class="link" type="button" @click="openDetail(row)">{{ row['角色编号'] }}</button></td>
            <td>{{ row['角色名称'] ?? '—' }}</td>
            <td>{{ row['角色类型'] ?? '—' }}</td>
            <td>
              <div class="candidate-cell">
                <span>{{ row['候选演员'] || '—' }}</span>
                <button
                  v-if="row.status !== STATUS_CAST"
                  class="link"
                  type="button"
                  :disabled="busyId === row.id"
                  @click="openCandidates(row)"
                >
                  调整
                </button>
              </div>
            </td>
            <td>{{ row['试镜日期'] || '—' }}</td>
            <td><span class="status-tag" :data-status="row.status">{{ row.status }}</span></td>
            <td>
              <template v-if="row['定角演员']">
                {{ row['定角演员'] }}<br />
                <small>{{ row['定角时间'] || '历史记录' }}</small>
              </template>
              <span v-else class="muted">—</span>
            </td>
            <td>
              <small>
                {{ latestLog(row)?.action || '—' }}<br />
                {{ latestLog(row)?.operator || '' }}
                <template v-if="latestLog(row)?.time"> · {{ latestLog(row)?.time }}</template>
              </small>
            </td>
            <td class="row-actions">
              <button
                v-for="action in allowedActions(row.status)"
                :key="action.name"
                class="link"
                type="button"
                :disabled="busyId === row.id"
                @click="openAction(action, row)"
              >
                {{ action.name }}
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="9" class="empty-state">暂无符合条件的角色，可先登记角色</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- ============ 定角追踪看板 ============ -->
    <template v-else>
      <div class="kanban">
        <section v-for="col in tracking" :key="col.status" class="kanban-col">
          <header class="kanban-head" :data-status="col.status">
            <span class="status-tag" :data-status="col.status">{{ col.status }}</span>
            <strong>{{ col.count }}</strong>
          </header>
          <article v-for="card in col.cards" :key="String(card.id)" class="kanban-card">
            <div class="kanban-card-head">
              <button class="link" type="button" @click="openDetailById(card.id)">{{ card['角色编号'] }}</button>
              <span>{{ card['角色名称'] }}</span>
            </div>
            <p class="muted">{{ card['角色类型'] }} · 试镜 {{ card['试镜日期'] || '未定' }}</p>
            <p v-if="col.status === STATUS_CAST && card['定角演员']">
              定角：<strong>{{ card['定角演员'] }}</strong>
              <small class="muted">（{{ card['定角时间'] || '历史记录' }}）</small>
            </p>
            <p v-else>候选：{{ card['候选演员'] || '未安排' }}</p>
            <p v-if="card['最新进展']" class="card-log">
              {{ card['最新进展'].action }} · {{ card['最新进展'].operator }}
              <template v-if="card['最新进展'].time"> · {{ card['最新进展'].time }}</template>
            </p>
          </article>
          <p v-if="!col.cards.length" class="empty-state kanban-empty">暂无角色</p>
        </section>
      </div>
    </template>

    <footer class="page-foot">
      <span>共 {{ total }} 条选角记录</span>
      <span v-if="actionMessage" class="success-text">{{ actionMessage }}</span>
    </footer>

    <!-- ============ 角色详情/流转记录 ============ -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal">
        <header class="modal-head">
          <h3>{{ detail['角色名称'] }}（{{ detail['角色编号'] }}）</h3>
          <button class="btn ghost" type="button" @click="detail = null">关闭</button>
        </header>
        <div class="detail-grid">
          <span class="muted">角色类型</span><span>{{ detail['角色类型'] || '—' }}</span>
          <span class="muted">候选演员</span><span>{{ detail['候选演员'] || '—' }}</span>
          <span class="muted">试镜日期</span><span>{{ detail['试镜日期'] || '—' }}</span>
          <span class="muted">片酬区间</span><span>{{ detail['片酬区间'] || '—' }}</span>
          <span class="muted">当前状态</span><span><span class="status-tag" :data-status="detail.status">{{ detail.status }}</span></span>
          <span class="muted">定角演员</span><span>{{ detail['定角演员'] || '—' }}</span>
          <span class="muted">定角时间</span><span>{{ detail['定角时间'] || '—' }}</span>
          <span class="muted">角色说明</span><span>{{ detail['角色说明'] || '—' }}</span>
        </div>
        <h4>状态流转记录</h4>
        <ol class="timeline">
          <li v-for="(log, idx) in [...(detail.status_logs || [])].reverse()" :key="idx">
            <div>
              <strong>{{ log.action }}</strong>
              <span class="muted">
                {{ log.from || '—' }} → {{ log.to }}
              </span>
            </div>
            <div class="muted">
              {{ log.operator }}<template v-if="log.time"> · {{ log.time }}</template>
            </div>
            <div v-if="log.note" class="log-note">{{ log.note }}</div>
          </li>
        </ol>
      </div>
    </div>

    <!-- ============ 动作确认（安排试镜/确认定角/取消/换角共用） ============ -->
    <div v-if="actionDialog" class="modal-mask" @click.self="closeAction">
      <form class="modal" @submit.prevent="confirmAction">
        <header class="modal-head">
          <h3>{{ actionDialog.action.name }}：{{ actionDialog.row['角色名称'] }}</h3>
          <button class="btn ghost" type="button" @click="closeAction">取消</button>
        </header>
        <div v-if="actionDialog.action.needDate" class="form-line">
          <label><span>试镜日期</span>
            <input v-model="actionDialog.auditionDate" type="date" />
          </label>
        </div>
        <div v-if="actionDialog.action.needActor" class="form-line">
          <label><span>{{ actionDialog.action.actorLabel }}</span>
            <input v-model="actionDialog.actor" :placeholder="actionDialog.action.actorPlaceholder" />
          </label>
          <p class="muted">留空时取候选名单第一位：{{ firstCandidate(actionDialog.row['候选演员']) || '（暂无候选）' }}</p>
        </div>
        <div class="form-line">
          <label><span>备注 / 原因</span>
            <textarea v-model="actionDialog.note" rows="2"></textarea>
          </label>
        </div>
        <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
        <footer class="modal-foot">
          <button class="btn primary" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : '确认执行' }}
          </button>
        </footer>
      </form>
    </div>

    <!-- ============ 调整候选演员 ============ -->
    <div v-if="candidateDialog" class="modal-mask" @click.self="candidateDialog = null">
      <form class="modal" @submit.prevent="saveCandidates">
        <header class="modal-head">
          <h3>调整候选演员：{{ candidateDialog.row['角色名称'] }}</h3>
          <button class="btn ghost" type="button" @click="candidateDialog = null">取消</button>
        </header>
        <div class="form-line">
          <label><span>候选演员</span>
            <textarea v-model="candidateDialog.candidates" rows="3" placeholder="多位候选人用顿号或逗号分隔"></textarea>
          </label>
        </div>
        <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
        <footer class="modal-foot">
          <button class="btn primary" type="submit" :disabled="submitting">{{ submitting ? '保存中…' : '保存并同步' }}</button>
        </footer>
      </form>
    </div>

    <!-- ============ 登记角色 ============ -->
    <div v-if="createDialog" class="modal-mask" @click.self="createDialog = false">
      <form class="modal" @submit.prevent="saveCreate">
        <header class="modal-head">
          <h3>登记角色</h3>
          <button class="btn ghost" type="button" @click="createDialog = false">取消</button>
        </header>
        <div class="form-line"><label><span>角色编号 *</span><input v-model="createForm['角色编号']" /></label></div>
        <div class="form-line"><label><span>角色名称 *</span><input v-model="createForm['角色名称']" /></label></div>
        <div class="form-line"><label><span>角色类型 *</span><input v-model="createForm['角色类型']" /></label></div>
        <div class="form-line"><label><span>候选演员</span>
          <textarea v-model="createForm['候选演员']" rows="2" placeholder="多位候选人用顿号或逗号分隔"></textarea>
        </label></div>
        <div class="form-line"><label><span>试镜日期</span><input v-model="createForm['试镜日期']" type="date" /></label></div>
        <div class="form-line"><label><span>片酬区间</span><input v-model="createForm['片酬区间']" /></label></div>
        <div class="form-line"><label><span>角色说明</span><textarea v-model="createForm['角色说明']" rows="2"></textarea></label></div>
        <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
        <footer class="modal-foot">
          <button class="btn primary" type="submit" :disabled="submitting">{{ submitting ? '提交中…' : '登记' }}</button>
        </footer>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { useSessionStore } from '@/stores/session'
import { request } from '@/api/client'

const ENDPOINT = '/api/casting'

const STATUS_PENDING = '待试镜'
const STATUS_AUDITION = '试镜中'
const STATUS_CAST = '已定角'
const STATUS_CANCELLED = '已取消'
const STATUSES = [STATUS_PENDING, STATUS_AUDITION, STATUS_CAST, STATUS_CANCELLED] as const

type Status = (typeof STATUSES)[number]
interface LogEntry { action: string; from: string | null; to: string; operator: string; time: string | null; note: string | null }
interface Row extends Record<string, unknown> {
  id: number
  status: Status
  status_logs?: LogEntry[]
}
interface TrackingCard {
  id: number
  '角色编号': string
  '角色名称': string
  '角色类型': string
  '候选演员': string | null
  '试镜日期': string | null
  '定角演员': string | null
  '定角时间': string | null
  '最新进展': LogEntry | null
}

interface ActionDef {
  name: string
  needDate?: boolean
  needActor?: boolean
  actorLabel?: string
  actorPlaceholder?: string
}

const session = useSessionStore()
const operator = ref(session.operator)
const view = ref<'list' | 'tracking'>('list')
const tabs = [
  { key: 'list' as const, label: '选角列表' },
  { key: 'tracking' as const, label: '定角追踪' },
]

const rows = ref<Row[]>([])
const total = ref(0)
const tracking = ref<{ status: Status; count: number; cards: TrackingCard[] }[]>(
  STATUSES.map((status) => ({ status, count: 0, cards: [] })),
)
const loading = ref(false)
const readFailed = ref(false)
const errorMessage = ref('')
const actionMessage = ref('')
const filters = reactive<{ keyword: string; status: string }>({ keyword: '', status: '' })

const busyId = ref<number | null>(null)
const submitting = ref(false)
const dialogError = ref('')
const detail = ref<Row | null>(null)

const stats = computed(() => [
  { label: '待试镜', value: countBy(STATUS_PENDING), tone: '' },
  { label: '试镜中', value: countBy(STATUS_AUDITION), tone: 'tone-audition' },
  { label: '已定角', value: countBy(STATUS_CAST), tone: 'tone-cast' },
  { label: '已取消', value: countBy(STATUS_CANCELLED), tone: 'tone-cancel' },
])

function countBy(status: Status): number {
  return tracking.value.find((col) => col.status === status)?.count ?? 0
}

function latestLog(row: Row): LogEntry | null {
  const logs = row.status_logs
  return logs && logs.length ? logs[logs.length - 1] : null
}

function firstCandidate(candidates: unknown): string {
  const text = String(candidates ?? '')
  return text.split(/[,，、;；]/).map((item) => item.trim()).find(Boolean) ?? ''
}

/** 按状态放行动作，非法流转在前端先收敛一次，后端再兜底。 */
function allowedActions(status: Status): ActionDef[] {
  if (status === STATUS_PENDING) {
    return [{ name: '安排试镜', needDate: true }]
  }
  if (status === STATUS_AUDITION) {
    return [
      { name: '确认定角', needActor: true, actorLabel: '定角演员', actorPlaceholder: '留空取候选第一位' },
      { name: '更换演员', needActor: true, actorLabel: '新候选演员', actorPlaceholder: '更换后的候选人' },
      { name: '取消试镜' },
    ]
  }
  if (status === STATUS_CAST) {
    return [{ name: '更换演员', needActor: true, actorLabel: '新候选演员', actorPlaceholder: '撤下定角后重新试镜' }]
  }
  return []
}

// ---------- 读取（失败保留上一份数据，可重试恢复） ----------

async function reload() {
  loading.value = true
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword.trim()) query.set('keyword', filters.keyword.trim())
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error(`列表读取失败（${response.status}），当前仍展示上一次数据`)
    const payload = await response.json()
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
    // 追踪视图独立拉取全量，不受列表筛选影响；失败时列表数据仍然可读
    await reloadTracking({ silent: true })
    readFailed.value = false
  } catch (error) {
    readFailed.value = true
    errorMessage.value = error instanceof Error ? error.message : '角色数据读取失败，已保留上次数据，可点重试恢复'
  } finally {
    loading.value = false
  }
}

async function reloadTracking({ silent = false }: { silent?: boolean } = {}) {
  try {
    const response = await request(`${ENDPOINT}/tracking`)
    if (!response.ok) throw new Error('追踪视图读取失败')
    const payload = await response.json()
    tracking.value = (payload.columns ?? []) as typeof tracking.value
  } catch (error) {
    if (!silent) {
      errorMessage.value = error instanceof Error ? error.message : '追踪视图读取失败，列表数据仍可用'
    }
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// ---------- 详情 ----------

async function openDetail(row: Row) {
  detail.value = row
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) throw new Error('明细读取失败，展示列表缓存数据')
    detail.value = (await response.json()) as Row
  } catch (error) {
    // 读失败不清空，继续展示列表里已有的角色说明与定角信息
    dialogError.value = error instanceof Error ? error.message : '明细读取失败'
  }
}

async function openDetailById(id: number) {
  const cached = rows.value.find((row) => row.id === id)
  if (cached) {
    await openDetail(cached)
    return
  }
  detail.value = null
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) throw new Error('明细读取失败')
    detail.value = (await response.json()) as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '明细读取失败，可重试'
  }
}

// ---------- 状态动作（乐观更新 + 快照回滚，防止重复提交） ----------

interface ActionDialog {
  action: ActionDef
  row: Row
  auditionDate: string
  actor: string
  note: string
}
const actionDialog = ref<ActionDialog | null>(null)

function openAction(action: ActionDef, row: Row) {
  dialogError.value = ''
  actionDialog.value = {
    action,
    row,
    auditionDate: String(row['试镜日期'] ?? ''),
    actor: '',
    note: '',
  }
}

function closeAction() {
  if (submitting.value) return
  actionDialog.value = null
}

async function confirmAction() {
  const dialog = actionDialog.value
  if (!dialog || busyId.value !== null) return
  submitting.value = true
  busyId.value = dialog.row.id
  dialogError.value = ''
  actionMessage.value = ''

  const values: Record<string, string> = { action: dialog.action.name, operator: operator.value || session.operator }
  if (dialog.action.needDate && dialog.auditionDate) values['试镜日期'] = dialog.auditionDate
  if (dialog.action.needActor && dialog.actor.trim()) {
    values[dialog.action.name === '确认定角' ? '定角演员' : '候选演员'] = dialog.actor.trim()
  }
  if (dialog.note.trim()) values['note'] = dialog.note.trim()

  // 乐观更新前先快照，请求失败或后续刷新失败都能回到上一状态
  const snapshotRows = rows.value.map((row) => structuredClone(toPlain(row)))
  const snapshotTracking = structuredClone(toPlain(tracking.value))
  await mutateOptimistic(
    async () => {
      const response = await request(`${ENDPOINT}/${dialog.row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ values }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok || !payload?.ok) {
        throw new Error(payload?.message || `动作未生效（${response.status}），已恢复到操作前状态`)
      }
      return payload.entry as Row
    },
    snapshotRows,
    snapshotTracking,
    `「${dialog.action.name}」已提交`,
  )
  actionDialog.value = null
}

// ---------- 调整候选演员 ----------

interface CandidateDialog { row: Row; candidates: string }
const candidateDialog = ref<CandidateDialog | null>(null)

function openCandidates(row: Row) {
  if (busyId.value !== null) return
  dialogError.value = ''
  candidateDialog.value = { row, candidates: String(row['候选演员'] ?? '') }
}

async function saveCandidates() {
  const dialog = candidateDialog.value
  if (!dialog || busyId.value !== null) return
  const candidates = dialog.candidates.trim()
  if (!candidates) {
    dialogError.value = '候选演员不能为空，至少保留一位候选人'
    return
  }
  submitting.value = true
  busyId.value = dialog.row.id
  dialogError.value = ''

  const snapshotRows = rows.value.map((row) => structuredClone(toPlain(row)))
  const snapshotTracking = structuredClone(toPlain(tracking.value))
  await mutateOptimistic(
    async () => {
      const response = await request(`${ENDPOINT}/${dialog.row.id}/candidates`, {
        method: 'PATCH',
        body: JSON.stringify({ values: { '候选演员': candidates, operator: operator.value || session.operator }, remark: '调整候选演员' }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok || !payload?.ok) {
        throw new Error(payload?.message || `候选调整未生效（${response.status}），已恢复到调整前`)
      }
      return payload.entry as Row
    },
    snapshotRows,
    snapshotTracking,
    '候选演员已调整，选角列表与追踪视图已同步',
  )
  candidateDialog.value = null
}

/** 乐观写入：先用返回记录替换本地数据并同步追踪列，失败则整体回滚快照并重试拉取。 */
async function mutateOptimistic(
  call: () => Promise<Row>,
  snapshotRows: Row[],
  snapshotTracking: typeof tracking.value,
  okMessage: string,
) {
  try {
    const updated = await call()
    applyEntry(updated)
    actionMessage.value = okMessage
    // 以服务端为准再拉一次；这一步失败也保留本地刚应用的结果，并允许重试恢复
    await Promise.all([reloadSilentList(), reloadTracking()])
  } catch (error) {
    rows.value = snapshotRows
    tracking.value = snapshotTracking
    dialogError.value = error instanceof Error ? error.message : '操作失败，已恢复到上一状态'
    // 再尝试从服务端恢复一次，避免本地与服务端长期不一致
    await Promise.all([reloadSilentList(), reloadTracking()])
  } finally {
    submitting.value = false
    busyId.value = null
  }
}

async function reloadSilentList() {
  try {
    const query = new URLSearchParams()
    if (filters.keyword.trim()) query.set('keyword', filters.keyword.trim())
    if (filters.status) query.set('status', filters.status)
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (response.ok) {
      const payload = await response.json()
      rows.value = (payload.items ?? []) as Row[]
      total.value = payload.total ?? rows.value.length
      readFailed.value = false
    }
  } catch {
    readFailed.value = true
  }
}

/** 把一条最新记录合并进列表与详情；追踪视图由调用方随后统一刷新，保证两处同步。 */
function applyEntry(entry: Row) {
  const listIdx = rows.value.findIndex((row) => row.id === entry.id)
  if (listIdx >= 0) rows.value[listIdx] = entry
  if (detail.value?.id === entry.id) detail.value = entry
}

function toPlain<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

// ---------- 登记角色 ----------

const createDialog = ref(false)
const createForm = reactive<Record<string, string>>({
  '角色编号': '', '角色名称': '', '角色类型': '', '候选演员': '',
  '试镜日期': '', '片酬区间': '', '角色说明': '',
})

function openCreate() {
  dialogError.value = ''
  for (const key of Object.keys(createForm)) createForm[key] = ''
  createDialog.value = true
}

async function saveCreate() {
  submitting.value = true
  dialogError.value = ''
  try {
    const values: Record<string, string> = { operator: operator.value || session.operator }
    for (const [key, val] of Object.entries(createForm)) {
      if (val.trim()) values[key] = val.trim()
    }
    const response = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values }) })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '角色登记失败')
    }
    createDialog.value = false
    actionMessage.value = '角色已登记'
    await reload()
  } catch (error) {
    dialogError.value = error instanceof Error ? error.message : '角色登记失败'
  } finally {
    submitting.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; align-items: flex-end; }
.operator-box { display: flex; flex-direction: column; font-size: 12px; color: var(--muted); }
.operator-box input { width: 120px; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }

.stat-card.tone-audition { border-left: 3px solid #b54708; }
.stat-card.tone-cast { border-left: 3px solid #067647; }
.stat-card.tone-cancel { border-left: 3px solid #b42318; }

.tab-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.tab-btn { border: 1px solid var(--border); background: #fff; border-radius: 6px 6px 0 0; padding: 6px 16px; cursor: pointer; font-size: 13px; }
.tab-btn.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.loading-hint, .success-text { color: #067647; font-size: 12px; }
.muted { color: var(--muted); }

.candidate-cell { display: flex; gap: 8px; align-items: center; }
.status-tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; background: #e5e7eb; }
.status-tag[data-status='试镜中'] { background: #fef0c7; color: #b54708; }
.status-tag[data-status='已定角'] { background: #d1fadf; color: #067647; }
.status-tag[data-status='已取消'] { background: #fee4e2; color: #b42318; }

.kanban { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kanban-col { background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 8px; min-height: 200px; }
.kanban-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.kanban-card { background: #fff; border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; font-size: 13px; }
.kanban-card-head { display: flex; justify-content: space-between; gap: 8px; font-weight: 600; }
.kanban-card p { margin: 4px 0; }
.card-log { font-size: 12px; color: var(--muted); border-top: 1px dashed var(--border); padding-top: 4px; }
.kanban-empty { font-size: 12px; padding: 12px 0; }

.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: #fff; border-radius: 8px; width: 520px; max-width: 92vw; max-height: 86vh; overflow-y: auto; padding: 16px 20px; }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.modal-head h3 { margin: 0; font-size: 16px; }
.modal-foot { display: flex; justify-content: flex-end; margin-top: 12px; }
.form-line { margin-bottom: 10px; }
.form-line label span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-line input, .form-line textarea { width: 100%; box-sizing: border-box; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-family: inherit; }
button:disabled { opacity: 0.5; cursor: not-allowed; }

.detail-grid { display: grid; grid-template-columns: 90px 1fr; gap: 6px 12px; font-size: 13px; margin-bottom: 12px; }
.timeline { list-style: none; margin: 0; padding: 0; border-left: 2px solid var(--border); }
.timeline li { padding: 6px 0 6px 14px; font-size: 13px; }
.log-note { margin-top: 2px; }
</style>
