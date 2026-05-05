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

          <button class="btn-share" @click="openShare">
            Поделиться смешным ответом
          </button>
        </div>

      </div>
    </div>

    <!-- Share modal -->
    <Teleport to="body">
      <div v-if="shareOpen" class="share-backdrop" @click.self="shareOpen = false"></div>
      <div v-if="shareOpen" class="share-modal">
        <div class="share-head">
          <h3>Поделиться ответом</h3>
          <button class="close-btn" @click="shareOpen = false">✕</button>
        </div>
        <p class="share-hint">
          Выбери вопрос — карточка с ответом отправится в Telegram-чат факультета.
        </p>
        <div class="share-list">
          <label
            v-for="qa in shareableQA"
            :key="qa.key"
            class="share-item"
            :class="{ selected: selectedQA === qa.key }"
          >
            <input type="radio" :value="qa.key" v-model="selectedQA" />
            <div class="qa-content">
              <div class="qa-q">{{ qa.label }}</div>
              <div class="qa-a">{{ qa.answer }}</div>
            </div>
          </label>
        </div>
        <div v-if="shareMsg" class="share-msg" :class="shareMsgKind">{{ shareMsg }}</div>
        <div class="share-actions">
          <button class="btn-cancel" @click="shareOpen = false">Отмена</button>
          <button
            class="btn-send"
            :disabled="!selectedQA || sharing"
            @click="doShare"
          >
            {{ sharing ? 'Отправка…' : 'Отправить в Telegram' }}
          </button>
        </div>
      </div>
    </Teleport>

    <!-- Кнопка-флажок и выезжающая панель подсказки -->
    <Teleport to="body">
      <button
        class="rubric-toggle"
        :class="{ open: rubricOpen }"
        :title="rubricOpen ? 'Скрыть подсказку (Esc)' : 'Показать подсказку по баллам'"
        @click="rubricOpen = !rubricOpen"
      >
        <span class="rubric-toggle-icon">📋</span>
        <span class="rubric-toggle-text">Подсказка</span>
      </button>

      <transition name="rubric-fade">
        <div
          v-if="rubricOpen"
          class="rubric-backdrop"
          @click="rubricOpen = false"
        />
      </transition>

      <transition name="rubric-slide">
        <aside v-if="rubricOpen" class="rubric-panel" role="dialog" aria-label="Подсказка по баллам">
          <header class="rubric-head">
            <div>
              <h3>Подсказка по баллам</h3>
              <p>Что и за сколько баллов ставить</p>
            </div>
            <button class="rubric-close" @click="rubricOpen = false" aria-label="Закрыть">×</button>
          </header>

          <div class="rubric-body">
            <section
              v-for="r in RUBRIC"
              :key="r.key"
              class="rubric-item"
            >
              <h4 class="rubric-item-title">{{ r.label }}</h4>

              <div class="rubric-levels">
                <div
                  v-for="lvl in r.levels"
                  :key="lvl.score"
                  class="rubric-level"
                >
                  <span class="rubric-score" :data-score="lvl.score">{{ lvl.score }}</span>
                  <div class="rubric-text">{{ lvl.text }}</div>
                </div>
              </div>
            </section>
          </div>
        </aside>
      </transition>
    </Teleport>
  </AppLayout>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import { RUBRIC } from '../data/rubric'

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

// Подсказка по баллам
const rubricOpen = ref(false)

// Share modal
const shareOpen = ref(false)
const selectedQA = ref(null)
const sharing = ref(false)
const shareMsg = ref('')
const shareMsgKind = ref('ok')

const shareableQA = computed(() => {
  return Object.entries(displayData.value)
    .filter(([, v]) => v && String(v).trim().length > 5)
    .map(([label, answer]) => ({ key: label, label, answer: String(answer) }))
})

function openShare() {
  selectedQA.value = null
  shareMsg.value = ''
  shareOpen.value = true
}

