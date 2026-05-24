<template>
  <AppLayout>
    <div class="top-bar">
      <h2>Ответы на собеседованиях</h2>
      <input v-model="search" class="search-input" placeholder="Поиск по ФИО…" />
    </div>

    <div v-if="loading" class="state-msg">Загрузка…</div>
    <div v-else-if="!rows.length" class="state-msg muted">Нет записей о собеседованиях.</div>

    <div v-else class="card">
      <div class="summary-line">
        Всего: <b>{{ filtered.length }}</b>
        · С ответами обоих: <b>{{ bothSaved }}</b>
        · Частично: <b>{{ oneSaved }}</b>
        · Без ответов: <b>{{ noneSaved }}</b>
      </div>

      <table>
        <thead>
          <tr>
            <th></th>
            <th>ФИО</th>
            <th>Факультет</th>
            <th>Слот</th>
            <th>Проверяющий 1</th>
            <th>Проверяющий 2</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in filtered" :key="row.row_number">
            <tr class="main-row" :class="{ expanded: expandedRow === row.row_number }" @click="toggle(row.row_number)">
              <td class="expand-cell">
                <span class="arrow" :class="{ open: expandedRow === row.row_number }">▶</span>
              </td>
              <td>{{ row.fio || '—' }}</td>
              <td>
                <span v-if="row.faculty" class="fac-badge">{{ row.faculty }}</span>
                <span v-else class="muted">—</span>
              </td>
              <td class="slot-cell">
                <template v-if="row.slot_date">
                  {{ formatDate(row.slot_date) }} {{ row.slot_hour }}:00
                </template>
                <span v-else class="muted">не записан</span>
              </td>
              <td>
                <span v-if="row.reviewer1" class="rev-name">
                  {{ row.reviewer1.name }}
                  <span class="saved-badge" :class="row.reviewer1.scores ? 'yes' : 'no'">
                    {{ row.reviewer1.scores ? '✓' : '—' }}
                  </span>
                </span>
                <span v-else class="muted">—</span>
              </td>
              <td>
                <span v-if="row.reviewer2" class="rev-name">
                  {{ row.reviewer2.name }}
                  <span class="saved-badge" :class="row.reviewer2.scores ? 'yes' : 'no'">
                    {{ row.reviewer2.scores ? '✓' : '—' }}
                  </span>
                </span>
                <span v-else class="muted">—</span>
              </td>
            </tr>
            <tr v-if="expandedRow === row.row_number" class="detail-row">
              <td colspan="6">
                <div class="detail-panel">
                  <div v-if="!row.reviewer1 && !row.reviewer2" class="no-reviews">
                    Проверяющие не назначены.
                  </div>
                  <div class="reviewers-grid">
                    <div v-for="slot in ['reviewer1', 'reviewer2']" :key="slot" class="reviewer-block">
                      <template v-if="row[slot]">
                        <div class="reviewer-header">
                          <span class="reviewer-label">{{ slot === 'reviewer1' ? 'Проверяющий 1' : 'Проверяющий 2' }}</span>
                          <span class="reviewer-name">{{ row[slot].name }}</span>
                          <span v-if="row[slot].saved_at" class="saved-at">
                            сохранено {{ formatDateTime(row[slot].saved_at) }}
                          </span>
                        </div>
                        <div v-if="row[slot].scores && Object.keys(row[slot].scores).length" class="scores-list">
                          <div v-for="(val, key) in row[slot].scores" :key="key" class="score-item">
                            <div class="score-key">{{ questionText(key) }}</div>
                            <div class="score-val">{{ val }}</div>
                          </div>
                        </div>
                        <div v-else class="no-scores">Ответы не сохранены.</div>
                      </template>
                      <template v-else>
                        <div class="reviewer-header">
                          <span class="reviewer-label">{{ slot === 'reviewer1' ? 'Проверяющий 1' : 'Проверяющий 2' }}</span>
                          <span class="muted">не назначен</span>
                        </div>
                      </template>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const loading = ref(true)
const rows = ref([])
const search = ref('')
const expandedRow = ref(null)
const formKeyMap = ref({})  // field_key → question text

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter(r => r.fio.toLowerCase().includes(q))
})

