<template>
  <AppLayout>
    <div class="top-bar">
      <h2>Статистика проверяющих по собесам</h2>
    </div>

    <div v-if="loading" class="state-msg">Загрузка…</div>
    <div v-else-if="!reviewers.length" class="state-msg muted">Нет данных о собеседованиях.</div>

    <div v-else class="card">
      <table>
        <thead>
          <tr>
            <th>Проверяющий</th>
            <th class="num-col">Назначено собесов</th>
            <th class="num-col">Сохранено ответов</th>
            <th class="num-col">%</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in reviewers" :key="r.id">
            <td>{{ r.name }}</td>
            <td class="num-cell">{{ r.assigned }}</td>
            <td class="num-cell">
              <span :class="r.completed === r.assigned && r.assigned > 0 ? 'done' : ''">
                {{ r.completed }}
              </span>
            </td>
            <td class="num-cell">
              <span v-if="r.assigned > 0" class="pct" :class="pctClass(r)">
                {{ Math.round(r.completed / r.assigned * 100) }}%
              </span>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr class="total-row">
            <td>Итого</td>
            <td class="num-cell">{{ totals.assigned }}</td>
            <td class="num-cell">{{ totals.completed }}</td>
            <td class="num-cell">
              <span v-if="totals.assigned > 0" class="pct" :class="pctClass(totals)">
                {{ Math.round(totals.completed / totals.assigned * 100) }}%
              </span>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const loading = ref(true)
const reviewers = ref([])

const totals = computed(() => ({
  assigned: reviewers.value.reduce((s, r) => s + r.assigned, 0),
  completed: reviewers.value.reduce((s, r) => s + r.completed, 0),
}))

function pctClass(r) {
  if (!r.assigned) return ''
  const p = r.completed / r.assigned
  if (p >= 1) return 'pct-full'
  if (p >= 0.5) return 'pct-half'
  return 'pct-low'
}

onMounted(async () => {
  try {
    const { data } = await api.get('/interview/admin/reviewer-stats')
    reviewers.value = data.reviewers
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  margin-bottom: 1.5rem;
}
h2 { margin: 0; color: #1a1a2e; font-size: 1.4rem; }

.state-msg { color: #888; font-size: 0.9rem; padding: 2rem 0; }
.muted { color: #bbb; }

.card {
  background: white;
  padding: 1.5rem;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

table { width: 100%; border-collapse: collapse; }

th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  font-size: 0.78rem;
  color: #888;
  font-weight: 600;
  border-bottom: 1.5px solid #f0f0f0;
}
.num-col { text-align: center; }

td {
  padding: 0.65rem 0.75rem;
  font-size: 0.875rem;
  color: #333;
  border-bottom: 1px solid #f9f9f9;
}
.num-cell { text-align: center; }

.done { color: #05a87c; font-weight: 600; }

.pct { font-weight: 600; }
.pct-full  { color: #05a87c; }
.pct-half  { color: #f4a261; }
.pct-low   { color: #e63946; }

.total-row td { border-top: 1.5px solid #e8e8e8; font-weight: 600; color: #1a1a2e; }
</style>
