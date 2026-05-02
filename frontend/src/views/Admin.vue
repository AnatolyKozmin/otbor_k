<template>
  <AppLayout>
    <div class="top-bar">
      <h2>Управление</h2>
      <div class="top-actions">
        <button class="action-btn distribute-btn" :disabled="distributing" @click="distribute">
          <span v-if="distributing">Распределяю…</span>
          <span v-else>Распределить анкеты</span>
        </button>
        <button class="action-btn load-btn" :disabled="loading" @click="loadSheets">
          <span v-if="loading">Загрузка…</span>
          <span v-else>Загрузить из Google Sheets</span>
        </button>
      </div>
    </div>

    <div v-if="loadResult" class="load-result" :class="loadResult.ok ? 'ok' : 'err'">
      {{ loadResult.message }}
    </div>

    <!-- Результат распределения -->
    <div v-if="distResult" class="dist-result" :class="distResult.ok ? 'ok' : 'err'">
      <template v-if="distResult.ok">
        <div class="dist-summary">
          Распределено <strong>{{ distResult.assigned }}</strong> анкет
          <template v-if="distResult.unassigned">
            · без назначения: <strong>{{ distResult.unassigned }}</strong>
            ({{ Object.entries(distResult.unassigned_faculties).map(([f,n]) => `${f}: ${n}`).join(', ') }})
          </template>
        </div>
        <div class="dist-table">
          <div v-for="(cnt, name) in distResult.distribution" :key="name" class="dist-row">
            <span class="dist-name">{{ name }}</span>
            <span class="dist-bar-wrap">
              <span class="dist-bar" :style="{ width: barWidth(cnt, distResult.distribution) + '%' }"></span>
            </span>
            <span class="dist-cnt">{{ cnt }}</span>
          </div>
        </div>
      </template>
      <template v-else>{{ distResult.message }}</template>
    </div>

    <div class="card">
      <h3>Добавить пользователя</h3>
      <form class="create-form" @submit.prevent="createUser">
        <input v-model="form.name" placeholder="Имя" required />
        <input v-model="form.email" type="email" placeholder="Email" required />
        <input v-model="form.password" type="password" placeholder="Пароль" required />
        <select v-model="form.role">
          <option value="coordinator">Координатор</option>
          <option value="admin">Админ</option>
        </select>
        <button type="submit" :disabled="creating">
          {{ creating ? 'Создание...' : 'Создать' }}
        </button>
      </form>
      <p v-if="createError" class="error">{{ createError }}</p>
    </div>

    <div class="card">
      <h3>Пользователи</h3>
      <table>
        <thead>
          <tr>
            <th>Имя</th>
            <th>Email</th>
            <th>Роль</th>
            <th>Факультеты</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>{{ u.name }}</td>
            <td class="email-cell">{{ u.email }}</td>
            <td>
              <span class="role-badge" :class="u.role">
                {{ u.role === 'admin' ? 'Админ' : 'Координатор' }}
              </span>
            </td>
            <td>
              <div class="faculties-cell">
                <span v-if="u.faculties?.length" class="fac-tags">
                  <span v-for="f in u.faculties" :key="f" class="fac-tag">{{ f }}</span>
                </span>
                <span v-else class="no-faculties">не выбраны</span>
                <button class="edit-fac-btn" @click="openModal(u)">✏️</button>
              </div>
            </td>
            <td>
              <button
                v-if="u.id !== auth.user.id"
                class="delete-btn"
                @click="deleteUser(u)"
              >
                Удалить
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Faculty modal -->
    <div v-if="modalUser" class="modal-overlay" @click.self="modalUser = null">
      <div class="modal">
        <h3>Факультеты — {{ modalUser.name }}</h3>
        <div class="faculty-grid">
          <label v-for="f in FACULTIES" :key="f" class="fac-check" :class="{ selected: modalFaculties.includes(f) }">
            <input type="checkbox" :value="f" v-model="modalFaculties" />
            {{ f }}
          </label>
        </div>
        <div class="modal-actions">
          <button class="btn-cancel" @click="modalUser = null">Отмена</button>
          <button class="btn-save" @click="saveFaculties" :disabled="saving">
            {{ saving ? 'Сохранение...' : 'Сохранить' }}
          </button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const FACULTIES = ['НАБ', 'ФЭБ', 'ВШУ', 'ИТиАБД', 'СНиМК', 'МЭО', 'Финфак', 'Юрфак']

