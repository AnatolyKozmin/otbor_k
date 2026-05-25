<template>
  <AppLayout>
    <h2>Добро пожаловать, {{ auth.user.name }}!</h2>

    <div class="stages">
      <router-link to="/applicants?tab=anketa" class="stage-card">
        <div class="stage-icon">📋</div>
        <h3>Анкета</h3>
        <p>Первый этап отбора</p>
        <span class="stage-badge">Этап 1</span>
      </router-link>
      <router-link to="/applicants?tab=homework" class="stage-card">
        <div class="stage-icon">📝</div>
        <h3>Домашка</h3>
        <p>Второй этап отбора</p>
        <span class="stage-badge">Этап 2</span>
      </router-link>
      <router-link to="/applicants?tab=interview" class="stage-card">
        <div class="stage-icon">🎙️</div>
        <h3>Собес</h3>
        <p>Третий этап отбора</p>
        <span class="stage-badge">Этап 3</span>
      </router-link>
    </div>

    <!-- Admin: распределение проверки -->
    <div v-if="auth.isAdmin" class="card">
      <div class="dist-header">
        <h3>Распределение проверки</h3>
        <div class="dist-header-actions">
          <button
            class="sync-btn"
            :disabled="syncing"
            :title="'Перезаписать ВСЕ оценки в Google Sheets из базы и подчистить пустые ячейки'"
            @click="syncNow"
          >
            {{ syncing ? 'Выгрузка…' : '⟳ Выгрузить всё в Sheets' }}
          </button>
          <router-link to="/admin/assignments" class="dist-link">Подробнее →</router-link>
        </div>
      </div>

      <div v-if="syncMsg" class="sync-msg" :class="syncMsgKind">{{ syncMsg }}</div>

      <div v-if="overviewLoading" class="muted-msg">Загрузка…</div>
      <div v-else-if="overviewError" class="muted-msg err">{{ overviewError }}</div>
      <template v-else-if="overview">

        <!-- Totals -->
        <div class="totals-grid">
          <div v-for="s in SHEETS" :key="s.key" class="total-cell">
            <span class="total-icon">{{ s.icon }}</span>
            <div class="total-info">
              <div class="total-num">
                {{ overview.totals_reviewed[s.key] }} / {{ overview.totals_assigned[s.key] }}
              </div>
              <div class="total-lbl">{{ s.label }} (проверено / назначено)</div>
            </div>
          </div>
        </div>

        <!-- Per-coordinator table -->
        <div class="dist-table-wrap">
          <table class="dist-table">
            <thead>
              <tr>
                <th>Координатор</th>
                <th>Факультеты</th>
                <th class="num-th" v-for="s in SHEETS" :key="s.key">{{ s.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in overview.coordinators" :key="c.id">
                <td class="name-cell">{{ c.name }}</td>
                <td>
                  <span v-if="c.faculties.length" class="fac-mini-tags">
                    <span v-for="f in c.faculties" :key="f" class="fac-mini">{{ f }}</span>
                  </span>
                  <span v-else class="muted">—</span>
                </td>
                <td v-for="s in SHEETS" :key="s.key" class="num-cell">
                  <span
                    v-if="c.assigned[s.key] > 0"
                    class="cnt"
                    :class="{ done: c.reviewed[s.key] === c.assigned[s.key] }"
                  >
                    {{ c.reviewed[s.key] }}<span class="cnt-sep">/</span>{{ c.assigned[s.key] }}
                  </span>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <!-- Selected candidates by faculty -->
    <div class="card" v-if="selSummary">
      <div class="sel-header">
        <h3>Отобранные кандидаты</h3>
        <span class="sel-total-badge">Итого: {{ selSummary.total }}</span>
      </div>
      <div v-if="!selSummary.total" class="muted-msg">Пока никто не отмечен.</div>
      <div v-else class="sel-grid">
        <div
          v-for="(count, faculty) in sortedFaculties"
          :key="faculty"
          class="sel-fac-cell"
        >
          <span class="sel-fac-name">{{ faculty }}</span>
          <span class="sel-fac-count">{{ count }}</span>
        </div>
      </div>
    </div>

    <div v-if="auth.user.role === 'coordinator'" class="card">
      <div class="faculties-header">
        <div>
          <h3>Мои факультеты</h3>
          <p class="hint">Отметь факультеты, анкеты которых ты готов проверять</p>
        </div>
        <button v-if="!editing" class="edit-btn" @click="startEdit">Изменить</button>
        <div v-else class="edit-actions">
          <button class="btn-cancel" @click="cancelEdit">Отмена</button>
          <button class="btn-save" @click="saveEdit" :disabled="saving">
            {{ saving ? 'Сохранение...' : 'Сохранить' }}
          </button>
        </div>
      </div>

      <div v-if="!editing" class="fac-display">
        <span v-if="currentFaculties.length" class="fac-tags">
          <span v-for="f in currentFaculties" :key="f" class="fac-tag">{{ f }}</span>
        </span>
        <span v-else class="no-faculties">Факультеты не выбраны</span>
      </div>

      <div v-else class="faculty-grid">
        <label v-for="f in FACULTIES" :key="f" class="fac-check" :class="{ selected: draftFaculties.includes(f) }">
          <input type="checkbox" :value="f" v-model="draftFaculties" />
          {{ f }}
        </label>
      </div>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const FACULTIES = ['НАБ', 'ФЭБ', 'ВШУ', 'ИТиАБД', 'СНиМК', 'МЭО', 'Финфак', 'Юрфак']

const SHEETS = [
  { key: 'anketa',    label: 'Анкета',  icon: '📋' },
  { key: 'homework',  label: 'Домашка', icon: '📝' },
  { key: 'interview', label: 'Собес',   icon: '🎙️' },
]

const auth = useAuthStore()

// Selected summary (all users)
const selSummary = ref(null)

const sortedFaculties = computed(() => {
  if (!selSummary.value?.by_faculty) return {}
  return Object.fromEntries(
    Object.entries(selSummary.value.by_faculty).sort((a, b) => b[1] - a[1])
  )
})

// Admin overview
const overview = ref(null)
const overviewLoading = ref(false)
const overviewError = ref('')

// Sync now
const syncing = ref(false)
const syncMsg = ref('')
const syncMsgKind = ref('ok')  // 'ok' | 'warn' | 'err'

async function loadOverview() {
  overviewLoading.value = true
  try {
    const { data } = await api.get('/admin/distribution-overview')
    overview.value = data
  } catch (e) {
    overviewError.value = e.response?.data?.detail || 'Ошибка загрузки'
  } finally {
    overviewLoading.value = false
  }
}

onMounted(async () => {
  const { data } = await api.get('/results/selected-summary')
  selSummary.value = data

  if (!auth.isAdmin) return
  await loadOverview()
})

async function syncNow() {
  syncing.value = true
  syncMsg.value = ''
  try {
    const { data } = await api.post('/admin/sync-now')
    const labelMap = { anketa: 'Анкета', homework: 'Домашка', interview: 'Собес' }

    if (!data.sheets_available) {
      syncMsgKind.value = 'err'
      syncMsg.value = 'Google Sheets недоступен: ' + (data.errors?.[0]?.message || 'неизвестная ошибка')
    } else if (data.total_reviews === 0) {
      syncMsgKind.value = 'ok'
      syncMsg.value = 'В базе нет ни одной финальной оценки — выгружать нечего.'
    } else {
      const exported = Object.entries(data.exported || {})
        .filter(([, n]) => n > 0)
        .map(([k, n]) => `${labelMap[k] || k}: ${n}`)
      const cleaned = Object.values(data.none_cleaned || {}).reduce((a, b) => a + b, 0)
      const errs = data.errors?.length || 0
      syncMsgKind.value = errs ? 'warn' : 'ok'

      let msg = exported.length
        ? `Выгружено в Sheets — ${exported.join(', ')}.`
        : 'Ничего не выгружено.'
      if (cleaned) msg += ` Подчищено пустых ячеек ('None'): ${cleaned}.`
      if (errs) msg += ` Ошибок: ${errs} (${data.errors[0].message}).`
      syncMsg.value = msg
    }
    await loadOverview()
  } catch (e) {
    syncMsgKind.value = 'err'
    syncMsg.value = e.response?.data?.detail || 'Ошибка выгрузки'
  } finally {
    syncing.value = false
  }
}

const currentFaculties = ref([...(auth.user.faculties || [])])
const draftFaculties = ref([])
const editing = ref(false)
const saving = ref(false)

function startEdit() {
  draftFaculties.value = [...currentFaculties.value]
  editing.value = true
}

function cancelEdit() {
  editing.value = false
}

async function saveEdit() {
  saving.value = true
  try {
    const { data } = await api.patch(`/users/${auth.user.id}/faculties`, { faculties: draftFaculties.value })
    currentFaculties.value = data.faculties
    // sync store so sidebar stays consistent
    auth.user.faculties = data.faculties
    localStorage.setItem('user', JSON.stringify(auth.user))
    editing.value = false
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
h2 { margin: 0 0 1.5rem; color: #1a1a2e; font-size: 1.4rem; }

.stages {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stage-card {
  background: white;
  padding: 1.75rem;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  text-decoration: none;
  color: inherit;
  display: block;
  transition: box-shadow 0.15s, transform 0.15s;
  cursor: pointer;
}
.stage-card:hover {
  box-shadow: 0 4px 16px rgba(67, 97, 238, 0.15);
  transform: translateY(-2px);
}

.stage-icon { font-size: 2rem; margin-bottom: 0.75rem; }
.stage-card h3 { margin: 0 0 0.4rem; color: #1a1a2e; }
.stage-card p { margin: 0 0 1rem; color: #888; font-size: 0.875rem; }

.stage-badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  background: rgba(67, 97, 238, 0.1);
  color: #4361ee;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
}

.card {
  background: white;
  padding: 1.5rem;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  margin-bottom: 1.5rem;
}

/* Admin distribution */
.dist-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.dist-header h3 { margin: 0; color: #1a1a2e; font-size: 1rem; }

.dist-link {
  color: #4361ee;
  text-decoration: none;
  font-size: 0.82rem;
  font-weight: 600;
}
.dist-link:hover { text-decoration: underline; }

.dist-header-actions { display: flex; align-items: center; gap: 1rem; }

.sync-btn {
  padding: 0.45rem 0.9rem;
  border: 1.5px solid #4361ee;
  background: white;
  color: #4361ee;
  border-radius: 8px;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.sync-btn:hover:not(:disabled) { background: #4361ee; color: white; }
.sync-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.sync-msg {
  margin-bottom: 0.85rem;
  padding: 0.6rem 0.85rem;
  border-radius: 8px;
  font-size: 0.82rem;
  line-height: 1.4;
}
.sync-msg.ok   { background: rgba(6,214,160,0.1);  color: #06875e; }
.sync-msg.warn { background: rgba(255,190,11,0.15); color: #c98a00; }
.sync-msg.err  { background: rgba(230,57,70,0.1);   color: #b02935; }

.muted-msg { color: #aaa; font-size: 0.875rem; padding: 1rem 0; }
.muted-msg.err { color: #e63946; }

.totals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.total-cell {
  background: rgba(67,97,238,0.04);
  border-radius: 10px;
  padding: 0.85rem 1rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.total-icon { font-size: 1.6rem; flex-shrink: 0; }

.total-info { display: flex; flex-direction: column; min-width: 0; }
.total-num { font-size: 1.15rem; font-weight: 700; color: #1a1a2e; line-height: 1.2; }
.total-lbl { font-size: 0.7rem; color: #888; }

.dist-table-wrap { overflow-x: auto; }

.dist-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.dist-table th {
  text-align: left;
  padding: 0.5rem 0.6rem;
  font-size: 0.7rem;
  color: #888;
  font-weight: 600;
  border-bottom: 1.5px solid #f0f0f0;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.dist-table th.num-th { text-align: center; width: 90px; }

.dist-table td {
  padding: 0.55rem 0.6rem;
  border-bottom: 1px solid #f7f7f7;
  color: #333;
  vertical-align: middle;
}

.name-cell { font-weight: 500; white-space: nowrap; }

.fac-mini-tags { display: flex; gap: 0.25rem; flex-wrap: wrap; }

.fac-mini {
  background: rgba(67,97,238,0.08);
  color: #4361ee;
  border-radius: 4px;
  padding: 0.1rem 0.4rem;
  font-size: 0.7rem;
  font-weight: 600;
}

.num-cell { text-align: center; }

.cnt {
  display: inline-block;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: #4361ee;
  font-size: 0.85rem;
}
.cnt.done { color: #06a07a; }
.cnt-sep { color: #ccc; margin: 0 0.15rem; font-weight: 400; }

.muted { color: #ccc; }

.faculties-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.faculties-header h3 { margin: 0 0 0.2rem; color: #1a1a2e; font-size: 1rem; }
.hint { margin: 0; color: #999; font-size: 0.82rem; }

.edit-btn {
  padding: 0.4rem 1rem;
  background: transparent;
  border: 1.5px solid #4361ee;
  color: #4361ee;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.15s;
  flex-shrink: 0;
}

.edit-btn:hover { background: #4361ee; color: white; }

.edit-actions { display: flex; gap: 0.5rem; }

.btn-cancel {
  padding: 0.4rem 0.9rem;
  background: transparent;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.85rem;
  color: #666;
}

.btn-save {
  padding: 0.4rem 1rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
}

.btn-save:disabled { opacity: 0.6; cursor: not-allowed; }

.fac-display { min-height: 2rem; display: flex; align-items: center; }

.fac-tags { display: flex; gap: 0.4rem; flex-wrap: wrap; }

.fac-tag {
  display: inline-block;
  padding: 0.3rem 0.7rem;
  background: rgba(67, 97, 238, 0.1);
  color: #4361ee;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
}

.no-faculties { color: #bbb; font-size: 0.875rem; font-style: italic; }

/* Selected summary */
.sel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.sel-header h3 { margin: 0; color: #1a1a2e; font-size: 1rem; }

.sel-total-badge {
  background: rgba(67,97,238,0.1);
  color: #4361ee;
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.25rem 0.7rem;
  border-radius: 20px;
}

.sel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 0.6rem;
}

.sel-fac-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(67,97,238,0.04);
  border: 1.5px solid rgba(67,97,238,0.12);
  border-radius: 8px;
  padding: 0.55rem 0.75rem;
}

.sel-fac-name {
  font-size: 0.82rem;
  font-weight: 600;
  color: #333;
}

.sel-fac-count {
  font-size: 1.1rem;
  font-weight: 800;
  color: #4361ee;
  line-height: 1;
}

.faculty-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 0.5rem;
}

.fac-check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  border: 1.5px solid #e8e8e8;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
  transition: all 0.15s;
  user-select: none;
}

.fac-check:hover { border-color: #4361ee; background: rgba(67, 97, 238, 0.04); }
.fac-check.selected { border-color: #4361ee; background: rgba(67, 97, 238, 0.08); color: #4361ee; }
.fac-check input { display: none; }
</style>
