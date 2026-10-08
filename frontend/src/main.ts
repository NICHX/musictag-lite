import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import { useUiStore } from './stores/ui'
import './design/tokens.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

useUiStore().init()

app.mount('#app')
