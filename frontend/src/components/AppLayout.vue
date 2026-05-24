<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">Координаторство'26</div>
      <nav>
        <router-link to="/">Дашборд</router-link>
        <router-link to="/applicants">Заявки</router-link>
        <router-link to="/availability">Занятость</router-link>
        <router-link to="/interviews">Собеседования</router-link>
        <router-link v-if="auth.isAdmin" to="/admin">Управление</router-link>
        <router-link v-if="auth.isAdmin" to="/admin/assignments">Распределение</router-link>
        <router-link v-if="auth.isAdmin" to="/admin/interview">Собесы (адм.)</router-link>
        <router-link v-if="auth.isAdmin" to="/admin/interview-stats">Статистика собесов</router-link>
        <router-link v-if="auth.isAdmin" to="/admin/applicant-reviews">Ответы кандидатов</router-link>
        <router-link v-if="auth.isAdmin" to="/admin/availability">Занятость (адм.)</router-link>
        <router-link v-if="auth.isAdmin" to="/admin/settings">Настройки</router-link>
      </nav>
      <div class="user-footer">
        <span class="role-badge" :class="auth.user.role">
          {{ auth.user.role === 'admin' ? 'Админ' : 'Координатор' }}
        </span>
        <span class="user-name">{{ auth.user.name }}</span>
        <button class="logout-btn" @click="logout">Выйти</button>
      </div>
    </aside>
    <main class="content">
      <slot />
    </main>
  </div>
</template>

<script setup>
import { useAuthStore } from '../stores/auth'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout { display: flex; height: 100vh; overflow: hidden; }

.sidebar {
  width: 240px;
  background: #1a1a2e;
  color: white;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.brand {
  font-size: 0.95rem;
  font-weight: 700;
  color: #4361ee;
  margin-bottom: 2rem;
  line-height: 1.3;
}

nav { flex: 1; }

nav a {
  display: block;
  padding: 0.6rem 0.75rem;
  color: #9a9ab0;
  text-decoration: none;
  border-radius: 8px;
  margin-bottom: 0.25rem;
  font-size: 0.9rem;
  transition: background 0.15s, color 0.15s;
}

nav a:hover { background: #2d2d44; color: white; }
nav a.router-link-active { background: #2d2d44; color: white; }

.user-footer {
  padding-top: 1rem;
  border-top: 1px solid #2d2d44;
}

.role-badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 20px;
  font-size: 0.7rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.role-badge.admin { background: rgba(67,97,238,0.2); color: #7b9cff; }
.role-badge.coordinator { background: rgba(6,214,160,0.15); color: #06d6a0; }

.user-name {
  display: block;
  font-size: 0.875rem;
  color: #ccc;
  margin-bottom: 0.75rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logout-btn {
  width: 100%;
  padding: 0.5rem;
  background: transparent;
  border: 1px solid #2d2d44;
  color: #9a9ab0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.15s;
}

.logout-btn:hover { background: #e63946; border-color: #e63946; color: white; }

.content { flex: 1; padding: 2rem; background: #f0f2f5; overflow-y: auto; min-height: 0; }
</style>