const auth = useAuthStore()

const users = ref([])
const creating = ref(false)
const createError = ref('')
const form = ref({ name: '', email: '', password: '', role: 'coordinator' })

const modalUser = ref(null)
const modalFaculties = ref([])
const saving = ref(false)

const loading = ref(false)
const loadResult = ref(null)

const distributing = ref(false)
const distResult = ref(null)

async function distribute() {
  distributing.value = true
  distResult.value = null
  try {
    const { data } = await api.post('/admin/distribute', { sheet: 'anketa' })
    distResult.value = { ok: true, ...data }
  } catch (e) {
    distResult.value = { ok: false, message: e.response?.data?.detail || 'Ошибка распределения' }
  } finally {
    distributing.value = false
  }
}

function barWidth(cnt, distribution) {
  const max = Math.max(...Object.values(distribution))
  return max > 0 ? Math.round((cnt / max) * 100) : 0
}

async function loadSheets() {
  loading.value = true
  loadResult.value = null
  try {
    const { data } = await api.post('/sheets/load')
    const parts = Object.entries(data).map(([k, n]) => `${k}: ${n} строк`)
    loadResult.value = { ok: true, message: 'Загружено — ' + parts.join(', ') }
  } catch (e) {
    loadResult.value = { ok: false, message: e.response?.data?.detail || 'Ошибка загрузки' }
  } finally {
    loading.value = false
  }
}

onMounted(fetchUsers)

async function fetchUsers() {
  const { data } = await api.get('/users/')
  users.value = data
}

async function createUser() {
  creating.value = true
  createError.value = ''
  try {
    await api.post('/users/', form.value)
    form.value = { name: '', email: '', password: '', role: 'coordinator' }
    await fetchUsers()
  } catch (e) {
    createError.value = e.response?.data?.detail || 'Ошибка создания'
  } finally {
    creating.value = false
  }
}

async function deleteUser(user) {
  if (!confirm(`Удалить ${user.name}?`)) return
  await api.delete(`/users/${user.id}`)
  await fetchUsers()
}

function openModal(user) {
  modalUser.value = user
  modalFaculties.value = [...(user.faculties || [])]
}

