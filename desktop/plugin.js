/**
 * hermes-wiki desktop plugin — Wiki viewer/editor in the sidebar.
 *
 * Features: list, search, create, edit, delete, multi-select, export.
 * Data flows through gateway JSON-RPC: wiki.list, wiki.get, wiki.create,
 * wiki.update, wiki.delete, wiki.stats, wiki.batch_process.
 */

import { cn, haptic, host, Tip, useValue, Codicon, Badge, Button, SearchField, ScrollArea, EmptyState, Separator, Tooltip, ConfirmDialog } from '@hermes/plugin-sdk'
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'
import { useState, useEffect, useCallback } from 'react'
import { ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'

// ── Gateway RPC helpers ────────────────────────────────────────────────

async function wikiList(params = {}) {
  try { return await host.request('wiki.list', params) }
  catch (e) { return { pages: [], count: 0 } }
}

async function wikiGet(slug) {
  try { return await host.request('wiki.get', { slug }) }
  catch (e) { return null }
}

async function wikiCreate(params) { return host.request('wiki.create', params) }
async function wikiUpdate(params) { return host.request('wiki.update', params) }
async function wikiDelete(slug) { return host.request('wiki.delete', { slug }) }

async function wikiStats() {
  try { return await host.request('wiki.stats', {}) }
  catch (e) { return { total: 0, by_type: {}, avg_quality: 0 } }
}

async function wikiBatchProcess(limit = 20) {
  try { return await host.request('wiki.batch_process', { limit }) }
  catch (e) { return { enqueued: 0 } }
}

async function wikiListTopics() {
  try { return await host.request('wiki.list_topics', {}) }
  catch (e) { return { topics: [], count: 0 } }
}

async function wikiGetTopic(slug) {
  try { return await host.request('wiki.get_topic', { slug }) }
  catch (e) { return null }
}

// ── Export helpers ─────────────────────────────────────────────────────

function downloadFile(filename, content) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

async function exportPages(slugs, format = 'individual') {
  if (slugs.length === 0) return
  let exported = 0
  for (const slug of slugs) {
    const page = await wikiGet(slug)
    if (!page) continue
    const filename = `${slug}.md`
    downloadFile(filename, page.full_content || `# ${page.title}\n\nNo content`)
    exported++
    await new Promise(r => setTimeout(r, 100)) // stagger downloads
  }
  host.notify({ kind: 'info', message: `Exported ${exported} page(s)` })
}

async function exportPagesCombined(slugs) {
  if (slugs.length === 0) return
  const parts = []
  for (const slug of slugs) {
    const page = await wikiGet(slug)
    if (!page) continue
    parts.push(page.full_content || `# ${page.title}\n\nNo content`)
  }
  const combined = parts.join('\n\n---\n\n')
  downloadFile('wiki-export.md', combined)
  host.notify({ kind: 'info', message: `Exported ${parts.length} page(s) as combined file` })
}

// ── Quality badge color ────────────────────────────────────────────────

function qualityColor(q) {
  if (q >= 5) return 'var(--ui-accent)'
  if (q >= 4) return 'var(--ui-text-secondary)'
  if (q >= 3) return 'var(--ui-text-tertiary)'
  return 'var(--ui-text-quaternary)'
}

// ── Wiki page list item ────────────────────────────────────────────────

function qualityDotColor(q) {
  if (q >= 5) return '#3fb950'  // green
  if (q >= 4) return '#58a6ff'  // blue
  if (q >= 3) return '#d29922'  // yellow
  return '#555'
}

function WikiListItem({ page, selected, onClick, selectable, checked, onCheck }) {
  const q = page.quality
  return jsxs('div', {
    className: cn(
      'grid grid-cols-[minmax(0,1fr)_auto] items-stretch rounded-md min-h-[1.625rem] transition-colors',
      'hover:bg-(--chrome-action-hover)',
      selected && 'bg-(--chrome-action-hover)'
    ),
    children: [
      jsxs('button', {
        className: 'flex h-full min-w-0 items-center gap-1.5 self-stretch py-0.5 pl-4 pr-1',
        onClick: () => { haptic('tap'); onClick(page) },
        children: [
          // Status dot
          jsx('span', {
            className: 'grid size-3.5 shrink-0 place-items-center',
            children: jsx('span', {
              className: 'size-1.5 rounded-full',
              style: { backgroundColor: qualityDotColor(q) }
            })
          }),
          // Title
          jsx('span', {
            className: cn('min-w-0 flex-1 truncate text-[0.8125rem] leading-none',
              selected ? 'text-foreground' : 'text-(--ui-text-secondary)'),
            children: page.title || page.slug
          }),
          // Date (right-aligned)
          jsx('span', {
            className: 'text-[0.6875rem] text-(--ui-text-quaternary)',
            children: page.date || ''
          })
        ]
      })
    ]
  })
}

// ── Wiki page detail / editor ──────────────────────────────────────────

function WikiDetail({ page, onBack, onRefresh }) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(page?.title || '')
  const [content, setContent] = useState(page?.full_content || '')
  const [topics, setTopics] = useState(Array.isArray(page?.topics) ? page.topics.join(', ') : (page?.topics || ''))
  const [saving, setSaving] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  useEffect(() => {
    if (page) {
      setTitle(page.title || '')
      setContent(page.full_content || '')
      setTopics(Array.isArray(page.topics) ? page.topics.join(', ') : (page.topics || ''))
      setEditing(false)
    }
  }, [page?.slug])

  if (!page) {
    return jsx('div', {
      className: 'flex h-full items-center justify-center text-(--ui-text-tertiary)',
      children: 'Select a wiki page'
    })
  }

  async function handleSave() {
    setSaving(true)
    try {
      await wikiUpdate({ slug: page.slug, title, full_content: content,
        topics: topics.split(',').map(t => t.trim()).filter(Boolean),
        summary: content.slice(0, 200) })
      host.notify({ kind: 'info', message: 'Saved' })
      setEditing(false); onRefresh()
    } catch (e) { host.notify({ kind: 'error', message: `Save failed: ${e.message}` }) }
    setSaving(false)
  }

  async function handleDelete() {
    try {
      await wikiDelete(page.slug)
      host.notify({ kind: 'info', message: 'Deleted' })
      setShowDeleteConfirm(false); onBack(); onRefresh()
    } catch (e) { host.notify({ kind: 'error', message: `Delete failed: ${e.message}` }) }
  }

  function handleExportSingle() {
    downloadFile(`${page.slug}.md`, page.full_content || `# ${page.title}`)
  }

  return jsxs('div', {
    className: 'flex h-full flex-col',
    children: [
      // Toolbar
      jsxs('div', {
        className: 'flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
        children: [
          jsx('button', { className: 'rounded p-1 hover:bg-(--chrome-action-hover)', onClick: onBack,
            children: jsx(Codicon, { name: 'arrow-left' }) }),
          jsx('span', { className: 'flex-1 truncate text-sm font-medium', children: page.title }),
          page.quality != null && jsx(Badge, { variant: 'secondary', children: `Q${page.quality}` }),
          jsx(Separator, { orientation: 'vertical', className: 'h-4' }),
          jsx(Tooltip, { label: 'Export as .md',
            children: jsx('button', { className: 'rounded p-1 hover:bg-(--chrome-action-hover)',
              onClick: handleExportSingle, children: jsx(Codicon, { name: 'desktop-download' }) }) }),
          jsx(Tooltip, { label: editing ? 'Cancel' : 'Edit',
            children: jsx('button', {
              className: cn('rounded p-1 hover:bg-(--chrome-action-hover)', editing && 'text-(--ui-accent)'),
              onClick: () => { setEditing(!editing); if (editing) { setTitle(page.title); setContent(page.full_content || '') } },
              children: jsx(Codicon, { name: editing ? 'close' : 'edit' }) }) }),
          editing && jsx(Tooltip, { label: saving ? 'Saving...' : 'Save',
            children: jsx('button', { className: 'rounded p-1 text-(--ui-accent) hover:bg-(--chrome-action-hover)',
              onClick: handleSave, disabled: saving,
              children: jsx(Codicon, { name: saving ? 'loading' : 'check' }) }) }),
          jsx(Tooltip, { label: 'Delete',
            children: jsx('button', { className: 'rounded p-1 text-red-500 hover:bg-(--chrome-action-hover)',
              onClick: () => setShowDeleteConfirm(true),
              children: jsx(Codicon, { name: 'trash' }) }) })
        ]
      }),
      // Metadata
      jsxs('div', {
        className: 'flex flex-wrap items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-1.5 text-xs text-(--ui-text-tertiary)',
        children: [
          page.date && jsxs('span', { children: ['📅 ', page.date] }),
          page.language && jsxs('span', { children: ['🌐 ', page.language] }),
          page.content_type && jsxs('span', { children: ['📁 ', page.content_type] }),
          Array.isArray(page.topics) && page.topics.length > 0 &&
            jsx(Fragment, { children: page.topics.map(t =>
              jsx(Badge, { variant: 'outline', className: 'text-[0.625rem]', children: t }, t)) })
        ]
      }),
      // Content
      jsx('div', {
        className: 'flex-1 overflow-y-auto px-4 py-3',
        children: editing
          ? jsxs('div', {
              className: 'flex flex-col gap-3',
              children: [
                jsxs('div', { children: [
                  jsx('label', { className: 'mb-1 block text-xs text-(--ui-text-tertiary)', children: 'Title' }),
                  jsx('input', { className: 'w-full rounded border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) px-2 py-1 text-sm',
                    value: title, onChange: e => setTitle(e.target.value) })
                ]}),
                jsxs('div', { children: [
                  jsx('label', { className: 'mb-1 block text-xs text-(--ui-text-tertiary)', children: 'Topics (comma-separated)' }),
                  jsx('input', { className: 'w-full rounded border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) px-2 py-1 text-sm',
                    value: topics, onChange: e => setTopics(e.target.value) })
                ]}),
                jsxs('div', { className: 'flex-1', children: [
                  jsx('label', { className: 'mb-1 block text-xs', style: { color: '#666' }, children: 'Content (Markdown)' }),
                  jsx('textarea', {
                    className: 'w-full resize-y rounded-md px-3 py-2 font-mono text-sm leading-relaxed',
                    style: { height: '500px', backgroundColor: '#ffffff', color: '#1a1a1a', border: '1px solid #ccc', tabSize: 2 },
                    value: content, onChange: e => setContent(e.target.value),
                    spellCheck: false
                  })
                ]})
              ]
            })
          : jsx('div', {
              className: 'prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap text-sm',
              children: page.full_content || page.summary || 'No content'
            })
      }),
      showDeleteConfirm && jsx(ConfirmDialog, {
        open: true, title: 'Delete Wiki Page',
        description: `Delete "${page.title}"? This cannot be undone.`,
        confirmLabel: 'Delete', variant: 'destructive',
        onConfirm: handleDelete, onCancel: () => setShowDeleteConfirm(false)
      })
    ]
  })
}

