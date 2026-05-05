<template>
  <AppLayout>
    <div class="settings-page">
      <h2>Настройки</h2>

      <div class="card">
        <div class="card-header">
          <div>
            <h3>Telegram-чаты</h3>
            <p class="hint">
              Добавь бота в нужные группы — чаты появятся здесь автоматически.
              Или напиши <b>/chatid</b> в группе, чтобы бот ответил своим ID.
              Потом назначь каждому чату факультеты через «Изменить».
            </p>
          </div>
          <div class="head-btns">
            <button class="btn-refresh" @click="load" :disabled="loading" title="Обновить список">⟳</button>
            <button class="btn-add" @click="openAdd">+ Добавить чат</button>
          </div>
        </div>

        <div v-if="loading" class="state-msg">Загрузка…</div>
        <div v-else-if="chats.length === 0" class="state-msg muted">
          Чаты не настроены
        </div>

        <div v-else class="chat-list">
          <div v-for="chat in chats" :key="chat.id" class="chat-item">
            <div class="chat-main">
              <div class="chat-title">{{ chat.title }}</div>
              <div class="chat-id">{{ chat.chat_id }}</div>
              <div class="fac-tags">
                <span v-if="chat.faculties.length === 0" class="no-fac">Факультеты не выбраны</span>
                <span v-for="f in chat.faculties" :key="f" class="fac-tag">{{ f }}</span>
              </div>
            </div>
            <div class="chat-actions">
              <button class="btn-edit" @click="openEdit(chat)">Изменить</button>
              <button class="btn-delete" @click="deleteChat(chat)">Удалить</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Modal: add / edit -->
      <div v-if="modal" class="modal-overlay" @click.self="modal = null">
        <div class="modal">
          <h3>{{ modal.id ? 'Редактировать чат' : 'Добавить чат' }}</h3>

          <label class="field-label">Chat ID</label>
          <input
            v-model="modal.chat_id"
            class="field-input"
            placeholder="-1001234567890"
            :disabled="!!modal.id"
          />
          <p class="field-hint">Отрицательное число для супергрупп/каналов</p>

          <label class="field-label">Название</label>
          <input v-model="modal.title" class="field-input" placeholder="Чат НАБ и ФЭБ" />

          <label class="field-label">Факультеты</label>
          <div class="fac-grid">
            <label
              v-for="f in FACULTIES"
              :key="f"
              class="fac-check"
              :class="{ selected: modal.faculties.includes(f) }"
            >
              <input type="checkbox" :value="f" v-model="modal.faculties" />
              {{ f }}
            </label>
          </div>

          <div class="modal-actions">
            <button class="btn-cancel" @click="modal = null">Отмена</button>
            <button class="btn-save" :disabled="saving || !modal.chat_id || !modal.title" @click="saveChat">
              {{ saving ? 'Сохранение…' : 'Сохранить' }}
            </button>
          </div>
          <p v-if="saveError" class="save-error">{{ saveError }}</p>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const FACULTIES = ['НАБ', 'ФЭБ', 'ВШУ', 'ИТиАБД', 'СНиМК', 'МЭО', 'Финфак', 'Юрфак']

const chats = ref([])
const loading = ref(true)
const modal = ref(null)
const saving = ref(false)
const saveError = ref('')

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/telegram/chats')
    chats.value = data
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openAdd() {
  modal.value = { chat_id: '', title: '', faculties: [] }
  saveError.value = ''
}

function openEdit(chat) {
  modal.value = { ...chat, faculties: [...(chat.faculties || [])] }
  saveError.value = ''
}

async function saveChat() {
  saving.value = true
  saveError.value = ''
  try {
    await api.post('/telegram/chats', {
      chat_id: modal.value.chat_id,
      title: modal.value.title,
      faculties: modal.value.faculties,
    })
    modal.value = null
    await load()
  } catch (e) {
    saveError.value = e.response?.data?.detail || 'Ошибка сохранения'
  } finally {
    saving.value = false
  }
}

async function deleteChat(chat) {
  if (!confirm(`Удалить чат «${chat.title}»?`)) return
  await api.delete(`/telegram/chats/${chat.id}`)
  await load()
}
</script>

<style scoped>
.settings-page { display: flex; flex-direction: column; gap: 1.5rem; }

