<template>
  <AppLayout>
    <!-- Header -->
    <div class="form-header">
      <button class="back-btn" @click="$router.back()">← Назад</button>
      <div class="header-info">
        <span class="candidate-name">{{ info.fio || 'Кандидат' }}</span>
        <div class="candidate-meta">
          <span v-if="info.faculty" class="meta-chip fac-chip">{{ info.faculty }}</span>
          <a
            v-if="info.telegram"
            :href="tgLink(info.telegram)"
            target="_blank"
            class="meta-chip tg-chip"
          >
            <span class="meta-label">TG:</span>
            <b>{{ info.telegram }}</b>
          </a>
          <span v-if="info.prior_coord" class="meta-chip prior" :class="priorCoordClass">
            <span class="meta-label">Был коордом:</span>
            <b>{{ info.prior_coord }}</b>
          </span>
          <span v-if="info.hw_package" class="meta-chip pkg">
            <span class="meta-label">Пакет ДЗ:</span>
            <b>{{ info.hw_package }}</b>
            <span v-if="info.hw_submissions_count > 1" class="multi-hw" :title="`Кандидат сдавал ДЗ ${info.hw_submissions_count} раза — показан пакет последней сдачи`">
              ⚠ {{ info.hw_submissions_count }} сдачи
            </span>
          </span>
        </div>
        <div class="reviewers-line">
          <span class="rev-chip r1" :class="{ me: info.my_slot === 1 }">
            {{ info.reviewer1?.name || '—' }}{{ info.my_slot === 1 ? ' (я)' : '' }}
          </span>
          <span class="rev-sep">+</span>
          <span class="rev-chip r2" :class="{ me: info.my_slot === 2 }">
            {{ info.reviewer2?.name || '—' }}{{ info.my_slot === 2 ? ' (я)' : '' }}
          </span>
        </div>
      </div>
      <div class="header-actions">
        <span v-if="syncStatus === 'saving'" class="sync-dot saving">● Сохраняю…</span>
        <span v-else-if="syncStatus === 'saved'" class="sync-dot saved">● Сохранено</span>
        <span v-else-if="syncStatus === 'error'" class="sync-dot error">● Ошибка</span>
        <button class="save-btn" :disabled="saving" @click="saveAll">
          {{ saving ? 'Сохраняю…' : 'Сохранить всё' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="state-msg">Загрузка формы…</div>

    <div v-else class="form-layout">
      <!-- Left: scrollable form -->
      <div class="form-scroll">
        <div v-for="section in sections" :key="section.key" class="section-block">
          <div class="section-header" :class="'sec-' + section.key">
            {{ section.section }}
            <span v-if="section.key === 'hw_questions' && (context.homework?.alternate_submissions?.length || 0) > 0" class="alt-pill">
              ⚠ сдач: {{ (context.homework.alternate_submissions.length + 1) }}
            </span>
          </div>

          <!-- Динамические секции: вопросы анкеты и ДЗ из /context -->
          <template v-if="section.key === 'anketa_questions'">
            <div v-if="!context.anketa?.qa?.length" class="form-item context-empty">
              Ответы из анкеты не подтянулись.
            </div>
            <div
              v-for="(qa, qIdx) in (context.anketa?.qa || [])"
              :key="'ank_' + qIdx"
              class="form-item context-item"
            >
              <div class="context-q">{{ qa.question }}</div>
              <div class="context-a">{{ qa.answer }}</div>
              <div class="note-columns">
                <div class="note-col mine">
                  <div class="note-label">{{ myLabel }}</div>
                  <textarea
                    class="note-area"
                    :value="myNotes['anketa_n_' + qIdx] || ''"
                    placeholder="Заметка по ответу анкеты…"
                    @input="onInput('anketa_n_' + qIdx, $event.target.value)"
                  />
                </div>
                <div class="note-col other" v-if="otherLabel">
                  <div class="note-label other-lbl">{{ otherLabel }}</div>
                  <div class="note-area readonly">
                    {{ otherNotes['anketa_n_' + qIdx] || '' }}
                    <span v-if="!otherNotes['anketa_n_' + qIdx]" class="placeholder">Пусто…</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="context.anketa?.prior_comments?.length" class="form-item prior-block">
              <div class="prior-title">Комментарии проверявших анкету:</div>
              <div v-for="(pc, pIdx) in context.anketa.prior_comments" :key="pIdx" class="prior-card">
                <div class="prior-name">{{ pc.reviewer_name }}</div>
                <div v-for="(v, k) in pc.text_fields" :key="k" class="prior-row">
                  <span class="prior-k">{{ k }}:</span> {{ v }}
                </div>
              </div>
            </div>
          </template>

          <template v-else-if="section.key === 'hw_questions'">
            <div class="form-item context-item">
              <div class="hw-link-row">
                <a v-if="info.hw_link" :href="info.hw_link" target="_blank" class="hw-link-btn">
                  📂 Открыть папку с ДЗ<span v-if="info.hw_package"> (пакет {{ info.hw_package }})</span>
                </a>
                <span v-else class="context-empty">Нет ссылки на ДЗ</span>
              </div>
              <div v-if="context.homework?.alternate_submissions?.length" class="alt-list">
                <div class="alt-list-title">Другие сдачи этого кандидата:</div>
                <div v-for="alt in context.homework.alternate_submissions" :key="alt.row_number" class="alt-item">
                  <span class="alt-pkg" v-if="alt.package">Пакет {{ alt.package }}</span>
                  <a v-if="alt.link" :href="alt.link" target="_blank" class="alt-link">открыть</a>
                  <span v-else class="muted">без ссылки</span>
                </div>
              </div>
              <div class="note-columns">
                <div class="note-col mine">
                  <div class="note-label">{{ myLabel }}</div>
                  <textarea
                    class="note-area"
                    :value="myNotes['hw_notes'] || ''"
                    placeholder="Заметка по ДЗ…"
                    @input="onInput('hw_notes', $event.target.value)"
                  />
                </div>
                <div class="note-col other" v-if="otherLabel">
                  <div class="note-label other-lbl">{{ otherLabel }}</div>
                  <div class="note-area readonly">
                    {{ otherNotes['hw_notes'] || '' }}
                    <span v-if="!otherNotes['hw_notes']" class="placeholder">Пусто…</span>
                  </div>
                </div>
              </div>
              <div v-if="context.homework?.prior_comments?.length" class="prior-block">
                <div class="prior-title">Комментарии проверявших ДЗ:</div>
                <div v-for="(pc, pIdx) in context.homework.prior_comments" :key="pIdx" class="prior-card">
                  <div class="prior-name">{{ pc.reviewer_name }}</div>
                  <div v-for="(v, k) in pc.text_fields" :key="k" class="prior-row">
                    <span class="prior-k">{{ k }}:</span> {{ v }}
                  </div>
                </div>
              </div>
            </div>
          </template>

          <template v-else>
          <div
            v-for="(item, idx) in section.items"
            :key="section.key + '_' + idx"
            class="form-item"
            :class="item.type"
          >
            <div v-if="item.type === 'script' && item.collapsible" class="script-collapsible">
              <button
                class="script-toggle"
                @click="toggleScript(section.key + '_' + idx)"
              >
                <span class="toggle-icon">{{ scriptOpen[section.key + '_' + idx] ? '▾' : '▸' }}</span>
                Скрипт ({{ scriptOpen[section.key + '_' + idx] ? 'свернуть' : 'развернуть' }})
              </button>
              <div v-if="scriptOpen[section.key + '_' + idx]" class="script-text">
                <span v-for="(seg, sIdx) in markBold(item.text)" :key="sIdx" :class="{ bold: seg.bold }">{{ seg.text }}</span>
              </div>
            </div>
            <div v-else-if="item.type === 'script'" class="script-text">
              <span v-for="(seg, sIdx) in markBold(item.text)" :key="sIdx" :class="{ bold: seg.bold }">{{ seg.text }}</span>
            </div>
            <div v-else-if="item.type === 'label'" class="sub-label">{{ item.text }}</div>

            <template v-else>
              <div class="question-text" :class="{ 'is-case': item.type === 'case' }">
                <span v-if="item.type === 'case'" class="case-badge">КЕЙС</span>
                <span v-for="(seg, sIdx) in markBold(stripCasePrefix(item.text))" :key="sIdx" :class="{ bold: seg.bold }">{{ seg.text }}</span>
              </div>
              <div class="note-columns">
                <div class="note-col mine">
                  <div class="note-label">{{ myLabel }}</div>
                  <textarea
                    class="note-area"
                    :value="myNotes[item.key] || ''"
                    :placeholder="mySlot ? 'Твои заметки…' : 'Заметки…'"
                    @input="onInput(item.key, $event.target.value)"
                  />
                </div>
                <div class="note-col other" v-if="otherLabel">
                  <div class="note-label other-lbl">{{ otherLabel }}</div>
                  <div class="note-area readonly">
                    {{ otherNotes[item.key] || '' }}
                    <span v-if="!otherNotes[item.key]" class="placeholder">Пусто…</span>
                  </div>
                </div>
              </div>
            </template>
          </div>
          </template>
        </div>

        <!-- Competency scoring -->
        <div class="comp-section section-block">
          <div class="section-header comp-header">
            <span>Оценка компетенций</span>
            <span class="comp-counter">{{ scoredCount }}/{{ COMPETENCIES.length }} заполнено</span>
          </div>
          <div class="comp-list">
            <div v-for="comp in COMPETENCIES" :key="comp.key" class="comp-item">
              <div class="comp-name">{{ comp.label }}</div>
              <div class="comp-score-line">
                <div class="comp-score-row">
                  <button
                    v-for="s in comp.scores"
                    :key="s"
                    class="score-btn"
                    :class="{
                      'score-active': myNotes['comp_score_' + comp.key] !== undefined && myNotes['comp_score_' + comp.key] !== '' && myNotes['comp_score_' + comp.key] == s,
                      'score-0': s === 0,
                      'score-hi': s === Math.max(...comp.scores),
                    }"
                    @click="setScore(comp.key, s)"
                  >{{ s }}</button>
                </div>
                <div class="other-score-val" :class="{ 'score-filled': otherNotes['comp_score_' + comp.key] !== undefined && otherNotes['comp_score_' + comp.key] !== '' }" v-if="otherLabel">
                  {{ (otherNotes['comp_score_' + comp.key] !== undefined && otherNotes['comp_score_' + comp.key] !== '') ? otherNotes['comp_score_' + comp.key] + '/' + Math.max(...comp.scores) : '—' }}
                </div>
              </div>
            </div>
          </div>
          <div class="comp-general-comment">
            <div class="note-columns">
              <div class="note-col mine">
                <div class="note-label">Общий комментарий {{ myLabel }}</div>
                <textarea
                  class="note-area"
                  :value="myNotes['comp_comment_general'] || ''"
                  placeholder="Общее впечатление, замечания…"
                  @input="onInput('comp_comment_general', $event.target.value)"
                />
              </div>
              <div class="note-col other" v-if="otherLabel">
                <div class="note-label other-lbl">{{ otherLabel }}</div>
                <div class="note-area readonly">
                  {{ otherNotes['comp_comment_general'] || '' }}
                  <span v-if="!otherNotes['comp_comment_general']" class="placeholder">Пусто…</span>
                </div>
              </div>
            </div>
          </div>

          <div class="comp-totals">
            <div class="comp-total-mine">
              Мой итог: <b>{{ myTotal }}</b> / {{ maxTotal }}
            </div>
            <div class="comp-total-other" v-if="otherLabel">
              {{ otherLabel }}: <b>{{ otherTotal }}</b> / {{ maxTotal }}
            </div>
          </div>
        </div>

        <div class="bottom-save">
          <button class="save-btn-big" :disabled="saving" @click="saveAll">
            {{ saving ? 'Сохраняю…' : '✓ Сохранить итоги собеседования' }}
          </button>
          <span v-if="savedMsg" class="saved-msg">{{ savedMsg }}</span>
        </div>
      </div>

      <!-- Right: fun panel -->
      <aside class="fun-panel" :class="{ collapsed: !panelOpen }">
        <button class="panel-toggle" @click="panelOpen = !panelOpen" :title="panelOpen ? 'Свернуть' : 'Развернуть'">
          {{ panelOpen ? '›' : '‹' }}
        </button>

        <template v-if="panelOpen">
          <div class="panel-tabs">
            <button
              v-for="tab in TABS"
              :key="tab.key"
              class="ptab"
              :class="{ active: funTab === tab.key }"
              @click="funTab = tab.key"
            >{{ tab.label }}</button>
          </div>

          <!-- ── ЭМОДЗИ ───────────────────────────────── -->
          <div v-if="funTab === 'emoji'" class="tab-content">
            <div class="emoji-grid">
              <button
                v-for="e in EMOJI_LIST"
                :key="e"
                class="emoji-btn"
                @click="sendEmoji(e)"
              >{{ e }}</button>
            </div>
            <div class="emoji-feed">
              <TransitionGroup name="emoji-pop">
                <div
                  v-for="item in receivedEmojis"
                  :key="item.id"
                  class="emoji-received"
                >
                  <span class="emoji-big">{{ item.emoji }}</span>
                  <span class="emoji-from">от {{ item.from_name }}</span>
                </div>
              </TransitionGroup>
              <div v-if="!receivedEmojis.length" class="feed-empty">Пусто пока…</div>
            </div>
          </div>

          <!-- ── КРЕСТИКИ-НОЛИКИ ─────────────────────── -->
          <div v-if="funTab === 'ttt'" class="tab-content ttt-tab">
            <div class="ttt-status">
              <template v-if="ttt.winner">
                <span v-if="ttt.winner === 'draw'" class="ttt-result draw">Ничья!</span>
                <span v-else-if="ttt.winner === mySymbol" class="ttt-result win">Победа! 🎉</span>
                <span v-else class="ttt-result lose">Проиграл 😔</span>
              </template>
              <template v-else>
                <span class="ttt-turn" :class="{ 'my-turn': isMyTurn }">
                  {{ isMyTurn ? 'Твой ход (' + mySymbol + ')' : 'Ход соперника…' }}
                </span>
              </template>
            </div>
            <div class="ttt-board">
              <button
                v-for="(cell, i) in ttt.board"
                :key="i"
                class="ttt-cell"
                :class="{ 'cell-x': cell === 'X', 'cell-o': cell === 'O', 'cell-clickable': !cell && !ttt.winner && isMyTurn }"
                :disabled="!!cell || !!ttt.winner || !isMyTurn"
                @click="tttMove(i)"
              >{{ cell }}</button>
            </div>
            <button class="ttt-reset-btn" @click="tttReset">Новая игра</button>
          </div>

          <!-- ── ЧАТ ────────────────────────────────────── -->
          <div v-if="funTab === 'chat'" class="tab-content chat-tab">
            <div class="chat-messages" ref="chatEl">
              <div v-if="!chatMessages.length" class="feed-empty">Напишите первым…</div>
              <div
                v-for="msg in chatMessages"
                :key="msg.id"
                class="chat-msg"
                :class="{ mine: msg.user_id === myId }"
              >
                <div class="chat-meta">
                  <span class="chat-name">{{ msg.user_id === myId ? 'Я' : msg.name }}</span>
                  <span class="chat-time">{{ chatTime(msg.ts) }}</span>
                </div>
                <div class="chat-bubble">{{ msg.text }}</div>
              </div>
            </div>
            <div class="chat-input-row">
              <input
                v-model="chatInput"
                class="chat-input"
                placeholder="Сообщение…"
                maxlength="300"
                @keydown.enter.prevent="sendChat"
              />
              <button class="chat-send-btn" @click="sendChat" :disabled="!chatInput.trim()">↑</button>
            </div>
          </div>

          <!-- ── РАКЕТКА ──────────────────────────────── -->
          <div v-if="funTab === 'rocket'" class="tab-content rocket-tab">
            <!-- IDLE -->
            <template v-if="rocket.status === 'idle'">
              <div class="rocket-idle">
                <div class="rocket-emoji-big">🚀</div>
                <div class="rocket-idle-text">Запусти ракету!</div>
                <button class="rocket-start-btn" @click="startRocket">Старт!</button>
              </div>
            </template>

            <!-- FLYING -->
            <template v-else-if="rocket.status === 'flying'">
              <div class="rocket-flying">
                <div class="rocket-anim">🚀</div>
                <div
                  class="rocket-mult"
                  :class="{
                    'mult-green':  parseFloat(rocketDisplay) < 2,
                    'mult-yellow': parseFloat(rocketDisplay) >= 2 && parseFloat(rocketDisplay) < 4,
                    'mult-red':    parseFloat(rocketDisplay) >= 4,
                  }"
                >{{ rocketDisplay }}×</div>

                <!-- Cashout status -->
                <div class="cashouts">
                  <div
                    v-for="(mult, uid) in rocket.cashouts"
                    :key="uid"
                    class="cashout-chip"
                  >💰 {{ getReviewerName(uid) }}: {{ mult }}×</div>
                </div>

                <button
                  v-if="!myCashout"
                  class="cashout-btn"
                  :disabled="cashingOut"
                  @click="cashout"
                >{{ cashingOut ? '…' : 'ЗАБРАТЬ ' + rocketDisplay + '×!' }}</button>
                <div v-else class="cashed-out-msg">
                  ✅ Ты забрал {{ myCashout }}× — ждём остальных…
                </div>
              </div>
            </template>

            <!-- CRASHED -->
            <template v-else-if="rocket.status === 'crashed'">
              <div class="rocket-crashed">
                <div class="crash-emoji">💥</div>
                <div class="crash-mult">{{ rocket.crash_mult }}×</div>
                <div class="crash-results">
                  <div
                    v-for="(mult, uid) in rocket.cashouts"
                    :key="uid"
                    class="result-row win"
                  >
                    ✅ {{ getReviewerName(uid) }} забрал {{ mult }}×
                  </div>
                  <div
                    v-for="name in missedNames"
                    :key="name"
                    class="result-row lose"
                  >
                    💀 {{ name }} не успел
                  </div>
                </div>
                <button class="rocket-start-btn small" @click="resetRocket">Ещё раз!</button>
              </div>
            </template>
          </div>
        </template>
      </aside>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const route = useRoute()