// ── New page dialog ────────────────────────────────────────────────────

function NewPageDialog({ onClose, onCreated }) {
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [topics, setTopics] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleCreate() {
    if (!title.trim()) { host.notify({ kind: 'error', message: 'Title is required' }); return }
    setSaving(true)
    try {
      const slug = new Date().toISOString().slice(0, 10) + '_' +
        title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40)
      await wikiCreate({ slug, title, full_content: content,
        topics: topics.split(',').map(t => t.trim()).filter(Boolean),
        summary: content.slice(0, 200), page_type: 'manual',
        date: new Date().toISOString().slice(0, 10) })
      host.notify({ kind: 'info', message: 'Created' })
      onCreated()
    } catch (e) { host.notify({ kind: 'error', message: `Create failed: ${e.message}` }) }
    setSaving(false)
  }

  return jsx('div', {
    className: 'fixed inset-0 z-50 flex items-center justify-center',
    style: { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 },
    onClick: e => { if (e.target === e.currentTarget) onClose() },
    children: jsxs('div', {
      className: 'w-[600px] max-h-[85vh] overflow-y-auto rounded-lg p-5 shadow-2xl',
      style: { border: '1px solid #ccc', backgroundColor: '#ffffff', color: '#1a1a1a' },
      children: [
        jsx('h2', { className: 'mb-4 text-lg font-medium', style: { color: '#1a1a1a' }, children: 'New Wiki Page' }),
        jsxs('div', { className: 'flex flex-col gap-3', children: [
          jsxs('div', { children: [
            jsx('label', { className: 'mb-1 block text-xs', style: { color: '#666' }, children: 'Title *' }),
            jsx('input', { className: 'w-full rounded px-2 py-1 text-sm',
              style: { backgroundColor: '#fff', color: '#1a1a1a', border: '1px solid #ccc' },
              value: title, onChange: e => setTitle(e.target.value), placeholder: 'Page title', autoFocus: true })
          ]}),
          jsxs('div', { children: [
            jsx('label', { className: 'mb-1 block text-xs', style: { color: '#666' }, children: 'Topics (comma-separated)' }),
            jsx('input', { className: 'w-full rounded px-2 py-1 text-sm',
              style: { backgroundColor: '#fff', color: '#1a1a1a', border: '1px solid #ccc' },
              value: topics, onChange: e => setTopics(e.target.value), placeholder: 'docker, nginx, ssl' })
          ]}),
          jsxs('div', { className: 'flex justify-end gap-2', children: [
            jsx(Button, { variant: 'secondary', onClick: onClose, children: 'Cancel' }),
            jsx(Button, { onClick: handleCreate, disabled: saving, children: saving ? 'Creating...' : 'Create' })
          ]})
        ]})
      ]
    })
  })
}