async function saveFaculties() {
  saving.value = true
  try {
    await api.patch(`/users/${modalUser.value.id}/faculties`, { faculties: modalFaculties.value })
    await fetchUsers()
    modalUser.value = null
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
  gap: 0.75rem;
}

h2 { margin: 0; color: #1a1a2e; font-size: 1.4rem; }

.top-actions { display: flex; gap: 0.6rem; flex-wrap: wrap; }

.action-btn {
  padding: 0.6rem 1.25rem;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}
.action-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.load-btn { background: #06d6a0; color: white; }
.load-btn:hover:not(:disabled) { background: #05b889; }

.distribute-btn { background: #4361ee; color: white; }
.distribute-btn:hover:not(:disabled) { background: #3451d1; }

.load-result {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.875rem;
  margin-bottom: 1.25rem;
}
.load-result.ok { background: rgba(6, 214, 160, 0.12); color: #05a87c; }
.load-result.err { background: rgba(230, 57, 70, 0.1); color: #e63946; }

/* Результат распределения */
.dist-result {
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}
.dist-result.ok  { background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.dist-result.err { background: rgba(230, 57, 70, 0.08); color: #e63946; font-size: 0.875rem; }

.dist-summary {
  font-size: 0.9rem;
  color: #333;
  margin-bottom: 1rem;
}

.dist-table { display: flex; flex-direction: column; gap: 0.4rem; }

.dist-row {
  display: grid;
  grid-template-columns: 200px 1fr 40px;
  align-items: center;
  gap: 0.75rem;
}

.dist-name { font-size: 0.82rem; color: #444; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.dist-bar-wrap {
  height: 8px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}

.dist-bar {
  display: block;
  height: 100%;
  background: #4361ee;
  border-radius: 4px;
  transition: width 0.4s ease;
}

.dist-cnt { font-size: 0.8rem; font-weight: 700; color: #4361ee; text-align: right; }

.card {
  background: white;
  padding: 1.5rem;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  margin-bottom: 1.5rem;
}

h3 { margin: 0 0 1rem; color: #1a1a2e; font-size: 1rem; }

.create-form {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: center;
}

.create-form input,
.create-form select {
  padding: 0.6rem 0.75rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.875rem;
  flex: 1;
  min-width: 130px;
  outline: none;
  transition: border-color 0.15s;
}

.create-form input:focus,
.create-form select:focus { border-color: #4361ee; }

.create-form button {
  padding: 0.6rem 1.25rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.create-form button:hover:not(:disabled) { background: #3451d1; }
.create-form button:disabled { opacity: 0.6; cursor: not-allowed; }

.error { color: #e63946; font-size: 0.85rem; margin: 0.75rem 0 0; }

table { width: 100%; border-collapse: collapse; }

th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  font-size: 0.78rem;
  color: #888;
  font-weight: 600;
  border-bottom: 1px solid #f0f0f0;
}

td {
  padding: 0.6rem 0.75rem;
  font-size: 0.875rem;
  color: #333;
  border-bottom: 1px solid #f9f9f9;
  vertical-align: middle;
}

.email-cell { color: #666; font-size: 0.82rem; }

.role-badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 20px;
  font-size: 0.72rem;
  font-weight: 600;
}

.role-badge.admin { background: rgba(67, 97, 238, 0.12); color: #4361ee; }
.role-badge.coordinator { background: rgba(6, 214, 160, 0.12); color: #05a87c; }

.faculties-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.fac-tags { display: flex; gap: 0.3rem; flex-wrap: wrap; }

.fac-tag {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  background: rgba(67, 97, 238, 0.08);
  color: #4361ee;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 600;
}

.no-faculties { color: #bbb; font-size: 0.8rem; font-style: italic; }

.edit-fac-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.85rem;
  padding: 0.2rem;
  opacity: 0.5;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.edit-fac-btn:hover { opacity: 1; }

.delete-btn {
  padding: 0.3rem 0.75rem;
  background: transparent;
  border: 1px solid #e63946;
  color: #e63946;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.15s;
  white-space: nowrap;
}

.delete-btn:hover { background: #e63946; color: white; }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: white;
  border-radius: 16px;
  padding: 2rem;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15);
}

.modal h3 { margin: 0 0 1.25rem; color: #1a1a2e; font-size: 1rem; }

.faculty-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.fac-check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  border: 1.5px solid #e8e8e8;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
  transition: all 0.15s;
  user-select: none;
}

.fac-check:hover { border-color: #4361ee; background: rgba(67, 97, 238, 0.04); }
.fac-check.selected { border-color: #4361ee; background: rgba(67, 97, 238, 0.08); color: #4361ee; }

.fac-check input { display: none; }

.modal-actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}

.btn-cancel {
  padding: 0.6rem 1.25rem;
  background: transparent;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  color: #666;
  transition: all 0.15s;
}

.btn-cancel:hover { border-color: #999; color: #333; }

.btn-save {
  padding: 0.6rem 1.5rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
  transition: background 0.15s;
}

.btn-save:hover:not(:disabled) { background: #3451d1; }
.btn-save:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