const rowNumber = Number(route.params.rowNumber)

// ── Form state ────────────────────────────────────────────────────────────
const loading = ref(true)
const saving = ref(false)
const savedMsg = ref('')
const syncStatus = ref('')

const info = ref({ fio: '', my_slot: null, reviewer1: null, reviewer2: null })
const sections = ref([])
const context = ref({ anketa: null, homework: null })
const myNotes = reactive({})
const otherNotes = reactive({})
const mySlot = ref(null)
const myId = ref(null)

const saveTimers = {}
let notesPollTimer = null

const myLabel = computed(() => {
  if (!mySlot.value) return 'Заметки'
  const r = mySlot.value === 1 ? info.value.reviewer1 : info.value.reviewer2
  return r?.name ? `${r.name} (я)` : 'Мои заметки'
})
const otherLabel = computed(() => {
  if (!mySlot.value) return null
  const r = mySlot.value === 1 ? info.value.reviewer2 : info.value.reviewer1
  return r?.name || `Проверяющий ${mySlot.value === 1 ? 2 : 1}`
})

const myTotal = computed(() =>
  COMPETENCIES.reduce((sum, c) => {
    const v = parseInt(myNotes['comp_score_' + c.key])
    return sum + (isNaN(v) ? 0 : v)
  }, 0)
)
const otherTotal = computed(() =>
  COMPETENCIES.reduce((sum, c) => {
    const v = parseInt(otherNotes['comp_score_' + c.key])
    return sum + (isNaN(v) ? 0 : v)
  }, 0)
)
const maxTotal = computed(() =>
  COMPETENCIES.reduce((sum, c) => sum + Math.max(...c.scores), 0)
)
const scoredCount = computed(() =>
  COMPETENCIES.filter(c => myNotes['comp_score_' + c.key] !== undefined && myNotes['comp_score_' + c.key] !== '').length
)