// ── Export menu ────────────────────────────────────────────────────────

function ExportMenu({ selectedSlugs, onClose }) {
  return jsx('div', {
    className: 'fixed inset-0 z-50',
    onClick: onClose,
    children: jsxs('div', {
      className: 'absolute right-4 top-16 w-56 rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) p-1 shadow-xl',
      onClick: e => e.stopPropagation(),
      children: [
        jsxs('div', {
          className: 'flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-sm hover:bg-(--chrome-action-hover)',
          onClick: () => { exportPages(selectedSlugs, 'individual'); onClose() },
          children: [jsx(Codicon, { name: 'file-zip' }), `Export as .md files (${selectedSlugs.length})`]
        }),
        jsxs('div', {
          className: 'flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-sm hover:bg-(--chrome-action-hover)',
          onClick: () => { exportPagesCombined(selectedSlugs); onClose() },
          children: [jsx(Codicon, { name: 'combine' }), 'Export as single .md']
        })
      ]
    })
  })
}

// ── Topic detail view ─────────────────────────────────────────────────

function TopicDetail({ topic, onBack, onSessionClick }) {
  if (!topic) {
    return jsx('div', {
      className: 'flex h-full items-center justify-center text-(--ui-text-tertiary)',
      children: 'Loading topic...'
    })
  }

  const sessions = topic.sessions || []
  const overview = topic.overview || ''
  const timeline = topic.timeline || []
  const entities = topic.entities || []

  function parseSections(content) {
    if (!content) return { overview, timeline, entities }
    const lines = content.split('\n')
    let current = 'overview'
    const sections = { overview: '', timeline: '', entities: '' }
    for (const line of lines) {
      const lower = line.toLowerCase().trim()
      if (lower.startsWith('## timeline') || lower.startsWith('### timeline')) { current = 'timeline'; continue }
      if (lower.startsWith('## entities') || lower.startsWith('### entities')) { current = 'entities'; continue }
      if (lower.startsWith('## overview') || lower.startsWith('### overview')) { current = 'overview'; continue }
      sections[current] += line + '\n'
    }
    return sections
  }

  const sections = parseSections(topic.full_content)
  const timelineEntries = sections.timeline.trim() ? sections.timeline.trim().split('\n').filter(Boolean) : timeline
  const entityList = sections.entities.trim() ? sections.entities.trim().split(/[,\n]/).map(e => e.trim()).filter(Boolean) : entities

  return jsxs('div', {
    className: 'flex h-full flex-col',
    children: [
      // Header
      jsxs('div', {
        className: 'flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
        children: [
          jsx('button', {
            className: 'rounded p-1 hover:bg-(--chrome-action-hover)',
            onClick: onBack,
            children: jsx(Codicon, { name: 'arrow-left' })
          }),
          jsx('span', { className: 'flex-1 truncate text-sm font-medium', children: topic.title || topic.slug }),
          jsx(Badge, { variant: 'secondary', children: `${sessions.length} session${sessions.length !== 1 ? 's' : ''}` })
        ]
      }),
      // Content
      jsx('div', {
        className: 'flex-1 overflow-y-auto px-4 py-3',
        children: jsxs('div', { className: 'flex flex-col gap-4', children: [
          // Overview
          sections.overview.trim() && jsxs('div', { children: [
            jsx('h3', { className: 'text-[0.6875rem] font-medium text-(--ui-text-quaternary) uppercase tracking-wide mb-1.5', children: 'Overview' }),
            jsx('div', { className: 'text-[0.8125rem] text-(--ui-text-secondary) whitespace-pre-wrap leading-relaxed', children: sections.overview.trim() })
          ]}),
          // Timeline
          timelineEntries.length > 0 && jsxs('div', { children: [
            jsx('h3', { className: 'text-[0.6875rem] font-medium text-(--ui-text-quaternary) uppercase tracking-wide mb-1.5', children: 'Timeline' }),
            jsx('div', { className: 'flex flex-col', children: timelineEntries.map((entry, i) => {
              const entryStr = typeof entry === 'string' ? entry : (entry.label || entry.title || JSON.stringify(entry))
              const slug = typeof entry === 'object' ? entry.slug : null
              return jsx('button', {
                key: i,
                className: cn('min-h-[1.625rem] text-left text-[0.8125rem] text-(--ui-text-secondary) rounded-md px-2 py-0.5', slug ? 'cursor-pointer hover:bg-(--chrome-action-hover) hover:text-(--ui-accent)' : 'cursor-default'),
                onClick: slug ? () => { haptic('tap'); onSessionClick(slug) } : undefined,
                children: entryStr
              })
            })})
          ]}),
          // Entities
          entityList.length > 0 && jsxs('div', { children: [
            jsx('h3', { className: 'text-[0.6875rem] font-medium text-(--ui-text-quaternary) uppercase tracking-wide mb-1.5', children: 'Entities' }),
            jsx('div', { className: 'flex flex-wrap gap-1.5', children: entityList.map((entity, i) =>
              jsx('span', { key: i, className: 'rounded-sm bg-(--ui-bg-secondary) px-1.5 py-0.5 text-[0.6875rem] text-(--ui-text-tertiary)', children: entity })
            )})
          ]}),
          // Sessions list
          sessions.length > 0 && jsxs('div', { children: [
            jsx('h3', { className: 'text-[0.6875rem] font-medium text-(--ui-text-quaternary) uppercase tracking-wide mb-1.5', children: 'Sessions' }),
            jsx('div', { className: 'flex flex-col', children: sessions.map((s, i) =>
              jsx('button', {
                key: s.slug || i,
                className: 'min-h-[1.625rem] grid grid-cols-[minmax(0,1fr)_auto] rounded-md px-2 py-0.5 text-left hover:bg-(--chrome-action-hover)',
                onClick: () => { haptic('tap'); onSessionClick(s.slug) },
                children: jsxs('div', { className: 'flex items-center gap-2 min-w-0', children: [
                  jsx('span', { className: 'shrink-0 text-[0.6875rem] text-(--ui-text-tertiary)', children: s.date || '' }),
                  jsx('span', { className: 'truncate text-[0.8125rem] text-(--ui-text-secondary)', children: s.title || s.slug })
                ]})
              })
            )})
          ]})
        ]})
      })
    ]
  })
}