h2 { margin: 0; color: #1a1a2e; font-size: 1.4rem; }

.card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 1.5rem;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
}

.card-header h3 { margin: 0 0 0.35rem; color: #1a1a2e; font-size: 1rem; }
.hint { margin: 0; color: #888; font-size: 0.82rem; max-width: 580px; line-height: 1.45; }

.head-btns { display: flex; gap: 0.5rem; flex-shrink: 0; }

.btn-refresh {
  padding: 0.5rem 0.75rem;
  background: white;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 1rem;
  color: #666;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-refresh:hover:not(:disabled) { border-color: #4361ee; color: #4361ee; }
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-add {
  padding: 0.5rem 1.1rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.15s;
}
.btn-add:hover { background: #3451d1; }

.state-msg { color: #aaa; font-size: 0.875rem; padding: 1rem 0; }
.state-msg.muted { font-style: italic; }

.chat-list { display: flex; flex-direction: column; gap: 0.75rem; }

.chat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.1rem;
  border: 1.5px solid #eee;
  border-radius: 10px;
  background: #fafbfc;
  flex-wrap: wrap;
}

.chat-main { flex: 1; min-width: 0; }
.chat-title { font-weight: 600; color: #1a1a2e; font-size: 0.95rem; margin-bottom: 0.15rem; }
.chat-id { font-size: 0.78rem; color: #888; margin-bottom: 0.5rem; font-family: monospace; }

.fac-tags { display: flex; gap: 0.3rem; flex-wrap: wrap; }
.fac-tag {
  background: rgba(67,97,238,0.09);
  color: #4361ee;
  border-radius: 4px;
  padding: 0.1rem 0.45rem;
  font-size: 0.72rem;
  font-weight: 600;
}
.no-fac { color: #bbb; font-size: 0.78rem; font-style: italic; }

.chat-actions { display: flex; gap: 0.5rem; flex-shrink: 0; }

.btn-edit {
  padding: 0.35rem 0.8rem;
  border: 1.5px solid #4361ee;
  color: #4361ee;
  background: white;
  border-radius: 7px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-edit:hover { background: #4361ee; color: white; }

.btn-delete {
  padding: 0.35rem 0.8rem;
  border: 1.5px solid #e63946;
  color: #e63946;
  background: white;
  border-radius: 7px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-delete:hover { background: #e63946; color: white; }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.modal {
  background: white;
  border-radius: 14px;
  padding: 2rem;
  width: 100%;
  max-width: 480px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.15);
}

.modal h3 { margin: 0 0 1.25rem; color: #1a1a2e; font-size: 1rem; }

.field-label {
  display: block;
  font-size: 0.82rem;
  font-weight: 600;
  color: #555;
  margin-bottom: 0.35rem;
  margin-top: 0.85rem;
}
.field-label:first-of-type { margin-top: 0; }

.field-input {
  width: 100%;
  padding: 0.55rem 0.75rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.9rem;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.15s;
}
.field-input:focus { border-color: #4361ee; }
.field-input:disabled { background: #f5f5f5; color: #888; }

.field-hint { margin: 0.3rem 0 0; font-size: 0.75rem; color: #aaa; }

.fac-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(105px, 1fr));
  gap: 0.4rem;
  margin-top: 0.4rem;
}

.fac-check {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.5rem 0.65rem;
  border: 1.5px solid #e8e8e8;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.88rem;
  transition: all 0.12s;
  user-select: none;
}
.fac-check:hover { border-color: #4361ee; }
.fac-check.selected { border-color: #4361ee; background: rgba(67,97,238,0.08); color: #4361ee; font-weight: 600; }
.fac-check input { display: none; }

.modal-actions {
  display: flex;
  gap: 0.65rem;
  justify-content: flex-end;
  margin-top: 1.5rem;
}

.btn-cancel {
  padding: 0.55rem 1.1rem;
  background: white;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.9rem;
  cursor: pointer;
  color: #666;
  transition: all 0.15s;
}
.btn-cancel:hover { border-color: #999; }

.btn-save {
  padding: 0.55rem 1.4rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-save:hover:not(:disabled) { background: #3451d1; }
.btn-save:disabled { opacity: 0.55; cursor: not-allowed; }

.save-error { margin: 0.75rem 0 0; font-size: 0.82rem; color: #e63946; }
</style>
