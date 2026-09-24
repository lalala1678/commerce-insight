<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import Chart from './Chart.vue'
import { getJson, number, money, percent } from './api'
const props = defineProps({ scope: { type: Object, required: true }, version: String })
const data = ref(null), loading = ref(false), error = ref('')
let controller, sequence = 0
async function load() {
  controller?.abort()
  controller = new AbortController()
  const current = ++sequence
  data.value = null; error.value = ''; loading.value = true
  try {
    const result = await getJson('/api/customers', props.scope, controller.signal)
    if (current !== sequence) return
    if (result.meta.data_source !== 'olist') throw new Error('客户接口未返回真实 Olist 数据。')
    if (result.meta.data_version !== props.version) throw new Error('数据版本已更新，请重新应用顶部筛选以同步整个页面。')
    data.value = result
  } catch (e) { if (current === sequence && e.name !== 'AbortError') error.value = e.message }
  finally { if (current === sequence) loading.value = false }
}
watch(() => [props.scope, props.version], load, { immediate: true, deep: true })
onBeforeUnmount(() => { ++sequence; controller?.abort() })
const cards = computed(() => {
  const s = data.value?.summary || {}
  return [
    { label: '购买客户', value: number(s.customer_count), hint: '跨订单稳定身份去重' },
    { label: '数据内新客', value: number(s.new_customers), hint: '全品类历史首次购买在本窗口' },
    { label: '数据内老客', value: number(s.returning_customers), hint: '首次购买早于本窗口' },
    { label: '观察期复购率', value: s.repeat_rate == null ? '不可计算' : `${number(s.repeat_rate * 100, 2)}%`, hint: `${number(s.repeat_customers)} 位客户在窗口内购买至少2次` },
  ]
})
const frequencyChart = computed(() => ({
  color: ['#16897f'], tooltip: { trigger: 'axis' },
  grid: { left: 60, right: 20, top: 25, bottom: 40 },
  xAxis: { type: 'category', data: (data.value?.frequency_distribution || []).map(x => `${x.frequency}次`) },
  yAxis: { type: 'value', minInterval: 1, name: '客户数' },
  series: [{ type: 'bar', barMaxWidth: 45, data: (data.value?.frequency_distribution || []).map(x => x.customer_count), itemStyle: { borderRadius: [4,4,0,0] } }],
}))
</script>

