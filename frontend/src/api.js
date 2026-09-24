// A request failure stays a failure: never substitute demonstration values.
export const staticDemo = import.meta.env.VITE_STATIC_DEMO === '1'
let staticOptionsPromise

async function fetchJson(url, signal) {
  const response = await fetch(url, { signal })
  let body
  try { body = await response.json() } catch {
    throw new Error(staticDemo ? '静态数据文件无法读取，请刷新或稍后再试。' : '接口未返回有效数据，请确认后端服务已经启动。')
  }
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : null
    throw new Error(detail || `查询失败（${response.status}），请检查筛选范围或稍后重试。`)
  }
  return body
}

async function getStaticJson(path, params, signal) {
  const base = `${import.meta.env.BASE_URL}static-data/`
  if (path === '/api/options') {
    staticOptionsPromise ||= fetchJson(`${base}options.json`)
    return staticOptionsPromise
  }
  const options = await (staticOptionsPromise ||= fetchJson(`${base}options.json`))
  if (signal?.aborted) throw new DOMException('Request aborted', 'AbortError')
  const preset = options.static_presets.find(item =>
    ['start', 'end', 'category', 'state'].every(key => item[key] === (params[key] || '')))
  if (!preset) throw new Error('此筛选范围未预先导出。请选择页面中的演示范围。')
  let filename
  if (path === '/api/dashboard') filename = `dashboard-${params.grain || 'day'}.json`
  else if (path === '/api/customers') filename = 'customers.json'
  else if (path === '/api/reports') filename = 'reports.json'
  else throw new Error('静态演示仅提供聚合分析；订单级明细请在本地后台查看。')
  const result = await fetchJson(`${base}${preset.id}/${filename}`, signal)
  if (result.meta?.data_version !== options.data_version) throw new Error('静态文件的数据版本不一致，请刷新页面。')
  return result
}

export async function getJson(path, params = {}, signal) {
  if (staticDemo) return getStaticJson(path, params, signal)
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== '' && value != null) search.set(key, String(value))
  }
  return fetchJson(`${path}${search.size ? `?${search}` : ''}`, signal)
}

export const number = (value, digits = 0) => value == null ? '—' : Number(value).toLocaleString('zh-CN', {
  minimumFractionDigits: digits, maximumFractionDigits: digits,
})
export const money = cents => cents == null ? '不可计算' : `R$ ${number(cents / 100, 2)}`
export const percent = value => value == null ? '不可计算' : `${number(value * 100, 1)}%`

const categoryNames = {
  cama_mesa_banho: '床上与卫浴', beleza_saude: '健康美容', esporte_lazer: '运动休闲',
  moveis_decoracao: '家具装饰', informatica_acessorios: '电脑配件', utilidades_domesticas: '家居日用',
  relogios_presentes: '手表与礼品', telefonia: '手机通讯', ferramentas_jardim: '园艺工具',
  automotivo: '汽车用品', brinquedos: '玩具', perfumaria: '香水', bebes: '婴童用品',
  unknown: '未分类', unclassified: '未分类', '__unknown__': '未分类',
}
export function categoryLabel(value, translated) {
  return categoryNames[value] || (translated || value || '未分类').replaceAll('_', ' ')
}
