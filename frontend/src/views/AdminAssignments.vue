<template>
  <AppLayout>
    <div class="top-bar">
      <h2>Распределение проверки</h2>

      <div class="tab-group">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          class="tab"
          :class="{ active: activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >{{ tab.label }}</button>
      </div>

      <button
        v-if="activeTab === 'homework'"
        class="btn-distribute"
        :disabled="syncing"
        @click="syncHomework"
      >
        {{ syncing ? 'Синхронизирую…' : '⟳ Синхронизировать домашки' }}
      </button>
      <button
        v-else
        class="btn-distribute"
        :disabled="distributing"
        @click="doDistribute"
      >
        {{ distributing ? 'Распределяю…' : 'Распределить равномерно' }}
      </button>
    </div>

    <!-- Homework-only stats: потери по причинам + нагрузка координаторов -->
    <template v-if="activeTab === 'homework' && hwStats">
      <div class="stats-bar">
        <div class="stat">
          <span class="stat-val">{{ hwStats.total }}</span>
          <span class="stat-lbl">Всего домашек</span>
        </div>
        <div class="stat ok">
          <span class="stat-val">{{ hwStats.distributed }}</span>
          <span class="stat-lbl">Распределено</span>
        </div>
        <div class="stat warn" v-if="hwStats.lost_no_id > 0">
          <span class="stat-val">{{ hwStats.lost_no_id }}</span>
          <span class="stat-lbl">Без студ. билета</span>
        </div>
        <div class="stat warn" v-if="hwStats.lost_no_anketa > 0">
          <span class="stat-val">{{ hwStats.lost_no_anketa }}</span>
          <span class="stat-lbl">Нет матча с анкетой</span>
        </div>
        <div class="stat warn" v-if="hwStats.lost_no_coord > 0">
          <span class="stat-val">{{ hwStats.lost_no_coord }}</span>
          <span class="stat-lbl">Нет координатора</span>
        </div>
      </div>

      <div class="hw-coord-card">
        <h3>Нагрузка координаторов (домашка)</h3>
        <div class="hw-coord-table-wrap">
          <table class="hw-coord-table">
            <thead>
              <tr>
                <th>Координатор</th>
                <th>Факультеты</th>
                <th class="num-col">Назначено</th>
                <th class="num-col">Проверено</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in hwStats.coordinators" :key="c.id">
                <td class="name-cell">{{ c.name }}</td>
                <td>
                  <span v-if="c.faculties.length" class="fac-tags-mini">
                    <span v-for="f in c.faculties" :key="f" class="fac-mini">{{ f }}</span>
                  </span>
                  <span v-else class="muted">—</span>
                </td>
                <td class="num-col">
                  <span v-if="c.assigned > 0" class="cnt">{{ c.assigned }}</span>
                  <span v-else class="muted">—</span>
                </td>
                <td class="num-col">
                  <span
                    v-if="c.assigned > 0"
                    class="cnt"
                    :class="{ done: c.reviewed === c.assigned }"
                  >
                    {{ c.reviewed }}<span class="cnt-sep">/</span>{{ c.assigned }}
                  </span>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Статистика -->
    <div v-if="stats" class="stats-bar">
      <div class="stat">
        <span class="stat-val">{{ stats.total }}</span>
        <span class="stat-lbl">Всего</span>
      </div>
      <div class="stat ok">
        <span class="stat-val">{{ stats.assigned }}</span>
        <span class="stat-lbl">Назначено</span>
      </div>
      <div class="stat warn" v-if="stats.total - stats.assigned > 0">
        <span class="stat-val">{{ stats.total - stats.assigned }}</span>
        <span class="stat-lbl">Без проверяющего</span>
      </div>
    </div>

    <!-- Уведомление о распределении -->
    <div v-if="distMsg" class="dist-msg" :class="distMsg.ok ? 'ok' : 'err'">
      {{ distMsg.text }}
    </div>

    <!-- Поиск -->
    <div class="search-wrap">
      <input
        v-model="search"
        class="search-input"
        placeholder="Поиск по ФИО или проверяющему…"
      />
    </div>

    <!-- Состояния -->
    <div v-if="state === 'loading'" class="state-msg">Загрузка…</div>
    <div v-else-if="state === 'empty'" class="state-msg muted">
      Данные не загружены. Сначала загрузите данные из Google Sheets.
    </div>
    <div v-else-if="state === 'error'" class="state-msg error">{{ errorMsg }}</div>

    <!-- Таблица -->
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="num-col">#</th>
            <th>ФИО</th>
            <th>Факультет</th>
            <th>Проверяющий</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredRows"
            :key="row.row_number"
            :class="{ 'no-reviewer': !row.reviewer }"
          >
            <td class="num-col muted">{{ row.row_number }}</td>
            <td class="fio-cell">{{ row.fio || '—' }}</td>
            <td>
              <span v-if="row.faculty" class="fac-badge">{{ row.faculty }}</span>
              <span v-else class="muted">—</span>
            </td>
            <td>
              <span v-if="row.reviewer" class="reviewer">{{ row.reviewer }}</span>
              <span v-else class="no-rev-label">не назначен</span>
            </td>
          </tr>
          <tr v-if="filteredRows.length === 0 && search">
            <td colspan="4" class="muted" style="text-align:center;padding:2rem">
              Ничего не найдено
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const TABS = [
  { key: 'anketa',   label: 'Анкета' },
  { key: 'homework', label: 'Домашка' },
]

