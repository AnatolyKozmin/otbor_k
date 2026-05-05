<template>
  <AppLayout>
    <div class="avail-admin-page">
      <header class="page-head">
        <div>
          <h2>Занятость координаторов</h2>
          <p class="hint">
            Цифра в ячейке — количество доступных координаторов. Нажми на ячейку, чтобы
            увидеть список и задать количество слотов.
          </p>
        </div>
        <div class="head-actions">
          <label class="hide-empty-toggle">
            <input type="checkbox" v-model="hideEmpty" />
            Скрыть пустые
          </label>
        </div>
      </header>

      <div v-if="loading" class="state-msg">Загрузка…</div>
      <div v-else-if="loadError" class="state-msg err">{{ loadError }}</div>

      <div v-else class="grid-wrap">
        <table class="grid">
          <thead>
            <tr>
              <th class="corner"></th>
              <th
                v-for="d in visibleDates"
                :key="d.date"
                class="day-h"
                :class="{ weekend: d.weekend, reserve: d.reserve }"
              >
                <div class="day-toggle">
                  <div class="day-dow">{{ d.dow }}</div>
                  <div class="day-num">{{ d.day }}</div>
                  <span v-if="d.reserve" class="reserve-tag">резерв</span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in HOURS" :key="h">
              <th class="hour-h">{{ formatHour(h) }}</th>
              <td
                v-for="d in visibleDates"
                :key="d.date + ':' + h"
                class="cell"
                :class="{
                  weekend: d.weekend,
                  reserve: d.reserve,
                  'has-people': slotInfo(d.date, h).count > 0,
                  'has-capacity': slotInfo(d.date, h).capacity > 0,
                  active: activeSlot && activeSlot.date === d.date && activeSlot.hour === h,
                }"
                @click="openPanel(d.date, h)"
              >
                <span class="count" v-if="slotInfo(d.date, h).count > 0">
                  {{ slotInfo(d.date, h).count }}
                </span>
                <span class="cap" v-if="slotInfo(d.date, h).capacity > 0">
                  /{{ slotInfo(d.date, h).capacity }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Side panel -->
      <Teleport to="body">
        <div v-if="panelSlot" class="panel-backdrop" @click.self="closePanel"></div>
        <div class="slot-panel" :class="{ open: panelSlot !== null }">
          <template v-if="panelSlot">
            <div class="panel-head">
              <div>
                <div class="panel-date">{{ panelDateLabel }}</div>
                <div class="panel-hour">{{ formatHour(panelSlot.hour) }}</div>
              </div>
              <button class="close-btn" @click="closePanel">✕</button>
            </div>

            <div class="capacity-row">
              <label class="cap-label">Слотов:</label>
              <input
                v-model.number="editCapacity"
                type="number"
                min="0"
                max="50"
                class="cap-input"
                @keyup.enter="saveCapacity"
              />
              <button
                class="btn-save"
                :disabled="saving || editCapacity === panelSlot.capacity"
                @click="saveCapacity"
              >
                {{ saving ? '…' : 'Сохранить' }}
              </button>
            </div>

            <div class="people-section">
              <div class="people-header">
                <span class="people-count-badge">{{ panelSlot.count }}</span>
                <span class="people-title">координатора(-ов) доступны</span>
              </div>
              <div v-if="panelSlot.people.length === 0" class="no-people">
                Никто не отметил этот слот
              </div>
              <ul v-else class="people-list">
                <li v-for="name in panelSlot.people" :key="name" class="person-item">
                  <span class="person-dot"></span>
                  {{ name }}
                </li>
              </ul>
            </div>
          </template>
        </div>
      </Teleport>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const HOURS = Array.from({ length: 13 }, (_, i) => 9 + i)
const DOW_RU = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']

const DATES = Array.from({ length: 15 }, (_, i) => {
  const day = 9 + i
  const d = new Date(Date.UTC(2026, 4, day))
  const dow = DOW_RU[d.getUTCDay()]
  const date = `2026-05-${String(day).padStart(2, '0')}`
  return {
    date, day, dow,
    label: `${day} мая`,
    weekend: d.getUTCDay() === 0 || d.getUTCDay() === 6,
    reserve: day === 22 || day === 23,
  }
})

const DATE_LABELS = Object.fromEntries(DATES.map(d => [d.date, d.label]))

function formatHour(h) {
  return `${String(h).padStart(2, '0')}:00–${String(h + 1).padStart(2, '0')}:00`
}

const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const hideEmpty = ref(false)

// slotMap: "YYYY-MM-DD:H" → { count, people, capacity }
const slotMap = ref({})

const visibleDates = computed(() => {
  if (!hideEmpty.value) return DATES
  return DATES.filter(d =>
    HOURS.some(h => (slotMap.value[`${d.date}:${h}`]?.count ?? 0) > 0)
  )
})

function slotInfo(date, hour) {
  return slotMap.value[`${date}:${hour}`] ?? { count: 0, people: [], capacity: 0 }
}

const activeSlot = ref(null)  // { date, hour }
const panelSlot = ref(null)   // full slot info
const editCapacity = ref(0)

const panelDateLabel = computed(() => panelSlot.value ? DATE_LABELS[panelSlot.value.date] : '')

function openPanel(date, hour) {
  const info = slotInfo(date, hour)
  panelSlot.value = { date, hour, ...info }
  activeSlot.value = { date, hour }
  editCapacity.value = info.capacity
}

function closePanel() {
  panelSlot.value = null
  activeSlot.value = null
}

async function saveCapacity() {
  if (!panelSlot.value) return
  saving.value = true
  try {
    await api.put('/availability/admin/capacity', {
      date: panelSlot.value.date,
      hour: panelSlot.value.hour,
      capacity: editCapacity.value,
    })
    const key = `${panelSlot.value.date}:${panelSlot.value.hour}`
    slotMap.value[key] = { ...slotMap.value[key], capacity: editCapacity.value }
    panelSlot.value = { ...panelSlot.value, capacity: editCapacity.value }
  } catch (e) {
    alert(e.response?.data?.detail || 'Ошибка сохранения')
  } finally {
    saving.value = false
  }
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get('/availability/admin/overview')
    const map = {}
    for (const s of data.slots) {
      map[`${s.date}:${s.hour}`] = { count: s.count, people: s.people, capacity: s.capacity }
    }
    slotMap.value = map
  } catch (e) {
    loadError.value = e.response?.data?.detail || 'Не удалось загрузить данные'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.avail-admin-page { display: flex; flex-direction: column; gap: 1rem; }

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1.5rem;
  flex-wrap: wrap;
}
.page-head h2 { margin: 0 0 0.4rem; color: #1a1a2e; }
.hint { margin: 0; color: #666; font-size: 0.85rem; max-width: 720px; line-height: 1.45; }

.head-actions { display: flex; align-items: center; gap: 0.85rem; flex-shrink: 0; }

.hide-empty-toggle {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  color: #555;
  cursor: pointer;
  user-select: none;
}

.state-msg {
  background: white;
  border-radius: 12px;
  padding: 3rem;
  text-align: center;
  font-size: 0.9rem;
  color: #888;
}
.state-msg.err { color: #e63946; }

.grid-wrap {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 0.5rem;
  overflow: auto;
}

.grid {
  border-collapse: separate;
  border-spacing: 4px;
  width: 100%;
  table-layout: fixed;
}

.grid th, .grid td { padding: 0; user-select: none; }

.corner {
  width: 96px;
  background: transparent;
  position: sticky;
  left: 0;
  z-index: 2;
}

.day-h {
  background: transparent;
  font-weight: 600;
  color: #444;
  font-size: 0.78rem;
}

.day-h.weekend .day-toggle { background: #fff3eb; }
.day-h.reserve .day-toggle { background: #f0eef9; }

.day-toggle {
  width: 100%;
  height: 56px;
  border: 1.5px solid #e8eaf2;
  background: #f7f8fb;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.2rem;
  position: relative;
}
.day-dow { font-size: 0.65rem; color: #888; text-transform: uppercase; letter-spacing: 0.05em; }
.day-num { font-size: 1.05rem; font-weight: 700; color: #1a1a2e; line-height: 1.1; }

.reserve-tag {
  position: absolute;
  bottom: -2px;
  font-size: 0.55rem;
  color: #7c5cd8;
  background: white;
  padding: 0 0.3rem;
  border-radius: 8px;
  border: 1px solid #ddd6f4;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.hour-h {
  position: sticky;
  left: 0;
  z-index: 1;
  background: #fafbfc;
  font-size: 0.74rem;
  font-weight: 600;
  color: #555;
  padding: 0 0.35rem;
  white-space: nowrap;
}

.cell {
  width: 56px;
  height: 36px;
  background: #f7f8fb;
  border: 1.5px solid #e8eaf2;
  border-radius: 8px;
  cursor: pointer;
  text-align: center;
  vertical-align: middle;
  transition: all 0.12s;
  position: relative;
}
.cell:hover { background: #eef0f8; border-color: #b8c5ff; }
.cell.weekend { background: #fff3eb; }
.cell.weekend:hover { background: #ffe7d4; }
.cell.reserve { background: #f0eef9; }
.cell.reserve:hover { background: #e8e3f7; }

.cell.has-people {
  background: linear-gradient(135deg, #e8f4ff 0%, #dbeeff 100%);
  border-color: #93c5fd;
}
.cell.has-people:hover { background: linear-gradient(135deg, #dbeeff 0%, #c3d9ff 100%); border-color: #60a5fa; }
.cell.has-capacity { border-color: #4361ee; }
.cell.active { outline: 2.5px solid #4361ee; outline-offset: 1px; }

.count {
  font-size: 1rem;
  font-weight: 700;
  color: #1d4ed8;
}
.cap {
  font-size: 0.7rem;
  color: #4361ee;
  font-weight: 600;
}
</style>

<style>
/* Panel styles — not scoped (Teleport escapes scoped CSS) */
.panel-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.18);
  z-index: 200;
}

.slot-panel {
  position: fixed;
  top: 0;
  right: -380px;
  width: 340px;
  height: 100vh;
  background: white;
  box-shadow: -4px 0 24px rgba(0,0,0,0.12);
  z-index: 201;
  display: flex;
  flex-direction: column;
  transition: right 0.25s ease;
  overflow-y: auto;
}
.slot-panel.open { right: 0; }

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 1.25rem 1.25rem 1rem;
  border-bottom: 1px solid #eee;
}
.panel-date { font-size: 0.78rem; color: #888; font-weight: 500; margin-bottom: 0.2rem; }
.panel-hour { font-size: 1rem; font-weight: 700; color: #1a1a2e; }

.close-btn {
  background: none;
  border: none;
  font-size: 1rem;
  color: #888;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  transition: background 0.15s;
}
.close-btn:hover { background: #f0f2f5; color: #333; }

.capacity-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 1rem 1.25rem;
  background: #f7f8fb;
  border-bottom: 1px solid #eee;
}
.cap-label { font-size: 0.85rem; font-weight: 600; color: #555; white-space: nowrap; }
.cap-input {
  width: 70px;
  padding: 0.4rem 0.6rem;
  border: 1.5px solid #d1d5db;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  color: #1a1a2e;
  text-align: center;
  outline: none;
  transition: border-color 0.15s;
}
.cap-input:focus { border-color: #4361ee; }

.btn-save {
  padding: 0.4rem 0.9rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}
.btn-save:hover:not(:disabled) { background: #3451d1; }
.btn-save:disabled { background: #c9c9d4; cursor: not-allowed; }

.people-section { padding: 1rem 1.25rem; flex: 1; }

.people-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.85rem;
}
.people-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: #eff6ff;
  border: 1.5px solid #93c5fd;
  border-radius: 50%;
  font-size: 0.88rem;
  font-weight: 700;
  color: #1d4ed8;
}
.people-title { font-size: 0.85rem; color: #555; font-weight: 500; }

.no-people { font-size: 0.85rem; color: #aaa; font-style: italic; padding: 0.5rem 0; }

.people-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.person-item {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.45rem 0.75rem;
  background: #f7f8fb;
  border-radius: 8px;
  font-size: 0.875rem;
  color: #1a1a2e;
}
.person-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #06d6a0;
  flex-shrink: 0;
}
</style>
