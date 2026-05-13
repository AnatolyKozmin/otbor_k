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
            <th>Когда</th>
            <th>Кандидат</th>
            <th>Студ. билет</th>
            <th>Проверяющий 1</th>
            <th>Проверяющий 2</th>
            <th class="reco-col">Рекомендация</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredRows"
            :key="row.row_number"
            :class="{
              'full': row.reviewer1_id && row.reviewer2_id,
              'partial': (row.reviewer1_id || row.reviewer2_id) && !(row.reviewer1_id && row.reviewer2_id),
              'no-slot': !row.slot_date,
            }"
          >
            <td class="num-col muted">{{ row.row_number }}</td>
            <td class="when-cell">
              <template v-if="row.slot_date">
                <div class="when-date">{{ formatDate(row.slot_date) }}</div>
                <div class="when-time">{{ row.slot_hour }}:00</div>
              </template>
              <span v-else class="muted">—</span>
            </td>
            <td class="fio-cell">
              <div>{{ row.fio || '—' }}</div>
              <span v-if="row.faculty" class="fac-badge">{{ row.faculty }}</span>
            </td>
            <td class="mono muted">
              {{ row.student_id || '—' }}
              <button class="edit-sid-btn" @click="openEditModal(row)" title="Редактировать анкету">✏️</button>
            </td>
            <td>
              <select
                class="rev-select"
                :value="row.reviewer1_id || ''"
                @change="setReviewer(row, 1, $event.target.value)"
              >
                <option value="">— не назначен —</option>
                <option
                  v-for="c in sortedCoords(row)"
                  :key="c.id"
                  :value="c.id"
                  :disabled="c.id === row.reviewer2_id"
                >{{ optionLabel(row, c) }}</option>
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
                  v-for="c in sortedCoords(row)"
                  :key="c.id"
                  :value="c.id"
                  :disabled="c.id === row.reviewer1_id"
                >{{ optionLabel(row, c) }}</option>
              </select>
            </td>
            <td class="reco-col">
              <button class="del-btn" @click="deleteRow(row)" title="Удалить запись">✕</button>
              <div v-if="!row.slot_date" class="reco muted-empty">—</div>
              <template v-else-if="pickRecommendedPair(row)">
                <div class="reco reco-clickable" :class="recoClass(row)" @click="openRecoModal(row)">
                  <span class="reco-icon">💡</span>
                  <span class="reco-names">{{ recoNames(row) }}</span>
                  <span class="reco-hint">{{ recoHint(row) }}</span>
                </div>
              </template>
              <div v-else class="reco reco-none">недостаточно свободных проверяющих</div>
            </td>
          </tr>
          <tr v-if="!filteredRows.length">
            <td colspan="7" class="muted" style="text-align:center;padding:2rem">
              {{ search ? 'Ничего не найдено' : 'Нет данных. Загрузите собесы из Google Sheets.' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="legend-bar">
      <span><b>🎓</b> свой факультет кандидата</span>
      <span><b>✓</b> доступен в этот час</span>
      <span class="muted">(без значков — не указал занятость или уже занят другим собесом)</span>
    </div>

    <!-- Saving indicator -->
    <div v-if="savingRow" class="saving-toast">Сохраняю…</div>

    <!-- Edit anketa modal -->
    <Teleport to="body">
      <div v-if="editModal.open" class="modal-overlay" @click.self="editModal.open = false">
        <div class="modal edit-modal">
          <div class="modal-head">
            <div>
              <div class="modal-title">Редактирование анкеты</div>
              <div class="modal-sub" v-if="editModal.fio">{{ editModal.fio }}</div>
            </div>
            <button class="close-btn" @click="editModal.open = false">✕</button>
          </div>

          <div v-if="editModal.loading" class="modal-state">Загрузка…</div>
          <div v-else-if="editModal.error" class="modal-state err">{{ editModal.error }}</div>
          <div v-else class="edit-content">
            <p class="edit-hint">Изменения применяются только в базе данных — Google Sheets не обновляется.</p>
            <div v-for="(val, key) in editModal.fields" :key="key" class="edit-field">
              <label class="edit-label">{{ key }}</label>
              <input
                class="edit-input"
                :value="editModal.fields[key]"
                @input="editModal.fields[key] = $event.target.value"
              />
            </div>
            <div v-if="editModal.saveError" class="modal-state err" style="padding:0.5rem 0">{{ editModal.saveError }}</div>
            <div class="modal-actions">
              <button class="btn-cancel" @click="editModal.open = false">Отмена</button>
              <button class="btn-confirm" :disabled="editModal.saving" @click="saveEditModal">
                {{ editModal.saving ? 'Сохраняю…' : 'Сохранить' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Reco availability modal -->
    <Teleport to="body">
      <div v-if="recoModal.open" class="modal-overlay" @click.self="recoModal.open = false">
        <div class="modal reco-modal">
          <div class="modal-head">
            <div>
              <div class="modal-title">Занятость проверяющих</div>
              <div class="modal-sub" v-if="recoModal.names">{{ recoModal.names }}</div>
            </div>
            <button class="close-btn" @click="recoModal.open = false">✕</button>
          </div>

          <div v-if="recoModal.loading" class="modal-state">Загрузка…</div>
          <div v-else-if="recoModal.error" class="modal-state err">{{ recoModal.error }}</div>

          <div v-else class="avail-content">
            <div v-for="(coord, uid) in recoModal.data" :key="uid" class="coord-section">
              <div class="coord-name">{{ coord.name }}</div>
              <div v-if="!coord.slots.length" class="no-slots">Занятость не заполнена</div>
              <div v-else class="day-list">
                <div v-for="(daySlots, date) in groupByDate(coord.slots)" :key="date" class="day-row">
                  <span class="day-label">{{ formatDate(date) }}</span>
                  <div class="hour-chips">
                    <span
                      v-for="s in daySlots"
                      :key="s.hour"
                      class="hour-chip"
                      :class="{ common: isCommonSlot(date, s.hour) }"
                    >{{ s.hour }}:00</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="legend-row">
              <span class="hour-chip common">10:00</span> — оба свободны
            </div>
          </div>
        </div>
      </div>
    </Teleport>

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

const recoModal = ref({ open: false, loading: false, error: '', names: '', data: {} })
const editModal = ref({ open: false, loading: false, error: '', saveError: '', saving: false, rowNumber: null, fio: '', fields: {} })

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

const MONTHS = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
const WEEKDAYS = ['вс','пн','вт','ср','чт','пт','сб']

function formatDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  return `${WEEKDAYS[dt.getDay()]}, ${d} ${MONTHS[m - 1]}`
}

function coordPriority(row, c) {
  const sameFac = row.same_faculty_coord_ids?.includes(c.id)
  const available = row.available_coord_ids?.includes(c.id)
  if (sameFac && available) return 0
  if (available) return 1
  return 2
}

function sortedCoords(row) {
  // У строк без слота — отдаём как есть (нет смысла сортировать по доступности)
  if (!row.slot_date) return coordinators.value
  return [...coordinators.value].sort((a, b) => {
    const pa = coordPriority(row, a)
    const pb = coordPriority(row, b)
    if (pa !== pb) return pa - pb
    return a.name.localeCompare(b.name, 'ru')
  })
}

function optionLabel(row, c) {
  if (!row.slot_date) return c.name
  const sameFac = row.same_faculty_coord_ids?.includes(c.id)
  const available = row.available_coord_ids?.includes(c.id)
  const prefix = `${sameFac ? '🎓' : ''}${available ? '✓' : ''}`
  return prefix ? `${prefix} ${c.name}` : c.name
}

function pickRecommendedPair(row) {
  const sameFac = row.same_faculty_coord_ids || []
  const avail = row.available_coord_ids || []
  const others = avail.filter(id => !sameFac.includes(id))
  const picked = []
  picked.push(...sameFac.slice(0, 2))
  if (picked.length < 2) picked.push(...others.slice(0, 2 - picked.length))
  return picked.length === 2 ? picked : null
}

function shortName(fullName) {
  if (!fullName) return ''
  const parts = fullName.split(' ').filter(Boolean)
  if (parts.length < 2) return fullName
  return `${parts[0]} ${parts[1][0]}.`
}

function recoNames(row) {
  const pair = pickRecommendedPair(row)
  if (!pair) return ''
  const byId = Object.fromEntries(coordinators.value.map(c => [c.id, c.name]))
  return `${shortName(byId[pair[0]])} + ${shortName(byId[pair[1]])}`
}

function recoClass(row) {
  const pair = pickRecommendedPair(row)
  if (!pair) return ''
  const sameFac = row.same_faculty_coord_ids || []
  const sameCount = pair.filter(id => sameFac.includes(id)).length
  if (sameCount === 2) return 'reco-strong'
  if (sameCount === 1) return 'reco-mixed'
  return 'reco-weak'
}

function recoHint(row) {
  const pair = pickRecommendedPair(row)
  if (!pair) return ''
  const sameFac = row.same_faculty_coord_ids || []
  const sameCount = pair.filter(id => sameFac.includes(id)).length
  if (sameCount === 2) return 'оба свой факультет'
  if (sameCount === 1) return '1 свой + 1 другой'
  return 'другой факультет'
}

async function openRecoModal(row) {
  const pair = pickRecommendedPair(row)
  if (!pair) return
  const byId = Object.fromEntries(coordinators.value.map(c => [c.id, c.name]))
  recoModal.value = {
    open: true,
    loading: true,
    error: '',
    names: pair.map(id => shortName(byId[id])).join(' + '),
    data: {},
  }
  try {
    const { data } = await api.get('/interview/coord-availability', {
      params: { ids: pair.join(',') },
    })
    recoModal.value.data = data.coordinators
  } catch (e) {
    recoModal.value.error = e.response?.data?.detail || 'Ошибка загрузки'
  } finally {
    recoModal.value.loading = false
  }
}

function groupByDate(slots) {
  const map = {}
  for (const s of slots) {
    if (!map[s.date]) map[s.date] = []
    map[s.date].push(s)
  }
  return map
}

function isCommonSlot(date, hour) {
  const coords = Object.values(recoModal.value.data)
  return coords.length === 2 &&
    coords[0].slots.some(s => s.date === date && s.hour === hour) &&
    coords[1].slots.some(s => s.date === date && s.hour === hour)
}

async function openEditModal(row) {
  // Нужно найти row_number анкеты по студ. билету
  editModal.value = { open: true, loading: true, error: '', saveError: '', saving: false, rowNumber: null, fio: row.fio, fields: {} }
  try {
    // Ищем анкету через search по ФИО
    const sid = row.student_id
    // Пробуем получить прямо через поиск
    const { data } = await api.get('/admin/anketa/search', { params: { q: row.fio || '' } })
    // Ищем совпадение по студ. билету
    const digits = s => (s || '').replace(/\D/g, '')
    let found = data.rows.find(r => digits(r.student_id) === digits(sid))
    if (!found && data.rows.length === 1) found = data.rows[0]
    if (!found) {
      editModal.value.error = 'Анкета не найдена. Попробуйте загрузить данные из Sheets.'
      editModal.value.loading = false
      return
    }
    editModal.value.rowNumber = found.row_number
    const detail = await api.get(`/admin/anketa/${found.row_number}`)
    editModal.value.fields = detail.data.fields
  } catch (e) {
    editModal.value.error = e.response?.data?.detail || 'Ошибка загрузки'
  } finally {
    editModal.value.loading = false
  }
}

async function saveEditModal() {
  editModal.value.saving = true
  editModal.value.saveError = ''
  try {
    await api.patch(`/admin/anketa/${editModal.value.rowNumber}`, { fields: editModal.value.fields })
    editModal.value.open = false
    await load()
  } catch (e) {
    editModal.value.saveError = e.response?.data?.detail || 'Ошибка сохранения'
  } finally {
    editModal.value.saving = false
  }
}

async function deleteRow(row) {
  if (!confirm(`Удалить запись «${row.fio || '—'}»?`)) return
  try {
    await api.delete(`/interview/assignments/${row.row_number}`)
    rows.value = rows.value.filter(r => r.row_number !== row.row_number)
  } catch (e) {
    alert(e.response?.data?.detail || 'Ошибка удаления')
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

.when-cell { white-space: nowrap; }
.when-date {
  font-size: 0.82rem; font-weight: 600; color: #1a1a2e;
  text-transform: capitalize;
}
.when-time { font-size: 0.78rem; color: #888; font-variant-numeric: tabular-nums; }

tr.no-slot td { opacity: 0.7; }

.fac-badge {
  display: inline-block;
  margin-top: 0.15rem;
  padding: 0.05rem 0.45rem;
  background: rgba(67,97,238,0.1);
  color: #4361ee;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
}

.legend-bar {
  margin-top: 0.85rem;
  font-size: 0.78rem;
  color: #777;
  display: flex; flex-wrap: wrap; gap: 1rem;
  padding: 0.5rem 0.85rem;
}
.legend-bar b { color: #1a1a2e; }
.legend-bar .muted { font-style: italic; }

.reco-col { min-width: 200px; }
.reco {
  display: inline-flex; flex-direction: column;
  padding: 0.35rem 0.65rem;
  border-radius: 8px;
  font-size: 0.78rem;
  line-height: 1.35;
  max-width: 240px;
}
.reco-icon { margin-right: 0.25rem; }
.reco-names { font-weight: 600; }
.reco-hint { font-size: 0.7rem; opacity: 0.8; margin-top: 0.1rem; }

.reco.reco-strong { background: rgba(6,160,122,0.1);  color: #058c6b; }
.reco.reco-mixed  { background: rgba(67,97,238,0.08); color: #4361ee; }
.reco.reco-weak   { background: rgba(255,190,11,0.12); color: #b08000; }
.reco.reco-none   { background: #f5f5f5; color: #aaa; font-style: italic; }
.reco.muted-empty { background: transparent; color: #ccc; }

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

/* Reco clickable */
.reco-clickable { cursor: pointer; transition: filter 0.12s, transform 0.1s; }
.reco-clickable:hover { filter: brightness(0.95); transform: translateY(-1px); }

.del-btn {
  float: right;
  margin-left: 0.5rem;
  background: none;
  border: none;
  color: #ddd;
  font-size: 0.85rem;
  cursor: pointer;
  padding: 0.1rem 0.3rem;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
  line-height: 1;
}
.del-btn:hover { color: #e63946; background: rgba(230,57,70,0.08); }

/* Reco modal */
.reco-modal { width: 520px; max-width: 95vw; max-height: 80vh; display: flex; flex-direction: column; }
.modal-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 1.25rem 1.5rem 1rem; border-bottom: 1px solid #eee; flex-shrink: 0;
}
.modal-title { font-size: 1rem; font-weight: 700; color: #1a1a2e; }
.modal-sub { font-size: 0.82rem; color: #4361ee; font-weight: 600; margin-top: 0.2rem; }
.modal-state { padding: 2rem; text-align: center; color: #aaa; font-size: 0.9rem; }
.modal-state.err { color: #e63946; }

.avail-content { overflow-y: auto; padding: 1rem 1.5rem 1.25rem; display: flex; flex-direction: column; gap: 1.25rem; }

.coord-section { }
.coord-name { font-weight: 700; font-size: 0.88rem; color: #1a1a2e; margin-bottom: 0.55rem; }
.no-slots { font-size: 0.82rem; color: #aaa; font-style: italic; }

.day-list { display: flex; flex-direction: column; gap: 0.45rem; }
.day-row { display: flex; align-items: flex-start; gap: 0.75rem; }
.day-label {
  font-size: 0.74rem; font-weight: 600; color: #6b7280;
  white-space: nowrap; min-width: 80px; padding-top: 0.15rem;
  text-transform: capitalize;
}
.hour-chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.hour-chip {
  padding: 0.18rem 0.55rem;
  border-radius: 6px;
  font-size: 0.74rem;
  font-weight: 600;
  background: #f0f2f5;
  color: #6b7280;
  font-variant-numeric: tabular-nums;
}
.hour-chip.common {
  background: rgba(6,160,122,0.15);
  color: #058c6b;
  border: 1px solid rgba(6,160,122,0.3);
}

.legend-row {
  display: flex; align-items: center; gap: 0.5rem;
  font-size: 0.78rem; color: #888;
  padding-top: 0.25rem; border-top: 1px solid #f0f0f0;
}

.close-btn {
  background: none; border: none; font-size: 1rem;
  color: #888; cursor: pointer; padding: 0.25rem 0.5rem;
  border-radius: 6px; transition: background 0.15s; flex-shrink: 0;
}
.close-btn:hover { background: #f0f2f5; color: #333; }

.edit-sid-btn {
  background: none; border: none; cursor: pointer;
  font-size: 0.75rem; padding: 0 0.2rem;
  opacity: 0.3; transition: opacity 0.15s;
  vertical-align: middle;
}
.edit-sid-btn:hover { opacity: 1; }

.edit-modal { width: 560px; max-width: 95vw; max-height: 85vh; display: flex; flex-direction: column; }
.edit-content { overflow-y: auto; padding: 0.75rem 1.5rem 1.25rem; display: flex; flex-direction: column; gap: 0.6rem; }
.edit-hint { font-size: 0.78rem; color: #e08c00; background: rgba(255,190,11,0.1); border-radius: 7px; padding: 0.5rem 0.75rem; margin: 0 0 0.25rem; }
.edit-field { display: flex; flex-direction: column; gap: 0.2rem; }
.edit-label { font-size: 0.72rem; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.03em; }
.edit-input {
  padding: 0.45rem 0.7rem; border: 1.5px solid #e0e0e0; border-radius: 7px;
  font-size: 0.875rem; outline: none; transition: border-color 0.15s;
}
.edit-input:focus { border-color: #4361ee; }

.state-msg {
  background: white; border-radius: 12px; padding: 3rem;
  text-align: center; font-size: 0.9rem; color: #aaa;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
</style>
