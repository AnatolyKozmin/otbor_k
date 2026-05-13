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
          @input="onStudentIdInput"
          class="big-input pin-input"
          placeholder="123456"
          inputmode="numeric"
          pattern="[0-9]*"
          maxlength="6"
          autocomplete="off"
          @keydown.enter="lookup"
          :disabled="loading"
        />
        <div v-if="errorMsg" class="error-box">{{ errorMsg }}</div>
        <button class="primary-btn" :disabled="loading || studentId.length < 6" @click="lookup">
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
              <b>назначаются обучающими координаторами</b>
            </div>
          </div>
          <p class="hint">Хотите перенести запись? Выберите другой слот.</p>
          <button class="ghost-btn rebook-btn" @click="goRebook">Перенести запись →</button>
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
                  <span class="slot-meta">{{ s.free_capacity }} мест</span>
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
                  <span class="slot-meta">{{ s.free_capacity }} мест</span>
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
        <p class="hint">Проверяющих позже назначат обучающие координаторы.</p>
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
              <b>назначаются обучающими координаторами</b>
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

function onStudentIdInput(e) {
  studentId.value = e.target.value.replace(/\D/g, '').slice(0, 6)
}

async function goRebook() {
  step.value = 'slots'
  await loadSlots()
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

function filterAvailableSlots(dates) {
  const now = new Date()
  const cutoff = new Date(now.getTime() + 12 * 60 * 60 * 1000)
  return dates
    .map(day => ({
      ...day,
      slots: day.slots.filter(s => {
        const slot = new Date(`${day.date}T${String(s.hour).padStart(2,'0')}:00`)
        return slot > cutoff
      }),
    }))
    .filter(day => day.slots.length > 0)
}

async function loadSlots() {
  slotsLoading.value = true
  try {
    const { data } = await axios.get(`${API_BASE}/booking/slots`, {
      params: { student_id: studentId.value.trim() },
    })
    recommended.value = filterAvailableSlots(data.recommended?.dates || [])
    other.value = filterAvailableSlots(data.other?.dates || [])
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
  background:
    radial-gradient(1200px 600px at 80% -10%, rgba(67,97,238,0.35), transparent 60%),
    radial-gradient(900px 500px at -10% 110%, rgba(123,45,139,0.30), transparent 60%),
    linear-gradient(135deg, #0f1024 0%, #16213e 60%, #0f1024 100%);
  display: flex; align-items: center; justify-content: center;
  padding: 2.5rem 1rem;
  font-feature-settings: "ss01", "cv01";
}

.booking-card {
  position: relative;
  background: white;
  border-radius: 22px;
  padding: 2.4rem 2.6rem 2.2rem;
  width: 100%; max-width: 540px;
  box-shadow: 0 30px 80px rgba(0,0,0,0.35), 0 2px 6px rgba(0,0,0,0.08);
  overflow: hidden;
}
/* верхняя градиентная полоска для акцента */
.booking-card::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 5px;
  background: linear-gradient(90deg, #4361ee, #7b2d8b, #06a07a);
}

.brand {
  font-size: 0.74rem; color: #4361ee;
  font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.12em;
  display: inline-flex; align-items: center; gap: 0.5rem;
  margin-bottom: 0.4rem;
}
.brand::before {
  content: "🎓";
  font-size: 1.1rem;
}

h1 {
  margin: 0 0 1.6rem;
  color: #0f1024;
  font-size: 1.7rem;
  font-weight: 800;
  letter-spacing: -0.01em;
}
h2 {
  margin: 0 0 0.85rem;
  color: #0f1024;
  font-size: 1.25rem;
  font-weight: 700;
}

.step { animation: fadeIn 0.3s cubic-bezier(.2,.7,.2,1); }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

.hint {
  font-size: 0.9rem; color: #6b7280;
  line-height: 1.55; margin: 0 0 1.2rem;
}

/* ── input ──────────────────────────────────────────────────────────────── */
.big-input {
  width: 100%;
  padding: 1rem 1.1rem;
  border: 2px solid #e8eaf0;
  background: #fafbfc;
  border-radius: 12px;
  font-size: 1rem; font-family: inherit;
  outline: none; box-sizing: border-box;
  transition: border-color 0.18s, background 0.18s, box-shadow 0.18s;
  margin-bottom: 0.95rem;
  color: #0f1024;
}
.big-input:hover { background: white; }
.big-input:focus {
  border-color: #4361ee; background: white;
  box-shadow: 0 0 0 4px rgba(67,97,238,0.12);
}
/* pin-style для 6-значного номера */
.pin-input {
  text-align: center;
  font-size: 1.65rem;
  font-weight: 700;
  letter-spacing: 0.45em;
  padding-left: 0.45em;     /* центрирует с letter-spacing */
  font-variant-numeric: tabular-nums;
}
.pin-input::placeholder {
  color: #d0d4dd;
  font-weight: 600;
  letter-spacing: 0.45em;
}

/* ── buttons ────────────────────────────────────────────────────────────── */
.primary-btn {
  width: 100%;
  padding: 0.95rem 1.2rem;
  background: linear-gradient(135deg, #4361ee 0%, #5e3df5 100%);
  color: white; border: none;
  border-radius: 12px;
  font-size: 0.98rem; font-weight: 700;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(67,97,238,0.32);
  transition: transform 0.12s, box-shadow 0.18s, filter 0.18s;
}
.primary-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(67,97,238,0.45);
  filter: brightness(1.05);
}
.primary-btn:active:not(:disabled) { transform: translateY(0); }
.primary-btn:disabled {
  opacity: 0.5; cursor: not-allowed;
  box-shadow: none;
  filter: grayscale(0.4);
}

.ghost-btn {
  padding: 0.85rem 1.2rem;
  background: transparent;
  border: 1.5px solid #e8eaf0;
  color: #4b5563;
  border-radius: 12px;
  font-size: 0.9rem; font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.ghost-btn:hover { border-color: #4361ee; color: #4361ee; background: rgba(67,97,238,0.04); }

/* ── states ─────────────────────────────────────────────────────────────── */
.error-box {
  padding: 0.7rem 0.95rem;
  background: rgba(230,57,70,0.08);
  color: #c0392b;
  border-left: 3px solid #e63946;
  border-radius: 8px;
  font-size: 0.86rem; margin-bottom: 0.95rem;
}

.candidate-info {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 1rem; padding: 1rem 1.2rem;
  background: linear-gradient(135deg, rgba(67,97,238,0.06), rgba(123,45,139,0.05));
  border: 1px solid rgba(67,97,238,0.12);
  border-radius: 14px;
  margin-bottom: 1.4rem;
}
.ci-fio { font-weight: 700; font-size: 1.08rem; color: #0f1024; }
.ci-faculty { font-size: 0.85rem; color: #4b5563; margin-top: 0.25rem; }
.ci-faculty b { color: #4361ee; }
.ci-faculty.muted { color: #aaa; font-style: italic; }

.link-btn {
  background: none; border: none;
  color: #4361ee; cursor: pointer;
  font-size: 0.8rem; padding: 0;
  font-weight: 600;
}
.link-btn:hover { text-decoration: underline; }

/* ── slots ──────────────────────────────────────────────────────────────── */
.section { margin-bottom: 1.4rem; }
.section-title {
  font-size: 0.78rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.08em;
  padding: 0.42rem 0.85rem; border-radius: 999px;
  margin-bottom: 0.85rem; display: inline-block;
}
.section-title.rec-title {
  background: rgba(6,160,122,0.12); color: #058c6b;
}
.section-title.other-title {
  background: #eef0f4; color: #6b7280;
}

.empty-slots {
  padding: 2.2rem; text-align: center;
  color: #9ca3af; font-size: 0.92rem;
  background: #fafbfc; border: 1px dashed #e0e3ea;
  border-radius: 12px;
}

.day-block { margin-bottom: 1.15rem; }
.day-header {
  font-size: 0.76rem; font-weight: 700;
  color: #6b7280; text-transform: uppercase;
  letter-spacing: 0.05em; margin-bottom: 0.55rem;
}
.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(95px, 1fr));
  gap: 0.55rem;
}
.slot-btn {
  display: flex; flex-direction: column; align-items: center;
  padding: 0.65rem 0.5rem;
  border: 2px solid transparent;
  border-radius: 11px; cursor: pointer;
  background: white;
  transition: transform 0.12s, box-shadow 0.18s, border-color 0.15s, background 0.15s;
}
.slot-btn.rec   {
  background: rgba(6,160,122,0.08);
  border-color: rgba(6,160,122,0.28);
  color: #058c6b;
}
.slot-btn.other {
  background: #f5f6f9;
  border-color: #e3e6ec;
  color: #4b5563;
}
.slot-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 18px rgba(67,97,238,0.14);
}
.slot-btn.rec:hover   { border-color: #06a07a; background: rgba(6,160,122,0.13); }
.slot-btn.other:hover { border-color: #9ca3af; color: #1f2937; }
.slot-hour { font-size: 1.05rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.slot-meta { font-size: 0.66rem; opacity: 0.75; margin-top: 0.18rem; }

/* ── details box ────────────────────────────────────────────────────────── */
.booking-details {
  background: #fafbfc;
  border: 1px solid #eef0f4;
  border-radius: 12px;
  padding: 1rem 1.2rem;
  margin: 0.95rem 0;
}
.bd-row {
  display: flex; justify-content: space-between;
  padding: 0.35rem 0; font-size: 0.93rem;
  border-bottom: 1px dashed #eef0f4;
}
.bd-row:last-child { border-bottom: none; }
.bd-row span { color: #6b7280; }
.bd-row b { color: #0f1024; font-weight: 600; }
.bd-row.pending b { color: #9ca3af; font-weight: 500; font-style: italic; }

.actions { display: flex; gap: 0.7rem; margin-top: 0.65rem; }
.actions .primary-btn { flex: 1; }

/* ── success banner ─────────────────────────────────────────────────────── */
.success-banner { text-align: center; }
.big-emoji {
  font-size: 3.8rem;
  margin-bottom: 0.4rem;
  filter: drop-shadow(0 6px 14px rgba(67,97,238,0.25));
  animation: pop 0.45s cubic-bezier(.2,.9,.3,1.2);
}
@keyframes pop {
  0%   { transform: scale(0.5); opacity: 0; }
  60%  { transform: scale(1.15); opacity: 1; }
  100% { transform: scale(1); }
}
.rec-text   { color: #058c6b; }
.other-text { color: #6b7280; }

.rebook-btn {
  width: 100%;
  margin-top: 0.75rem;
}

.state-msg {
  text-align: center; padding: 2.2rem;
  color: #9ca3af; font-size: 0.92rem;
}

/* ── mobile ─────────────────────────────────────────────────────────────── */
@media (max-width: 540px) {
  .booking-card { padding: 1.8rem 1.4rem; border-radius: 16px; }
  h1 { font-size: 1.45rem; }
  .pin-input { font-size: 1.4rem; letter-spacing: 0.3em; }
}
</style>
