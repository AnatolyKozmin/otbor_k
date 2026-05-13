<template>
  <div class="booking-page">
    <div class="booking-card">
      <div class="brand">Координаторство'26</div>
      <h1>Запись на собеседование</h1>

      <!-- Step 1: Student ID -->
      <div v-if="step === 'id'" class="step">
        <p class="hint">Введите номер вашего студенческого билета — мы найдём вас в списке и подберём свободные слоты.</p>
        <input
          v-model="studentId"
          class="big-input"
          placeholder="Например: 21/12345"
          @keydown.enter="lookup"
          :disabled="loading"
        />
        <div v-if="errorMsg" class="error-box">{{ errorMsg }}</div>
        <button class="primary-btn" :disabled="loading || !studentId.trim()" @click="lookup">
          {{ loading ? 'Ищу…' : 'Продолжить →' }}
        </button>
      </div>

      <!-- Step 2: Already booked -->
      <div v-else-if="step === 'already'" class="step">
        <div class="success-banner">
          <div class="big-emoji">📅</div>
          <h2>Вы уже записаны</h2>
          <div class="booking-details">
            <div class="bd-row"><span>Дата:</span> <b>{{ formatDate(candidate.already_booked.slot_date) }}</b></div>
            <div class="bd-row"><span>Время:</span> <b>{{ candidate.already_booked.slot_hour }}:00</b></div>
            <div class="bd-row" v-if="!candidate.already_booked.reviewers_pending">
              <span>Проверяющие:</span>
              <b>{{ candidate.already_booked.reviewer1 }} + {{ candidate.already_booked.reviewer2 }}</b>
            </div>
            <div class="bd-row pending" v-else>
              <span>Проверяющие:</span>
              <b>назначаются координаторами</b>
            </div>
          </div>
          <p class="hint">Если нужно перенести — свяжитесь с координатором.</p>
        </div>
      </div>

      <!-- Step 3: Slot picker -->
      <div v-else-if="step === 'slots'" class="step">
        <div class="candidate-info">
          <div>
            <div class="ci-fio">{{ candidate.fio || 'Кандидат' }}</div>
            <div class="ci-faculty" v-if="candidate.faculty">Факультет: <b>{{ candidate.faculty }}</b></div>
            <div class="ci-faculty muted" v-else>Факультет не определён</div>
          </div>
          <button class="link-btn" @click="resetForm">сменить билет</button>
        </div>

        <div v-if="slotsLoading" class="state-msg">Подбираю слоты…</div>

        <template v-else>
          <div v-if="!recommended.length && !other.length" class="empty-slots">
            Свободных слотов пока нет. Попробуйте позже.
          </div>

          <div v-if="recommended.length" class="section">
            <div class="section-title rec-title">Свои по факультету</div>
            <div v-for="day in recommended" :key="'r-' + day.date" class="day-block">
              <div class="day-header">{{ formatDate(day.date) }}</div>
              <div class="slot-grid">
                <button
                  v-for="s in day.slots"
                  :key="s.hour"
                  class="slot-btn rec"
                  @click="selectSlot(day.date, s)"
                >
                  <span class="slot-hour">{{ s.hour }}:00</span>
                  <span class="slot-meta">{{ s.free_count }} своб.</span>
                </button>
              </div>
            </div>
          </div>

          <div v-if="other.length" class="section">
            <div class="section-title other-title">Другие проверяющие</div>
            <div v-for="day in other" :key="'o-' + day.date" class="day-block">
              <div class="day-header">{{ formatDate(day.date) }}</div>
              <div class="slot-grid">
                <button
                  v-for="s in day.slots"
                  :key="s.hour"
                  class="slot-btn other"
                  @click="selectSlot(day.date, s)"
                >
                  <span class="slot-hour">{{ s.hour }}:00</span>
                  <span class="slot-meta">{{ s.free_count }} своб.</span>
                </button>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Step 4: Confirmation -->
      <div v-else-if="step === 'confirm'" class="step">
        <h2>Подтвердите запись</h2>
        <div class="booking-details">
          <div class="bd-row"><span>Кандидат:</span> <b>{{ candidate.fio || '—' }}</b></div>
          <div class="bd-row"><span>Дата:</span> <b>{{ formatDate(selectedSlot.date) }}</b></div>
          <div class="bd-row"><span>Время:</span> <b>{{ selectedSlot.hour }}:00 — {{ selectedSlot.hour + 1 }}:00</b></div>
          <div class="bd-row">
            <span>Тип:</span>
            <b :class="selectedSlot.type === 'recommended' ? 'rec-text' : 'other-text'">
              {{ selectedSlot.type === 'recommended' ? 'свой факультет' : 'другой факультет' }}
            </b>
          </div>
        </div>
        <p class="hint">Проверяющих позже назначат координаторы.</p>
        <div v-if="errorMsg" class="error-box">{{ errorMsg }}</div>
        <div class="actions">
          <button class="ghost-btn" @click="step = 'slots'">← Назад</button>
          <button class="primary-btn" :disabled="booking" @click="confirmBooking">
            {{ booking ? 'Записываю…' : 'Записаться' }}
          </button>
        </div>
      </div>

      <!-- Step 5: Success -->
      <div v-else-if="step === 'done'" class="step">
        <div class="success-banner">
          <div class="big-emoji">✅</div>
          <h2>Вы записаны!</h2>
          <div class="booking-details">
            <div class="bd-row"><span>Дата:</span> <b>{{ formatDate(result.slot_date) }}</b></div>
            <div class="bd-row"><span>Время:</span> <b>{{ result.slot_hour }}:00 — {{ result.slot_hour + 1 }}:00</b></div>
            <div class="bd-row pending">
              <span>Проверяющие:</span>
              <b>назначаются координаторами</b>
            </div>
          </div>
          <p class="hint">Сохраните эту страницу или сделайте скриншот. До встречи!</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const API_BASE = (import.meta.env.VITE_API_URL || '') + '/api'

