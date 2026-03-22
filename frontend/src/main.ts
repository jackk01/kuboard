import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router, { setupRouterGuards } from './router'
import { useSessionStore } from './stores/session'
import './style.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)

const sessionStore = useSessionStore(pinia)
await sessionStore.bootstrap()

setupRouterGuards(router)
app.use(router)
app.mount('#app')
