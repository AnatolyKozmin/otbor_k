<template>
  <AppLayout>
    <div class="avail-page">
      <header class="page-head">
        <div>
          <h2>Занятость на собес</h2>
          <p class="hint">
            Отметь часовые слоты, в которые ты <b>можешь</b> приходить.
            Пустая ячейка = «не могу». Клик по заголовку дня или часа —
            переключить весь столбец/строку.
          </p>
        </div>
        <div class="head-actions">
          <span v-if="modified" class="dirty-badge">● несохранённые изменения</span>
          <span v-else-if="lastSaved" class="saved-badge">✓ сохранено</span>
          <button
            class="btn-save"
            :disabled="!modified || saving"
            @click="save"
          >
            {{ saving ? 'Сохранение…' : 'Сохранить' }}
          </button>
        </div>
      </header>

      <div v-if="loading" class="state-msg">Загрузка…</div>
      <div v-else-if="loadError" class="state-msg err">{{ loadError }}</div>

      <div v-else class="grid-wrap">
        <table class="grid">
          <thead>
            <tr>
              <th class="corner">
                <button class="bulk-btn" @click="toggleAll" :title="allSelected ? 'Очистить всё' : 'Выбрать всё'">
                  {{ allSelected ? '☒' : '☐' }}
                </button>
              </th>
              <th
                v-for="d in DATES"
                :key="d.date"
                class="day-h"
                :class="{ weekend: d.weekend, reserve: d.reserve }"
              >
                <button class="day-toggle" @click="toggleDay(d.date)" :title="`Переключить весь день ${d.label}`">
                  <div class="day-dow">{{ d.dow }}</div>
                  <div class="day-num">{{ d.day }}</div>
                  <span v-if="d.reserve" class="reserve-tag">резерв</span>
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in HOURS" :key="h">
              <th class="hour-h">
                <button class="hour-toggle" @click="toggleHour(h)" :title="`Переключить весь час ${formatHour(h)}`">
                  {{ formatHour(h) }}
                </button>
              </th>
              <td
                v-for="d in DATES"
                :key="d.date + ':' + h"
                class="cell"
                :class="{
                  selected: isSelected(d.date, h),
                  weekend: d.weekend,
                  reserve: d.reserve,
                  past: isPast(d.date, h),
                }"
                @click="!isPast(d.date, h) && toggle(d.date, h)"
              >
                <span v-if="isSelected(d.date, h) && !isPast(d.date, h)" class="check">✓</span>
                <span v-else-if="isPast(d.date, h)" class="past-mark">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer v-if="!loading && !loadError" class="legend">
        <div class="legend-item">
          <span class="cell legend-cell selected"><span class="check">✓</span></span>
          могу
        </div>
        <div class="legend-item">
          <span class="cell legend-cell"></span>
          не могу
        </div>
        <div class="legend-item">
          <span class="cell legend-cell reserve"></span>
          резервный день (23–24 мая)
        </div>
        <div class="legend-spacer" />
        <div class="counter">Отмечено слотов: <b>{{ slots.size }}</b></div>
      </footer>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const HOURS = Array.from({ length: 13 }, (_, i) => 9 + i)  // 9..21

function isPast(date, hour) {
  const now = new Date()
  const slot = new Date(`${date}T${String(hour).padStart(2,'0')}:00`)
  return slot <= now
}
const DOW_RU = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']

const DATES = Array.from({ length: 16 }, (_, i) => {
  const day = 9 + i
  const d = new Date(Date.UTC(2026, 4, day))  // месяц май = 4
  const dow = DOW_RU[d.getUTCDay()]
  const date = `2026-05-${String(day).padStart(2, '0')}`
  return {
    date,
    day,
    dow,
    label: `${day} мая`,
    weekend: d.getUTCDay() === 0 || d.getUTCDay() === 6,
    reserve: day === 23 || day === 24,
  }
})

function formatHour(h) {
  return `${String(h).padStart(2, '0')}:00–${String(h + 1).padStart(2, '0')}:00`
}

function slotKey(date, hour) {
  return `${date}:${hour}`
}

const slots = ref(new Set())
const initialSlots = ref(new Set())

const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const lastSaved = ref(false)

const modified = computed(() => {
  if (slots.value.size !== initialSlots.value.size) return true
  for (const k of slots.value) if (!initialSlots.value.has(k)) return true
  return false
})

const allSelected = computed(() => slots.value.size === DATES.length * HOURS.length)

function isSelected(date, hour) {
  return slots.value.has(slotKey(date, hour))
}

