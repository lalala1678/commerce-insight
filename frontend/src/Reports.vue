<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { getJson, number, money, categoryLabel } from './api'
const props=defineProps({ scope:{type:Object,required:true}, version:String })
defineEmits(['week'])
const report=ref(null), error=ref(''), loading=ref(false)
const reviewByTask=ref({}), reviewWarning=ref('')
let controller,sequence=0
const reviewStatuses=[{value:'pending',label:'待核查'},{value:'working',label:'核查中'},{value:'recorded',label:'已写核查记录'}]
function reviewKey(meta,task){
 return `commerce-insight:investigation:v1:${JSON.stringify([meta.data_version,meta.start,meta.end,meta.category||'',meta.state||'',task.id])}`
}
function readReview(meta,task){
 const fallback={status:'pending',owner:'',note:'',saved_at:null}
 try{
  const saved=JSON.parse(localStorage.getItem(reviewKey(meta,task))||'null')
  if(!saved||typeof saved!=='object')return fallback
  return {status:reviewStatuses.some(x=>x.value===saved.status)?saved.status:'pending',
          owner:String(saved.owner||'').slice(0,40),note:String(saved.note||'').slice(0,1000),
          saved_at:typeof saved.saved_at==='string'?saved.saved_at:null}
 }catch{
  reviewWarning.value='无法读取本机核查记录；可下载记录 JSON 保存当前填写内容。'
  return fallback
 }
}
function saveReview(task){
 const item=reviewByTask.value[task.id]
 if(!item||!report.value)return
 let downgraded=false
 if(item.status==='recorded'&&!item.note.trim()){
  item.status='working';downgraded=true
 }
 try{
  const savedAt=new Date().toISOString()
  localStorage.setItem(reviewKey(report.value.meta,task),JSON.stringify({...item,saved_at:savedAt}))
  item.saved_at=savedAt
  reviewWarning.value=downgraded?'写下核查记录后，才能标记为“已写核查记录”。':''
 }catch{
  reviewWarning.value='浏览器未能保存核查进度；请下载核查记录 JSON。'
 }
}
async function load(){
 controller?.abort();controller=new AbortController();const current=++sequence
 report.value=null;error.value='';loading.value=true
 try{
  const data=await getJson('/api/reports',props.scope,controller.signal)
  if(current!==sequence)return
  if(data.meta.data_source!=='olist'||data.meta.data_version!==props.version)throw new Error('数据版本未同步，请重新应用顶部筛选。')
  reviewWarning.value=''
  reviewByTask.value=Object.fromEntries((data.investigations||[]).map(task=>[task.id,readReview(data.meta,task)]))
  report.value=data
 }catch(e){if(current===sequence&&e.name!=='AbortError')error.value=e.message}
 finally{if(current===sequence)loading.value=false}
}
watch(()=>[props.scope,props.version],load,{immediate:true,deep:true})
onBeforeUnmount(()=>{++sequence;controller?.abort()})
const flags=computed(()=>report.value?.anomalies.filter(x=>['high','low'].includes(x.status))||[])
const insufficient=computed(()=>report.value?.anomalies.filter(x=>x.status==='insufficient').length||0)
const groupRows=computed(()=>['on_time','late','unknown'].map((key,i)=>({label:['按期交付','延迟交付','日期不足'][i],...report.value?.delivery.groups[key]})))
function evidenceValue(item){
 if(item.unit==='cents')return money(item.value)
 if(item.unit==='score')return `${number(item.value,3)} 分`
 return `${number(item.value)} 单`
}
function saveFile(filename,content,type){
 const blob=new Blob([content],{type}),url=URL.createObjectURL(blob),a=document.createElement('a')
 a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
function download(format){
 const data=report.value
 if(!data)return
 const content=format==='json'?JSON.stringify(data,null,2):data.rendered[format]
 saveFile(`commerce-report-${data.meta.start}-${data.meta.end}.${format==='markdown'?'md':format}`,
          content,format==='html'?'text/html;charset=utf-8':'text/plain;charset=utf-8')
}
function downloadTaskReviews(){
 const data=report.value
 if(!data)return
 for(const task of data.investigations||[])saveReview(task)
 const content=JSON.stringify({data_source:data.meta.data_source,data_version:data.meta.data_version,
   scope:{start:data.meta.start,end:data.meta.end,category:data.meta.category,state:data.meta.state},
   exported_at:new Date().toISOString(),storage:'本机浏览器；未同步到服务器',
   tasks:(data.investigations||[]).map(task=>({task,review:reviewByTask.value[task.id]}))},null,2)
 saveFile(`commerce-investigations-${data.meta.start}-${data.meta.end}.json`,content,'application/json;charset=utf-8')
}
</script>
<template>
 <section class="reports-view" aria-label="经营报告结果">
  <div v-if="loading" class="loading-state" aria-busy="true"><p>正在核对比较期、贡献变化与历史同星期基线…</p><el-skeleton :rows="6" animated /></div>
  <div v-else-if="error" class="error-state" role="alert"><h2>暂时无法生成报告</h2><p>{{ error }}</p><el-button @click="load">重试经营报告</el-button></div>
  <template v-else-if="report">
   <section class="panel"><div class="panel-heading"><div><h2>{{ report.meta.is_calendar_week?'经营周报':'经营期间报告' }}</h2><p>{{ report.meta.start }} 至 {{ report.meta.end }} · {{ report.meta.category||'全部品类' }} · {{ report.meta.state||'全部客户州' }} · {{ report.meta.is_calendar_week?'周一至周日':'按所选日期，非自然周' }}</p></div><el-button @click="$emit('week')">切换至最近完整周</el-button></div>
    <div class="report-downloads"><el-button type="primary" @click="download('markdown')">下载 Markdown</el-button><el-button @click="download('html')">下载 HTML</el-button><el-button @click="download('json')">下载核对 JSON</el-button></div>
    <p class="table-note">固定模板按当前结果生成，三种文件使用同一数据快照。无额外模型调用；建议不代表已实施收益。</p>
   </section>
   <div class="kpi-grid report-kpis"><article class="kpi"><p class="kpi-label">本期商品金额</p><div class="kpi-value">{{ money(report.current.revenue_cents) }}</div><p class="kpi-hint">{{ number(report.current.order_count) }} 笔订单 · 不含运费</p></article><article class="kpi"><p class="kpi-label">比较期商品金额</p><div class="kpi-value">{{ money(report.previous?.revenue_cents) }}</div><p class="kpi-hint">{{ report.meta.comparison_start }} — {{ report.meta.comparison_end }}</p></article><article class="kpi"><p class="kpi-label">金额变化</p><div class="kpi-value">{{ money(report.delta_cents) }}</div><p class="kpi-hint">{{ report.revenue_change_rate==null?'不可计算':`${number(report.revenue_change_rate*100,2)}%` }} · {{ report.meta.comparison_label }}</p></article><article class="kpi"><p class="kpi-label">异常日期待核查</p><div class="kpi-value">{{ flags.length }}</div><p class="kpi-hint">另有 {{ insufficient }} 天数据不足，未作判断</p></article></div>
   <section class="panel" aria-label="待核查任务"><div class="panel-heading"><div><h2>把发现转成核查任务</h2><p>每项任务保留观察事实、证据位置、待验证假设和验证指标；任务状态由你填写</p></div><el-button :disabled="!report.investigations?.length" @click="downloadTaskReviews">下载核查记录 JSON</el-button></div>
    <p v-if="reviewWarning" class="review-warning" role="alert">{{ reviewWarning }}</p>
    <div v-if="report.investigations?.length" class="investigation-list">
     <article v-for="task in report.investigations" :key="task.id" class="investigation-card">
      <div class="investigation-heading"><h3>{{ task.title }}</h3><el-tag type="warning" effect="plain">尚未验证</el-tag></div>
      <p><strong>观察事实：</strong>{{ task.observation }}</p>
      <p><strong>待验证假设：</strong>{{ task.hypothesis }}</p>
      <p class="investigation-subtitle">可追溯证据</p>
      <ul class="investigation-evidence"><li v-for="item in task.evidence" :key="item.pointer"><a :href="`#${item.anchor}`">{{ item.label }}</a>：{{ evidenceValue(item) }} <code>{{ item.pointer }}</code></li></ul>
      <p class="investigation-subtitle">下一步核查</p><ol><li v-for="step in task.checks" :key="step">{{ step }}</li></ol>
      <p><strong>尚缺数据：</strong>{{ task.missing_data.join('；') }}</p>
      <p><strong>验证指标：</strong>{{ task.verification_metric }}</p>
      <div class="review-controls"><label>负责人代号<el-input v-model="reviewByTask[task.id].owner" maxlength="40" placeholder="角色或代号，可留空" @blur="saveReview(task)" /></label><label>核查进度<el-select v-model="reviewByTask[task.id].status" @change="saveReview(task)"><el-option v-for="item in reviewStatuses" :key="item.value" :label="item.label" :value="item.value" /></el-select></label></div>
      <label class="review-note">核查记录<el-input v-model="reviewByTask[task.id].note" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="记录已查证的资料、仍未解决的问题或下一次复核日期" @blur="saveReview(task)" /></label>
      <p class="table-note">仅存于当前浏览器；不上传服务器，清理浏览器数据会丢失。请勿填写真实姓名或商业敏感信息。{{ reviewByTask[task.id].saved_at?`上次保存：${reviewByTask[task.id].saved_at}`:'' }}</p>
     </article>
    </div><el-empty v-else description="比较期或评价样本不足，当前无法提出有证据的核查任务" :image-size="60" />
   </section>
   <section id="sales-breakdown" class="panel"><div class="panel-heading"><div><h2>销售变化拆解</h2><p>订单量与客单价的对称算术分解，不是因果解释</p></div></div>
    <div v-if="report.decomposition" class="report-split"><p>订单量项 <strong>{{ money(report.decomposition.order_effect_cents) }}</strong></p><p>客单价项 <strong>{{ money(report.decomposition.aov_effect_cents) }}</strong></p></div><el-empty v-else description="覆盖或订单基数不足，无法拆解" :image-size="60" />
    <p class="table-note">日均金额：本期 {{ money(report.daily_revenue_cents) }}，比较期 {{ money(report.previous_daily_revenue_cents) }}。自然月天数不同，应同时看总额与日均。</p>
   </section>
   <div class="two-columns"><section v-for="(title,key) in {category:'品类金额贡献',state:'地区金额贡献'}" :id="`${key}-contribution`" :key="key" class="panel"><div class="panel-heading"><div><h2>{{ title }}</h2><p>按绝对变动排序 · 前8项；完整明细见JSON</p></div></div><el-table :data="report.contributions[key].slice(0,8)" empty-text="无可比较的贡献"><el-table-column label="名称" min-width="130"><template #default="{row}">{{ key==='category'?categoryLabel(row.name):row.name }}</template></el-table-column><el-table-column label="差额 / BRL" min-width="125" align="right"><template #default="{row}">{{ money(row.delta_cents) }}</template></el-table-column></el-table><p class="table-note">每个维度完整贡献之和等于总变化；前8项可能相互抵消，不能当作全部。</p></section></div>
   <section class="panel"><div class="panel-heading"><div><h2>异常日期提示</h2><p>只使用目标日前8个同星期日；检测指标为订单量</p></div></div>
    <el-table v-if="flags.length" :data="flags"><el-table-column prop="day" label="日期" min-width="115" /><el-table-column prop="order_count" label="实际订单" min-width="90" /><el-table-column prop="baseline_median" label="历史中位数" min-width="110" /><el-table-column label="偏差阈值" min-width="100"><template #default="{row}">{{ number(row.threshold,2) }}</template></el-table-column><el-table-column label="提示" min-width="100"><template #default="{row}">{{ row.status==='high'?'偏高':'偏低' }} · 待核查</template></el-table-column></el-table>
    <el-empty v-else :description="insufficient===report.anomalies.length?'所选日期均不满足判断条件':'未发现满足当前规则的异常日期'" :image-size="60" />
    <p class="table-note">历史中位数需≥5单，偏差严格超过 max(3×1.4826×MAD, 50%×中位数, 10单) 才提示。{{ insufficient }}天数据不足。没有提示不等于没有经营问题，也不能从提示推断促销或欺诈。</p>
   </section>
   <section id="delivery-diagnosis" class="panel"><div class="panel-heading"><div><h2>履约与评价诊断</h2><p>同时展示订单与有评价样本；差异只描述相关性</p></div></div>
    <el-table :data="groupRows"><el-table-column prop="label" label="交付组" min-width="105" /><el-table-column prop="order_count" label="订单数" min-width="85" /><el-table-column prop="reviewed_orders" label="有评价" min-width="85" /><el-table-column prop="missing_reviews" label="缺评价" min-width="85" /><el-table-column label="均分" min-width="75"><template #default="{row}">{{ number(row.mean_score,3) }}</template></el-table-column><el-table-column label="中位数" min-width="85"><template #default="{row}">{{ number(row.median_score,1) }}</template></el-table-column></el-table>
    <div class="delivery-strata"><div v-for="(title,key) in {category:'品类',state:'客户州'}" :key="key"><h3>{{ title }}分层中可比较的前5组</h3><el-table :data="report.delivery.strata[key].filter(x=>x.comparison_eligible).slice(0,5)" empty-text="两组评价样本不足"><el-table-column label="名称" min-width="110"><template #default="{row}">{{ key==='category'?categoryLabel(row.name):row.name }}</template></el-table-column><el-table-column label="按期 / 延迟评价数" min-width="125"><template #default="{row}">{{ row.on_time.reviewed_orders }} / {{ row.late.reviewed_orders }}</template></el-table-column><el-table-column label="均分差" min-width="80"><template #default="{row}">{{ number(row.score_gap,3) }}</template></el-table-column></el-table></div></div>
    <p class="table-note">上方仅显示可比较分层的前5组；完整品类、地区及1–5分分布见JSON。各层两组至少20条评价才给出层内差值；这不是显著性门槛，仍有选择偏差与混杂因素。</p>
   </section>
   <details class="report-preview"><summary>查看完整报告正文与解释限制</summary><pre>{{ report.rendered.markdown }}</pre></details>
   <p class="table-note">数据版本 {{ report.meta.data_version }} · 规则 {{ report.meta.rule_version }}</p>
  </template>
 </section>
</template>
<style scoped>
.report-downloads{display:flex;flex-wrap:wrap;gap:10px}.report-downloads .el-button{margin:0}.report-split{display:flex;gap:35px;flex-wrap:wrap;color:#647b8b;font-size:13px}.report-split strong{display:block;margin-top:10px;font-size:22px;color:#167f77}.report-preview{background:#edf4f2;border-radius:8px;padding:18px;font-size:12px;line-height:1.8;color:#547c77;margin-bottom:16px}.report-preview summary{cursor:pointer}.report-preview pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.8 inherit}.report-kpis .kpi-value{font-size:24px}
.investigation-list{display:grid;gap:16px}.investigation-card{border:1px solid #dbe9e6;background:#f9fcfb;border-radius:10px;padding:18px}.investigation-card p{line-height:1.7}.investigation-heading{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.investigation-heading h3{margin:0;color:#214b50}.investigation-subtitle{font-weight:700;margin-bottom:5px}.investigation-evidence{padding-left:22px}.investigation-evidence li,.investigation-card ol li{margin:5px 0;line-height:1.6}.investigation-evidence a{color:#087c73;text-decoration:underline}.investigation-evidence code{display:inline-block;margin-left:8px;color:#667d82;font-size:11px;overflow-wrap:anywhere}.review-controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:18px}.review-controls label,.review-note{display:block;font-weight:600;color:#375b60}.review-controls .el-input,.review-controls .el-select,.review-note .el-textarea{display:block;margin-top:6px;width:100%}.review-note{margin-top:12px}.review-warning{border-radius:6px;padding:10px;background:#fff5df;color:#764e0c}
.delivery-strata{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-top:16px}.delivery-strata h3{font-size:14px;color:#365b5e}
@media(max-width:700px){.delivery-strata{grid-template-columns:1fr}}@media(max-width:600px){.panel-heading{flex-wrap:wrap}.report-kpis .kpi-value{font-size:18px}.report-split{gap:20px}.review-controls{grid-template-columns:1fr}.investigation-card{padding:14px}}
</style>
