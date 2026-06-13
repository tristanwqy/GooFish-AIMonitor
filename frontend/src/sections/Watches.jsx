import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Button, Badge, Spinner, EmptyState, Toggle, Field } from '../components/ui'
import { splitCsv } from '../util'

const blank = () => ({
  id: null,
  name: '',
  keywordsText: '',
  price_min: '',
  price_max: '',
  city: '',
  conditionText: '',
  requirement: '',
  free_shipping: false,
  enabled: true,
})

export default function Watches() {
  const [list, setList] = useState(null)
  const [form, setForm] = useState(blank())

  const load = () => api.watches().then(setList)
  useEffect(() => {
    load()
  }, [])

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const save = async () => {
    if (!form.name.trim() || !form.keywordsText.trim()) return
    const body = {
      name: form.name.trim(),
      keywords: splitCsv(form.keywordsText),
      price_min: form.price_min === '' ? null : Number(form.price_min),
      price_max: form.price_max === '' ? null : Number(form.price_max),
      city: form.city.trim() || null,
      condition: form.conditionText.trim() ? splitCsv(form.conditionText) : null,
      requirement: form.requirement.trim() || null,
      free_shipping: form.free_shipping || null,
      enabled: form.enabled,
    }
    if (form.id) await api.updateWatch(form.id, body)
    else await api.createWatch(body)
    setForm(blank())
    load()
  }

  const edit = (w) =>
    setForm({
      id: w.id,
      name: w.name,
      keywordsText: (w.keywords || []).join(', '),
      price_min: w.price_min ?? '',
      price_max: w.price_max ?? '',
      city: w.city ?? '',
      conditionText: (w.condition || []).join(', '),
      requirement: w.requirement ?? '',
      free_shipping: !!w.free_shipping,
      enabled: w.enabled,
    })

  const toggleEnabled = async (w) => {
    await api.updateWatch(w.id, {
      name: w.name,
      keywords: w.keywords,
      price_min: w.price_min,
      price_max: w.price_max,
      city: w.city,
      condition: w.condition,
      requirement: w.requirement,
      free_shipping: w.free_shipping,
      enabled: !w.enabled,
    })
    load()
  }

  const remove = async (id) => {
    await api.deleteWatch(id)
    load()
  }

  if (list === null) return <Spinner />

  return (
    <section>
      <h1 className="page-title">监控条件</h1>
      <p className="page-sub">关键词与价格范围等，定时按这些条件搜索并推荐。</p>

      <Card className="form-card">
        <div className="form-title">{form.id ? '编辑条件' : '新增条件'}</div>
        <div className="form-grid">
          <Field label="名称">
            <input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="iPhone15Pro" />
          </Field>
          <Field label="搜索词" hint="整体作为一条搜索词去搜（空格分隔），不是逐词分搜">
            <input
              value={form.keywordsText}
              onChange={(e) => set('keywordsText', e.target.value)}
              placeholder="MacBook Pro M1 Pro 16寸 32G 1T"
            />
          </Field>
          <Field label="最低价">
            <input type="number" value={form.price_min} onChange={(e) => set('price_min', e.target.value)} />
          </Field>
          <Field label="最高价">
            <input type="number" value={form.price_max} onChange={(e) => set('price_max', e.target.value)} />
          </Field>
          <Field label="城市（可选）">
            <input value={form.city} onChange={(e) => set('city', e.target.value)} placeholder="上海" />
          </Field>
          <Field label="成色（逗号分隔，可选）">
            <input
              value={form.conditionText}
              onChange={(e) => set('conditionText', e.target.value)}
              placeholder="99新, 几乎全新"
            />
          </Field>
        </div>
        <div className="req-field">
          <Field
            label="AI 审核要求（自然语言，可选）"
            hint="定时搜索命中后，交给大模型按这段要求二次筛选；不符合的不会进推荐。"
          >
            <textarea
              className="req-input"
              rows={3}
              value={form.requirement}
              onChange={(e) => set('requirement', e.target.value)}
              placeholder="例：只要 14 寸 M5 Pro 国行本机，48G 以上，成色 95 新以上，价格不超过 19000，排除 16 寸 / Max 芯片 / 未拆封全新 / 配件 / 维修"
            />
          </Field>
        </div>
        <div className="form-row">
          <Toggle checked={form.free_shipping} onChange={(v) => set('free_shipping', v)} label="仅包邮" />
          <Toggle checked={form.enabled} onChange={(v) => set('enabled', v)} label="启用" />
          <div className="grow" />
          {form.id && (
            <Button variant="ghost" onClick={() => setForm(blank())}>
              取消
            </Button>
          )}
          <Button onClick={save}>{form.id ? '保存' : '添加'}</Button>
        </div>
      </Card>

      {list.length === 0 ? (
        <EmptyState title="还没有监控条件" sub="在上面添加一个，定时任务就会开始找货" />
      ) : (
        <div className="watch-list">
          {list.map((w) => (
            <Card key={w.id} className="watch-row">
              <div className="watch-main">
                <div className="watch-name">
                  {w.name}
                  {!w.enabled && <span className="muted-tag">已停用</span>}
                </div>
                <div className="watch-kw">{(w.keywords || []).join(' · ')}</div>
                <div className="rec-meta">
                  {(w.price_min || w.price_max) && (
                    <span>
                      ¥{w.price_min ?? 0} – {w.price_max ?? '∞'}
                    </span>
                  )}
                  {w.city && <span>{w.city}</span>}
                  {w.free_shipping && <Badge>包邮</Badge>}
                  {(w.condition || []).map((c) => (
                    <span key={c}>{c}</span>
                  ))}
                </div>
                {w.requirement && (
                  <div className="watch-req">
                    <span className="watch-req-tag">AI</span>
                    {w.requirement}
                  </div>
                )}
              </div>
              <div className="watch-actions">
                <Toggle checked={w.enabled} onChange={() => toggleEnabled(w)} />
                <Button variant="ghost" className="btn-sm" onClick={() => edit(w)}>
                  编辑
                </Button>
                <Button variant="ghost" className="btn-sm btn-danger" onClick={() => remove(w.id)}>
                  删除
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </section>
  )
}