// ── Topic group (collapsible tree node) ────────────────────────────────

function TopicGroup({ topic, expanded, onToggle, onTopicClick, onSessionClick }) {
  const sessions = topic.sessions || []

  return jsxs('div', { children: [
    // Topic row — matches mockup exactly
    jsxs('div', {
      className: 'grid grid-cols-[minmax(0,1fr)_auto] items-stretch rounded-md min-h-[1.625rem] hover:bg-(--chrome-action-hover)',
      children: jsxs('button', {
        className: 'flex h-full min-w-0 items-center gap-1.5 self-stretch py-0.5 pl-4 pr-1',
        onClick: () => onTopicClick(topic),
        children: [
          jsx(Codicon, { name: expanded ? 'chevron-down' : 'chevron-right', className: 'size-3 shrink-0 text-(--ui-text-tertiary) cursor-pointer', onClick: e => { e.stopPropagation(); onToggle(topic.slug) } }),
          jsx(Codicon, { name: 'folder', className: 'size-3.5 shrink-0 text-[#dcb67a] opacity-72' }),
          jsx('span', { className: 'min-w-0 flex-1 truncate text-[0.8125rem] leading-none text-(--ui-text-secondary)', children: topic.title || topic.slug }),
          jsx('span', { className: 'text-[0.6875rem] font-medium text-(--ui-text-quaternary)', children: sessions.length })
        ]
      })
    }),
    // Child sessions — matches mockup exactly
    expanded && sessions.map((s, i) =>
      jsxs('div', {
        className: 'grid grid-cols-[minmax(0,1fr)_auto] items-stretch rounded-md min-h-[1.625rem] hover:bg-(--chrome-action-hover)',
        children: jsxs('button', {
          className: 'flex h-full min-w-0 items-center gap-1.5 self-stretch py-0.5 pl-8 pr-1',
          onClick: () => { haptic('tap'); onSessionClick(s.slug) },
          children: [
            // Status dot
            jsx('span', {
              className: 'grid size-3.5 shrink-0 place-items-center',
              children: jsx('span', {
                className: 'size-1.5 rounded-full',
                style: { backgroundColor: qualityDotColor(s.quality) }
              })
            }),
            // Title
            jsx('span', { className: 'min-w-0 flex-1 truncate text-[0.8125rem] leading-none text-(--ui-text-secondary)', children: s.title || s.slug }),
            // Date
            jsx('span', { className: 'text-[0.6875rem] text-(--ui-text-quaternary)', children: s.date || '' })
          ]
        })
      }, s.slug || i)
    )
  ]})
}

