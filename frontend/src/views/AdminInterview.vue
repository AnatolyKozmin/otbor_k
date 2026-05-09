<template>
  <AppLayout>
    <div class="top-bar">
      <h2>Собеседования</h2>
      <div class="stats-inline" v-if="rows.length">
        <span>Всего: <b>{{ rows.length }}</b></span>
        <span>·</span>
        <span class="ok">Назначено: <b>{{ fullyAssigned }}</b></span>
        <span v-if="partiallyAssigned" class="warn">· Частично: <b>{{ partiallyAssigned }}</b></span>
        <span v-if="notAssigned" class="muted">· Без проверяющих: <b>{{ notAssigned }}</b></span>
      </div>
      <div class="top-actions">
        <input v-model="search" class="search-input" placeholder="Поиск по ФИО…" />
        <button class="btn-create" @click="createModal = true">+ Создать вручную</button>
      </div>
    </div>

    <div v-if="loading" class="state-msg">Загрузка…</div>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="num-col">#</th>
            <th>ФИО</th>
            <th>Студ. билет</th>
            <th>Проверяющий 1</th>
            <th>Проверяющий 2</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredRows"
            :key="row.row_number"
            :class="{
              'full': row.reviewer1_id && row.reviewer2_id,
              'partial': (row.reviewer1_id || row.reviewer2_id) && !(row.reviewer1_id && row.reviewer2_id),
            }"
          >
            <td class="num-col muted">{{ row.row_number }}</td>
            <td class="fio-cell">{{ row.fio || '—' }}</td>
            <td class="mono muted">{{ row.student_id || '—' }}</td>
            <td>
              <select
                class="rev-select"
                :value="row.reviewer1_id || ''"
                @change="setReviewer(row, 1, $event.target.value)"
              >
                <option value="">— не назначен —</option>
                <option
                  v-for="c in coordinators"
                  :key="c.id"
                  :value="c.id"
                  :disabled="c.id === row.reviewer2_id"
                >{{ c.name }}</option>
              </select>
            </td>
            <td>
              <select
                class="rev-select"
                :value="row.reviewer2_id || ''"
                @change="setReviewer(row, 2, $event.target.value)"
              >
                <option value="">— не назначен —</option>
                <option
                  v-for="c in coordinators"
                  :key="c.id"
                  :value="c.id"
                  :disabled="c.id === row.reviewer1_id"
                >{{ c.name }}</option>
              </select>
            </td>
          </tr>
          <tr v-if="!filteredRows.length">
            <td colspan="5" class="muted" style="text-align:center;padding:2rem">
              {{ search ? 'Ничего не найдено' : 'Нет данных. Загрузите собесы из Google Sheets.' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Saving indicator -->
    <div v-if="savingRow" class="saving-toast">Сохраняю…</div>

    <!-- Manual create modal -->
    <Teleport to="body">
      <div v-if="createModal" class="modal-overlay" @click.self="createModal = false">
        <div class="modal">
          <h3>Создать запись вручную</h3>
          <p class="modal-hint">Для тестовых «оков» и ручного ввода.</p>
          <label>ФИО кандидата *</label>
          <input v-model="newFio" class="modal-input" placeholder="Иванов Иван Иванович" />
          <label>Номер студ. билета</label>
          <input v-model="newStudentId" class="modal-input" placeholder="21/12345" />
          <div class="modal-actions">
            <button class="btn-cancel" @click="createModal = false">Отмена</button>
            <button class="btn-confirm" :disabled="!newFio.trim() || creating" @click="createManual">
              {{ creating ? 'Создаю…' : 'Создать' }}
            </button>
          </div>
          <div v-if="createMsg" class="create-msg" :class="createMsg.ok ? 'ok' : 'err'">
            {{ createMsg.text }}
          </div>
        </div>
      </div>
    </Teleport>
  </AppLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const loading = ref(true)
const rows = ref([])
const coordinators = ref([])
const search = ref('')
const savingRow = ref(false)

const createModal = ref(false)
const newFio = ref('')
const newStudentId = ref('')
const creating = ref(false)
const createMsg = ref(null)

const filteredRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter(r => r.fio?.toLowerCase().includes(q))
})

const fullyAssigned = computed(
  () => rows.value.filter(r => r.reviewer1_id && r.reviewer2_id).length
)
const partiallyAssigned = computed(
  () => rows.value.filter(r => (r.reviewer1_id || r.reviewer2_id) && !(r.reviewer1_id && r.reviewer2_id)).length
)
const notAssigned = computed(
  () => rows.value.filter(r => !r.reviewer1_id && !r.reviewer2_id).length
)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/interview/assignments')
    rows.value = data.rows
    coordinators.value = data.coordinators
  } finally {
    loading.value = false
  }
}

