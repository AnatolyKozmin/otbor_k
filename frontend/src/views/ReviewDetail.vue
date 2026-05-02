<template>
  <AppLayout>
    <div class="review-page">

      <!-- Header -->
      <div class="page-header">
        <button class="back-btn" @click="$router.back()">← Назад</button>
        <div class="header-center">
          <span class="sheet-badge">{{ SHEET_LABELS[sheet] }}</span>
          <h2>Строка #{{ rowNumber }}</h2>
        </div>
        <div class="header-right">
          <span v-if="autosaveMsg" class="autosave-msg">{{ autosaveMsg }}</span>
          <button class="btn-save" :disabled="saving" @click="saveReview">
            {{ saving ? 'Сохранение…' : 'Сохранить' }}
          </button>
        </div>
      </div>

      <!-- Loading / Error -->
      <div v-if="loading" class="state-msg">Загрузка…</div>
      <div v-else-if="loadError" class="state-msg error">{{ loadError }}</div>

      <!-- Main layout -->
      <div v-else class="review-layout">

        <!-- Left: applicant answers -->
        <div class="answers-panel">
          <div
            v-for="(value, key) in displayData"
            :key="key"
            class="qa-item"
          >
            <div class="q-label">{{ key }}</div>
            <div class="a-text" :class="{ empty: !value }">{{ value || '—' }}</div>
          </div>
        </div>

        <!-- Right: scoring panel -->
        <div class="scoring-panel">
          <div class="scoring-header">
            <span class="scoring-title">Оценка</span>
            <span v-if="hasAutosave" class="restored-badge">Восстановлено из черновика</span>
            <span v-else-if="isSaved" class="saved-badge">Сохранено</span>
          </div>

          <div class="criteria-list">
            <div
              v-for="c in criteria"
              :key="c.key"
              class="criterion"
            >
              <div class="c-label">{{ c.label }}</div>

              <!-- Score buttons -->
              <div v-if="c.options" class="option-group">
                <button
                  v-for="opt in c.options"
                  :key="opt"
                  class="opt-btn"
                  :class="{ selected: scores[c.key] === opt }"
                  @click="setScore(c.key, opt)"
                >
                  {{ opt }}
                </button>
              </div>

              <!-- Text input -->
              <textarea
                v-else
                v-model="scores[c.key]"
                class="text-input"
                rows="3"
                placeholder="Комментарий…"
                @input="onTextInput"
              />
            </div>
          </div>

          <button
            class="btn-save full"
            :disabled="saving"
            @click="saveReview"
          >
            {{ saving ? 'Сохранение…' : 'Сохранить' }}
          </button>

          <div v-if="saveOk" class="save-ok-msg">✓ Данные сохранены</div>
          <div v-if="saveError" class="save-err-msg">{{ saveError }}</div>

          <div class="redis-hint" v-if="!redisAvailable">
            Redis недоступен — автосохранение в браузере
          </div>
        </div>

      </div>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const SHEET_LABELS = { anketa: 'Анкета', homework: 'Домашка', interview: 'Собес' }

const route = useRoute()
const auth = useAuthStore()
const sheet = route.params.sheet
const rowNumber = Number(route.params.rowNumber)

// State
const loading = ref(true)
const loadError = ref('')
const displayData = ref({})
const criteria = ref([])
const scores = reactive({})
const hasAutosave = ref(false)
const isSaved = ref(false)
const redisAvailable = ref(true)

const saving = ref(false)
const saveOk = ref(false)
const saveError = ref('')
const autosaveMsg = ref('')

// localStorage — ВСЕГДА используется как защищённый бэкап (не только когда Redis offline).
// Включаем user.id, чтобы драфты не утекали между разными аккаунтами в одном браузере.
const LS_KEY = `autosave:${sheet}:${rowNumber}:u${auth.user?.id ?? 'anon'}`

let autosaveTimeout = null
let autosaveInterval = null

// ------------------------------------------------------------------
// Local storage helpers — наша последняя линия защиты от потери данных
// ------------------------------------------------------------------
function saveLocal() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      scores: { ...scores },
      ts: Date.now(),
    }))
  } catch {}
}

function loadLocal() {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && parsed.scores ? parsed : null
  } catch {
    return null
  }
}

