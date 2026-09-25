<template>
  <section class="page" data-module="casting">
    <header class="page-head">
      <div>
        <h2>角色选角管理</h2>
        <p class="page-desc">试镜排期与定角追踪：角色按 待试镜 → 试镜中 → 已定角 流转，每次变更记录时间与操作人。</p>
      </div>
      <div class="page-actions">
        <label class="operator-item">
          <span>操作人</span>
          <input v-model="operator" placeholder="操作人姓名" />
        </label>
        <button class="btn primary" type="button" @click="openCreate">登记角色</button>
        <button class="btn" type="button" @click="exportRows">导出角色选角清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: view === 'list' }" type="button" @click="view = 'list'">选角列表</button>
      <button class="tab" :class="{ active: view === 'tracking' }" type="button" @click="view = 'tracking'">定角追踪</button>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>角色编号</span>
        <input v-model="filters.keyword" placeholder="按角色编号检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table v-if="view === 'list'" class="data-table clickable">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>定角演员</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" @click="openTracking(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td><span class="status-tag" :data-status="row.status">{{ row.status }}</span></td>
          <td>{{ row.定角演员 ?? '—' }}</td>
          <td class="row-actions" @click.stop>
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="openAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 3" class="empty-state">暂无角色选角数据，可先登记角色</td>
        </tr>
      </tbody>
    </table>

    <template v-else>
      <table class="data-table clickable">
        <thead>
          <tr>
            <th>角色编号</th>
            <th>角色名称</th>
            <th>状态</th>
            <th>候选演员</th>
            <th>试镜排期</th>
            <th>定角演员</th>
            <th>最近流转</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in tracking"
            :key="String(item.id)"
            :class="{ selected: currentId === item.id }"
            @click="toggleSelect(item.id)"
          >
            <td>{{ item.角色编号 }}</td>
            <td>{{ item.角色名称 }}</td>
            <td><span class="status-tag" :data-status="item.status">{{ item.status }}</span></td>
            <td>
              <span v-for="name in item.候选演员列表" :key="name" class="tag">{{ name }}</span>
              <span v-if="!item.候选演员列表.length">—</span>
            </td>
            <td>{{ auditionSummary(item) }}</td>
            <td>{{ item.定角演员 ?? '—' }}</td>
            <td>{{ lastFlow(item) }}</td>
          </tr>
          <tr v-if="!tracking.length">
            <td colspan="7" class="empty-state">暂无定角追踪数据</td>
          </tr>
        </tbody>
      </table>

      <section v-if="current" class="panel">
        <h3>定角追踪详情：{{ current.角色名称 }}（{{ current.角色编号 }}）</h3>
        <p class="muted">角色说明：{{ current.角色说明 || '—' }}</p>
        <div class="panel-grid">
          <div>
            <h4>定角记录</h4>
            <p v-if="current.定角记录">
              「{{ current.定角记录.演员 }}」 · {{ current.定角记录.时间 ?? '时间未留存' }} · 操作人：{{ current.定角记录.操作人 }}
              <span v-if="current.定角记录.备注" class="muted">（{{ current.定角记录.备注 }}）</span>
            </p>
            <p v-else class="muted">尚未定角</p>
            <h4>试镜排期</h4>
            <table class="data-table">
              <thead>
                <tr>
                  <th>演员</th>
                  <th>试镜日期</th>
                  <th>状态</th>
                  <th>排期时间 / 操作人</th>
                  <th>取消时间 / 操作人</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="session in current.试镜排期" :key="session.id">
                  <td>{{ session.演员 }}</td>
                  <td>{{ session.试镜日期 }}</td>
                  <td>{{ session.状态 }}</td>
                  <td>{{ session.排期时间 }} / {{ session.操作人 }}</td>
                  <td>{{ session.取消时间 ? `${session.取消时间} / ${session.取消人}` : '—' }}</td>
                </tr>
                <tr v-if="!current.试镜排期.length">
                  <td colspan="5" class="empty-state">暂无试镜安排</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <h4>流转记录</h4>
            <ul class="timeline">
              <li v-for="(flow, index) in current.流转记录" :key="index">
                <strong>{{ flow.动作 }}</strong>
                {{ flow.从状态 ?? '—' }} → {{ flow.到状态 }}
                <span class="muted">{{ flow.时间 ?? '时间未留存' }} · {{ flow.操作人 }}</span>
                <div v-if="flow.说明" class="muted">{{ flow.说明 }}</div>
              </li>
              <li v-if="!current.流转记录.length" class="muted">暂无流转记录</li>
            </ul>
          </div>
        </div>
      </section>
    </template>

    <div v-if="actionForm" class="dialog-mask" @click.self="actionForm = null">
      <div class="dialog">
        <h3>{{ actionForm.action }} · {{ actionForm.row.角色名称 }}</h3>
        <label v-if="actionForm.action === '安排试镜'">
          演员
          <input v-model="actionForm.actor" placeholder="试镜演员姓名" />
        </label>
        <label v-if="actionForm.action === '安排试镜'">
          试镜日期
          <input v-model="actionForm.date" type="date" />
        </label>
        <label v-if="actionForm.action === '确认定角'">
          定角演员
          <input v-model="actionForm.actor" placeholder="定角演员姓名" />
        </label>
        <label v-if="actionForm.action === '更换演员'">
          新演员
          <input v-model="actionForm.actor" placeholder="更换后的演员姓名" />
        </label>
        <label v-if="actionForm.action === '取消试镜'">
          演员（留空表示取消全部进行中的试镜）
          <input v-model="actionForm.actor" placeholder="可指定演员" />
        </label>
        <label v-if="actionForm.action === '调整候选'">
          候选演员（用「、」分隔）
          <input v-model="actionForm.candidates" placeholder="例如：张三、李四" />
        </label>
        <label>
          操作人
          <input v-model="operator" placeholder="操作人姓名" />
        </label>
        <div class="dialog-actions">
          <button class="btn ghost" type="button" @click="actionForm = null">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitAction">
            确认{{ actionForm.action }}
          </button>
        </div>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条角色选角记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

