<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { DataAnalysis, Goods, TrendCharts, ArrowRight, Refresh, InfoFilled, Tickets, TopRight } from '@element-plus/icons-vue'
import Chart from './Chart.vue'
import Customers from './Customers.vue'
import Reports from './Reports.vue'
import { getJson, number, money, percent, categoryLabel, staticDemo } from './api'

const navigation = [
  { label: '经营概览', note: '观察销售表现，定位品类与地区贡献。', icon: DataAnalysis },
  { label: '商品与履约', note: '看清商品结构，核查订单交付与评价。', icon: Goods },
  { label: '客户分析', note: '区分新老客户，理解观察期复购与 RFM。', icon: DataAnalysis },
  { label: '经营报告', note: '核对经营变化，生成可追溯的分析报告。', icon: Tickets },
]
const staticMethodology = `${import.meta.env.BASE_URL}methodology.html`
const page = ref(0), options = ref(null), dashboard = ref(null), loading = ref(true), error = ref(''), validation = ref('')
const draft = ref({ start: '2018-07-01', end: '2018-07-31', category: '', state: '' })
const applied = ref({ ...draft.value }), grain = ref('day'), rankMode = ref('top')
const draftPresetId = ref('july-2018'), appliedPresetId = ref('july-2018')
const presetOptions = computed(() => options.value?.static_presets || [])
const hasPending = computed(() => staticDemo ? draftPresetId.value !== appliedPresetId.value : Object.keys(draft.value).some(key => draft.value[key] !== applied.value[key]))
const kpis = computed(() => dashboard.value?.kpis || {})
const fulfillment = computed(() => dashboard.value?.fulfillment || {})
const categoryText = value => categoryLabel(value, options.value?.categories.find(item => item.value === value)?.label)
const currentScope = computed(() => `${applied.value.start} — ${applied.value.end}`)
const scopeLabel = computed(() => `${applied.value.category ? categoryText(applied.value.category) : '全部品类'} · ${applied.value.state || '全部地区'}`)
const rankedProducts = computed(() => dashboard.value?.[rankMode.value === 'top' ? 'products' : 'low_volume_products'] || [])
const cards = computed(() => [
  { label: '成交商品金额', value: money(kpis.value.revenue_cents), field: 'revenue_cents', hint: '已交付 · 商品金额 · 不含运费', accent: true },
  { label: '已交付订单', value: number(kpis.value.order_count), field: 'order_count', hint: '筛选范围内，按订单 ID 去重', unit: '笔' },
  { label: '平均客单价', value: money(kpis.value.average_order_value_cents), field: 'average_order_value_cents', hint: '同一集合商品金额 ÷ 订单数' },
  { label: '购买客户数', value: number(kpis.value.customer_count), field: 'customer_count', hint: '按跨订单稳定客户标识去重', unit: '位' },
])
function comparison(field) {
  const previous = dashboard.value?.previous?.[field], current = kpis.value[field]
  if (previous == null || current == null) return { text: '比较期数据不足', className: '' }
  if (previous === 0) return { text: '比较基数为 0', className: '' }
  const value = (current - previous) / previous
  return { text: `${value > 0 ? '+' : ''}${number(value * 100, 1)}%`, className: value > 0 ? 'positive' : value < 0 ? 'negative' : '' }
}