function setScore(key, value) {
  const noteKey = 'comp_score_' + key
  const cur = myNotes[noteKey]
  const newVal = (cur !== undefined && String(cur) === String(value)) ? '' : String(value)
  myNotes[noteKey] = newVal
  syncStatus.value = 'saving'
  clearTimeout(saveTimers[noteKey])
  saveTimers[noteKey] = setTimeout(() => autosave(noteKey, newVal), 800)
}

function stripCasePrefix(text) {
  return text.replace(/^КЕЙС\s*\n\n?/, '')
}

// Свёрнутые/развёрнутые collapsible-скрипты по ключу секции+индекса
const scriptOpen = reactive({})
function toggleScript(key) {
  scriptOpen[key] = !scriptOpen[key]
}

function tgLink(handle) {
  const clean = handle.replace(/^@/, '')
  return `https://t.me/${clean}`
}

const priorCoordClass = computed(() => {
  const v = (info.value?.prior_coord || '').toLowerCase()
  if (/^да\b/.test(v)) return 'yes'
  if (/^нет\b/.test(v)) return 'no'
  return ''
})

// Превращает текст в массив сегментов {text, bold}.
// Bold-им многословные комменты в скобках («не задаём тем, кто подаётся 2-й раз»),
// но НЕ короткие: «(-а)», «(пауза)», «(?)» и т.п.
function markBold(text) {
  if (!text) return [{ text: '', bold: false }]
  const out = []
  // (≥4 символов И содержит пробел) — фактически «фраза в скобках»
  const re = /\((?=[^()]*\s)[^()]{4,}\)/g
  let last = 0
  let m
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push({ text: text.slice(last, m.index), bold: false })
    out.push({ text: m[0], bold: true })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push({ text: text.slice(last), bold: false })
  return out.length ? out : [{ text, bold: false }]
}