const activeTab = ref('anketa')
const state = ref('loading')
const errorMsg = ref('')
const rows = ref([])
const stats = ref(null)
const search = ref('')
const distributing = ref(false)
const distMsg = ref(null)
const syncing = ref(false)
const hwStats = ref(null)

const filteredRows = computed(() => {
  if (!search.value.trim()) return rows.value
  const q = search.value.trim().toLowerCase()
  return rows.value.filter(r =>
    r.fio?.toLowerCase().includes(q) ||
    r.reviewer?.toLowerCase().includes(q) ||
    r.faculty?.toLowerCase().includes(q)
  )
})

onMounted(() => loadTab('anketa'))

async function switchTab(key) {
  activeTab.value = key
  search.value = ''
  await loadTab(key)
}

async function loadTab(key) {
  state.value = 'loading'
  distMsg.value = null
  hwStats.value = null
  try {
    const reqs = [api.get(`/admin/assignments/${key}`)]
    if (key === 'homework') reqs.push(api.get('/admin/homework/stats'))
    const responses = await Promise.all(reqs)
    const data = responses[0].data
    if (!data.total) {
      state.value = 'empty'
      rows.value = []
      stats.value = null
    } else {
      state.value = 'ok'
      rows.value = data.rows
      stats.value = { total: data.total, assigned: data.assigned }
    }
    if (key === 'homework') {
      hwStats.value = responses[1].data
    }
  } catch (e) {
    state.value = 'error'
    errorMsg.value = e.response?.data?.detail || 'Ошибка загрузки'
  }
}

async function syncHomework() {
  syncing.value = true
  distMsg.value = null
  try {
    const { data } = await api.post('/admin/homework/sync')
    const parts = []
    if (data.loaded_new) parts.push(`загружено: ${data.loaded_new}`)
    if (data.distributed) parts.push(`распределено: ${data.distributed}`)
    const lost = data.lost_no_id + data.lost_no_anketa + data.lost_no_coord
    if (lost) parts.push(`не назначено: ${lost}`)
    distMsg.value = {
      ok: !data.errors?.length,
      text: parts.length ? parts.join(', ') : 'Новых домашек нет',
    }
    if (data.errors?.length) distMsg.value.text += ` · ошибки: ${data.errors.join('; ')}`
    await loadTab('homework')
  } catch (e) {
    distMsg.value = { ok: false, text: e.response?.data?.detail || 'Ошибка синхронизации' }
  } finally {
    syncing.value = false
  }
}

