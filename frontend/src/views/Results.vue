<template>
  <AppLayout>
    <div class="top-bar">
      <h2>Финальные результаты</h2>
      <div class="top-controls">
        <label class="toggle-label">
          <input type="checkbox" v-model="onlyIncomplete" />
          Только неполные
        </label>
        <label class="toggle-label" v-if="auth.isAdmin">
          <input type="checkbox" v-model="onlySelected" />
          Только выбранные
        </label>
      </div>
    </div>

    <!-- Faculty tabs -->
    <div v-if="faculties.length" class="faculty-tabs">
      <button
        v-for="f in ['Все', ...faculties]"
        :key="f"
        class="fac-tab"
        :class="{ active: activeFaculty === f }"
        @click="activeFaculty = f"
      >
        {{ f }}
        <span class="fac-count">{{ f === 'Все' ? filtered.length : filtered.filter(c => c.faculty === f).length }}</span>
      </button>
    </div>

    <div v-if="loading" class="state-msg">Загрузка…</div>
    <div v-else-if="!filtered.length" class="state-msg muted">Нет данных.</div>

    <div v-else>
      <!-- Summary -->
      <div class="summary-bar">
        <span>Всего: <b>{{ filtered.length }}</b></span>
        <span v-if="auth.isAdmin"> · Выбрано: <b class="sel-count">{{ filtered.filter(c => c.selected).length }}</b></span>
        <span class="warn" v-if="incompleteCount"> · Неполных собесов: <b>{{ incompleteCount }}</b></span>
      </div>

      <!-- Legend -->
      <div class="legend">
        <span class="leg-item leg-one">незаполнен 1 проверяющий</span>
        <span class="leg-item leg-both">не заполнено ни одного</span>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="th-arrow"></th>
              <th>ФИО</th>
              <th>Факультет</th>
              <th class="th-score">Анкета</th>
              <th class="th-score">ДЗ</th>
              <th>Проверяющий 1</th>
              <th>Проверяющий 2</th>
              <th class="th-score th-total">Итого</th>
              <th v-if="auth.isAdmin" class="th-check">✓</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="c in pageFaculty" :key="c.row_number">
              <tr
                class="main-row"
                :class="rowClass(c)"
                @click="toggle(c.row_number)"
              >
                <td class="td-arrow">
                  <span class="arrow" :class="{ open: expanded === c.row_number }">▶</span>
                </td>
                <td class="td-fio">{{ c.fio || '—' }}</td>
                <td>
                  <span v-if="c.faculty" class="fac-badge">{{ c.faculty }}</span>
                  <span v-else class="muted">—</span>
                </td>
                <td class="td-score">
                  <span v-if="c.anketa.score !== null" :class="scoreClass(c.anketa.score, 15)">
                    {{ c.anketa.score }}
                  </span>
                  <span v-else class="muted">—</span>
                </td>
                <td class="td-score">
                  <span v-if="c.homework.score !== null" :class="scoreClass(c.homework.score, 18)">
                    {{ c.homework.score }}
                  </span>
                  <span v-else class="muted">—</span>
                </td>
                <td>
                  <span v-if="c.interview.reviewer1" class="rev-cell">
                    <span class="rev-name">{{ c.interview.reviewer1.name }}</span>
                    <span class="saved-dot" :class="c.interview.reviewer1.saved ? 'dot-ok' : 'dot-no'" :title="c.interview.reviewer1.saved ? 'Заметки сохранены' : 'Заметки не сохранены'"></span>
                  </span>
                  <span v-else class="muted">—</span>
                </td>
                <td>
                  <span v-if="c.interview.reviewer2" class="rev-cell">
                    <span class="rev-name">{{ c.interview.reviewer2.name }}</span>
                    <span class="saved-dot" :class="c.interview.reviewer2.saved ? 'dot-ok' : 'dot-no'" :title="c.interview.reviewer2.saved ? 'Заметки сохранены' : 'Заметки не сохранены'"></span>
                  </span>
                  <span v-else class="muted">—</span>
                </td>
                <td class="td-score td-total">
                  <b v-if="c.total_score !== null">{{ c.total_score }}</b>
                  <span v-else class="muted">—</span>
                </td>
                <td v-if="auth.isAdmin" class="td-check" @click.stop>
                  <input
                    type="checkbox"
                    :checked="c.selected"
                    @change="toggleSelect(c)"
                    class="final-check"
                  />
                </td>
              </tr>

              <!-- Expanded detail -->
              <tr v-if="expanded === c.row_number" class="detail-row">
                <td :colspan="auth.isAdmin ? 9 : 8">
                  <div class="detail-panel">
                    <div class="detail-grid">

                      <!-- Anketa comments -->
                      <div v-if="hasComments(c.anketa.comments)" class="detail-block">
                        <div class="detail-block-title">
                          Анкета
                          <span v-if="c.anketa.reviewer" class="reviewer-hint">— {{ c.anketa.reviewer }}</span>
                          <span v-if="c.anketa.score !== null" class="score-hint">{{ c.anketa.score }} б.</span>
                        </div>
                        <div v-for="(val, label) in c.anketa.comments" :key="label" class="comment-item">
                          <div class="c-label">{{ label }}</div>
                          <div class="c-val">{{ val }}</div>
                        </div>
                      </div>

                      <!-- Homework comments -->
                      <div v-if="hasComments(c.homework.comments)" class="detail-block">
                        <div class="detail-block-title">
                          Домашнее задание
                          <span v-if="c.homework.reviewer" class="reviewer-hint">— {{ c.homework.reviewer }}</span>
                          <span v-if="c.homework.score !== null" class="score-hint">{{ c.homework.score }} б.</span>
                        </div>
                        <div v-for="(val, label) in c.homework.comments" :key="label" class="comment-item">
                          <div class="c-label">{{ label }}</div>
                          <div class="c-val">{{ val }}</div>
                        </div>
                      </div>

                      <!-- Interview reviewer 1 -->
                      <div v-if="c.interview.reviewer1" class="detail-block">
                        <div class="detail-block-title">
                          Собес — {{ c.interview.reviewer1.name }}
                          <span class="saved-tag" :class="c.interview.reviewer1.saved ? 'tag-ok' : 'tag-no'">
                            {{ c.interview.reviewer1.saved ? 'сохранено' : 'не сохранено' }}
                          </span>
                        </div>
                        <template v-if="c.interview.reviewer1.notes && Object.keys(c.interview.reviewer1.notes).length">
                          <div v-for="(val, key) in c.interview.reviewer1.notes" :key="key" class="comment-item">
                            <div class="c-label">{{ key }}</div>
                            <div class="c-val">{{ val }}</div>
                          </div>
                        </template>
                        <div v-else class="no-data">Заметки не сохранены.</div>
                      </div>

                      <!-- Interview reviewer 2 -->
                      <div v-if="c.interview.reviewer2" class="detail-block">
                        <div class="detail-block-title">
                          Собес — {{ c.interview.reviewer2.name }}
                          <span class="saved-tag" :class="c.interview.reviewer2.saved ? 'tag-ok' : 'tag-no'">
                            {{ c.interview.reviewer2.saved ? 'сохранено' : 'не сохранено' }}
                          </span>
                        </div>
                        <template v-if="c.interview.reviewer2.notes && Object.keys(c.interview.reviewer2.notes).length">
                          <div v-for="(val, key) in c.interview.reviewer2.notes" :key="key" class="comment-item">
                            <div class="c-label">{{ key }}</div>
                            <div class="c-val">{{ val }}</div>
                          </div>
                        </template>
                        <div v-else class="no-data">Заметки не сохранены.</div>
                      </div>

                      <div v-if="!c.interview.reviewer1 && !c.interview.reviewer2" class="detail-block">
                        <div class="no-data">Проверяющие на собес не назначены.</div>
                      </div>

                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const auth = useAuthStore()