function onInput(fieldKey, value) {
  myNotes[fieldKey] = value
  syncStatus.value = 'saving'
  clearTimeout(saveTimers[fieldKey])
  saveTimers[fieldKey] = setTimeout(() => autosave(fieldKey, value), 800)
}

async function autosave(fieldKey, value) {
  try {
    await api.post(`/interview/${rowNumber}/note`, { field_key: fieldKey, value })
    syncStatus.value = 'saved'
    setTimeout(() => { if (syncStatus.value === 'saved') syncStatus.value = '' }, 2000)
  } catch {
    syncStatus.value = 'error'
  }
}

async function pollNotes() {
  try {
    const { data } = await api.get(`/interview/${rowNumber}/notes`)
    const otherKey = mySlot.value === 1 ? 'reviewer2' : 'reviewer1'
    const incoming = data[otherKey]?.notes || {}
    Object.keys(incoming).forEach(k => { otherNotes[k] = incoming[k] })
    Object.keys(otherNotes).forEach(k => { if (!(k in incoming)) delete otherNotes[k] })
  } catch { /* silent */ }
}

async function saveAll() {
  saving.value = true
  savedMsg.value = ''
  try {
    const { data } = await api.post(`/interview/${rowNumber}/save`)
    savedMsg.value = `Сохранено ${data.saved_fields} полей`
    setTimeout(() => { savedMsg.value = '' }, 3000)
  } catch {
    savedMsg.value = 'Ошибка сохранения'
  } finally {
    saving.value = false
  }
}

// ── Fun panel ─────────────────────────────────────────────────────────────
const COMPETENCIES = [
  { key: 'efcom',      label: 'Эфком',                       scores: [0,1,2,3] },
  { key: 'timemgmt',   label: 'Тайм-менеджмент',             scores: [0,1,2,3] },
  { key: 'public',     label: 'Публичка',                    scores: [0,1,2,3] },
  { key: 'emoint',     label: 'Эм. интеллект + эмпатия',    scores: [0,1,2,3] },
  { key: 'project',    label: 'Понимание проекта',           scores: [0,1,3]   },
  { key: 'initiative', label: 'Инициативность',              scores: [0,2,3]   },
  { key: 'stress',     label: 'Стрессоустойчивость',         scores: [0,1,2,3] },
  { key: 'critical',   label: 'Критическое мышление',        scores: [0,1,2,3] },
  { key: 'teamwork',   label: 'Работа в команде',            scores: [0,1,2,3] },
  { key: 'creative',   label: 'Креативное мышление',         scores: [0,1,2,3] },
  { key: 'commun',     label: 'Коммуникабельность',          scores: [0,1,2,3] },
  { key: 'deviant',    label: 'Девиантность',                scores: [0,3]     },
  { key: 'interest',   label: 'Заинтересованность',          scores: [0,2,3]   },
]

const TABS = [
  { key: 'emoji',  label: '😂' },
  { key: 'ttt',    label: '❌' },
  { key: 'rocket', label: '🚀' },
  { key: 'chat',   label: '💬' },
]
const EMOJI_LIST = ['😂', '🔥', '👍', '🤦', '🤔', '💀', '👏', '😈']

const panelOpen = ref(true)
const funTab = ref('emoji')

// Emoji
const receivedEmojis = ref([])

// Tic-tac-toe
const ttt = ref({ board: Array(9).fill(''), turn: 'X', winner: null })
const mySymbol = computed(() => mySlot.value === 1 ? 'X' : mySlot.value === 2 ? 'O' : null)
const isMyTurn = computed(() => !ttt.value.winner && ttt.value.turn === mySymbol.value)

// Rocket
const rocket = ref({ status: 'idle' })
const rocketDisplay = ref('1.00')
const rocketStartedAt = ref(0)
const cashingOut = ref(false)
let rafId = null

// Chat
const chatMessages = ref([])
const chatInput = ref('')
const chatEl = ref(null)

let funPollTimer = null

const myCashout = computed(() => {
  if (!myId.value || !rocket.value.cashouts) return null
  return rocket.value.cashouts[String(myId.value)] ?? null
})

const missedNames = computed(() => {
  if (rocket.value.status !== 'crashed') return []
  const cashedIds = Object.keys(rocket.value.cashouts || {}).map(Number)
  const allReviewers = [info.value.reviewer1, info.value.reviewer2].filter(Boolean)
  return allReviewers
    .filter(r => r?.id && !cashedIds.includes(r.id))
    .map(r => r.name)
})

function getReviewerName(uid) {
  const id = Number(uid)
  if (info.value.reviewer1?.id === id) return info.value.reviewer1.name
  if (info.value.reviewer2?.id === id) return info.value.reviewer2.name
  return `#${uid}`
}

function animateRocket() {
  if (rocket.value.status !== 'flying') { cancelAnimationFrame(rafId); return }
  const elapsed = (Date.now() - rocketStartedAt.value) / 1000
  rocketDisplay.value = Math.exp(elapsed * 0.1).toFixed(2)
  rafId = requestAnimationFrame(animateRocket)
}

