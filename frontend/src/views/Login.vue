<template>
  <div class="page">
    <div class="card">
      <h1>Координаторство'26</h1>
      <p class="subtitle">HR система отбора</p>

      <form @submit.prevent="handleLogin">
        <div class="field">
          <label>Email</label>
          <input v-model="email" type="email" placeholder="admin@koord.ru" required autocomplete="email" />
        </div>
        <div class="field">
          <label>Пароль</label>
          <input v-model="password" type="password" placeholder="••••••••" required autocomplete="current-password" />
        </div>

        <p v-if="error" class="error">{{ error }}</p>

        <button type="submit" :disabled="loading">
          {{ loading ? 'Вход...' : 'Войти' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    router.push('/')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Ошибка входа'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
}

.card {
  background: white;
  padding: 2.5rem;
  border-radius: 16px;
  box-shadow: 0 4px 32px rgba(0, 0, 0, 0.08);
  width: 100%;
  max-width: 400px;
}

h1 { margin: 0 0 0.25rem; font-size: 1.5rem; color: #1a1a2e; }

.subtitle { color: #888; margin: 0 0 2rem; font-size: 0.9rem; }

.field { margin-bottom: 1rem; }

.field label {
  display: block;
  margin-bottom: 0.4rem;
  font-size: 0.85rem;
  font-weight: 500;
  color: #444;
}

.field input {
  width: 100%;
  padding: 0.7rem 0.9rem;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.95rem;
  outline: none;
  transition: border-color 0.15s;
}

.field input:focus { border-color: #4361ee; }

.error {
  color: #e63946;
  font-size: 0.85rem;
  margin: 0.5rem 0;
}

button {
  width: 100%;
  padding: 0.75rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  margin-top: 0.5rem;
  transition: background 0.15s;
}

button:hover:not(:disabled) { background: #3451d1; }
button:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
