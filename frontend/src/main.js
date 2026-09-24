import { createApp, h } from 'vue'
import { ElAlert, ElButton, ElIcon, ElInput, ElTag, ElSelect, ElOption, ElTable, ElTableColumn,
  ElDialog, ElDrawer, ElPagination, ElSkeleton, ElEmpty, ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn.mjs'
import 'element-plus/dist/index.css'
import App from './App.vue'
import './style.css'

const app = createApp({
  render: () => h(ElConfigProvider, { locale: zhCn }, () => h(App)),
})
for (const component of [ElAlert, ElButton, ElIcon, ElInput, ElTag, ElSelect, ElOption, ElTable,
  ElTableColumn, ElDialog, ElDrawer, ElPagination, ElSkeleton, ElEmpty]) {
  app.component(component.name, component)
}
app.mount('#app')
