import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/library' },
  {
    path: '/library',
    name: 'library',
    component: () => import('@/views/LibraryView.vue'),
    meta: { title: '资源库' },
  },
  {
    path: '/scrape',
    name: 'scrape',
    component: () => import('@/views/ScrapeView.vue'),
    meta: { title: '刮削中心' },
  },
  {
    path: '/organize',
    name: 'organize',
    component: () => import('@/views/OrganizeView.vue'),
    meta: { title: '整理' },
  },
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('@/views/TasksView.vue'),
    meta: { title: '任务与日志' },
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('@/views/LogsView.vue'),
    meta: { title: '操作日志' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '设置' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '未找到' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const APP_NAME = 'MusicTag Lite'
router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} · ${APP_NAME}` : APP_NAME
})

export default router