const loading = ref(true)
const candidates = ref([])
const faculties = ref([])
const activeFaculty = ref('Все')
const expanded = ref(null)
const onlyIncomplete = ref(false)
const onlySelected = ref(false)

const filtered = computed(() => {
  let list = candidates.value
  if (onlyIncomplete.value) {
    list = list.filter(c => c.incomplete === 'one' || c.incomplete === 'both' || c.incomplete === 'no_reviewers')
  }
  if (onlySelected.value) {
    list = list.filter(c => c.selected)
  }
  return list
})

const pageFaculty = computed(() => {
  if (activeFaculty.value === 'Все') return filtered.value
  return filtered.value.filter(c => c.faculty === activeFaculty.value)
})

const incompleteCount = computed(() =>
  filtered.value.filter(c => c.incomplete !== 'none' && c.incomplete !== 'ok').length
)

function toggle(rowNumber) {
  expanded.value = expanded.value === rowNumber ? null : rowNumber
}

function rowClass(c) {
  if (c.incomplete === 'both' || c.incomplete === 'no_reviewers') return 'row-both'
  if (c.incomplete === 'one') return 'row-one'
  if (c.selected) return 'row-selected'
  return ''
}

function scoreClass(score, max) {
  if (score === null || score === undefined) return ''
  const pct = score / max
  if (pct >= 0.75) return 'score-hi'
  if (pct >= 0.4) return 'score-mid'
  return 'score-lo'
}

function hasComments(obj) {
  return obj && Object.keys(obj).length > 0
}

async function toggleSelect(c) {
  const prev = c.selected
  c.selected = !c.selected  // optimistic update
  try {
    const { data } = await api.post(`/results/${c.row_number}/select`)
    c.selected = data.selected
  } catch {
    c.selected = prev
  }
}