const step = ref('id')
const studentId = ref('')
const loading = ref(false)
const slotsLoading = ref(false)
const booking = ref(false)
const errorMsg = ref('')

const candidate = ref({ fio: '', faculty: '', already_booked: null })
const recommended = ref([])
const other = ref([])
const selectedSlot = ref(null)
const result = ref({})

const MONTHS = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
const WEEKDAYS = ['вс','пн','вт','ср','чт','пт','сб']

function formatDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  return `${WEEKDAYS[dt.getDay()]}, ${d} ${MONTHS[m - 1]}`
}

function resetForm() {
  step.value = 'id'
  studentId.value = ''
  errorMsg.value = ''
  candidate.value = { fio: '', faculty: '', already_booked: null }
  recommended.value = []
  other.value = []
  selectedSlot.value = null
}

async function lookup() {
  if (!studentId.value.trim()) return
  errorMsg.value = ''
  loading.value = true
  try {
    const { data } = await axios.get(`${API_BASE}/booking/lookup`, {
      params: { student_id: studentId.value.trim() },
    })
    candidate.value = data
    if (data.already_booked) {
      step.value = 'already'
    } else {
      step.value = 'slots'
      await loadSlots()
    }
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Ошибка'
  } finally {
    loading.value = false
  }
}

async function loadSlots() {
  slotsLoading.value = true
  try {
    const { data } = await axios.get(`${API_BASE}/booking/slots`, {
      params: { student_id: studentId.value.trim() },
    })
    recommended.value = data.recommended?.dates || []
    other.value = data.other?.dates || []
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Не удалось загрузить слоты'
  } finally {
    slotsLoading.value = false
  }
}

function selectSlot(date, slot) {
  selectedSlot.value = { date, hour: slot.hour, type: slot.type }
  errorMsg.value = ''
  step.value = 'confirm'
}

async function confirmBooking() {
  booking.value = true
  errorMsg.value = ''
  try {
    const { data } = await axios.post(`${API_BASE}/booking/book`, {
      student_id: studentId.value.trim(),
      slot_date: selectedSlot.value.date,
      slot_hour: selectedSlot.value.hour,
    })
    result.value = data
    step.value = 'done'
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Не удалось забронировать'
    if (e.response?.status === 409) {
      // Слот ушёл — обновим список
      await loadSlots()
    }
  } finally {
    booking.value = false
  }
}
</script>

