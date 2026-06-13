import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Button, Badge, Spinner, EmptyState, Thumb, TimeMeta } from '../components/ui'
import { yuan, fmtDate, fmtDateTime, ago } from '../util'

export default function Recommendations({ refreshKey, onToast }) {
  const [items, setItems] = useState(null)
  const [busy, setBusy] = useState({})
  const [muteOpen, setMuteOpen] = useState(null)
  const [onlyPassed, setOnlyPassed] = useState(true) // 默认只看 LLM 通过的

  const load = () => api.recommendations('new').then(setItems)
  useEffect(() => {
    load()
  }, [refreshKey])

  const act = async (id, fn) => {
    setBusy((b) => ({ ...b, [id]: true }))
    try {
      const r = await fn(id)
      if (r && r.ok === false) {                 // 收藏没真成功 → 保留卡片 + 提示, 不再假装成功
        onToast?.('收藏没成功（可能遇到验证或网络波动），卡片已保留，可稍后重试')
        return
      }
      setItems((xs) => xs.filter((x) => x.item_id !== id))
    } finally {
      setBusy((b) => ({ ...b, [id]: false }))
    }
  }

  const mute = (id, days) => {
    setMuteOpen(null)
    act(id, () => api.mute(id, days))
  }

  const renderCard = (it) => {
    const failed = it.rec_ok === false
    return (
    <Card key={it.item_id} className={`rec${it.dead ? ' dead' : ''}${failed ? ' failed' : ''}`}>
      <Thumb url={it.pic_url} dead={it.dead} deadReason={it.dead_reason} />
      <div className="rec-body">
        <a className="rec-title" href={it.url} target="_blank" rel="noreferrer">
          {it.title}
        </a>
        <div className="rec-price">{yuan(it.price)}</div>
        <div className="rec-meta">
          {it.location && <span>{it.location}</span>}
          {it.condition && <span>{it.condition}</span>}
          {it.free_shipping && <Badge>包邮</Badge>}
        </div>
        {it.reason && (
          <div className={`rec-reason${failed ? ' rejected' : ''}`}>
            <span className="rec-reason-tag">{failed ? '未通过' : 'AI'}</span>
            <span>{it.reason}</span>
          </div>
        )}
        <TimeMeta
          items={[
            ['上架', ago(it.publish_time)],
            ['推荐', fmtDateTime(it.rec_created_at)],
            ['调价', fmtDate(it.price_changed_at)],
          ]}
        />
        <div className="rec-actions">
          {!it.dead && (
            <Button disabled={busy[it.item_id]} onClick={() => act(it.item_id, api.approve)}>
              {busy[it.item_id] ? '收藏中…' : '收藏'}
            </Button>
          )}
          <Button
            variant="ghost"
            disabled={busy[it.item_id]}
            onClick={() => act(it.item_id, api.reject)}
          >
            {it.dead ? '移除' : '忽略'}
          </Button>
        </div>
        {!it.dead && (
          <div className="mute-row">
            <button
              className="mute-trigger"
              disabled={busy[it.item_id]}
              onClick={() => setMuteOpen(muteOpen === it.item_id ? null : it.item_id)}
            >
              近期不看 ▾
            </button>
            {muteOpen === it.item_id && (
              <div className="mute-menu">
                <button onClick={() => mute(it.item_id, 1)}>1 天内不看</button>
                <button onClick={() => mute(it.item_id, 7)}>7 天内不看</button>
                <button onClick={() => mute(it.item_id, 0)}>永远不看</button>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
    )
  }

  if (items === null) return <Spinner />

  const passedCount = items.filter((x) => x.rec_ok !== false).length
  const shown = onlyPassed ? items.filter((x) => x.rec_ok !== false) : items

  // 按监控条件(watch)分组, 保持原有顺序(死链末尾 / 新推荐在前)
  const order = []
  const byWatch = {}
  for (const it of shown) {
    const k = it.watch_name || '未分组'
    if (!byWatch[k]) {
      byWatch[k] = []
      order.push(k)
    }
    byWatch[k].push(it)
  }

  return (
    <section>
      <h1 className="page-title">
        待审推荐 {shown.length > 0 && <span className="count">{shown.length}</span>}
      </h1>
      <p className="page-sub">定时发现你没见过的商品，你来决定收藏或忽略。按监控条件分组。</p>
      {items.length > 0 && (
        <div className="rec-filter">
          <button className={`seg${onlyPassed ? ' on' : ''}`} onClick={() => setOnlyPassed(true)}>
            仅 LLM 通过 <b>{passedCount}</b>
          </button>
          <button className={`seg${!onlyPassed ? ' on' : ''}`} onClick={() => setOnlyPassed(false)}>
            全部 <b>{items.length}</b>
          </button>
        </div>
      )}
      {shown.length === 0 ? (
        <EmptyState
          title={onlyPassed && items.length > 0 ? '本轮没有 LLM 通过的' : '暂无新推荐'}
          sub={
            onlyPassed && items.length > 0
              ? `有 ${items.length} 条候选未通过审核，点「全部」查看原因`
              : '定时任务会按你的条件自动发现新商品'
          }
        />
      ) : (
        order.map((name) => (
          <div key={name} className="rec-group">
            <div className="rec-group-head">
              <span className="rec-group-name">{name}</span>
              <span className="rec-group-count">{byWatch[name].length}</span>
            </div>
            <div className="grid">{byWatch[name].map(renderCard)}</div>
          </div>
        ))
      )}
    </section>
  )
}