// Every query owns an AbortController and a sequence number, so older responses
// cannot replace a newer filter selection, including during a fast retry.
let dashboardAbort, optionsAbort, dashboardSequence = 0
async function loadDashboard(filters, nextGrain = grain.value) {
  dashboardAbort?.abort()
  closeOrders()
  const sequence = ++dashboardSequence
  dashboardAbort = new AbortController()
  applied.value = { ...filters }
  grain.value = nextGrain
  loading.value = true
  error.value = ''
  dashboard.value = null
  try {
    const result = await getJson('/api/dashboard', { ...filters, grain: nextGrain }, dashboardAbort.signal)
    if (sequence !== dashboardSequence) return
    if (result.meta?.data_source !== 'olist') throw new Error('当前接口不是 Olist 真实数据，请先完成真实数据导入。')
    dashboard.value = result
  } catch (exception) {
    if (sequence === dashboardSequence && exception.name !== 'AbortError') error.value = exception.message || '暂时无法连接数据服务。'
  } finally {
    if (sequence === dashboardSequence) loading.value = false
  }
}
function applyFilters() {
  validation.value = ''
  if (staticDemo) {
    const preset = presetOptions.value.find(item => item.id === draftPresetId.value)
    if (!preset) { validation.value = '请选择可用的演示范围。'; return }
    appliedPresetId.value = preset.id
    draft.value = { start: preset.start, end: preset.end, category: preset.category, state: preset.state }
    loadDashboard({ ...draft.value })
    return
  }
  if (!draft.value.start || !draft.value.end) { validation.value = '请填写开始日期和结束日期。'; return }
  if (draft.value.start > draft.value.end) { validation.value = '开始日期不能晚于结束日期。'; return }
  loadDashboard({ ...draft.value })
}
function latestWeek() {
  if (staticDemo) {
    const preset = presetOptions.value.find(item => item.latest_week)
    if (preset) { draftPresetId.value = preset.id; applyFilters() }
    return
  }
  const limit = options.value.supported_end
  const end = new Date(`${limit && applied.value.end > limit ? limit : applied.value.end}T00:00:00Z`)
  end.setUTCDate(end.getUTCDate() - end.getUTCDay())
  const start = new Date(end); start.setUTCDate(start.getUTCDate() - 6)
  draft.value = { ...applied.value, start: start.toISOString().slice(0,10), end: end.toISOString().slice(0,10) }
  applyFilters()
}
function resetFilters() {
  if (staticDemo) { draftPresetId.value = 'july-2018'; applyFilters(); return }
  draft.value = { start: options.value.default_start, end: options.value.default_end, category: '', state: '' }
  applyFilters()
}
async function initialize() {
  optionsAbort?.abort()
  optionsAbort = new AbortController()
  loading.value = true
  error.value = ''
  try {
    const result = await getJson('/api/options', {}, optionsAbort.signal)
    if (result.data_source !== 'olist') throw new Error('当前服务尚未准备 Olist 真实数据，请先运行导入。')
    options.value = result
    if (staticDemo) { draftPresetId.value = 'july-2018'; appliedPresetId.value = 'july-2018' }
    draft.value = { start: result.default_start, end: result.default_end, category: '', state: '' }
    await loadDashboard({ ...draft.value })
  } catch (exception) {
    if (exception.name !== 'AbortError') { error.value = exception.message; loading.value = false }
  }
}
const retry = () => options.value ? loadDashboard({ ...applied.value }) : initialize()
const changeGrain = value => { if (grain.value !== value) loadDashboard({ ...applied.value }, value) }
onMounted(initialize)