<style scoped>
.booking-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  display: flex; align-items: center; justify-content: center;
  padding: 2rem 1rem;
}
.booking-card {
  background: white; border-radius: 18px;
  padding: 2.25rem 2.5rem;
  width: 100%; max-width: 540px;
  box-shadow: 0 20px 50px rgba(0,0,0,0.25);
}
.brand {
  font-size: 0.78rem; color: #4361ee;
  font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; margin-bottom: 0.25rem;
}
h1 { margin: 0 0 1.5rem; color: #1a1a2e; font-size: 1.5rem; }
h2 { margin: 0 0 0.85rem; color: #1a1a2e; font-size: 1.2rem; }

.step { animation: fadeIn 0.25s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.hint { font-size: 0.88rem; color: #777; line-height: 1.5; margin: 0 0 1.1rem; }

.big-input {
  width: 100%; padding: 0.85rem 1rem;
  border: 2px solid #e0e0e0; border-radius: 10px;
  font-size: 1rem; font-family: inherit;
  outline: none; box-sizing: border-box;
  transition: border-color 0.15s;
  margin-bottom: 0.85rem;
}
.big-input:focus { border-color: #4361ee; }

.primary-btn {
  width: 100%; padding: 0.85rem 1.2rem;
  background: #4361ee; color: white; border: none;
  border-radius: 10px; font-size: 0.95rem; font-weight: 700;
  cursor: pointer; transition: background 0.15s;
}
.primary-btn:hover:not(:disabled) { background: #3451d1; }
.primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.ghost-btn {
  padding: 0.7rem 1.1rem; background: transparent;
  border: 1.5px solid #e0e0e0; color: #555;
  border-radius: 10px; font-size: 0.88rem; cursor: pointer;
}
.ghost-btn:hover { border-color: #4361ee; color: #4361ee; }

.error-box {
  padding: 0.65rem 0.85rem; background: rgba(230,57,70,0.08);
  color: #c0392b; border-radius: 8px;
  font-size: 0.85rem; margin-bottom: 0.85rem;
}

.candidate-info {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 1rem; padding: 0.85rem 1rem;
  background: #f7f8ff; border-radius: 10px;
  margin-bottom: 1.25rem;
}
.ci-fio { font-weight: 700; font-size: 1.05rem; color: #1a1a2e; }
.ci-faculty { font-size: 0.85rem; color: #555; margin-top: 0.2rem; }
.ci-faculty.muted { color: #aaa; font-style: italic; }
.link-btn { background: none; border: none; color: #4361ee; cursor: pointer; font-size: 0.8rem; padding: 0; }
.link-btn:hover { text-decoration: underline; }

.section { margin-bottom: 1.25rem; }
.section-title {
  font-size: 0.82rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em;
  padding: 0.4rem 0.7rem; border-radius: 7px;
  margin-bottom: 0.75rem; display: inline-block;
}
.section-title.rec-title   { background: rgba(6,160,122,0.1);  color: #06a07a; }
.section-title.other-title { background: #efefef; color: #777; }

.empty-slots {
  padding: 2rem; text-align: center;
  color: #aaa; font-size: 0.9rem;
  background: #fafafa; border-radius: 10px;
}

.day-block { margin-bottom: 1.1rem; }
.day-header {
  font-size: 0.78rem; font-weight: 700;
  color: #555; text-transform: uppercase;
  letter-spacing: 0.04em; margin-bottom: 0.5rem;
}
.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(95px, 1fr));
  gap: 0.5rem;
}
.slot-btn {
  display: flex; flex-direction: column; align-items: center;
  padding: 0.55rem 0.5rem;
  border: 2px solid transparent;
  border-radius: 9px; cursor: pointer;
  background: white; transition: all 0.12s;
}
.slot-btn.rec   { background: rgba(6,160,122,0.08); border-color: rgba(6,160,122,0.3); color: #06a07a; }
.slot-btn.other { background: #f5f5f7; border-color: #e0e0e0; color: #666; }
.slot-btn:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(67,97,238,0.15); }
.slot-btn.rec:hover   { border-color: #06a07a; }
.slot-btn.other:hover { border-color: #999; color: #333; }
.slot-hour { font-size: 1rem; font-weight: 700; }
.slot-meta { font-size: 0.65rem; opacity: 0.7; margin-top: 0.15rem; }

.booking-details {
  background: #fafafa; border-radius: 10px;
  padding: 0.85rem 1.1rem; margin: 0.85rem 0;
}
.bd-row {
  display: flex; justify-content: space-between;
  padding: 0.3rem 0; font-size: 0.92rem;
}
.bd-row span { color: #888; }
.bd-row b { color: #1a1a2e; }
.bd-row.pending b { color: #888; font-weight: 500; font-style: italic; }

.actions { display: flex; gap: 0.65rem; margin-top: 0.5rem; }
.actions .primary-btn { flex: 1; }

.success-banner { text-align: center; }
.big-emoji { font-size: 3.5rem; margin-bottom: 0.5rem; }
.rec-text   { color: #06a07a; }
.other-text { color: #888; }

.state-msg { text-align: center; padding: 2rem; color: #aaa; font-size: 0.9rem; }
</style>
