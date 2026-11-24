import { createRouter, createWebHashHistory } from 'vue-router'
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/closet' },
    ...['closet', 'stylist', 'studio', 'profile'].map(page => ({ path: '/' + page, name: page, component: { render: () => null } })),
    { path: '/:pathMatch(.*)*', redirect: '/closet' },
  ],
})