async function doDistribute() {
  distributing.value = true
  distMsg.value = null
  try {
    const { data } = await api.post('/admin/distribute', { sheet: activeTab.value })
    distMsg.value = {
      ok: true,
      text: `Распределено ${data.assigned} анкет` +
        (data.unassigned ? `. Без покрытия: ${data.unassigned} (нет координаторов для: ${Object.keys(data.unassigned_faculties).join(', ')})` : ''),
    }
    await loadTab(activeTab.value)
  } catch (e) {
    distMsg.value = { ok: false, text: e.response?.data?.detail || 'Ошибка распределения' }
  } finally {
    distributing.value = false
  }
}
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
}
h2 { margin: 0; font-size: 1.4rem; color: #1a1a2e; flex-shrink: 0; }

.tab-group { display: flex; gap: 0.35rem; }
.tab {
  padding: 0.4rem 1rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  background: white;
  font-size: 0.875rem;
  cursor: pointer;
  color: #555;
  transition: all 0.12s;
}
.tab:hover { border-color: #4361ee; color: #4361ee; }
.tab.active { background: #4361ee; border-color: #4361ee; color: white; }

.btn-distribute {
  margin-left: auto;
  padding: 0.5rem 1.2rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}
.btn-distribute:hover:not(:disabled) { background: #3451d1; }
.btn-distribute:disabled { opacity: 0.6; cursor: not-allowed; }

/* Stats */
.stats-bar {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}
.stat {
  background: white;
  border-radius: 10px;
  padding: 0.75rem 1.25rem;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 90px;
}
.stat-val { font-size: 1.4rem; font-weight: 700; color: #1a1a2e; }
.stat-lbl { font-size: 0.72rem; color: #888; margin-top: 0.1rem; }
.stat.ok .stat-val  { color: #06a07a; }
.stat.warn .stat-val { color: #e08c00; }

.dist-msg {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.875rem;
  margin-bottom: 1rem;
}
.dist-msg.ok  { background: rgba(6,214,160,0.1); color: #05a87c; }
.dist-msg.err { background: rgba(230,57,70,0.08); color: #e63946; }

.hw-coord-card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 1.25rem 1.4rem;
  margin-bottom: 1rem;
}
.hw-coord-card h3 { margin: 0 0 0.85rem; color: #1a1a2e; font-size: 0.95rem; }

.hw-coord-table-wrap { overflow-x: auto; }

.hw-coord-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.hw-coord-table th {
  text-align: left;
  padding: 0.5rem 0.6rem;
  font-size: 0.7rem;
  color: #888;
  font-weight: 600;
  border-bottom: 1.5px solid #f0f0f0;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.hw-coord-table th.num-col { text-align: center; width: 110px; }
.hw-coord-table td {
  padding: 0.55rem 0.6rem;
  border-bottom: 1px solid #f7f7f7;
  color: #333;
  vertical-align: middle;
}
.hw-coord-table td.num-col { text-align: center; }
.hw-coord-table .name-cell { font-weight: 500; white-space: nowrap; }

.fac-tags-mini { display: flex; gap: 0.25rem; flex-wrap: wrap; }
.fac-mini {
  background: rgba(67,97,238,0.08);
  color: #4361ee;
  border-radius: 4px;
  padding: 0.1rem 0.4rem;
  font-size: 0.7rem;
  font-weight: 600;
}

.cnt {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: #4361ee;
  font-size: 0.85rem;
}
.cnt.done { color: #06a07a; }
.cnt-sep { color: #ccc; margin: 0 0.15rem; font-weight: 400; }

.search-wrap { margin-bottom: 0.75rem; }
.search-input {
  width: 100%;
  max-width: 400px;
  padding: 0.55rem 0.85rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.875rem;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.search-input:focus { border-color: #4361ee; }

/* Table */
.table-wrap {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow: auto;
  max-height: calc(100vh - 300px);
}

table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }

thead { position: sticky; top: 0; z-index: 2; background: #fafafa; }

th {
  padding: 0.6rem 0.85rem;
  text-align: left;
  font-size: 0.72rem;
  color: #888;
  font-weight: 600;
  border-bottom: 2px solid #f0f0f0;
  white-space: nowrap;
}

td {
  padding: 0.55rem 0.85rem;
  border-bottom: 1px solid #f5f5f5;
  color: #333;
}

tr:hover td { background: #f7f8ff; }
tr.no-reviewer td { background: rgba(255,190,11,0.04); }
tr.no-reviewer:hover td { background: rgba(255,190,11,0.09); }

.num-col { width: 52px; text-align: center; color: #bbb; font-size: 0.72rem; }
.fio-cell { font-weight: 500; }

.fac-badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  background: rgba(67,97,238,0.08);
  color: #4361ee;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.reviewer { color: #333; }

.no-rev-label {
  color: #e08c00;
  font-size: 0.8rem;
  font-style: italic;
}

.muted { color: #bbb; }

.state-msg {
  background: white;
  border-radius: 12px;
  padding: 3rem;
  text-align: center;
  font-size: 0.9rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.state-msg.muted { color: #aaa; }
.state-msg.error { color: #e63946; }
</style>