async function doShare() {
  if (!selectedQA.value) return
  sharing.value = true
  shareMsg.value = ''
  const qa = shareableQA.value.find(q => q.key === selectedQA.value)
  try {
    const { data } = await api.post('/telegram/share', {
      sheet,
      row_number: rowNumber,
      question_label: qa.label,
      answer: qa.answer,
    })
    shareMsgKind.value = 'ok'
    shareMsg.value = `Отправлено в чат «${data.chat}»`
    setTimeout(() => { shareOpen.value = false }, 2000)
  } catch (e) {
    shareMsgKind.value = 'err'
    shareMsg.value = e.response?.data?.detail || 'Ошибка отправки'
  } finally {
    sharing.value = false
  }
}

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
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  clearInterval(autosaveInterval)
  clearTimeout(autosaveTimeout)
  window.removeEventListener('beforeunload', flushOnUnload)
  window.removeEventListener('pagehide', flushOnUnload)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  document.removeEventListener('keydown', onKeydown)
})

function onKeydown(e) {
  if (e.key === 'Escape' && rubricOpen.value) rubricOpen.value = false
}

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

.btn-share {
  width: 100%;
  padding: 0.55rem;
  background: transparent;
  border: 1.5px dashed #9b85d8;
  color: #7c5cd8;
  border-radius: 8px;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  margin-top: 0.35rem;
}
.btn-share:hover { background: rgba(124,92,216,0.08); border-style: solid; }

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

<!-- Глобальные стили для панели подсказки. Без scoped — потому что
     Teleport уносит элементы в body, а scoped-селекторы на data-v-XXX
     там не работают. Префикс .rubric-* уникален и не конфликтует. -->
<style>
/* Кнопка-флажок на левой кромке контента (после сайдбара 240px) */
.rubric-toggle {
  position: fixed;
  top: 50%;
  left: 240px;
  transform: translateY(-50%);
  z-index: 1100;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.7rem 0.55rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 0 12px 12px 0;
  cursor: pointer;
  box-shadow: 2px 2px 12px rgba(67,97,238,0.25);
  font-size: 0.78rem;
  font-weight: 600;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transition: left 0.28s cubic-bezier(0.22, 0.61, 0.36, 1), background 0.15s;
}
.rubric-toggle:hover { background: #3451d1; }
.rubric-toggle.open {
  left: calc(240px + 480px);
  background: #1a1a2e;
}
.rubric-toggle-icon { font-size: 1rem; writing-mode: horizontal-tb; }
.rubric-toggle-text { letter-spacing: 0.05em; }

/* Затемнение под панелью */
.rubric-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(26,26,46,0.35);
  z-index: 1050;
}

/* Сама выезжающая панель */
.rubric-panel {
  position: fixed;
  top: 0;
  left: 240px;
  bottom: 0;
  width: 480px;
  max-width: calc(100vw - 240px);
  background: white;
  box-shadow: 4px 0 24px rgba(0,0,0,0.15);
  z-index: 1080;
  display: flex;
  flex-direction: column;
}