// ── Main Wiki page ─────────────────────────────────────────────────────

function WikiPage() {
  const [pages, setPages] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [search, setSearch] = useState('')
  const [stats, setStats] = useState(null)
  const [showNew, setShowNew] = useState(false)
  const [loading, setLoading] = useState(true)
  const [selectMode, setSelectMode] = useState(false)
  const [checked, setChecked] = useState(new Set())
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [topics, setTopics] = useState([])
  const [view, setView] = useState('list') // 'list' | 'topic-detail' | 'session-detail'
  const [topicDetail, setTopicDetail] = useState(null)
  const [expandedTopics, setExpandedTopics] = useState(new Set())
  const [topicsSectionOpen, setTopicsSectionOpen] = useState(true)
  const [allPagesSectionOpen, setAllPagesSectionOpen] = useState(true)
  const [activeNav, setActiveNav] = useState('wiki') // 'wiki' | 'topics'

  const refresh = useCallback(async () => {
    setLoading(true)
    const [listResult, statsResult] = await Promise.all([
      wikiList(search ? { query: search } : {}),
      wikiStats()
    ])
    setPages(listResult.pages || [])
    setStats(statsResult)
    const topicResult = await wikiListTopics()
    setTopics(topicResult.topics || [])
    setLoading(false)
  }, [search])

  useEffect(() => {
    wikiStats().then(async (s) => {
      if (s.total === 0) {
        const result = await wikiBatchProcess(20)
        if (result.enqueued > 0) setTimeout(() => refresh(), 2000)
      }
    })
  }, [])

  useEffect(() => { refresh() }, [refresh])

  async function handleSelect(page) {
    setSelected(page)
    const full = await wikiGet(page.slug)
    setDetail(full)
    setView('session-detail')
  }

  async function handleTopicClick(topic) {
    setView('topic-detail')
    const full = await wikiGetTopic(topic.slug)
    setTopicDetail(full)
  }

  function handleSessionFromTopic(slug) {
    const page = pages.find(p => p.slug === slug)
    if (page) handleSelect(page)
    else { setSelected({ slug }); wikiGet(slug).then(d => { setDetail(d); setView('session-detail') }) }
  }

  function handleBack() {
    if (view === 'topic-detail') { setView('list'); setTopicDetail(null) }
    else { setSelected(null); setDetail(null); setView('list') }
  }

  function toggleTopicExpand(slug) {
    setExpandedTopics(prev => {
      const next = new Set(prev)
      if (next.has(slug)) next.delete(slug); else next.add(slug)
      return next
    })
  }

  function handleCheck(slug, isChecked) {
    setChecked(prev => {
      const next = new Set(prev)
      if (isChecked) next.add(slug); else next.delete(slug)
      return next
    })
  }

  function handleSelectAll() {
    if (checked.size === pages.length) {
      setChecked(new Set())
    } else {
      setChecked(new Set(pages.map(p => p.slug)))
    }
  }

  function toggleSelectMode() {
    setSelectMode(!selectMode)
    if (selectMode) setChecked(new Set())
  }

  // Detail view
  if (view === 'topic-detail') {
    return jsx(TopicDetail, {
      topic: topicDetail,
      onBack: handleBack,
      onSessionClick: handleSessionFromTopic
    })
  }

  if (view === 'session-detail' && selected) {
    return jsx(WikiDetail, {
      page: detail,
      onBack: handleBack,
      onRefresh: () => { refresh(); if (selected) wikiGet(selected.slug).then(setDetail) }
    })
  }

  // List view — matches wiki-sidebar-mockup.html exactly
  return jsxs('div', {
    className: 'flex h-full flex-col overflow-hidden border-r border-(--ui-stroke-secondary) bg-(--ui-sidebar-surface-background, #1f1f1f)',
    children: [
      // ── Nav items (Wiki + Topics buttons, matching mockup) ──
      jsxs('div', {
        className: 'shrink-0 px-2.5 pb-2 pt-3',
        children: jsx('div', {
          className: 'grid grid-cols-[minmax(0,1fr)] gap-px',
          children: [
            // Nav: Wiki (active)
            jsxs('button', {
              className: cn('flex h-7 w-full items-center gap-2 rounded-md px-2 text-left text-[0.8125rem] font-medium',
                activeNav === 'wiki'
                  ? 'border border-(--ui-stroke-tertiary) bg-(--ui-control-active-background) text-foreground'
                  : 'border border-transparent text-(--ui-text-secondary) hover:bg-(--ui-control-hover-background) hover:text-foreground'),
              onClick: () => setActiveNav('wiki'),
              children: [
                jsx(Codicon, { name: 'book', className: cn('size-3.5 shrink-0', activeNav === 'wiki' ? 'text-(--ui-accent)' : 'text-[color-mix(in_srgb,currentColor_72%,transparent)]') }),
                jsx('span', { className: 'min-w-0 flex-1 truncate', children: 'Wiki' }),
                stats && jsx('span', { className: 'text-[0.6875rem] font-medium text-(--ui-text-quaternary)', children: stats.total })
              ]
            }),
            // Nav: Topics (inactive)
            jsxs('button', {
              className: cn('flex h-7 w-full items-center gap-2 rounded-md px-2 text-left text-[0.8125rem] font-medium',
                activeNav === 'topics'
                  ? 'border border-(--ui-stroke-tertiary) bg-(--ui-control-active-background) text-foreground'
                  : 'border border-transparent text-(--ui-text-secondary) hover:bg-(--ui-control-hover-background) hover:text-foreground'),
              onClick: () => setActiveNav('topics'),
              children: [
                jsx(Codicon, { name: 'library', className: cn('size-3.5 shrink-0', activeNav === 'topics' ? 'text-(--ui-accent)' : 'text-[color-mix(in_srgb,currentColor_72%,transparent)]') }),
                jsx('span', { className: 'min-w-0 flex-1 truncate', children: 'Topics' }),
                jsx('span', { className: 'text-[0.6875rem] font-medium text-(--ui-text-quaternary)', children: topics.length })
              ]
            })
          ]
        })
      }),
      // ── Search ──
      jsxs('div', {
        className: 'shrink-0 px-2.5 pb-1.5',
        children: jsxs('div', {
          className: 'flex h-7 items-center gap-1.5 rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-tertiary, rgba(255,255,255,0.04)) px-2',
          children: [
            jsx(Codicon, { name: 'search', className: 'size-3.5 shrink-0 text-(--ui-text-quaternary)' }),
            jsx('input', {
              type: 'text',
              placeholder: 'Search wiki...',
              className: 'flex-1 bg-transparent text-[12px] text-(--ui-text-primary) outline-none placeholder:text-(--ui-text-quaternary)',
              value: search,
              onChange: e => setSearch(e.target.value)
            })
          ]
        })
      }),
      // ── Content (scrollable) ──
      jsxs('div', {
        className: 'flex-1 overflow-y-auto px-2.5',
        children: [
          // ── Topics section ──
          activeNav !== 'pages' && jsxs('div', {
            className: 'pb-1 pt-1',
            children: [
              // Section header
              jsxs('button', {
                className: 'flex h-[1.625rem] w-full items-center gap-1.5 pl-2 pr-1 text-[0.6875rem] font-medium text-(--ui-text-quaternary) uppercase tracking-wide cursor-default select-none',
                onClick: () => setTopicsSectionOpen(!topicsSectionOpen),
                children: [
                  jsx(Codicon, { name: topicsSectionOpen ? 'chevron-down' : 'chevron-right', className: 'size-3 shrink-0' }),
                  jsx('span', { className: 'flex-1', children: 'Topics' })
                ]
              }),
              // Topic groups
              topicsSectionOpen && topics.map(t =>
                jsx(TopicGroup, {
                  topic: t,
                  expanded: expandedTopics.has(t.slug),
                  onToggle: toggleTopicExpand,
                  onTopicClick: handleTopicClick,
                  onSessionClick: handleSessionFromTopic
                }, t.slug)
              )
            ]
          }),
          // ── Divider ──
          activeNav === 'wiki' && jsx('div', { className: 'mx-2 my-1.5 h-px bg-(--ui-stroke-secondary)' }),
          // ── All Pages section ──
          activeNav === 'wiki' && jsxs('div', {
            className: 'pb-1',
            children: [
              // Section header
              jsxs('button', {
                className: 'flex h-[1.625rem] w-full items-center gap-1.5 pl-2 pr-1 text-[0.6875rem] font-medium text-(--ui-text-quaternary) uppercase tracking-wide cursor-default select-none',
                onClick: () => setAllPagesSectionOpen(!allPagesSectionOpen),
                children: [
                  jsx(Codicon, { name: allPagesSectionOpen ? 'chevron-down' : 'chevron-right', className: 'size-3 shrink-0' }),
                  jsx('span', { className: 'flex-1', children: 'All Pages' })
                ]
              }),
              // Page rows
              allPagesSectionOpen && pages.map(page =>
                jsx(WikiListItem, {
                  page, selected: selected?.slug === page.slug, onClick: handleSelect,
                  selectable: selectMode, checked: checked.has(page.slug), onCheck: handleCheck
                }, page.slug)
              )
            ]
          })
        ]
      }),
      // ── Export menu ──
      showExportMenu && jsx(ExportMenu, { selectedSlugs: [...checked], onClose: () => setShowExportMenu(false) }),
      // ── New page dialog ──
      showNew && jsx(NewPageDialog, { onClose: () => setShowNew(false), onCreated: () => { setShowNew(false); refresh() } })
    ]
  })
}

// ── Plugin registration ────────────────────────────────────────────────

export default {
  id: 'hermes-wiki',
  name: 'Hermes Wiki',
  register(ctx) {
    ctx.register({
      id: 'wiki-nav',
      area: SIDEBAR_NAV_AREA,
      data: { codicon: 'book', label: 'Wiki', path: '/wiki' }
    })
    ctx.register({
      id: 'wiki-page',
      area: ROUTES_AREA,
      data: { path: '/wiki' },
      render: () => jsx(WikiPage, {})
    })
  }
}