async function pollFun() {
  try {
    const { data } = await api.get(`/interview/${rowNumber}/fun`)

    // Always keep myId in sync
    if (data.my_id) myId.value = data.my_id

    // Emojis
    if (data.emojis?.length) {
      data.emojis.forEach(e => {
        const id = Date.now() + Math.random()
        receivedEmojis.value.push({ ...e, id })
        setTimeout(() => {
          receivedEmojis.value = receivedEmojis.value.filter(x => x.id !== id)
        }, 4000)
      })
    }

    // TTT
    if (data.ttt) ttt.value = data.ttt

    // Chat
    if (data.chat) chatMessages.value = data.chat

    // Rocket
    const prev = rocket.value.status
    rocket.value = data.rocket
    if (data.rocket.status === 'flying') {
      if (prev !== 'flying') {
        rocketStartedAt.value = data.rocket.started_at_ms
        cancelAnimationFrame(rafId)
        rafId = requestAnimationFrame(animateRocket)
      }
    } else {
      cancelAnimationFrame(rafId)
      if (data.rocket.status === 'crashed') {
        rocketDisplay.value = String(data.rocket.crash_mult ?? '💥')
      } else {
        rocketDisplay.value = '1.00'
      }
    }
  } catch { /* silent */ }
}

async function sendEmoji(emoji) {
  try { await api.post(`/interview/${rowNumber}/fun/emoji`, { emoji }) } catch {}
}

async function tttMove(cell) {
  try {
    const { data } = await api.post(`/interview/${rowNumber}/fun/ttt/move`, { cell })
    if (data.ok) ttt.value = data.state
    else await pollFun()
  } catch {}
}

async function tttReset() {
  try {
    const { data } = await api.post(`/interview/${rowNumber}/fun/ttt/reset`)
    if (data.ok) ttt.value = data.state
  } catch {}
}

async function startRocket() {
  const { data } = await api.post(`/interview/${rowNumber}/fun/rocket/start`)
  if (data.ok) {
    rocket.value = { status: 'flying', cashouts: {} }
    rocketStartedAt.value = Date.now()
    rocketDisplay.value = '1.00'
    cancelAnimationFrame(rafId)
    rafId = requestAnimationFrame(animateRocket)
  }
}

async function cashout() {
  if (cashingOut.value || myCashout.value) return
  cashingOut.value = true
  const mult = parseFloat(rocketDisplay.value)
  try {
    const { data } = await api.post(`/interview/${rowNumber}/fun/rocket/cashout`, { multiplier: mult })
    if (data.ok) {
      if (!rocket.value.cashouts) rocket.value.cashouts = {}
      rocket.value.cashouts[String(myId.value)] = data.multiplier
    }
    // Sync state regardless of outcome (may have crashed)
    await pollFun()
  } catch {
    await pollFun()
  } finally {
    cashingOut.value = false
  }
}

async function sendChat() {
  const text = chatInput.value.trim()
  if (!text) return
  chatInput.value = ''
  try {
    await api.post(`/interview/${rowNumber}/fun/chat`, { text })
    await pollFun()
  } catch {}
}

function chatTime(ts) {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })
}

watch(chatMessages, async () => {
  if (funTab.value !== 'chat') return
  await nextTick()
  if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
})

watch(funTab, async (tab) => {
  if (tab !== 'chat') return
  await nextTick()
  if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
})

async function resetRocket() {
  await api.post(`/interview/${rowNumber}/fun/rocket/reset`)
  cancelAnimationFrame(rafId)
  rocket.value = { status: 'idle' }
  rocketDisplay.value = '1.00'
}

// ── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const [formResp, infoResp, notesResp, ctxResp] = await Promise.all([
      api.get('/interview/form'),
      api.get(`/interview/${rowNumber}/info`),
      api.get(`/interview/${rowNumber}/notes`),
      api.get(`/interview/${rowNumber}/context`).catch(() => ({ data: { anketa: null, homework: null } })),
    ])
    sections.value = formResp.data.sections
    info.value = infoResp.data
    context.value = ctxResp.data
    mySlot.value = infoResp.data.my_slot

    const myKey = `reviewer${mySlot.value}`
    const otherKey = mySlot.value === 1 ? 'reviewer2' : 'reviewer1'
    Object.assign(myNotes, notesResp.data[myKey]?.notes || {})
    Object.assign(otherNotes, notesResp.data[otherKey]?.notes || {})
  } finally {
    loading.value = false
  }

  // Отдельно получаем my_id из /fun
  try {
    const { data } = await api.get(`/interview/${rowNumber}/fun`)
    myId.value = data.my_id
  } catch {}

  notesPollTimer = setInterval(pollNotes, 3000)
  funPollTimer   = setInterval(pollFun, 2000)
})

onUnmounted(() => {
  clearInterval(notesPollTimer)
  clearInterval(funPollTimer)
  cancelAnimationFrame(rafId)
  Object.values(saveTimers).forEach(t => clearTimeout(t))
})
</script>

