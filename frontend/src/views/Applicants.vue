<template>
  <AppLayout>
    <div class="top-bar">
      <h2>Заявки</h2>
      <div class="tab-group">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          class="tab"
          :class="{ active: activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
          <span v-if="counts[tab.key] != null" class="count-badge">
            {{ counts[tab.key] }}
          </span>
        </button>
      </div>
    </div>

    <!-- Состояния -->
    <div v-if="state === 'loading'" class="state-msg">Загрузка...</div>

    <div v-else-if="state === 'empty'" class="state-msg muted">
      Данные не загружены. Нажмите «Загрузить из Google Sheets» в разделе Управление.
    </div>

    <div v-else-if="state === 'error'" class="state-msg error">{{ errorMsg }}</div>

    <!-- Таблица -->
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="num-col">#</th>
            <th
              v-for="h in headers"
              :key="h"
              :title="h"
            >
              {{ truncate(h, 40) }}
            </th>
            <th class="open-col"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, idx) in rows"
            :key="row._row ?? idx"
            :class="{ 'row-done': reviewed.has(row._row) }"
          >
            <td class="num-col muted">{{ row._row }}</td>
            <td
              v-for="h in headers"
              :key="h"
              :title="row[h]"
            >
              {{ truncate(row[h], 80) }}
            </td>
            <td class="open-col">
              <button
                class="open-btn"
                :class="{ 'open-btn--done': reviewed.has(row._row) }"
                @click="router.push(`/applicants/${activeTab}/${row._row}`)"
              >
                {{ reviewed.has(row._row) ? '✓ Проверено' : 'Открыть' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const TABS = [
  { key: 'anketa',    label: 'Анкета' },
  { key: 'homework',  label: 'Домашка' },
  { key: 'interview', label: 'Собес' },
]

const router = useRouter()
const route = useRoute()
const VALID_TABS = new Set(['anketa', 'homework', 'interview'])
const initialTab = VALID_TABS.has(route.query.tab) ? route.query.tab : 'anketa'
const activeTab = ref(initialTab)
const headers = ref([])
const rows = ref([])
const counts = ref({})
const state = ref('loading')   // loading | ok | empty | error
const errorMsg = ref('')

// Cache per tab
const cache = {}
const reviewedCache = {}      // key → Set<row_number>
const reviewed = ref(new Set())

onMounted(() => fetchTab(initialTab))

async function switchTab(key) {
  activeTab.value = key
  await fetchTab(key)
}

async function fetchTab(key) {
  state.value = 'loading'

  // Load sheet data (cached)
  if (!cache[key]) {
    try {
      const { data } = await api.get(`/sheets/${key}`)
      cache[key] = data
    } catch (e) {
      state.value = 'error'
      errorMsg.value = e.response?.data?.detail || 'Ошибка загрузки'
      return
    }
  }

  // Load review status (always fresh so new saves are reflected)
  try {
    const { data } = await api.get(`/reviews/${key}/status`)
    reviewedCache[key] = new Set(data.reviewed)
  } catch {
    reviewedCache[key] = new Set()
  }

  reviewed.value = reviewedCache[key]
  applyData(cache[key])
}

// Call after saving a review to update the indicator without full reload
function markReviewed(rowNumber) {
  reviewed.value = new Set([...reviewed.value, rowNumber])
  reviewedCache[activeTab.value] = reviewed.value
}

function applyData(data) {
  if (!data.total) {
    state.value = 'empty'
    headers.value = []
    rows.value = []
  } else {
    state.value = 'ok'
    headers.value = data.headers
    rows.value = data.rows
  }
  counts.value[activeTab.value] = data.total
}

function truncate(str, len) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '…' : str
}
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
}

h2 { margin: 0; color: #1a1a2e; font-size: 1.4rem; flex-shrink: 0; }

.tab-group { display: flex; gap: 0.4rem; }

.tab {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 1rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  background: white;
  font-size: 0.875rem;
  cursor: pointer;
  color: #555;
  transition: all 0.15s;
}

.tab:hover { border-color: #4361ee; color: #4361ee; }

.tab.active {
  background: #4361ee;
  border-color: #4361ee;
  color: white;
}

.count-badge {
  background: rgba(255,255,255,0.25);
  border-radius: 20px;
  padding: 0 0.4rem;
  font-size: 0.72rem;
  font-weight: 700;
}

.tab:not(.active) .count-badge {
  background: rgba(67,97,238,0.1);
  color: #4361ee;
}

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

.table-wrap {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow: auto;
  max-height: calc(100vh - 180px);
}

table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

thead {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #fafafa;
}

th {
  padding: 0.6rem 0.75rem;
  text-align: left;
  font-size: 0.72rem;
  color: #666;
  font-weight: 600;
  border-bottom: 2px solid #f0f0f0;
  white-space: nowrap;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
}

td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #f5f5f5;
  color: #333;
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

tr:hover td { background: #f7f8ff; }

.num-col {
  width: 48px;
  text-align: center;
  color: #bbb;
  font-size: 0.72rem;
  position: sticky;
  left: 0;
  background: inherit;
  z-index: 1;
}

thead .num-col { background: #fafafa; }

.open-col {
  width: 90px;
  text-align: center;
  position: sticky;
  right: 0;
  background: inherit;
  z-index: 1;
}
thead .open-col { background: #fafafa; }

.open-btn {
  padding: 0.3rem 0.65rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.open-btn:hover { background: #3451d1; }
.open-btn--done { background: #06d6a0; }
.open-btn--done:hover { background: #04b88a; }

.row-done td { background: rgba(6, 214, 160, 0.045); }
tr.row-done:hover td { background: rgba(6, 214, 160, 0.09); }
</style>
