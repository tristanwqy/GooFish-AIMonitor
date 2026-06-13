export const yuan = (n) => '¥' + Math.round(Number(n) || 0).toLocaleString('zh-CN')

// 闲鱼图走 alicdn, 部分是 .heic; 追加尺寸后缀强制转 jpg, 浏览器才能渲染。
export function imgSrc(u) {
  if (!u) return ''
  return u.includes('alicdn.com') ? u + '_400x400q90.jpg' : u
}

export const splitCsv = (s) =>
  (s || '')
    .split(/[,，]/)
    .map((x) => x.trim())
    .filter(Boolean)

// 后端发的是带 +00:00 的 UTC ISO; new Date 解析后按本地时区显示。
const pad = (n) => String(n).padStart(2, '0')

export function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function fmtDateTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function ago(iso) {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  const d = Math.floor(s / 86400)
  return d < 30 ? `${d} 天前` : fmtDate(iso)
}