function toggle(date, hour) {
  const key = slotKey(date, hour)
  const next = new Set(slots.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  slots.value = next
  lastSaved.value = false
}

function toggleDay(date) {
  // Если хоть одна ячейка дня пустая — заполняем все. Иначе очищаем все.
  const next = new Set(slots.value)
  const allFilled = HOURS.every(h => next.has(slotKey(date, h)))
  for (const h of HOURS) {
    const k = slotKey(date, h)
    if (allFilled) next.delete(k)
    else next.add(k)
  }
  slots.value = next
  lastSaved.value = false
}

function toggleHour(hour) {
  const next = new Set(slots.value)
  const allFilled = DATES.every(d => next.has(slotKey(d.date, hour)))
  for (const d of DATES) {
    const k = slotKey(d.date, hour)
    if (allFilled) next.delete(k)
    else next.add(k)
  }
  slots.value = next
  lastSaved.value = false
}

function toggleAll() {
  if (allSelected.value) slots.value = new Set()
  else {
    const next = new Set()
    for (const d of DATES) for (const h of HOURS) next.add(slotKey(d.date, h))
    slots.value = next
  }
  lastSaved.value = false
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get('/availability/me')
    const next = new Set()
    for (const s of data.slots) next.add(slotKey(s.date, s.hour))
    slots.value = next
    initialSlots.value = new Set(next)
  } catch (e) {
    loadError.value = e.response?.data?.detail || 'Не удалось загрузить занятость'
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const payload = {
      slots: Array.from(slots.value).map(k => {
        const [date, hour] = k.split(':')
        return { date, hour: Number(hour) }
      }),
    }
    await api.put('/availability/me', payload)
    initialSlots.value = new Set(slots.value)
    lastSaved.value = true
    setTimeout(() => { lastSaved.value = false }, 3000)
  } catch (e) {
    alert(e.response?.data?.detail || 'Ошибка сохранения')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.avail-page { display: flex; flex-direction: column; gap: 1rem; }

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

.dirty-badge {
  font-size: 0.78rem;
  color: #c98a00;
  background: rgba(255,190,11,0.15);
  padding: 0.25rem 0.65rem;
  border-radius: 20px;
  font-weight: 600;
}
.saved-badge {
  font-size: 0.78rem;
  color: #06875e;
  background: rgba(6,214,160,0.12);
  padding: 0.25rem 0.65rem;
  border-radius: 20px;
  font-weight: 600;
}

.btn-save {
  padding: 0.55rem 1.25rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-save:hover:not(:disabled) { background: #3451d1; }
.btn-save:disabled { background: #c9c9d4; cursor: not-allowed; }

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

/* Углы и заголовки */
.corner {
  width: 96px;
  background: transparent;
  position: sticky;
  left: 0;
  z-index: 2;
}

.bulk-btn {
  width: 100%;
  height: 56px;
  border: 1.5px dashed #ccc;
  background: white;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.2rem;
  color: #666;
  transition: all 0.15s;
}
.bulk-btn:hover { border-color: #4361ee; color: #4361ee; }

.day-h, .hour-h {
  background: transparent;
  font-weight: 600;
  color: #444;
  font-size: 0.78rem;
}

.day-h.weekend .day-toggle { background: #fff3eb; }
.day-h.reserve .day-toggle { background: #f0eef9; opacity: 0.78; }

.day-toggle {
  width: 100%;
  height: 56px;
  border: 1.5px solid #e8eaf2;
  background: #f7f8fb;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 0.2rem;
  transition: all 0.15s;
  position: relative;
}
.day-toggle:hover { border-color: #4361ee; background: white; }
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

.hour-h { position: sticky; left: 0; z-index: 1; background: #fafbfc; }
.hour-toggle {
  width: 100%;
  height: 36px;
  border: 1.5px solid #e8eaf2;
  background: #f7f8fb;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.74rem;
  font-weight: 600;
  color: #555;
  font-family: inherit;
  transition: all 0.15s;
  white-space: nowrap;
}
.hour-toggle:hover { border-color: #4361ee; background: white; color: #4361ee; }

/* Ячейки */
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
  font-size: 0.95rem;
  color: white;
  font-weight: 700;
}
.cell:hover { background: #eef0f8; border-color: #b8c5ff; }
.cell.weekend { background: #fff3eb; }
.cell.weekend:hover { background: #ffe7d4; }
.cell.reserve { background: #f0eef9; opacity: 0.85; }
.cell.reserve:hover { opacity: 1; background: #e8e3f7; }

.cell.selected {
  background: linear-gradient(135deg, #06d6a0 0%, #0db587 100%);
  border-color: #0db587;
  box-shadow: 0 1px 3px rgba(13,181,135,0.35);
}
.cell.selected:hover {
  background: linear-gradient(135deg, #0db587 0%, #099971 100%);
  border-color: #099971;
}
.cell.past {
  background: #f0f0f0;
  border-color: #e0e0e0;
  cursor: default;
  opacity: 0.45;
}
.cell.past:hover { background: #f0f0f0; border-color: #e0e0e0; }
.past-mark { color: #bbb; font-size: 0.8rem; }

.cell.selected.reserve {
  background: linear-gradient(135deg, #9b85d8 0%, #7c5cd8 100%);
  border-color: #7c5cd8;
  opacity: 1;
}

.check { display: inline-block; line-height: 1; }

/* Легенда снизу */
.legend {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding: 0.75rem 0.25rem 0;
  font-size: 0.78rem;
  color: #666;
  flex-wrap: wrap;
}
.legend-item { display: flex; align-items: center; gap: 0.4rem; }
.legend-cell {
  display: inline-flex;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  align-items: center;
  justify-content: center;
}
.legend-cell.selected { font-size: 0.8rem; }
.legend-spacer { flex: 1; }
.counter { color: #1a1a2e; font-size: 0.85rem; }
.counter b { color: #4361ee; }
</style>