const baseChart = {
  color: ['#16897f', '#82a5b6', '#dcac69'],
  textStyle: { fontFamily: 'Microsoft YaHei, sans-serif', color: '#788b9a', fontSize: 11 },
  grid: { left: 62, right: 20, top: 22, bottom: 34 },
}
const trendChart = computed(() => {
  const entries = dashboard.value?.trend || []
  return { ...baseChart,
    tooltip: { trigger: 'axis', formatter: params => {
      const point = entries[params[0]?.dataIndex]
      return point ? `${point.period}${point.complete ? '' : '（不完整周期）'}\n商品金额：${money(point.revenue_cents)}\n订单数：${number(point.order_count)}` : ''
    } },
    xAxis: { type: 'category', boundaryGap: false, data: entries.map(item => item.period), axisLabel: { formatter: value => value.slice(5) || value, hideOverlap: true }, axisLine: { lineStyle: { color: '#e0e8ee' } }, axisTick: { show: false } },
    yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed', color: '#eaf0f3' } }, axisLabel: { formatter: value => Math.abs(value) >= 10000 ? `${number(value / 10000, 1)}万` : number(value) } },
    series: [{ name: '商品金额', type: 'line', data: entries.map(item => item.revenue_cents == null ? null : item.revenue_cents / 100), smooth: false, connectNulls: false, symbol: 'circle', symbolSize: 5, lineStyle: { width: 2.5 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#16897f28' }, { offset: 1, color: '#16897f02' }] } } }],
  }
})
const regionChart = computed(() => {
  const entries = (dashboard.value?.regions || []).slice(0, 8)
  return { ...baseChart, grid: { left: 34, right: 64, top: 8, bottom: 25 },
    tooltip: { trigger: 'axis', valueFormatter: value => money(value * 100) },
    xAxis: { type: 'value', axisLabel: { formatter: value => value >= 10000 ? `${number(value / 10000, 0)}万` : number(value) }, splitLine: { lineStyle: { type: 'dashed', color: '#eaf0f3' } } },
    yAxis: { type: 'category', inverse: true, data: entries.map(item => item.name), axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', barWidth: 13, data: entries.map(item => item.revenue_cents / 100), itemStyle: { borderRadius: [0, 3, 3, 0] }, label: { show: true, position: 'right', color: '#788b9a', fontSize: 10, formatter: params => `${number(params.value / 1000, 1)}k` } }],
  }
})
const scoreChart = computed(() => ({ ...baseChart, grid: { left: 43, right: 15, top: 16, bottom: 28 },
  tooltip: { trigger: 'axis', valueFormatter: value => `${number(value)} 笔订单` },
  xAxis: { type: 'category', data: (fulfillment.value.scores || []).map(item => `${item.score} 分`), axisTick: { show: false }, axisLine: { lineStyle: { color: '#e0e8ee' } } },
  yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { type: 'dashed', color: '#eaf0f3' } } },
  series: [{ type: 'bar', barWidth: '32%', data: (fulfillment.value.scores || []).map(item => item.order_count), itemStyle: { borderRadius: [4, 4, 0, 0] } }],
}))
const categoryShare = item => kpis.value.revenue_cents ? item.revenue_cents / kpis.value.revenue_cents : 0

const ordersVisible = ref(false), orders = ref(null), ordersLoading = ref(false), ordersError = ref(''), orderPage = ref(1)
const detailVisible = ref(false), detail = ref(null), detailLoading = ref(false), detailError = ref(''), selectedOrderId = ref('')
let ordersAbort, detailAbort, ordersSequence = 0, detailSequence = 0, orderFilters = null
function closeDetail() { detailAbort?.abort(); ++detailSequence; detailVisible.value = false; detail.value = null; detailLoading.value = false }
function closeOrders() { ordersAbort?.abort(); ++ordersSequence; ordersVisible.value = false; orders.value = null; ordersLoading.value = false; closeDetail() }
function openOrders() { orderFilters = { ...applied.value }; ordersVisible.value = true; fetchOrders(1) }
async function fetchOrders(nextPage = 1) {
  ordersAbort?.abort()
  const sequence = ++ordersSequence
  ordersAbort = new AbortController()
  ordersLoading.value = true; ordersError.value = ''; orders.value = null; orderPage.value = nextPage
  try {
    const result = await getJson('/api/orders', { ...orderFilters, page: nextPage, page_size: 10 }, ordersAbort.signal)
    if (sequence === ordersSequence) orders.value = result
  } catch (exception) { if (sequence === ordersSequence && exception.name !== 'AbortError') ordersError.value = exception.message }
  finally { if (sequence === ordersSequence) ordersLoading.value = false }
}
async function openDetail(orderId) {
  detailAbort?.abort()
  const sequence = ++detailSequence
  detailAbort = new AbortController()
  selectedOrderId.value = orderId; detailVisible.value = true; detailLoading.value = true; detailError.value = ''; detail.value = null
  try {
    const result = await getJson(`/api/orders/${encodeURIComponent(orderId)}`, { category: orderFilters?.category }, detailAbort.signal)
    if (sequence === detailSequence) detail.value = result
  } catch (exception) { if (sequence === detailSequence && exception.name !== 'AbortError') detailError.value = exception.message }
  finally { if (sequence === detailSequence) detailLoading.value = false }
}
const lateLabel = value => value == null ? '日期不足' : value ? '延迟交付' : '按期交付'
const flagLabel = value => ({ missing_payment: '缺少支付记录', missing_review: '缺评价', missing_items: '缺少商品明细', delivered_missing_delivery_date: '缺送达日期', delivered_missing_estimated_date: '缺预计送达日期', carrier_before_purchase: '承运时间早于下单', delivery_before_carrier: '送达时间早于承运', delivery_before_purchase: '送达时间早于下单', payment_total_mismatch: '支付与商品及运费总额不一致', multiple_reviews: '多条评价已归一' }[value] || value)
onBeforeUnmount(() => { dashboardAbort?.abort(); optionsAbort?.abort(); ordersAbort?.abort(); detailAbort?.abort() })
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark"><el-icon><TrendCharts /></el-icon></span><div>商析<small>COMMERCE INSIGHT</small></div></div>
      <p class="workspace-label">经营工作台</p>
      <nav aria-label="主导航"><button v-for="(item, index) in navigation" :key="item.label" :class="{ active: page === index }" :aria-current="page === index ? 'page' : undefined" @click="page = index"><el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span><el-icon class="nav-arrow"><ArrowRight /></el-icon></button></nav>
      <div class="sidebar-context"><span class="context-line"></span><p>每个数字，都有来处。</p><small>从原始订单到经营指标<br>用一致的口径看清业务</small></div>
      <div class="sidebar-bottom"><div><span class="status-dot"></span> Olist 公开数据</div><p>{{ staticDemo ? '历史数据静态演示' : '历史经营分析 · 本地后台' }}</p><a href="https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce" target="_blank" rel="noreferrer">数据来源与许可 ↗</a></div>
    </aside>
    <div class="body">
      <header class="topbar"><div>经营工作台 <el-icon><ArrowRight /></el-icon><strong>{{ navigation[page].label }}</strong></div><span class="mode-badge"><i></i>{{ staticDemo ? '历史数据 · 静态演示' : '历史数据 · 本地分析服务' }}</span></header>
      <main>
        <div class="page-heading"><div><div class="eyebrow">BUSINESS INTELLIGENCE</div><h1>{{ navigation[page].label }}</h1><p>{{ navigation[page].note }}<span class="divider">/</span>巴西电商 · BRL</p></div><el-button v-if="!staticDemo" class="detail-button" :icon="Tickets" :disabled="!dashboard || loading" @click="openOrders">查看订单明细</el-button></div>
        <form class="filters" aria-label="分析筛选" @submit.prevent="applyFilters">
          <div v-if="staticDemo" class="filter-field static-preset"><label id="preset-label">已导出演示范围</label><el-select v-model="draftPresetId" aria-label="演示范围" aria-labelledby="preset-label" :disabled="!options"><el-option v-for="item in presetOptions" :key="item.id" :value="item.id" :label="item.label" /></el-select></div>
          <template v-else>
            <div class="filter-field date-field"><label for="start-date">日期范围</label><div class="date-range"><input id="start-date" v-model="draft.start" type="date" aria-label="开始日期" :disabled="!options"><span>至</span><input v-model="draft.end" type="date" aria-label="结束日期" :disabled="!options"></div></div>
            <div class="filter-field category-filter"><label id="category-label">商品品类</label><el-select v-model="draft.category" placeholder="全部品类" filterable aria-label="商品品类" aria-labelledby="category-label" :disabled="!options"><el-option label="全部品类" value="" /><el-option v-for="item in options?.categories || []" :key="item.value" :value="item.value" :label="categoryLabel(item.value, item.label)" /></el-select></div>
            <div class="filter-field region-filter"><label id="region-label">客户地区</label><el-select v-model="draft.state" placeholder="全部地区" filterable aria-label="客户地区" aria-labelledby="region-label" :disabled="!options"><el-option label="全部地区" value="" /><el-option v-for="state in options?.states || []" :key="state" :value="state" :label="state" /></el-select></div>
          </template>
          <div class="filter-actions"><el-button type="primary" native-type="submit" :icon="Refresh" :disabled="!options">{{ loading ? '重新查询' : '应用筛选' }}</el-button><button type="button" class="reset-button" :disabled="!options" @click="resetFilters">重置</button></div>
          <p v-if="validation" class="validation" role="alert">{{ validation }}</p>
        </form>
        <el-alert v-if="staticDemo" title="历史数据静态演示：仅提供预先导出的 6 个筛选范围；指标来自 Olist 公开历史数据。订单级查询需运行本地后台。" type="info" :closable="false" show-icon class="static-banner" />
        <div class="period-line"><span><span class="small-dot"></span>{{ loading ? '正在查询' : '当前已应用' }}：<b>{{ currentScope }}</b><span class="scope-label">{{ scopeLabel }}</span></span><span v-if="hasPending" class="pending-note">筛选已修改，点击「应用筛选」更新结果</span><span v-else class="scope-note">最终已交付状态 · 按下单日统计</span></div>

        <section v-if="error" class="error-state" role="alert"><span class="state-icon">!</span><h2>暂时无法读取经营数据</h2><p>{{ error }}</p><el-button type="primary" :icon="Refresh" @click="retry">重新连接</el-button><p class="error-help">{{ staticDemo ? '请刷新页面并检查静态数据文件是否可访问。' : '请确认真实数据已经导入，且后端服务正在运行。' }}</p></section>
        <section v-else-if="loading" class="loading-state" aria-live="polite" aria-busy="true"><p>正在读取当前范围的真实数据…</p><el-skeleton :rows="8" animated /></section>
        <template v-else-if="dashboard">
          <el-alert v-for="warning in dashboard.meta.warnings" :key="warning" :title="warning" type="warning" :closable="false" show-icon class="data-warning" />
          <div v-if="!kpis.order_count" class="empty-notice" role="status"><el-icon><InfoFilled /></el-icon>当前范围没有已交付订单。金额和订单数为 0，客单价与履约比例不可计算；可以调整日期、品类或地区。</div>
          <section v-if="page < 2" class="kpi-grid" aria-label="核心经营指标"><article v-for="card in cards" :key="card.field" :class="['kpi', { accent: card.accent }]"><p class="kpi-label">{{ card.label }}<el-icon v-if="card.accent"><TopRight /></el-icon></p><div class="kpi-value">{{ card.value }}<small v-if="card.unit">{{ card.unit }}</small></div><div class="kpi-change"><span :class="comparison(card.field).className">{{ comparison(card.field).text }}</span><span v-if="dashboard.previous">{{ dashboard.meta.comparison_label || '较比较期' }}</span></div><p class="kpi-hint">{{ card.hint }}</p></article></section>

          <template v-if="page === 0">
            <div class="overview-grid">
              <section class="panel trend-panel"><div class="panel-heading"><div><h2>销售趋势</h2><p>成交商品金额 · BRL</p></div><div class="segmented" aria-label="趋势统计粒度"><button v-for="item in [{ value: 'day', label: '日' }, { value: 'week', label: '周' }, { value: 'month', label: '月' }]" :key="item.value" :class="{ selected: grain === item.value }" :aria-pressed="grain === item.value" @click="changeGrain(item.value)">{{ item.label }}</button></div></div><Chart v-if="kpis.order_count" :option="trendChart" label="所选期间的商品销售金额趋势，横轴为日期，纵轴为巴西雷亚尔" /><el-empty v-else description="暂无可展示的销售趋势" :image-size="76" /><div class="chart-foot"><span>未覆盖的周期显示缺口，不补造为零</span><span>{{ { day: '按日汇总', week: '周一开始', month: '按自然月汇总' }[grain] }}</span></div></section>
              <section class="insight-panel"><div class="insight-label"><el-icon><InfoFilled /></el-icon>观察范围</div><h2>先确认口径，<br>再解读变化。</h2><p>筛选范围内共售出 <strong>{{ number(kpis.item_count) }}</strong> 件商品，涉及 <strong>{{ number(kpis.customer_count) }}</strong> 位客户。</p><div class="insight-rule"></div><dl><div><dt>金额范围</dt><dd>{{ applied.category ? '所选品类商品' : '全部商品' }}</dd></div><div><dt>比较期间</dt><dd v-if="dashboard.previous">{{ dashboard.meta.comparison_start }}<br>至 {{ dashboard.meta.comparison_end }}</dd><dd v-else>数据不足</dd></div></dl><p class="insight-small">历史最终状态不等于当时可见信息，变化比例仅描述结果，不自动推断原因。</p><button class="insight-action" @click="page = 1">进一步查看商品与履约 <el-icon><ArrowRight /></el-icon></button></section>
            </div>
            <div class="two-columns">
              <section class="panel"><div class="panel-heading"><div><h2>品类销售贡献</h2><p>按商品金额排序 · 前 6 位</p></div><span class="small-tag">占当前范围金额</span></div><div v-if="dashboard.categories.length" class="category-ranks"><div v-for="(item, index) in dashboard.categories.slice(0, 6)" :key="item.name" class="rank-row"><span class="rank-index">{{ String(index + 1).padStart(2, '0') }}</span><div class="rank-body"><div class="rank-text"><span :title="item.label">{{ categoryLabel(item.name, item.label) }}</span><b>{{ money(item.revenue_cents) }}</b></div><div class="rank-track"><i :style="{ width: `${categoryShare(item) * 100}%` }"></i></div></div><span class="rank-share">{{ percent(categoryShare(item)) }}</span></div></div><el-empty v-else description="暂无品类销售记录" :image-size="76" /></section>
              <section class="panel"><div class="panel-heading"><div><h2>地区销售分布</h2><p>按客户所在州 · 前 8 位 · BRL</p></div><span class="small-tag">{{ dashboard.regions.length }} 个地区</span></div><Chart v-if="dashboard.regions.length" :option="regionChart" label="按客户所在州统计的前八名商品销售金额" /><el-empty v-else description="暂无地区销售记录" :image-size="76" /></section>
            </div>
          </template>

          <template v-else-if="page === 1">
            <section class="panel products-panel"><div class="panel-heading"><div><h2>商品销售表现</h2><p>{{ rankMode === 'top' ? '按成交商品金额降序排列' : '按已售件数升序排列，仅包含有成交记录的商品' }} · 前 20 位</p></div><div class="segmented"><button :class="{ selected: rankMode === 'top' }" :aria-pressed="rankMode === 'top'" @click="rankMode = 'top'">TOP 商品</button><button :class="{ selected: rankMode === 'low' }" :aria-pressed="rankMode === 'low'" @click="rankMode = 'low'">低销量商品</button></div></div><p class="mobile-table-hint">左右滑动表格，查看销售件数、订单数和金额 →</p><el-table :data="rankedProducts" empty-text="当前范围没有商品成交记录" stripe><el-table-column type="index" label="排名" width="62" /><el-table-column prop="product_id" label="商品 ID" min-width="170"><template #default="{ row }"><span class="id-text" :title="row.product_id">{{ row.product_id }}</span></template></el-table-column><el-table-column label="品类" min-width="145"><template #default="{ row }">{{ categoryLabel(row.category, row.label) }}</template></el-table-column><el-table-column label="销售件数" min-width="95" align="right"><template #default="{ row }">{{ number(row.item_count) }}</template></el-table-column><el-table-column label="订单数" min-width="88" align="right"><template #default="{ row }">{{ number(row.order_count) }}</template></el-table-column><el-table-column label="商品金额 / BRL" min-width="150" align="right"><template #default="{ row }"><span class="amount-cell">{{ money(row.revenue_cents) }}</span></template></el-table-column></el-table><p class="table-note">商品没有公开名称，以原始 ID 识别。低销量表示当前范围内成交较少；缺少库存与上架时间，不能据此判断滞销。</p></section>
            <section class="fulfillment-section"><div class="section-heading"><div><div class="eyebrow">FULFILLMENT & EXPERIENCE</div><h2>交付表现与客户评价</h2></div><span class="small-tag">订单粒度 · 同一筛选范围</span></div><div class="service-grid"><article><p>延迟交付率</p><strong>{{ percent(fulfillment.late_rate) }}</strong><span>{{ number(fulfillment.late_orders) }} / {{ number(fulfillment.eligible_orders) }} 笔可判定订单</span></article><article><p>平均配送时长</p><strong>{{ number(fulfillment.average_delivery_days, 1) }}<small>天</small></strong><span>有效时长样本 {{ number(fulfillment.delivery_sample_count) }} 笔</span></article><article><p>配送时长中位数</p><strong>{{ number(fulfillment.median_delivery_days, 1) }}<small>天</small></strong><span>下单至送达的耗时</span></article><article><p>平均订单评分</p><strong>{{ number(fulfillment.average_review_score, 2) }}<small>/ 5</small></strong><span>有评分订单 {{ number(fulfillment.reviewed_orders) }} 笔</span></article></div></section>
            <div class="two-columns"><section class="panel"><div class="panel-heading"><div><h2>交付分组与评分</h2><p>同时展示组内订单数和有评价样本数</p></div></div><el-table :data="fulfillment.groups || []" empty-text="暂无履约分组"><el-table-column prop="label" label="交付分组" min-width="105" /><el-table-column label="订单数" align="right" min-width="75"><template #default="{ row }">{{ number(row.order_count) }}</template></el-table-column><el-table-column label="有评分" align="right" min-width="75"><template #default="{ row }">{{ number(row.reviewed_orders) }}</template></el-table-column><el-table-column label="平均分" align="right" min-width="78"><template #default="{ row }">{{ number(row.average_review_score, 2) }}</template></el-table-column></el-table><p class="table-note">缺日期订单不进入延迟率分母；缺评价不计为 0 分。分组差异为描述性结果，不证明配送导致评分变化。</p></section><section class="panel"><div class="panel-heading"><div><h2>订单评分分布</h2><p>每个订单仅保留一条规范评价</p></div><span class="small-tag">单位：笔</span></div><Chart v-if="fulfillment.reviewed_orders" :option="scoreChart" label="一至五分的订单评价数量分布" /><el-empty v-else description="当前范围没有有效评分" :image-size="76" /></section></div>
          </template>
          <Customers v-if="page === 2" :scope="applied" :version="dashboard.meta.data_version" />
          <Reports v-if="page === 3" :scope="applied" :version="dashboard.meta.data_version" @week="latestWeek" />
          <div class="method-strip"><el-icon><InfoFilled /></el-icon><span>统一口径：已交付订单，按下单日期归属；品类筛选只统计所选商品金额，订单、客户和履约按关联订单去重。支付金额是整单支付，可能包含运费，与商品金额不可直接等同。</span></div>
        </template>
        <footer><span><a href="https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce" target="_blank" rel="noreferrer">Olist 公开数据</a> · <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noreferrer">CC BY-NC-SA 4.0</a><span v-if="options"> · 数据版本 {{ dashboard?.meta.data_version || options.data_version }}</span></span><a :href="staticDemo ? staticMethodology : '/docs'" target="_blank" rel="noreferrer">{{ staticDemo ? '查看数据与口径说明 ↗' : '查看接口文档 ↗' }}</a><span>历史最终状态分析 · 非实时经营数据</span></footer>
      </main>
    </div>
    <el-dialog v-model="ordersVisible" title="订单明细" width="min(1080px, 96vw)" class="orders-dialog" @close="closeOrders"><p class="dialog-description">{{ currentScope }} · {{ scopeLabel }} · 仅已交付订单</p><p class="dialog-note">商品金额仅含当前品类；支付列为整单支付（含运费等），不能汇总后作为所选品类支付金额。</p><div v-if="ordersError" class="inline-error" role="alert"><p>{{ ordersError }}</p><el-button @click="fetchOrders(orderPage)">重试订单查询</el-button></div><el-skeleton v-else-if="ordersLoading" :rows="5" animated /><template v-else-if="orders"><el-table :data="orders.rows" empty-text="当前范围没有订单"><el-table-column label="订单 ID / 查看详情" min-width="150"><template #default="{ row }"><el-button link type="primary" :title="row.order_id" :aria-label="`查看订单 ${row.order_id}`" @click="openDetail(row.order_id)">{{ row.order_id.slice(0, 12) }}…</el-button></template></el-table-column><el-table-column prop="purchase_date" label="下单日期" min-width="112" /><el-table-column prop="state" label="地区" width="58" /><el-table-column label="所选商品金额" align="right" min-width="128"><template #default="{ row }">{{ money(row.revenue_cents) }}</template></el-table-column><el-table-column label="整单支付" align="right" min-width="120"><template #default="{ row }">{{ row.payment_cents == null ? '缺记录' : money(row.payment_cents) }}</template></el-table-column><el-table-column label="交付" min-width="100"><template #default="{ row }"><span :class="{ 'late-text': row.is_late === 1 }">{{ lateLabel(row.is_late) }}</span></template></el-table-column><el-table-column label="评分" width="60" align="right"><template #default="{ row }">{{ row.review_score == null ? '缺评价' : row.review_score }}</template></el-table-column></el-table><div class="pagination-row"><span>共 {{ number(orders.total) }} 笔订单</span><el-pagination :current-page="orderPage" :page-size="10" :total="orders.total" layout="prev, pager, next" :pager-count="5" @current-change="fetchOrders" /></div></template></el-dialog>
    <el-drawer v-model="detailVisible" title="订单详情" size="min(620px, 100vw)" append-to-body @close="closeDetail"><div v-if="detailError" class="inline-error" role="alert"><p>{{ detailError }}</p><el-button @click="openDetail(selectedOrderId)">重试详情</el-button></div><el-skeleton v-else-if="detailLoading" :rows="8" animated /><template v-else-if="detail"><div class="detail-id">{{ selectedOrderId }}</div><dl class="order-facts"><div><dt>下单日期</dt><dd>{{ detail.order.purchase_date }}</dd></div><div><dt>客户所在州</dt><dd>{{ detail.order.state }}</dd></div><div><dt>当前品类商品金额</dt><dd>{{ money(detail.order.revenue_cents) }}</dd></div><div><dt>整单商品金额（不含运费）</dt><dd>{{ money(detail.order.total_order_revenue_cents) }}</dd></div><div><dt>整单支付金额（含运费等）</dt><dd>{{ detail.order.payment_cents == null ? '缺支付记录' : money(detail.order.payment_cents) }}</dd></div><div><dt>交付状态 / 订单评分</dt><dd>{{ lateLabel(detail.order.is_late) }} / {{ detail.order.review_score == null ? '缺评价' : `${detail.order.review_score} 分` }}</dd></div></dl><el-alert v-if="detail.scope_note" :title="detail.scope_note" type="info" :closable="false" show-icon /><div v-if="detail.order.quality_flags?.length" class="quality-flags"><span v-for="flag in detail.order.quality_flags" :key="flag">{{ flagLabel(flag) }}</span></div><h3 class="detail-subheading">{{ applied.category ? '当前品类商品明细' : '整单商品明细' }}</h3><article v-for="item in detail.items" :key="item.item_id" class="order-item"><div><span>商品项 {{ item.item_id }}</span><strong>{{ money(item.price_cents) }}</strong></div><p>{{ categoryLabel(item.category, item.label) }}</p><p class="id-text">商品 {{ item.product_id }}</p><p class="id-text">卖家 {{ item.seller_id }}</p><small>该商品项运费 {{ money(item.freight_cents) }}</small></article></template></el-drawer>
  </div>
</template>