const bothSaved = computed(() =>
  filtered.value.filter(r => r.reviewer1?.scores && r.reviewer2?.scores).length
)
const oneSaved = computed(() =>
  filtered.value.filter(r =>
    (r.reviewer1?.scores || r.reviewer2?.scores) &&
    !(r.reviewer1?.scores && r.reviewer2?.scores)
  ).length
)
const noneSaved = computed(() =>
  filtered.value.filter(r => !r.reviewer1?.scores && !r.reviewer2?.scores).length
)

function toggle(rowNumber) {
  expandedRow.value = expandedRow.value === rowNumber ? null : rowNumber
}

function formatDate(d) {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

function formatDateTime(iso) {
  const dt = new Date(iso)
  return dt.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function questionText(key) {
  return formKeyMap.value[key] || key
}

onMounted(async () => {
  try {
    const [reviewsRes, formRes] = await Promise.all([
      api.get('/interview/admin/applicant-reviews'),
      api.get('/interview/form'),
    ])
    rows.value = reviewsRes.data.rows

    // Строим словарь key → text из структуры формы
    const map = {}
    for (const section of formRes.data.sections || []) {
      for (const item of section.items || []) {
        if (item.key && item.text) {
          map[item.key] = item.text
        }
      }
    }
    formKeyMap.value = map
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
}
h2 { margin: 0; color: #1a1a2e; font-size: 1.4rem; flex: 1; }

.search-input {
  padding: 0.55rem 0.9rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.875rem;
  outline: none;
  min-width: 200px;
  transition: border-color 0.15s;
}
.search-input:focus { border-color: #4361ee; }

.state-msg { color: #888; font-size: 0.9rem; padding: 2rem 0; }
.muted { color: #bbb; }

.card {
  background: white;
  padding: 1.5rem;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.summary-line {
  font-size: 0.875rem;
  color: #555;
  margin-bottom: 1.25rem;
}

table { width: 100%; border-collapse: collapse; }

th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  font-size: 0.78rem;
  color: #888;
  font-weight: 600;
  border-bottom: 1.5px solid #f0f0f0;
}

.main-row {
  cursor: pointer;
  transition: background 0.1s;
}
.main-row:hover { background: #fafafa; }
.main-row.expanded { background: #f7f8ff; }

td {
  padding: 0.6rem 0.75rem;
  font-size: 0.875rem;
  color: #333;
  border-bottom: 1px solid #f5f5f5;
  vertical-align: middle;
}

.expand-cell { width: 28px; padding-right: 0; }
.arrow { font-size: 0.6rem; color: #bbb; display: inline-block; transition: transform 0.15s; }
.arrow.open { transform: rotate(90deg); color: #4361ee; }

.fac-badge {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  background: rgba(67,97,238,0.08);
  color: #4361ee;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 600;
}

.slot-cell { font-size: 0.82rem; color: #555; white-space: nowrap; }

.rev-name { display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; }

.saved-badge {
  display: inline-block;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 700;
}
.saved-badge.yes { background: rgba(6,214,160,0.15); color: #05a87c; }
.saved-badge.no  { background: rgba(200,200,200,0.2); color: #aaa; }

/* Expanded detail row */
.detail-row td { padding: 0; border-bottom: 2px solid #e8eaf0; }

.detail-panel {
  background: #f7f8ff;
  padding: 1.25rem 1.5rem;
}

.no-reviews { color: #888; font-size: 0.875rem; }

.reviewers-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
}

@media (max-width: 800px) {
  .reviewers-grid { grid-template-columns: 1fr; }
}

.reviewer-block {
  background: white;
  border-radius: 10px;
  padding: 1rem 1.25rem;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.reviewer-header {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.reviewer-label {
  font-size: 0.72rem;
  font-weight: 700;
  color: #4361ee;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.reviewer-name { font-size: 0.9rem; font-weight: 600; color: #1a1a2e; }

.saved-at { font-size: 0.72rem; color: #aaa; margin-left: auto; }

.scores-list { display: flex; flex-direction: column; gap: 0.6rem; }

.score-item {
  border-left: 3px solid #e8eaf0;
  padding-left: 0.75rem;
}

.score-key {
  font-size: 0.75rem;
  color: #888;
  margin-bottom: 0.2rem;
  line-height: 1.3;
}

.score-val {
  font-size: 0.875rem;
  color: #222;
  white-space: pre-wrap;
  word-break: break-word;
}

.no-scores { font-size: 0.82rem; color: #bbb; font-style: italic; }
</style>