.rubric-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.25rem 1.4rem;
  border-bottom: 1px solid #eef0f4;
  background: linear-gradient(180deg, #f8f9fc 0%, white 100%);
}
.rubric-head h3 {
  margin: 0 0 0.2rem;
  font-size: 1.05rem;
  color: #1a1a2e;
}
.rubric-head p {
  margin: 0;
  font-size: 0.78rem;
  color: #888;
}
.rubric-close {
  width: 32px;
  height: 32px;
  border: none;
  background: #f0f2f5;
  color: #555;
  font-size: 1.4rem;
  line-height: 1;
  border-radius: 8px;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
.rubric-close:hover { background: #e63946; color: white; }

.rubric-body {
  overflow-y: auto;
  padding: 1rem 1.4rem 2rem;
  flex: 1;
}

.rubric-item {
  padding: 1rem 0 1.25rem;
  border-bottom: 1px solid #f0f2f5;
}
.rubric-item:last-child { border-bottom: none; }

.rubric-item-title {
  margin: 0 0 0.6rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: #1a1a2e;
}

.rubric-levels {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}
.rubric-level {
  display: grid;
  grid-template-columns: 32px 1fr;
  gap: 0.7rem;
  align-items: start;
}
.rubric-score {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  font-weight: 700;
  font-size: 0.85rem;
  flex-shrink: 0;
}
.rubric-score[data-score="0"] { background: #fdecea; color: #c0392b; }
.rubric-score[data-score="1"] { background: #fff5e0; color: #d68910; }
.rubric-score[data-score="2"] { background: #e8f4fd; color: #2874a6; }
.rubric-score[data-score="3"] { background: #e7f8ef; color: #1e8449; }

.rubric-text {
  font-size: 0.82rem;
  line-height: 1.5;
  color: #333;
  white-space: pre-wrap;
}

/* Анимации */
.rubric-fade-enter-active,
.rubric-fade-leave-active { transition: opacity 0.22s ease; }
.rubric-fade-enter-from,
.rubric-fade-leave-to { opacity: 0; }

.rubric-slide-enter-active,
.rubric-slide-leave-active {
  transition: transform 0.28s cubic-bezier(0.22, 0.61, 0.36, 1);
}
.rubric-slide-enter-from,
.rubric-slide-leave-to { transform: translateX(-100%); }

/* Адаптив: на узких экранах сайдбар может схлопываться — убираем 240px-смещение */
@media (max-width: 900px) {
  .rubric-toggle { left: 0; }
  .rubric-toggle.open { left: min(480px, 90vw); }
  .rubric-panel { left: 0; max-width: 90vw; }
}

/* ─── Share modal ─────────────────────────────────────────────────────────── */
.share-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  z-index: 300;
}

.share-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 301;
  background: white;
  border-radius: 16px;
  box-shadow: 0 8px 48px rgba(0,0,0,0.18);
  width: 540px;
  max-width: calc(100vw - 2rem);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.share-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.4rem 0.85rem;
  border-bottom: 1px solid #eee;
  flex-shrink: 0;
}
.share-head h3 { margin: 0; font-size: 1rem; color: #1a1a2e; }

.share-hint {
  margin: 0;
  padding: 0.75rem 1.4rem;
  font-size: 0.82rem;
  color: #888;
  line-height: 1.45;
  flex-shrink: 0;
}

.share-list {
  overflow-y: auto;
  padding: 0 1.4rem;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-bottom: 0.75rem;
}

.share-item {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  padding: 0.75rem 0.85rem;
  border: 1.5px solid #e8e8e8;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.12s;
  user-select: none;
}
.share-item:hover { border-color: #9b85d8; background: rgba(124,92,216,0.04); }
.share-item.selected { border-color: #7c5cd8; background: rgba(124,92,216,0.07); }
.share-item input { margin-top: 0.2rem; flex-shrink: 0; accent-color: #7c5cd8; }

.qa-content { min-width: 0; }
.qa-q { font-size: 0.75rem; font-weight: 600; color: #888; margin-bottom: 0.2rem; }
.qa-a {
  font-size: 0.875rem;
  color: #222;
  white-space: pre-wrap;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.share-msg {
  margin: 0 1.4rem;
  padding: 0.55rem 0.85rem;
  border-radius: 8px;
  font-size: 0.82rem;
  flex-shrink: 0;
}
.share-msg.ok  { background: rgba(6,214,160,0.1);  color: #06875e; }
.share-msg.err { background: rgba(230,57,70,0.08); color: #e63946; }

.share-actions {
  display: flex;
  gap: 0.65rem;
  justify-content: flex-end;
  padding: 0.85rem 1.4rem 1.1rem;
  border-top: 1px solid #eee;
  flex-shrink: 0;
}

.btn-send {
  padding: 0.55rem 1.4rem;
  background: #7c5cd8;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-send:hover:not(:disabled) { background: #6a4bc5; }
.btn-send:disabled { opacity: 0.55; cursor: not-allowed; }
</style>