<style scoped>
/* ── Header ─────────────────────────────────────────────────────────────── */
.form-header {
  display: flex; align-items: center; gap: 1rem;
  margin-bottom: 1.25rem;
  background: white; border-radius: 12px;
  padding: 0.85rem 1.25rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  flex-wrap: wrap;
}
.back-btn {
  background: none; border: 1.5px solid #e0e0e0; border-radius: 7px;
  padding: 0.4rem 0.75rem; font-size: 0.82rem; cursor: pointer; color: #555;
}
.back-btn:hover { border-color: #4361ee; color: #4361ee; }
.header-info { flex: 1; min-width: 0; }
.candidate-name { font-weight: 700; font-size: 1.1rem; color: #1a1a2e; display: block; }
.candidate-meta {
  display: flex; flex-wrap: wrap; gap: 0.4rem;
  margin-top: 0.35rem;
}
.meta-chip {
  display: inline-flex; align-items: center; gap: 0.3rem;
  padding: 0.18rem 0.55rem;
  border-radius: 6px;
  font-size: 0.78rem;
  background: #f3f4f8;
  color: #555;
}
.meta-chip b { color: #1a1a2e; font-weight: 700; }
.meta-chip .meta-label { color: #888; font-weight: 500; }
.meta-chip.prior.yes { background: rgba(67,97,238,0.12); color: #4361ee; }
.meta-chip.prior.yes b { color: #4361ee; }
.meta-chip.prior.no  { background: rgba(107,114,128,0.1); color: #6b7280; }
.meta-chip.pkg { background: rgba(6,160,122,0.1); color: #058c6b; }
.meta-chip.pkg b { color: #058c6b; }
.meta-chip.fac-chip { background: rgba(67,97,238,0.1); color: #4361ee; font-weight: 700; }
.meta-chip.tg-chip { background: rgba(0,136,204,0.1); color: #0088cc; text-decoration: none; }
.meta-chip.tg-chip:hover { background: rgba(0,136,204,0.18); }
.meta-chip.tg-chip b { color: #0088cc; }
.multi-hw {
  margin-left: 0.3rem;
  padding: 0.05rem 0.4rem;
  background: rgba(255,190,11,0.25);
  color: #92400e;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
}
.reviewers-line { display: flex; align-items: center; gap: 0.35rem; margin-top: 0.4rem; }
.rev-chip { padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 500; }
.rev-chip.r1 { background: rgba(67,97,238,0.08); color: #4361ee; }
.rev-chip.r2 { background: rgba(6,160,122,0.08); color: #06a07a; }
.rev-chip.me { font-weight: 700; }
.rev-sep { color: #ccc; font-size: 0.75rem; }
.header-actions { display: flex; align-items: center; gap: 0.75rem; }
.sync-dot { font-size: 0.78rem; white-space: nowrap; }
.sync-dot.saving { color: #e08c00; }
.sync-dot.saved  { color: #06a07a; }
.sync-dot.error  { color: #e63946; }
.save-btn {
  padding: 0.45rem 1rem; background: #4361ee; color: white;
  border: none; border-radius: 8px; font-size: 0.82rem; font-weight: 600;
  cursor: pointer; white-space: nowrap; transition: background 0.15s;
}
.save-btn:hover:not(:disabled) { background: #3451d1; }
.save-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* ── Layout ─────────────────────────────────────────────────────────────── */
.form-layout { display: flex; gap: 1rem; align-items: flex-start; }
.form-scroll { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.75rem; }

/* ── Sections & Items ───────────────────────────────────────────────────── */
.section-block { background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); overflow: hidden; }
.section-header { padding: 0.65rem 1.25rem; font-weight: 700; font-size: 0.85rem; letter-spacing: 0.02em; text-transform: uppercase; background: #4361ee; color: white; }
.sec-intro            { background: #4361ee; }
.sec-project_understanding { background: #7b2d8b; }
.sec-motivation       { background: #6941c6; }
.sec-cases_intro      { background: #6b7280; }
.sec-team_work        { background: #067a5f; }
.sec-efcom            { background: #0e7490; }
.sec-critical_thinking{ background: #b45309; }
.sec-stress_resistance{ background: #b91c1c; }
.sec-public_speaking  { background: #be185d; }
.sec-time_mgmt        { background: #0369a1; }
.sec-initiative       { background: #4d7c0f; }
.sec-emotional_intelligence { background: #9f1239; }
.sec-openness         { background: #6d28d9; }
.sec-anketa_questions { background: #1d4ed8; }
.sec-hw_questions     { background: #1d4ed8; }
.sec-mandatory        { background: #374151; }
.sec-mandatory_info   { background: #374151; }
.sec-creative_thinking{ background: #92400e; }
.sec-outro            { background: #374151; }

.form-item { padding: 0.85rem 1.25rem; border-bottom: 1px solid #f5f5f5; min-width: 0; }
.form-item:last-child { border-bottom: none; }
.script-text {
  font-size: 0.88rem; color: #444;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.6;
  background: #fafbfc;
  border-radius: 8px;
  padding: 0.85rem 1.05rem;
  border-left: 3px solid #c0c8d4;
  max-width: 100%;
}
.sub-label {
  font-size: 0.9rem; font-weight: 700; color: #4361ee;
  background: rgba(67,97,238,0.07);
  border-left: 3px solid #4361ee;
  border-radius: 6px;
  padding: 0.5rem 0.85rem;
  margin: 0.25rem 0;
  line-height: 1.4;
}
.question-text {
  font-size: 0.95rem; color: #1a1a2e; font-weight: 500;
  margin-bottom: 0.75rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.5;
}
.question-text .bold,
.script-text .bold {
  font-weight: 700;
  color: #4361ee;
}

/* Context (анкета / ДЗ — подтянутые ответы кандидата) */
.context-item { background: linear-gradient(180deg, #fafbfc 0%, white 100%); }
.context-empty { color: #aaa; font-style: italic; font-size: 0.9rem; }
.context-q {
  font-size: 0.78rem; font-weight: 600;
  color: #4361ee; text-transform: uppercase; letter-spacing: 0.03em;
  margin-bottom: 0.35rem;
}
.context-a {
  background: white;
  border: 1px solid #e8eaf0;
  border-left: 3px solid #4361ee;
  border-radius: 7px;
  padding: 0.7rem 0.85rem;
  color: #1f2937;
  font-size: 0.92rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin-bottom: 0.75rem;
}
.alt-pill {
  display: inline-block;
  margin-left: 0.6rem;
  padding: 0.1rem 0.5rem;
  background: rgba(255,255,255,0.25);
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 600;
}
.hw-link-row { margin-bottom: 0.85rem; }
.hw-link-btn {
  display: inline-flex; align-items: center; gap: 0.4rem;
  padding: 0.55rem 1rem;
  background: rgba(6,160,122,0.1);
  color: #058c6b;
  border: 1.5px solid rgba(6,160,122,0.3);
  border-radius: 9px;
  font-size: 0.9rem;
  font-weight: 600;
  text-decoration: none;
  transition: background 0.12s;
}
.hw-link-btn:hover { background: rgba(6,160,122,0.18); border-color: #06a07a; }
.alt-list {
  background: rgba(255,190,11,0.08);
  border: 1px dashed rgba(255,190,11,0.35);
  border-radius: 8px;
  padding: 0.5rem 0.85rem;
  margin-bottom: 0.85rem;
  font-size: 0.85rem;
}
.alt-list-title { font-weight: 600; color: #92400e; margin-bottom: 0.25rem; }
.alt-item { display: flex; gap: 0.5rem; align-items: center; padding: 0.15rem 0; }
.alt-pkg { color: #555; }
.alt-link { color: #4361ee; }
.prior-block {
  margin-top: 0.85rem;
  padding: 0.65rem 0.85rem;
  background: #f7f8fc;
  border-radius: 7px;
  border-left: 3px solid #c0c8d4;
}
.prior-title { font-size: 0.78rem; font-weight: 700; color: #555; margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.04em; }
.prior-card { background: white; border-radius: 5px; padding: 0.45rem 0.65rem; margin-bottom: 0.35rem; font-size: 0.83rem; }
.prior-name { font-weight: 700; color: #4361ee; margin-bottom: 0.2rem; font-size: 0.78rem; }
.prior-row { color: #4b5563; line-height: 1.4; margin: 0.15rem 0; }
.prior-k { color: #888; font-weight: 600; }

.script-collapsible { margin: 0.25rem 0; }
.script-toggle {
  background: none;
  border: 1.5px dashed #c0c8d4;
  color: #4361ee;
  border-radius: 8px;
  padding: 0.4rem 0.85rem;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 0.5rem;
  transition: background 0.12s, border-color 0.12s;
}
.script-toggle:hover { background: rgba(67,97,238,0.06); border-color: #4361ee; }
.script-toggle .toggle-icon { display: inline-block; margin-right: 0.35rem; font-size: 0.85rem; }
.question-text.is-case { background: rgba(180,83,9,0.05); border-left: 3px solid #b45309; padding: 0.5rem 0.75rem; border-radius: 4px; }
.case-badge { display: inline-block; background: #b45309; color: white; font-size: 0.65rem; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 3px; margin-right: 0.4rem; vertical-align: middle; }

.note-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
.note-label { font-size: 0.7rem; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 0.3rem; }
.note-label.other-lbl { color: #06a07a; }
.note-area { width: 100%; min-height: 72px; padding: 0.5rem 0.65rem; border: 1.5px solid #e0e0e0; border-radius: 7px; font-size: 0.85rem; font-family: inherit; resize: vertical; outline: none; box-sizing: border-box; transition: border-color 0.15s; color: #333; }
.note-area:focus { border-color: #4361ee; }
.note-area.readonly { background: #f8fffe; border-color: rgba(6,160,122,0.25); white-space: pre-wrap; word-break: break-word; line-height: 1.5; overflow-y: auto; display: block; }
.placeholder { color: #ccc; font-style: italic; }

.bottom-save { display: flex; align-items: center; gap: 1rem; padding: 1rem 0; }
.save-btn-big { padding: 0.7rem 1.8rem; background: #06a07a; color: white; border: none; border-radius: 10px; font-size: 0.9rem; font-weight: 700; cursor: pointer; transition: background 0.15s; }
.save-btn-big:hover:not(:disabled) { background: #058c6b; }
.save-btn-big:disabled { opacity: 0.6; cursor: not-allowed; }
.saved-msg { font-size: 0.85rem; color: #06a07a; }

/* ── Fun panel ───────────────────────────────────────────────────────────── */
.fun-panel {
  width: 260px; flex-shrink: 0;
  align-self: flex-start;
  background: white; border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  position: sticky; top: 0;
  max-height: 100vh;
  transition: width 0.2s;
  overflow: hidden;
  display: flex; flex-direction: column;
}
.fun-panel.collapsed { width: 36px; }

.panel-toggle {
  position: absolute; right: 0; top: 50%;
  transform: translateY(-50%);
  width: 36px; height: 36px;
  background: #f0f2f5; border: none;
  cursor: pointer; font-size: 1rem; color: #555;
  display: flex; align-items: center; justify-content: center;
  border-radius: 0 12px 12px 0;
  z-index: 1;
}
.fun-panel.collapsed .panel-toggle { border-radius: 12px; position: static; transform: none; height: 100%; width: 100%; min-height: 200px; background: #f0f2f5; }

.panel-tabs {
  display: flex; border-bottom: 1.5px solid #f0f0f0;
  padding: 0 0.5rem;
  padding-right: 40px; /* space for toggle */
}
.ptab {
  flex: 1; padding: 0.6rem 0; border: none; background: none;
  font-size: 1.1rem; cursor: pointer;
  border-bottom: 2.5px solid transparent;
  transition: border-color 0.15s;
}
.ptab.active { border-bottom-color: #4361ee; }
.ptab:hover { background: #f7f8ff; }

.tab-content { padding: 0.85rem; flex: 1; overflow-y: auto; min-height: 0; max-height: calc(100vh - 60px); }

/* Emoji tab */
.emoji-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.4rem; margin-bottom: 0.75rem; }
.emoji-btn { font-size: 1.5rem; padding: 0.35rem; border: 1.5px solid #f0f0f0; border-radius: 8px; cursor: pointer; background: white; transition: transform 0.1s, background 0.1s; }
.emoji-btn:hover { transform: scale(1.2); background: #f7f8ff; }
.emoji-btn:active { transform: scale(0.9); }

.emoji-feed { min-height: 60px; }
.feed-empty { font-size: 0.75rem; color: #ccc; text-align: center; padding: 1rem 0; }

.emoji-received {
  display: flex; align-items: center; gap: 0.5rem;
  background: #fff7ed; border-radius: 8px;
  padding: 0.4rem 0.6rem; margin-bottom: 0.4rem;
}
.emoji-big { font-size: 1.6rem; }
.emoji-from { font-size: 0.72rem; color: #888; }

.emoji-pop-enter-active { animation: emojiIn 0.3s ease; }
.emoji-pop-leave-active { animation: emojiOut 0.4s ease; }
@keyframes emojiIn  { from { opacity: 0; transform: scale(0.6) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }
@keyframes emojiOut { from { opacity: 1; } to { opacity: 0; transform: translateY(-8px); } }

/* TTT tab */
.ttt-tab { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; }
.ttt-status { font-size: 0.8rem; color: #888; text-align: center; min-height: 1.2rem; }
.ttt-turn { color: #888; }
.ttt-turn.my-turn { color: #4361ee; font-weight: 700; }
.ttt-result { font-weight: 700; font-size: 0.9rem; }
.ttt-result.win  { color: #06a07a; }
.ttt-result.lose { color: #e63946; }
.ttt-result.draw { color: #e08c00; }
.ttt-board {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 6px; width: 180px;
}
.ttt-cell {
  width: 54px; height: 54px;
  border: 2px solid #e0e0e0; border-radius: 10px;
  background: white; font-size: 1.6rem; font-weight: 900;
  cursor: pointer; transition: background 0.1s, border-color 0.1s, transform 0.08s;
  display: flex; align-items: center; justify-content: center;
}
.ttt-cell.cell-clickable:hover { background: #f0f4ff; border-color: #4361ee; }
.ttt-cell.cell-clickable:active { transform: scale(0.92); }
.ttt-cell:disabled { cursor: default; }
.ttt-cell.cell-x { color: #4361ee; border-color: rgba(67,97,238,0.3); }
.ttt-cell.cell-o { color: #06a07a; border-color: rgba(6,160,122,0.3); }
.ttt-reset-btn {
  padding: 0.4rem 1.1rem; background: #f0f2f5; color: #555;
  border: none; border-radius: 8px; font-size: 0.78rem;
  cursor: pointer; transition: background 0.15s;
}
.ttt-reset-btn:hover { background: #e0e3ea; }

/* Rocket tab */
.rocket-tab { display: flex; flex-direction: column; align-items: center; }

.rocket-idle { display: flex; flex-direction: column; align-items: center; gap: 0.6rem; padding: 1rem 0; }
.rocket-emoji-big { font-size: 3rem; }
.rocket-idle-text { font-size: 0.85rem; color: #888; }
.rocket-start-btn {
  padding: 0.6rem 1.4rem; background: #06a07a; color: white; border: none;
  border-radius: 10px; font-size: 0.9rem; font-weight: 700; cursor: pointer;
  transition: background 0.15s, transform 0.1s;
}
.rocket-start-btn:hover { background: #058c6b; }
.rocket-start-btn:active { transform: scale(0.96); }
.rocket-start-btn.small { font-size: 0.8rem; padding: 0.45rem 1rem; }

.rocket-flying { display: flex; flex-direction: column; align-items: center; gap: 0.5rem; width: 100%; }
.rocket-anim { font-size: 2.5rem; animation: rocketBounce 0.6s ease-in-out infinite; }
@keyframes rocketBounce { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }

.rocket-mult { font-size: 2.4rem; font-weight: 900; font-variant-numeric: tabular-nums; transition: color 0.3s; }
.mult-green  { color: #06a07a; }
.mult-yellow { color: #e08c00; }
.mult-red    { color: #e63946; }

.cashouts { display: flex; flex-direction: column; gap: 0.25rem; width: 100%; }
.cashout-chip { font-size: 0.75rem; background: rgba(6,160,122,0.1); color: #06a07a; border-radius: 6px; padding: 0.2rem 0.5rem; text-align: center; }

.cashout-btn {
  margin-top: 0.25rem; width: 100%;
  padding: 0.65rem; background: #e63946; color: white; border: none;
  border-radius: 10px; font-size: 0.9rem; font-weight: 800; cursor: pointer;
  animation: pulseCashout 1s ease-in-out infinite;
  transition: transform 0.08s;
}
.cashout-btn:hover { background: #c0392b; }
.cashout-btn:active { transform: scale(0.96); }
@keyframes pulseCashout { 0%,100% { box-shadow: 0 0 0 0 rgba(230,57,70,0.4); } 50% { box-shadow: 0 0 0 8px rgba(230,57,70,0); } }

.cashed-out-msg { font-size: 0.78rem; color: #06a07a; text-align: center; padding: 0.4rem; }

.rocket-crashed { display: flex; flex-direction: column; align-items: center; gap: 0.5rem; }
.crash-emoji { font-size: 3rem; animation: crashShake 0.5s ease; }
@keyframes crashShake { 0%,100% { transform: rotate(0); } 20% { transform: rotate(-10deg); } 40% { transform: rotate(10deg); } 60% { transform: rotate(-6deg); } 80% { transform: rotate(6deg); } }
.crash-mult { font-size: 2rem; font-weight: 900; color: #e63946; }
.crash-results { display: flex; flex-direction: column; gap: 0.3rem; width: 100%; }
.result-row { font-size: 0.78rem; padding: 0.3rem 0.5rem; border-radius: 6px; text-align: center; }
.result-row.win  { background: rgba(6,160,122,0.1); color: #06a07a; }
.result-row.lose { background: rgba(230,57,70,0.08); color: #e63946; }

/* Chat tab */
.chat-tab { display: flex; flex-direction: column; flex: 1; min-height: 0; padding: 0; }
.chat-messages {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 0.75rem 0.75rem 0.5rem;
  display: flex; flex-direction: column; gap: 0.4rem;
}
.chat-msg { display: flex; flex-direction: column; max-width: 88%; }
.chat-msg.mine { align-self: flex-end; align-items: flex-end; }
.chat-meta { display: flex; gap: 0.35rem; align-items: baseline; margin-bottom: 0.15rem; }
.chat-name { font-size: 0.65rem; font-weight: 700; color: #888; }
.chat-time { font-size: 0.6rem; color: #ccc; }
.chat-bubble {
  background: #f0f2f5; color: #1a1a2e;
  padding: 0.4rem 0.65rem; border-radius: 10px 10px 10px 2px;
  font-size: 0.82rem; line-height: 1.45; word-break: break-word;
}
.chat-msg.mine .chat-bubble {
  background: #4361ee; color: white;
  border-radius: 10px 10px 2px 10px;
}
.chat-input-row {
  display: flex; gap: 0.4rem; padding: 0.6rem 0.75rem;
  border-top: 1.5px solid #f0f0f0;
}
.chat-input {
  flex: 1; padding: 0.45rem 0.65rem;
  border: 1.5px solid #e0e0e0; border-radius: 8px;
  font-size: 0.82rem; outline: none; font-family: inherit;
  transition: border-color 0.15s;
}
.chat-input:focus { border-color: #4361ee; }
.chat-send-btn {
  width: 32px; height: 32px; border-radius: 8px;
  background: #4361ee; color: white; border: none;
  font-size: 1rem; cursor: pointer; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.15s;
}
.chat-send-btn:hover:not(:disabled) { background: #3451d1; }
.chat-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Competency scoring ──────────────────────────────────────────────────── */
.comp-section { margin-top: 0; }

.comp-header {
  background: #1a1a2e !important;
  display: flex; justify-content: space-between; align-items: center;
}
.comp-counter {
  font-size: 0.72rem; font-weight: 500; opacity: 0.65;
}

.comp-list { padding: 0.5rem 0; }

.comp-item {
  padding: 0.7rem 1.25rem;
  border-bottom: 1px solid #f5f5f5;
}
.comp-item:last-child { border-bottom: none; }

.comp-name {
  font-size: 0.78rem; font-weight: 700; color: #374151;
  text-transform: uppercase; letter-spacing: 0.03em;
  margin-bottom: 0.45rem;
}

.comp-score-line { display: flex; align-items: center; gap: 1rem; }
.comp-score-row { display: flex; gap: 0.3rem; flex-wrap: wrap; }

.score-btn {
  min-width: 30px; height: 30px; padding: 0 0.4rem;
  border: 2px solid #e0e0e0; border-radius: 7px;
  background: white; font-size: 0.82rem; font-weight: 700;
  cursor: pointer; color: #555; transition: all 0.12s;
}
.score-btn:hover { border-color: #4361ee; color: #4361ee; background: #f0f4ff; }
.score-btn.score-active { background: #4361ee; border-color: #4361ee; color: white; }
.score-btn.score-active.score-0 { background: #9b9ba8; border-color: #9b9ba8; }
.score-btn.score-active.score-hi { background: #06a07a; border-color: #06a07a; }

.comp-general-comment { padding: 0.85rem 1.25rem; border-top: 1px solid #f0f0f0; }

.other-score-val {
  font-size: 0.78rem; font-weight: 700; color: #ccc;
  min-width: 36px; text-align: center;
}
.other-score-val.score-filled { color: #06a07a; }

.comp-totals {
  display: flex; gap: 2rem; padding: 0.85rem 1.25rem;
  background: #fafafa; border-top: 2px solid #f0f0f0;
  font-size: 0.82rem; color: #555;
}
.comp-total-mine b { color: #4361ee; font-size: 1rem; }
.comp-total-other { color: #06a07a; }
.comp-total-other b { font-size: 1rem; }

.state-msg { background: white; border-radius: 12px; padding: 3rem; text-align: center; font-size: 0.9rem; color: #aaa; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
</style>