onMounted(async () => {
  try {
    const { data } = await api.get('/results/')
    candidates.value = data.candidates
    faculties.value = data.faculties
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}
h2 { margin: 0; color: #1a1a2e; font-size: 1.4rem; flex: 1; }

.top-controls { display: flex; gap: 1rem; align-items: center; }

.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.875rem;
  color: #555;
  cursor: pointer;
  user-select: none;
}

.faculty-tabs {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}

.fac-tab {
  padding: 0.4rem 0.9rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 20px;
  background: white;
  font-size: 0.82rem;
  cursor: pointer;
  color: #555;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
.fac-tab:hover { border-color: #4361ee; color: #4361ee; }
.fac-tab.active { background: #4361ee; border-color: #4361ee; color: white; }

.fac-count {
  display: inline-block;
  background: rgba(255,255,255,0.25);
  padding: 0.05rem 0.35rem;
  border-radius: 10px;
  font-size: 0.7rem;
  font-weight: 700;
}
.fac-tab:not(.active) .fac-count { background: #f0f0f0; color: #888; }

.summary-bar {
  font-size: 0.875rem;
  color: #555;
  margin-bottom: 0.4rem;
}
.sel-count { color: #4361ee; }
.warn { color: #e07b00; }

.legend {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.75rem;
}
.leg-item {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  color: #555;
}
.leg-one { background: rgba(255, 193, 7, 0.2); border-left: 3px solid #ffc107; }
.leg-both { background: rgba(230, 57, 70, 0.12); border-left: 3px solid #e63946; }

.state-msg { color: #888; font-size: 0.9rem; padding: 2rem 0; }
.muted { color: #bbb; }

.table-wrap { overflow-x: auto; }

table { width: 100%; border-collapse: collapse; background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden; }

th {
  text-align: left;
  padding: 0.55rem 0.75rem;
  font-size: 0.75rem;
  color: #888;
  font-weight: 600;
  border-bottom: 1.5px solid #f0f0f0;
  white-space: nowrap;
  background: white;
}
.th-arrow { width: 24px; padding-right: 0; }
.th-score { text-align: center; width: 60px; }
.th-total { color: #1a1a2e; font-size: 0.8rem; }
.th-check { text-align: center; width: 36px; }

td {
  padding: 0.55rem 0.75rem;
  font-size: 0.85rem;
  color: #333;
  border-bottom: 1px solid #f5f5f5;
  vertical-align: middle;
}

.td-arrow { width: 24px; padding-right: 0; }
.td-fio { font-weight: 500; max-width: 200px; }
.td-score { text-align: center; }
.td-total { font-size: 0.95rem; }
.td-check { text-align: center; }

.main-row { cursor: pointer; transition: background 0.1s; }
.main-row:hover { background: #fafafa; }

/* Incomplete highlighting */
.row-one  { background: rgba(255, 193, 7, 0.1); }
.row-one:hover { background: rgba(255, 193, 7, 0.17); }
.row-both { background: rgba(230, 57, 70, 0.07); }
.row-both:hover { background: rgba(230, 57, 70, 0.12); }

/* Selected */
.row-selected { background: rgba(67, 97, 238, 0.05); }
.row-selected:hover { background: rgba(67, 97, 238, 0.1); }

.arrow { font-size: 0.55rem; color: #ccc; display: inline-block; transition: transform 0.15s; }
.arrow.open { transform: rotate(90deg); color: #4361ee; }

.fac-badge {
  display: inline-block;
  padding: 0.15rem 0.4rem;
  background: rgba(67,97,238,0.08);
  color: #4361ee;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
}

.score-hi  { color: #05a87c; font-weight: 700; }
.score-mid { color: #e07b00; font-weight: 600; }
.score-lo  { color: #e63946; font-weight: 600; }

.rev-cell { display: flex; align-items: center; gap: 0.4rem; font-size: 0.82rem; }
.rev-name { color: #333; }

.saved-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
  display: inline-block;
}
.dot-ok  { background: #06d6a0; }
.dot-no  { background: #e0e0e0; }

.final-check { cursor: pointer; width: 16px; height: 16px; accent-color: #4361ee; }

/* Detail row */
.detail-row td { padding: 0; border-bottom: 2px solid #e8eaf0; }

.detail-panel {
  background: #f7f8ff;
  padding: 1.25rem 1.5rem;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.detail-block {
  background: white;
  border-radius: 10px;
  padding: 1rem 1.1rem;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.detail-block-title {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: #4361ee;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.reviewer-hint { font-weight: 500; color: #666; text-transform: none; letter-spacing: 0; }
.score-hint {
  margin-left: auto;
  background: rgba(67,97,238,0.1);
  color: #4361ee;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: none;
  letter-spacing: 0;
}

.saved-tag {
  margin-left: auto;
  font-size: 0.68rem;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0;
}
.tag-ok  { background: rgba(6,214,160,0.15); color: #05a87c; }
.tag-no  { background: rgba(200,200,200,0.3); color: #888; }

.comment-item {
  border-left: 3px solid #e8eaf0;
  padding-left: 0.65rem;
  margin-bottom: 0.5rem;
}
.c-label { font-size: 0.72rem; color: #888; margin-bottom: 0.15rem; }
.c-val { font-size: 0.85rem; color: #222; white-space: pre-wrap; word-break: break-word; }

.no-data { font-size: 0.82rem; color: #bbb; font-style: italic; }
</style>
