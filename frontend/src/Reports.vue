<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { getJson, number, money, categoryLabel } from './api'
const props=defineProps({ scope:{type:Object,required:true}, version:String })
defineEmits(['week'])
const report=ref(null), error=ref(''), loading=ref(false)
let controller,sequence=0
async function load(){
 controller?.abort();controller=new AbortController();const current=++sequence
 report.value=null;error.value='';loading.value=true
 try{
  const data=await getJson('/api/reports',props.scope,controller.signal)
  if(current!==sequence)return
  if(data.meta.data_source!=='olist'||data.meta.data_version!==props.version)throw new Error('数据版本未同步，请重新应用顶部筛选。')
  report.value=data
 }catch(e){if(current===sequence&&e.name!=='AbortError')error.value=e.message}
 finally{if(current===sequence)loading.value=false}
}
watch(()=>[props.scope,props.version],load,{immediate:true,deep:true})
onBeforeUnmount(()=>{++sequence;controller?.abort()})
const flags=computed(()=>report.value?.anomalies.filter(x=>['high','low'].includes(x.status))||[])
const insufficient=computed(()=>report.value?.anomalies.filter(x=>x.status==='insufficient').length||0)
const groupRows=computed(()=>['on_time','late','unknown'].map((key,i)=>({label:['按期交付','延迟交付','日期不足'][i],...report.value?.delivery.groups[key]})))
function download(format){
 const data=report.value
 if(!data)return
 const content=format==='json'?JSON.stringify(data,null,2):data.rendered[format]
 const blob=new Blob([content],{type:format==='html'?'text/html;charset=utf-8':'text/plain;charset=utf-8'})
 const url=URL.createObjectURL(blob),a=document.createElement('a')
 a.href=url;a.download=`commerce-report-${data.meta.start}-${data.meta.end}.${format==='markdown'?'md':format}`
 a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
</script>
<template>
 <section class="reports-view" aria-label="经营报告结果">
  <div v-if="loading" class="loading-state" aria-busy="true"><p>正在核对比较期、贡献变化与历史同星期基线…</p><el-skeleton :rows="6" animated /></div>
  <div v-else-if="error" class="error-state" role="alert"><h2>暂时无法生成报告</h2><p>{{ error }}</p><el-button @click="load">重试经营报告</el-button></div>
  <template v-else-if="report">
   <section class="panel"><div class="panel-heading"><div><h2>{{ report.meta.is_calendar_week?'经营周报':'经营期间报告' }}</h2><p>{{ report.meta.start }} 至 {{ report.meta.end }} · 当前品类与地区 · {{ report.meta.is_calendar_week?'周一至周日':'按所选日期，非自然周' }}</p></div><el-button @click="$emit('week')">切换至最近完整周</el-button></div>
    <div class="report-downloads"><el-button type="primary" @click="download('markdown')">下载 Markdown</el-button><el-button @click="download('html')">下载 HTML</el-button><el-button @click="download('json')">下载核对 JSON</el-button></div>
    <p class="table-note">固定模板按当前结果生成，三种文件使用同一数据快照。无额外模型调用；建议不代表已实施收益。</p>
   </section>
   <div class="kpi-grid report-kpis"><article class="kpi"><p class="kpi-label">本期商品金额</p><div class="kpi-value">{{ money(report.current.revenue_cents) }}</div><p class="kpi-hint">{{ number(report.current.order_count) }} 笔订单 · 不含运费</p></article><article class="kpi"><p class="kpi-label">比较期商品金额</p><div class="kpi-value">{{ money(report.previous?.revenue_cents) }}</div><p class="kpi-hint">{{ report.meta.comparison_start }} — {{ report.meta.comparison_end }}</p></article><article class="kpi"><p class="kpi-label">金额变化</p><div class="kpi-value">{{ money(report.delta_cents) }}</div><p class="kpi-hint">{{ report.revenue_change_rate==null?'不可计算':`${number(report.revenue_change_rate*100,2)}%` }} · {{ report.meta.comparison_label }}</p></article><article class="kpi"><p class="kpi-label">异常日期待核查</p><div class="kpi-value">{{ flags.length }}</div><p class="kpi-hint">另有 {{ insufficient }} 天数据不足，未作判断</p></article></div>
   <section class="panel"><div class="panel-heading"><div><h2>销售变化拆解</h2><p>订单量与客单价的对称算术分解，不是因果解释</p></div></div>
    <div v-if="report.decomposition" class="report-split"><p>订单量项 <strong>{{ money(report.decomposition.order_effect_cents) }}</strong></p><p>客单价项 <strong>{{ money(report.decomposition.aov_effect_cents) }}</strong></p></div><el-empty v-else description="覆盖或订单基数不足，无法拆解" :image-size="60" />
    <p class="table-note">日均金额：本期 {{ money(report.daily_revenue_cents) }}，比较期 {{ money(report.previous_daily_revenue_cents) }}。自然月天数不同，应同时看总额与日均。</p>
   </section>
   <div class="two-columns"><section v-for="(title,key) in {category:'品类金额贡献',state:'地区金额贡献'}" :key="key" class="panel"><div class="panel-heading"><div><h2>{{ title }}</h2><p>按绝对变动排序 · 前8项；完整明细见JSON</p></div></div><el-table :data="report.contributions[key].slice(0,8)" empty-text="无可比较的贡献"><el-table-column label="名称" min-width="130"><template #default="{row}">{{ key==='category'?categoryLabel(row.name):row.name }}</template></el-table-column><el-table-column label="差额 / BRL" min-width="125" align="right"><template #default="{row}">{{ money(row.delta_cents) }}</template></el-table-column></el-table><p class="table-note">每个维度完整贡献之和等于总变化；前8项可能相互抵消，不能当作全部。</p></section></div>
   <section class="panel"><div class="panel-heading"><div><h2>异常日期提示</h2><p>只使用目标日前8个同星期日；检测指标为订单量</p></div></div>
    <el-table v-if="flags.length" :data="flags"><el-table-column prop="day" label="日期" min-width="115" /><el-table-column prop="order_count" label="实际订单" min-width="90" /><el-table-column prop="baseline_median" label="历史中位数" min-width="110" /><el-table-column label="偏差阈值" min-width="100"><template #default="{row}">{{ number(row.threshold,2) }}</template></el-table-column><el-table-column label="提示" min-width="100"><template #default="{row}">{{ row.status==='high'?'偏高':'偏低' }} · 待核查</template></el-table-column></el-table>
    <el-empty v-else :description="insufficient===report.anomalies.length?'所选日期均不满足判断条件':'未发现满足当前规则的异常日期'" :image-size="60" />
    <p class="table-note">历史中位数需≥5单，偏差严格超过 max(3×1.4826×MAD, 50%×中位数, 10单) 才提示。{{ insufficient }}天数据不足。没有提示不等于没有经营问题，也不能从提示推断促销或欺诈。</p>
   </section>
   <section class="panel"><div class="panel-heading"><div><h2>履约与评价诊断</h2><p>同时展示订单与有评价样本；差异只描述相关性</p></div></div>
    <el-table :data="groupRows"><el-table-column prop="label" label="交付组" min-width="105" /><el-table-column prop="order_count" label="订单数" min-width="85" /><el-table-column prop="reviewed_orders" label="有评价" min-width="85" /><el-table-column prop="missing_reviews" label="缺评价" min-width="85" /><el-table-column label="均分" min-width="75"><template #default="{row}">{{ number(row.mean_score,3) }}</template></el-table-column><el-table-column label="中位数" min-width="85"><template #default="{row}">{{ number(row.median_score,1) }}</template></el-table-column></el-table>
    <p class="table-note">JSON还保留品类、地区分层及1–5分分布。各层两组至少20条评价才给出层内差值；这不是显著性门槛，仍有选择偏差与混杂因素。</p>
   </section>
   <details class="report-preview"><summary>查看完整报告正文与解释限制</summary><pre>{{ report.rendered.markdown }}</pre></details>
   <p class="table-note">数据版本 {{ report.meta.data_version }} · 规则 {{ report.meta.rule_version }}</p>
  </template>
 </section>
</template>
<style scoped>
.report-downloads{display:flex;flex-wrap:wrap;gap:10px}.report-downloads .el-button{margin:0}.report-split{display:flex;gap:35px;flex-wrap:wrap;color:#647b8b;font-size:13px}.report-split strong{display:block;margin-top:10px;font-size:22px;color:#167f77}.report-preview{background:#edf4f2;border-radius:8px;padding:18px;font-size:12px;line-height:1.8;color:#547c77;margin-bottom:16px}.report-preview summary{cursor:pointer}.report-preview pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.8 inherit}.report-kpis .kpi-value{font-size:24px}@media(max-width:600px){.panel-heading{flex-wrap:wrap}.report-kpis .kpi-value{font-size:18px}.report-split{gap:20px}}
</style>
