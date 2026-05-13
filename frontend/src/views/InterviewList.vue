<template>
  <AppLayout>
    <div class="page-header">
      <h2>Мои собеседования</h2>
    </div>

    <div v-if="loading" class="state-msg">Загрузка…</div>
    <div v-else-if="!interviews.length" class="state-msg muted">
      Вам пока не назначено ни одного собеседования.
    </div>

    <div v-else class="cards">
      <div
        v-for="item in interviews"
        :key="item.row_number"
        class="card"
        :class="{ scheduled: item.slot_date, unscheduled: !item.slot_date }"
        @click="openForm(item.row_number)"
      >
        <div class="card-when">
          <template v-if="item.slot_date">
            <span class="when-date">{{ formatDate(item.slot_date) }}</span>
            <span class="when-time">{{ item.slot_hour }}:00 — {{ item.slot_hour + 1 }}:00</span>
          </template>
          <span v-else class="when-empty">не записан кандидат</span>
        </div>
        <div class="card-fio">{{ item.fio || '— ФИО не указано —' }}</div>
        <div class="card-meta">
          <span class="slot-badge" :class="'slot' + item.my_slot">
            Проверяющий {{ item.my_slot }}
          </span>
          <span class="other-name">
            с {{ (item.my_slot === 1 ? item.reviewer2 : item.reviewer1) || '—' }}
          </span>
        </div>
        <button class="open-btn">Открыть →</button>
      </div>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '../components/AppLayout.vue'
import api from '../api'

const router = useRouter()
const loading = ref(true)
const interviews = ref([])

onMounted(async () => {
  try {
    const { data } = await api.get('/interview/my')
    interviews.value = data.interviews
  } finally {
    loading.value = false
  }
})

function openForm(rowNumber) {
  router.push(`/interviews/${rowNumber}`)
}

const MONTHS = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
const WEEKDAYS = ['вс','пн','вт','ср','чт','пт','сб']

function formatDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  return `${WEEKDAYS[dt.getDay()]}, ${d} ${MONTHS[m - 1]}`
}
</script>

<style scoped>
.page-header { margin-bottom: 1.5rem; }
h2 { margin: 0; font-size: 1.4rem; color: #1a1a2e; }

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 1.25rem 1.4rem;
  cursor: pointer;
  transition: box-shadow 0.15s, transform 0.1s;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.card:hover { box-shadow: 0 4px 16px rgba(67,97,238,0.12); transform: translateY(-1px); }
.card.unscheduled { opacity: 0.7; }

.card-when {
  display: flex; flex-direction: column; gap: 0.15rem;
  padding-bottom: 0.5rem; border-bottom: 1px solid #f0f0f0;
}
.when-date {
  font-weight: 700; font-size: 0.95rem; color: #4361ee;
  text-transform: capitalize;
}
.when-time { font-size: 0.78rem; color: #777; font-variant-numeric: tabular-nums; }
.when-empty { font-size: 0.8rem; color: #aaa; font-style: italic; }

.card-fio { font-weight: 600; font-size: 1rem; color: #1a1a2e; }

.card-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.82rem;
}

.slot-badge {
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.72rem;
}
.slot1 { background: rgba(67,97,238,0.1); color: #4361ee; }
.slot2 { background: rgba(6,160,122,0.1); color: #06a07a; }

.other-name { color: #888; }

.open-btn {
  margin-top: 0.25rem;
  align-self: flex-end;
  padding: 0.4rem 0.9rem;
  background: #4361ee;
  color: white;
  border: none;
  border-radius: 7px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.open-btn:hover { background: #3451d1; }

.state-msg {
  background: white;
  border-radius: 12px;
  padding: 3rem;
  text-align: center;
  font-size: 0.9rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.state-msg.muted { color: #aaa; }
</style>
