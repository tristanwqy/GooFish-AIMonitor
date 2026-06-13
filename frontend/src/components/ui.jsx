import { imgSrc } from '../util'

export function Button({ variant = 'primary', className = '', children, ...p }) {
  return (
    <button className={`btn btn-${variant} ${className}`} {...p}>
      {children}
    </button>
  )
}

export function Card({ className = '', children }) {
  return <div className={`card ${className}`}>{children}</div>
}

export function Badge({ tone = '', children }) {
  return <span className={`badge ${tone ? `badge-${tone}` : ''}`}>{children}</span>
}

export function Spinner() {
  return (
    <div className="spinner-wrap">
      <div className="spinner" />
    </div>
  )
}

export function EmptyState({ title, sub }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {sub && <div className="empty-sub">{sub}</div>}
    </div>
  )
}

export function Toggle({ checked, onChange, label }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" />
      {label && <span className="tog-label">{label}</span>}
    </label>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

// items: [['发布', '3天前'], ...] — 自动过滤空值
export function TimeMeta({ items }) {
  const shown = (items || []).filter(([, v]) => v)
  if (!shown.length) return null
  return (
    <div className="time-meta">
      {shown.map(([k, v]) => (
        <span key={k} className="tm-item">
          <span className="tm-k">{k}</span>
          {v}
        </span>
      ))}
    </div>
  )
}

// 统一的应用内对话框, 取代原生 window.confirm/alert(那些带 "localhost:8000 显示" 的丑框)
export function ConfirmDialog({
  open,
  title,
  message,
  confirmText = '确定',
  cancelText = '取消',
  danger = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" role="dialog" onClick={(e) => e.stopPropagation()}>
        {title && <div className="modal-title">{title}</div>}
        {message && <div className="modal-body">{message}</div>}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onCancel}>
            {cancelText}
          </button>
          <button className={'btn ' + (danger ? 'btn-danger-solid' : 'btn-primary')} onClick={onConfirm}>
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}

export function Thumb({ url, dead = false, deadReason = '' }) {
  const cls = `thumb${url ? '' : ' thumb-empty'}${dead ? ' thumb-dead' : ''}`
  return (
    <div className={cls}>
      {url && (
        <img
          src={imgSrc(url)}
          alt=""
          loading="lazy"
          onError={(e) => {
            e.currentTarget.style.display = 'none'
          }}
        />
      )}
      {dead && <span className="thumb-dead-label">{deadReason || '已下架'}</span>}
    </div>
  )
}
