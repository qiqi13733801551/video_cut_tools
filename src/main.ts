// main.ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './AppTest.vue'

// 引入组件样式
import 'vue-clip-track/style.css'

const app = createApp(App)
app.use(createPinia())
app.mount('#app')