// ------------------------------------------------------------------
// Load on mount
// ------------------------------------------------------------------
onMounted(async () => {
  try {
    const [rowRes, critRes, reviewRes] = await Promise.all([
      api.get(`/sheets/${sheet}/${rowNumber}`),
      api.get('/reviews/criteria'),
      api.get(`/reviews/${sheet}/${rowNumber}`),
    ])

    const raw = rowRes.data.row
    displayData.value = Object.fromEntries(
      Object.entries(raw).filter(([k]) => !k.startsWith('_'))
    )

    criteria.value = critRes.data.criteria
    redisAvailable.value = critRes.data.redis_available

    const review = reviewRes.data
    hasAutosave.value = review.has_autosave
    isSaved.value = review.is_saved
    const serverScores = review.scores || {}

    // Применяем серверные scores как базу
    criteria.value.forEach(c => {
      scores[c.key] = serverScores[c.key] ?? (c.options ? null : '')
    })

    // localStorage может быть свежее, чем сервер (если Redis падал, или
    // вкладку закрыли до того, как успел отправиться debounced autosave,
    // и flush-on-unload тоже не достучался). Сравниваем и используем,
    // если содержимое отличается.
    const local = loadLocal()
    if (local) {
      const localStr = JSON.stringify(local.scores)
      const serverStr = JSON.stringify(serverScores)
      if (localStr !== serverStr) {
        Object.assign(scores, local.scores)
        hasAutosave.value = true
      } else {
        // localStorage уже совпадает с сервером — можно почистить
        try { localStorage.removeItem(LS_KEY) } catch {}
      }
    }
  } catch (e) {
    loadError.value = e.response?.data?.detail || 'Ошибка загрузки'
  } finally {
    loading.value = false
  }

  // Периодический autosave каждые 60с — на случай, если debounce не успел
  autosaveInterval = setInterval(doAutosave, 60_000)

  // Flush при закрытии вкладки. Используем fetch с keepalive, который
  // переживает unload (sendBeacon не подошёл — не позволяет Authorization).
  window.addEventListener('beforeunload', flushOnUnload)
  window.addEventListener('pagehide', flushOnUnload)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  clearInterval(autosaveInterval)
  clearTimeout(autosaveTimeout)
  window.removeEventListener('beforeunload', flushOnUnload)
  window.removeEventListener('pagehide', flushOnUnload)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

function onVisibilityChange() {
  if (document.visibilityState === 'hidden') flushOnUnload()
}

// ------------------------------------------------------------------
// Score editing → immediate localStorage + debounced server autosave
// ------------------------------------------------------------------
function setScore(key, val) {
  scores[key] = val
  saveLocal()           // сохраняем СРАЗУ — никаких debounce
  scheduleAutosave()    // и ставим в очередь отправку на сервер
}

function onTextInput() {
  saveLocal()           // текст тоже сохраняем сразу в localStorage
  scheduleAutosave()
}

function scheduleAutosave() {
  clearTimeout(autosaveTimeout)
  autosaveTimeout = setTimeout(doAutosave, 5_000)
}

async function doAutosave() {
  saveLocal()  // belt-and-suspenders
  try {
    const { data } = await api.post(
      `/reviews/${sheet}/${rowNumber}/autosave`,
      { scores: { ...scores } },
    )
    if (data.ok) {
      autosaveMsg.value = 'Черновик сохранён'
      redisAvailable.value = true
    } else {
      // Сервер ответил, но Redis не доступен. Данные есть в localStorage —
      // их подцепят при следующей загрузке страницы. Координатор должен знать.
      autosaveMsg.value = '⚠ Сохранено только локально (Redis недоступен)'
      redisAvailable.value = false
    }
    setTimeout(() => { autosaveMsg.value = '' }, 4000)
  } catch {
    // Сеть/401/500 — но локальный бэкап уже есть.
    autosaveMsg.value = '⚠ Сохранено только в браузере'
    setTimeout(() => { autosaveMsg.value = '' }, 4000)
  }
}

// Flush на закрытии: гарантированный last-ditch attempt через fetch keepalive.
// Запрос продолжит лететь, даже если страница уже закрыта.
function flushOnUnload() {
  saveLocal()
  const token = localStorage.getItem('token')
  if (!token) return
  try {
    fetch(`/api/reviews/${sheet}/${rowNumber}/autosave`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ scores: { ...scores } }),
      keepalive: true,
    }).catch(() => {})
  } catch {}
}