interface AuditionItem {
  id: number
  演员: string
  试镜日期: string
  状态: string
  操作人: string
  排期时间: string
  取消时间?: string | null
  取消人?: string | null
}

interface FlowItem {
  时间: string | null
  操作人: string
  动作: string
  从状态: string | null
  到状态: string
  说明?: string
}

interface CastRecord {
  演员: string
  时间: string | null
  操作人: string
  备注?: string
}

interface TrackItem {
  id: number
  角色编号: string
  角色名称: string
  角色类型?: string
  角色说明?: string
  status: string
  候选演员列表: string[]
  试镜排期: AuditionItem[]
  定角演员: string | null
  定角记录: CastRecord | null
  流转记录: FlowItem[]
}

type Row = Record<string, unknown> & { id: number; status?: string; 定角演员?: string | null }

interface ActionForm {
  action: string
  row: Row
  actor: string
  date: string
  candidates: string
}

const ENDPOINT = '/api/casting'
const columns = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期", "片酬区间", "签约状态", "角色说明"]
const statuses = ["待试镜", "试镜中", "已定角", "已换角"]

const session = useSessionStore()
const operator = ref(session.operator)

const view = ref<'list' | 'tracking'>('list')
const rows = ref<Row[]>([])
const tracking = ref<TrackItem[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref({ keyword: '', status: '' })
const currentId = ref<number | null>(null)
const actionForm = ref<ActionForm | null>(null)
const submitting = ref(false)

// 上一次读取成功的快照：读取失败时恢复，页面不停在半更新状态
const lastGood = ref<{ rows: Row[]; tracking: TrackItem[]; total: number } | null>(null)

const current = computed(() => tracking.value.find((item) => item.id === currentId.value) ?? null)

const stats = computed(() => {
  const count = (status: string) => tracking.value.filter((item) => item.status === status).length
  return [
    { label: '待试镜角色', value: count('待试镜') },
    { label: '试镜中角色', value: count('试镜中') },
    { label: '已定角角色', value: count('已定角') },
  ]
})

function availableActions(row: Row): string[] {
  switch (row.status) {
    case '待试镜':
      return ['安排试镜', '调整候选']
    case '试镜中':
      return ['安排试镜', '取消试镜', '确认定角', '调整候选']
    case '已定角':
      return ['更换演员']
    default:
      return []
  }
}

function auditionSummary(item: TrackItem): string {
  if (!item.试镜排期.length) return '—'
  const open = item.试镜排期.filter((session) => session.状态 === '已排期').length
  return `共 ${item.试镜排期.length} 场 · 进行中 ${open} 场`
}

function lastFlow(item: TrackItem): string {
  const last = item.流转记录[item.流转记录.length - 1]
  if (!last) return '—'
  return `${last.动作} · ${last.时间 ?? '时间未留存'} · ${last.操作人}`
}

function openTracking(id: number) {
  currentId.value = id
  view.value = 'tracking'
}

function toggleSelect(id: number) {
  currentId.value = currentId.value === id ? null : id
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '角色登记入口尚未接入审批流'
}

function openAction(action: string, row: Row) {
  const candidates = Array.isArray(row.候选演员列表) ? (row.候选演员列表 as string[]) : []
  actionForm.value = {
    action,
    row,
    actor: action === '确认定角' ? candidates[0] ?? '' : '',
    date: '',
    candidates: candidates.join('、'),
  }
}

async function submitAction() {
  const form = actionForm.value
  if (!form) return
  submitting.value = true
  errorMessage.value = ''
  const values: Record<string, unknown> = { action: form.action, 操作人: operator.value }
  if (form.action === '安排试镜') {
    values.演员 = form.actor
    values.试镜日期 = form.date
  }
  if (form.action === '确认定角' || form.action === '取消试镜') {
    values.演员 = form.actor
  }
  if (form.action === '更换演员') {
    values.新演员 = form.actor
  }
  if (form.action === '调整候选') {
    values.候选演员 = form.candidates
  }
  try {
    const response = await request(`${ENDPOINT}/${form.row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      const detail = typeof payload?.detail === 'string' ? payload.detail : null
      throw new Error(payload?.message ?? detail ?? '角色选角动作未生效，请稍后重试')
    }
    actionForm.value = null
    // 候选或状态变化后，选角列表与定角追踪视图一起刷新，保持同步
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '角色选角操作失败'
  } finally {
    submitting.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const [listResponse, trackingResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/tracking?${query.toString()}`),
    ])
    if (!listResponse.ok || !trackingResponse.ok) {
      throw new Error('角色选角数据读取失败')
    }
    const listPayload = await listResponse.json()
    const trackingPayload = await trackingResponse.json()
    rows.value = listPayload.items ?? []
    total.value = listPayload.total ?? rows.value.length
    tracking.value = trackingPayload.items ?? []
    lastGood.value = structuredClone({ rows: rows.value, tracking: tracking.value, total: total.value })
  } catch (error) {
    if (lastGood.value) {
      rows.value = lastGood.value.rows
      tracking.value = lastGood.value.tracking
      total.value = lastGood.value.total
      errorMessage.value = '数据读取失败，已恢复到上一次成功的状态'
    } else {
      errorMessage.value = error instanceof Error ? error.message : '角色选角列表读取失败'
    }
  }
}

onMounted(reload)
</script>