async function setReviewer(row, slot, value) {
  const newId = value ? Number(value) : null

  // Optimistic update
  if (slot === 1) row.reviewer1_id = newId
  else row.reviewer2_id = newId

  savingRow.value = true
  try {
    await api.post(`/interview/assignments/${row.row_number}`, {
      reviewer1_id: row.reviewer1_id,
      reviewer2_id: row.reviewer2_id,
    })
  } catch {
    // Revert on error
    if (slot === 1) row.reviewer1_id = null
    else row.reviewer2_id = null
  } finally {
    savingRow.value = false
  }
}

async function createManual() {
  if (!newFio.value.trim()) return
  creating.value = true
  createMsg.value = null
  try {
    const { data } = await api.post('/interview/manual', {
      fio: newFio.value.trim(),
      student_id: newStudentId.value.trim(),
    })
    createMsg.value = { ok: true, text: `Создано, строка #${data.row_number}` }
    newFio.value = ''
    newStudentId.value = ''
    await load()
    setTimeout(() => { createModal.value = false; createMsg.value = null }, 1500)
  } catch (e) {
    createMsg.value = { ok: false, text: e.response?.data?.detail || 'Ошибка' }
  } finally {
    creating.value = false
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

.stats-inline {
  display: flex;
  gap: 0.4rem;
  align-items: center;
  font-size: 0.85rem;
  color: #555;
}
.stats-inline .ok  { color: #06a07a; }
.stats-inline .warn { color: #e08c00; }
.stats-inline .muted { color: #aaa; }

.top-actions {
  margin-left: auto;
  display: flex;
  gap: 0.6rem;
  align-items: center;
}

.search-input {
  padding: 0.5rem 0.85rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.875rem;
  outline: none;
  width: 220px;
  transition: border-color 0.15s;
}
.search-input:focus { border-color: #4361ee; }

.btn-create {
  padding: 0.5rem 1rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.btn-create:hover { background: #3451d1; }

.table-wrap {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow: auto;
  max-height: calc(100vh - 200px);
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
  text-transform: uppercase;
  letter-spacing: 0.03em;
  white-space: nowrap;
}
td { padding: 0.5rem 0.85rem; border-bottom: 1px solid #f5f5f5; color: #333; }

tr:hover td { background: #f7f8ff; }
tr.full td { background: rgba(6,214,160,0.03); }
tr.partial td { background: rgba(255,190,11,0.04); }

.num-col { width: 52px; text-align: center; }
.muted { color: #bbb; }
.fio-cell { font-weight: 500; }
.mono { font-family: monospace; font-size: 0.82rem; }

.rev-select {
  width: 100%;
  min-width: 180px;
  padding: 0.35rem 0.6rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 6px;
  font-size: 0.82rem;
  background: white;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}
.rev-select:focus { border-color: #4361ee; }

.saving-toast {
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  background: #1a1a2e;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-size: 0.82rem;
  z-index: 100;
}

/* Modal */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.35);
  display: flex; align-items: center; justify-content: center;
  z-index: 200;
}
.modal {
  background: white;
  border-radius: 16px;
  padding: 1.75rem 2rem;
  width: 400px;
  max-width: 90vw;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
}
.modal h3 { margin: 0 0 0.25rem; color: #1a1a2e; }
.modal-hint { font-size: 0.8rem; color: #aaa; margin: 0 0 1rem; }

label {
  display: block;
  font-size: 0.78rem;
  font-weight: 600;
  color: #555;
  margin-bottom: 0.25rem;
  margin-top: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.modal-input {
  width: 100%;
  padding: 0.55rem 0.85rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.9rem;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.15s;
}
.modal-input:focus { border-color: #4361ee; }

.modal-actions {
  display: flex; gap: 0.75rem; justify-content: flex-end;
  margin-top: 1.25rem;
}
.btn-cancel {
  padding: 0.5rem 1.1rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  background: white;
  font-size: 0.875rem;
  cursor: pointer;
  color: #555;
}
.btn-confirm {
  padding: 0.5rem 1.25rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-confirm:hover:not(:disabled) { background: #3451d1; }
.btn-confirm:disabled { opacity: 0.6; cursor: not-allowed; }

.create-msg {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 7px;
  font-size: 0.85rem;
}
.create-msg.ok  { background: rgba(6,214,160,0.1); color: #05a87c; }
.create-msg.err { background: rgba(230,57,70,0.08); color: #e63946; }

.state-msg {
  background: white; border-radius: 12px; padding: 3rem;
  text-align: center; font-size: 0.9rem; color: #aaa;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
</style>