// ------------------------------------------------------------------
// Save to SQLite
// ------------------------------------------------------------------
async function saveReview() {
  saving.value = true
  saveOk.value = false
  saveError.value = ''
  try {
    await api.post(`/reviews/${sheet}/${rowNumber}`, { scores: { ...scores } })
    isSaved.value = true
    hasAutosave.value = false
    saveOk.value = true
    try { localStorage.removeItem(LS_KEY) } catch {}
    setTimeout(() => { saveOk.value = false }, 4000)
  } catch (e) {
    saveError.value = e.response?.data?.detail || 'Ошибка сохранения'
    // НЕ чистим localStorage — данные нужно сохранить до удачной попытки
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.review-page { display: flex; flex-direction: column; height: 100%; }

/* Header */
.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
}

.back-btn {
  padding: 0.4rem 0.9rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  background: white;
  cursor: pointer;
  font-size: 0.85rem;
  color: #555;
  flex-shrink: 0;
  transition: all 0.15s;
}
.back-btn:hover { border-color: #4361ee; color: #4361ee; }

.header-center {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex: 1;
}

.header-center h2 { margin: 0; font-size: 1.25rem; color: #1a1a2e; }

.sheet-badge {
  background: rgba(67,97,238,0.12);
  color: #4361ee;
  padding: 0.2rem 0.65rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
}

.header-right { display: flex; align-items: center; gap: 0.75rem; margin-left: auto; }

.autosave-msg { font-size: 0.8rem; color: #06d6a0; }

/* Main layout */
.review-layout {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 1.25rem;
  flex: 1;
  min-height: 0;
  align-items: start;
}

/* Left panel */
.answers-panel {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow-y: auto;
  max-height: calc(100vh - 160px);
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.qa-item {
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 0.85rem;
}
.qa-item:last-child { border-bottom: none; padding-bottom: 0; }

.q-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #888;
  margin-bottom: 0.25rem;
  line-height: 1.3;
}

.a-text {
  font-size: 0.875rem;
  color: #222;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}
.a-text.empty { color: #bbb; font-style: italic; }

/* Right panel */
.scoring-panel {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 1.25rem;
  position: sticky;
  top: 0;
  max-height: calc(100vh - 160px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.scoring-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.scoring-title { font-size: 1rem; font-weight: 700; color: #1a1a2e; }

.restored-badge {
  font-size: 0.7rem;
  background: rgba(255,190,11,0.15);
  color: #c98a00;
  padding: 0.15rem 0.5rem;
  border-radius: 20px;
  font-weight: 600;
}
.saved-badge {
  font-size: 0.7rem;
  background: rgba(6,214,160,0.12);
  color: #06a07a;
  padding: 0.15rem 0.5rem;
  border-radius: 20px;
  font-weight: 600;
}

.criteria-list { display: flex; flex-direction: column; gap: 1rem; }

.criterion {}

.c-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: #444;
  margin-bottom: 0.4rem;
}

.option-group { display: flex; gap: 0.35rem; flex-wrap: wrap; }

.opt-btn {
  width: 40px;
  height: 36px;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  background: white;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  color: #555;
  transition: all 0.12s;
}
.opt-btn:hover { border-color: #4361ee; color: #4361ee; }
.opt-btn.selected { background: #4361ee; border-color: #4361ee; color: white; }

.text-input {
  width: 100%;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  padding: 0.5rem 0.65rem;
  font-size: 0.85rem;
  font-family: inherit;
  color: #333;
  resize: vertical;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.text-input:focus { outline: none; border-color: #4361ee; }

/* Buttons */
.btn-save {
  padding: 0.5rem 1.25rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}
.btn-save:hover:not(:disabled) { background: #3451d1; }
.btn-save:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-save.full { width: 100%; padding: 0.65rem; margin-top: 0.25rem; }

.save-ok-msg  { font-size: 0.82rem; color: #06a07a; text-align: center; }
.save-err-msg { font-size: 0.82rem; color: #e63946; text-align: center; }

.redis-hint {
  font-size: 0.72rem;
  color: #bbb;
  text-align: center;
  margin-top: -0.4rem;
}

.state-msg {
  background: white;
  border-radius: 12px;
  padding: 3rem;
  text-align: center;
  font-size: 0.9rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.state-msg.error { color: #e63946; }
</style>
