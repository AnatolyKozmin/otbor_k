import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    component: () => import('../views/Login.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    component: () => import('../views/Dashboard.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/applicants',
    component: () => import('../views/Applicants.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/applicants/:sheet/:rowNumber',
    component: () => import('../views/ReviewDetail.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/availability',
    component: () => import('../views/Availability.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/admin',
    component: () => import('../views/Admin.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/assignments',
    component: () => import('../views/AdminAssignments.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/availability',
    component: () => import('../views/AdminAvailability.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/settings',
    component: () => import('../views/Settings.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/interview',
    component: () => import('../views/AdminInterview.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/interviews',
    component: () => import('../views/InterviewList.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/interviews/:rowNumber',
    component: () => import('../views/InterviewForm.vue'),
    meta: { requiresAuth: true },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _, next) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) return next('/login')
  if (to.meta.requiresAdmin && !auth.isAdmin) return next('/')
  if (to.meta.guest && auth.isAuthenticated) return next('/')
  next()
})

export default router