<template>
  <section class="customer-analysis" aria-label="客户分析结果">
    <div v-if="loading" class="loading-state" aria-busy="true"><p>正在核对客户历史与观察窗口…</p><el-skeleton :rows="6" animated /></div>
    <div v-else-if="error" class="error-state" role="alert"><h2>暂时无法读取客户分析</h2><p>{{ error }}</p><el-button @click="load">重试客户分析</el-button></div>
    <template v-else-if="data">
      <section class="kpi-grid customer-kpis"><article v-for="card in cards" :key="card.label" class="kpi"><p class="kpi-label">{{ card.label }}</p><div class="kpi-value">{{ card.value }}</div><p class="kpi-hint">{{ card.hint }}</p></article></section>
      <div v-if="!data.summary.customer_count" class="empty-notice" role="status">当前范围没有购买客户，复购率不可计算，RFM 分组人数均为 0。</div>
      <div class="two-columns">
        <section class="panel"><div class="panel-heading"><div><h2>购买频次分布</h2><p>订单先去重，再按客户统计购买次数</p></div></div><Chart v-if="data.summary.customer_count" :option="frequencyChart" label="观察窗口内每种购买次数对应的客户数量" /><el-empty v-else description="没有购买记录" /><p class="table-note">仅购买一次的客户占 {{ percent(data.summary.single_purchase_share) }}。窗口复购率与“老客占比”是不同指标。</p></section>
        <section class="panel customer-rules"><div class="panel-heading"><div><h2>RFM 规则与观察窗口</h2><p>公开规则，保留金额与次数原值</p></div></div><dl>
          <dt>回看窗口</dt><dd>{{ data.meta.start }} 至 {{ data.meta.end }}</dd>
          <dt>历史截止日</dt><dd>{{ data.meta.cutoff }}（包含当天）</dd>
          <dt>R · 距末次购买天数</dt><dd>截止日减窗口内最近购买日；≤30 天 / >30 天</dd>
          <dt>F · 购买频次</dt><dd>窗口内已交付订单；1 次 / ≥2 次</dd>
          <dt>M · 商品金额</dt><dd>窗口内命中商品金额；< R$200 / ≥ R$200</dd>
        </dl><p class="table-note">默认月度窗口的 R 差异有限。可将顶部开始日期改为 2018-02-01，观察更长窗口；所有客户指标会一起重算。阈值用于探索，不表示“优质”或“流失”。</p></section>
      </div>
      <section class="panel"><div class="panel-heading"><div><h2>RFM 客户分组</h2><p>三个维度组合为8组，覆盖本窗口全部购买客户且互不重叠</p></div><span class="small-tag">{{ number(data.summary.customer_count) }} 位客户</span></div>
        <p class="mobile-table-hint">左右滑动，查看分组订单数与金额 →</p>
        <el-table :data="data.segments" stripe>
          <el-table-column prop="label" label="分组规则" min-width="335" />
          <el-table-column label="客户数" min-width="90" align="right"><template #default="{ row }">{{ number(row.customer_count) }}</template></el-table-column>
          <el-table-column label="客户占比" min-width="95" align="right"><template #default="{ row }">{{ percent(data.summary.customer_count ? row.customer_count / data.summary.customer_count : null) }}</template></el-table-column>
          <el-table-column label="订单数" min-width="90" align="right"><template #default="{ row }">{{ number(row.order_count) }}</template></el-table-column>
          <el-table-column label="商品金额 / BRL" min-width="145" align="right"><template #default="{ row }">{{ money(row.revenue_cents) }}</template></el-table-column>
        </el-table>
        <p class="table-note">合计 {{ number(data.summary.order_count) }} 笔订单 · {{ money(data.summary.revenue_cents) }}。金额跟随品类筛选，不含运费。</p>
      </section>
      <section class="panel"><div class="panel-heading"><div><h2>原始 R / F / M 分布</h2><p>P75 使用最近秩法；并列值不强制拆成等人数分组</p></div></div>
        <div class="customer-distributions"><article v-for="(d, key) in data.distribution" :key="key"><h3>{{ { recency_days:'R · 天', frequency:'F · 次', monetary_cents:'M · BRL' }[key] }}</h3><p>最小：{{ key==='monetary_cents' ? money(d.min) : number(d.min) }}</p><p>中位数：{{ key==='monetary_cents' ? money(d.median) : number(d.median,1) }}</p><p>P75：{{ key==='monetary_cents' ? money(d.p75) : number(d.p75) }}</p><p>最大：{{ key==='monetary_cents' ? money(d.max) : number(d.max) }}</p></article></div>
      </section>
      <details class="customer-notes"><summary>如何解读这些客户指标</summary><ul><li v-for="warning in data.meta.warnings" :key="warning">{{ warning }}</li></ul></details>
      <p class="table-note">客户分析数据版本 {{ data.meta.data_version }} · 规则 {{ data.meta.rules.version }}</p>
    </template>
  </section>
</template>

<style scoped>
.customer-rules dl{font-size:12px;line-height:1.8}.customer-rules dt{color:#547c77;margin-top:12px;font-weight:600}.customer-rules dd{color:#647b8b}.customer-distributions{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;font-size:12px;line-height:2;color:#647b8b}.customer-distributions h3{font-size:13px;color:#355164;margin-bottom:8px}.customer-notes{background:#edf4f2;padding:16px;margin-bottom:16px;border-radius:8px;font-size:12px;line-height:1.8;color:#547c77}.customer-notes summary{cursor:pointer}.customer-notes ul{padding-left:20px}@media(max-width:600px){.customer-distributions{grid-template-columns:1fr;gap:15px}.customer-kpis .kpi-value{font-size:25px}}
</style>
