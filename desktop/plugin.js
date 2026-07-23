/**
 * hermes-wiki desktop plugin — Wiki viewer/editor in the sidebar.
 *
 * Features: list, search, create, edit, delete, multi-select, export.
 * Data flows through gateway JSON-RPC: wiki.list, wiki.get, wiki.create,
 * wiki.update, wiki.delete, wiki.stats, wiki.batch_process.
 */

import { cn, haptic, host, Tip, useValue, Codicon, Badge, Button, ScrollArea, EmptyState, Separator, Tooltip, ConfirmDialog } from '@hermes/plugin-sdk'
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

async function topicList() {
  try { return await host.request('topic.list', {}) }
  catch (e) { return { topics: [], count: 0 } }
}

async function topicGet(slug) {
  try { return await host.request('topic.get', { slug }) }
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
  if (q >= 5) return 'var(--quality-green, #3fb950)'
  if (q >= 4) return 'var(--quality-blue, #58a6ff)'
  if (q >= 3) return 'var(--quality-yellow, #d29922)'
  return 'var(--ui-text-quaternary, #555)'
}

function WikiListItem({ page, selected, selectable, checked, onCheck, onClick }) {
  const handleRowClick = (e) => {
    if (selectable) return  // in select mode, outer div handles click
    haptic('tap'); onClick(page)
  }
  return jsxs('div', {
    className: cn(
      'grid grid-cols-[minmax(0,1fr)_auto] items-stretch rounded-md min-h-7 transition-colors',
      selectable ? 'cursor-pointer' : 'hover:bg-(--chrome-action-hover)',
      !selectable && selected && 'bg-(--chrome-action-hover)'
    ),
    onClick: selectable ? () => onCheck(page.slug, !checked) : undefined,
    children: [
      // Optional checkbox in select mode
      selectable && jsx('input', {
        type: 'checkbox',
        checked: !!checked,
        onChange: e => onCheck(page.slug, e.target.checked),
        onClick: e => e.stopPropagation(),
        className: 'ml-2 shrink-0'
      }),
      jsx('button', {
        className: cn('flex h-full min-w-0 items-center gap-1.5 self-stretch py-0.5 pr-1',
          selectable ? 'pl-1' : 'pl-7'),
        onClick: handleRowClick,
        style: { width: '100%' },
        children: [
          jsx('span', {
            className: 'grid size-3.5 shrink-0 place-items-center',
            children: jsx('span', {
              className: 'size-1.5 rounded-full',
              style: { backgroundColor: qualityDotColor(page.quality) }
            })
          }),
          jsx('span', {
            className: cn('min-w-0 flex-1 truncate text-sm leading-none',
              selected ? 'text-foreground' : 'text-(--ui-text-secondary)'),
            children: page.title || page.slug
          }),
          jsx('span', {
            className: 'shrink-0 text-xs text-(--ui-text-quaternary)',
            children: page.date || ''
          })
        ]
      })
    ]
  })
}

// ── DetailToolbar (shared by WikiDetail + TopicDetail) ─────────────────

function DetailToolbar({ back, title, badge, onExport, onDelete, extra }) {
  return jsxs('div', {
    className: 'flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
    children: [
      jsx('button', { className: 'rounded p-1 hover:bg-(--chrome-action-hover)', onClick: back,
        children: jsx(Codicon, { name: 'arrow-left' }) }),
      jsx('span', { className: 'flex-1 truncate text-sm font-medium', children: title }),
      badge && jsx(Badge, { variant: 'secondary', children: badge }),
      jsx(Separator, { orientation: 'vertical', className: 'h-4' }),
      extra, // optional left group (edit/save buttons, or other actions)
      onExport && jsx(Tip, { label: 'Export as .md',
        children: jsx('button', { className: 'rounded p-1 hover:bg-(--chrome-action-hover)',
          onClick: onExport, children: jsx(Codicon, { name: 'desktop-download' }) }) }),
      onDelete && jsx(Tip, { label: 'Delete',
        children: jsx('button', { className: 'rounded p-1 text-red-500 hover:bg-(--chrome-action-hover)',
          onClick: onDelete, children: jsx(Codicon, { name: 'trash' }) }) })
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
      jsx(DetailToolbar, {
        back: onBack,
        title: page.title,
        badge: page.quality != null ? `Q${page.quality}` : null,
        onExport: handleExportSingle,
        onDelete: () => setShowDeleteConfirm(true),
        extra: jsxs(Fragment, { children: [
          jsx(Tip, { label: editing ? 'Cancel' : 'Edit',
            children: jsx('button', {
              className: cn('rounded p-1 hover:bg-(--chrome-action-hover)', editing && 'text-(--ui-accent)'),
              onClick: () => { setEditing(!editing); if (editing) { setTitle(page.title); setContent(page.full_content || '') } },
              children: jsx(Codicon, { name: editing ? 'close' : 'edit' }) }) }),
          editing && jsx(Tip, { label: saving ? 'Saving...' : 'Save',
            children: jsx('button', { className: 'rounded p-1 text-(--ui-accent) hover:bg-(--chrome-action-hover)',
              onClick: handleSave, disabled: saving,
              children: jsx(Codicon, { name: saving ? 'loading' : 'check' }) }) })
        ] })
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
              jsx(Badge, { variant: 'outline', className: 'text-xs', children: t }, t)) })
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
    let inFrontmatter = false
    let frontmatterDone = false
    for (const line of lines) {
      const stripped = line.trim()
      // Skip YAML frontmatter fence (between two --- lines)
      if (stripped === '---') {
        if (!frontmatterDone) { inFrontmatter = true; frontmatterDone = true; continue }
        else { inFrontmatter = false; continue }
      }
      if (inFrontmatter) continue
      const lower = stripped.toLowerCase()
      // Recognize headings (English + Chinese variants from LLM output)
      if (lower.startsWith('## timeline') || lower.startsWith('### timeline')
          || /^##\s*时间线/.test(stripped) || /^###\s*时间线/.test(stripped)) {
        current = 'timeline'; continue
      }
      if (lower.startsWith('## entities') || lower.startsWith('### entities')
          || /^##\s*实体/.test(stripped) || /^###\s*实体/.test(stripped)
          || /^##\s*相关(实体|主题)/.test(stripped)) {
        current = 'entities'; continue
      }
      if (lower.startsWith('## overview') || lower.startsWith('### overview')
          || /^##\s*概述/.test(stripped) || /^###\s*概述/.test(stripped)
          || /^##\s*主题概述/.test(stripped)) {
        current = 'overview'; continue
      }
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
      // Toolbar (shared with WikiDetail via DetailToolbar)
      jsx(DetailToolbar, {
        back: onBack,
        title: topic.title || topic.slug,
        badge: `${sessions.length} session${sessions.length !== 1 ? 's' : ''}`,
        onExport: () => downloadFile(`${topic.slug || 'topic'}.md`,
          topic.full_content || (topic.overview ? `# ${topic.title}\n\n## Overview\n${topic.overview}\n` : '')),
        onDelete: () => {
          if (host.notify) host.notify({ kind: 'info', message: 'Topic deletion not yet supported in RPC — use SQL or wiki.delete on session pages' })
        }
      }),
      // Content
      jsx('div', {
        className: 'flex-1 overflow-y-auto px-4 py-3',
        children: jsxs('div', { className: 'flex flex-col gap-4', children: [
          // Overview — render markdown content (LLM output may use any language)
          sections.overview.trim() && jsxs('div', { children: [
            jsx('h3', { className: 'text-xs font-medium text-(--ui-text-quaternary) uppercase tracking-wide mb-1.5', children: 'Overview' }),
            jsx('div', {
              className: 'prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap text-sm leading-relaxed',
              children: sections.overview.trim()
            })
          ]}),
          // Timeline
          timelineEntries.length > 0 && jsxs('div', { children: [
            jsx('h3', { className: 'text-xs font-medium text-(--ui-text-quaternary) uppercase tracking-wide mb-1.5', children: 'Timeline' }),
            jsx('div', { className: 'flex flex-col', children: timelineEntries.map((entry, i) => {
              const entryStr = typeof entry === 'string' ? entry : (entry.label || entry.title || JSON.stringify(entry))
              const slug = typeof entry === 'object' ? entry.slug : null
              return jsx('button', {
                key: i,
                className: cn('min-h-7 text-left text-sm text-(--ui-text-secondary) rounded-md px-2 py-0.5', slug ? 'cursor-pointer hover:bg-(--chrome-action-hover) hover:text-(--ui-accent)' : 'cursor-default'),
                onClick: slug ? () => { haptic('tap'); onSessionClick(slug) } : undefined,
                children: entryStr
              })
            })})
          ]}),
          // Entities
          entityList.length > 0 && jsxs('div', { children: [
            jsx('h3', { className: 'text-xs font-medium text-(--ui-text-quaternary) uppercase tracking-wide mb-1.5', children: 'Entities' }),
            jsx('div', { className: 'flex flex-wrap gap-1.5', children: entityList.map((entity, i) =>
              jsx('span', { key: i, className: 'rounded-sm bg-(--ui-bg-secondary) px-1.5 py-0.5 text-xs text-(--ui-text-tertiary)', children: entity })
            )})
          ]}),
          // Sessions list
          sessions.length > 0 && jsxs('div', { children: [
            jsx('h3', { className: 'text-xs font-medium text-(--ui-text-quaternary) uppercase tracking-wide mb-1.5', children: 'Sessions' }),
            jsx('div', { className: 'flex flex-col', children: sessions.map((s, i) =>
              jsx('button', {
                key: s.slug || i,
                className: 'min-h-7 grid grid-cols-[minmax(0,1fr)_auto] rounded-md px-2 py-0.5 text-left hover:bg-(--chrome-action-hover)',
                onClick: () => { haptic('tap'); onSessionClick(s.slug) },
                children: jsxs('div', { className: 'flex items-center gap-2 min-w-0', children: [
                  jsx('span', { className: 'shrink-0 text-xs text-(--ui-text-tertiary)', children: s.date || '' }),
                  jsx('span', { className: 'truncate text-sm text-(--ui-text-secondary)', children: s.title || s.slug })
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

function TopicGroup({ topic, expanded, selectable, checked, onCheck, onToggle, onTopicClick, onSessionClick }) {
  const sessions = topic.sessions || []
  const topicSelected = !!checked
  return jsxs('div', { children: [
    // ── Topic row ──
    jsxs('div', {
      className: cn('grid grid-cols-[minmax(0,1fr)_auto] items-stretch rounded-md min-h-7',
        selectable ? 'cursor-pointer' : 'hover:bg-(--chrome-action-hover)'),
      onClick: selectable ? () => onCheck(topic.slug, !topicSelected) : undefined,
      children: [
        // Optional checkbox in select mode
        selectable && jsx('input', {
          type: 'checkbox',
          checked: topicSelected,
          onChange: e => onCheck(topic.slug, e.target.checked),
          onClick: e => e.stopPropagation(),
          className: 'ml-3 shrink-0 self-center'
        }),
        jsx('button', {
          className: cn('flex h-full min-w-0 items-center gap-1.5 self-stretch py-0.5 pr-1',
            selectable ? 'pl-1' : 'pl-4'),
          onClick: selectable ? undefined : () => onTopicClick(topic),
          style: { width: '100%' },
          children: [
            jsx(Codicon, {
              name: expanded ? 'chevron-down' : 'chevron-right',
              className: 'size-3 shrink-0 text-(--ui-text-quaternary) cursor-pointer',
              onClick: e => { e.stopPropagation(); onToggle(topic.slug) }
            }),
            jsx(Codicon, { name: 'folder', className: 'size-3.5 shrink-0 opacity-72', style: { color: '#dcb67a' } }),
            jsx('span', { className: 'min-w-0 flex-1 truncate text-sm leading-none text-(--ui-text-secondary)', children: topic.title || topic.slug }),
            jsx('span', { className: 'shrink-0 text-xs font-medium text-(--ui-text-quaternary)', children: sessions.length })
          ]
        })
      ]
    }),
    // ── Child sessions (always clickable, no checkbox — sessions are read-only when topic selected) ──
    expanded && sessions.map((s, i) =>
      jsxs('div', {
        className: 'grid grid-cols-[minmax(0,1fr)_auto] items-stretch rounded-md min-h-7 hover:bg-(--chrome-action-hover)',
        children: jsxs('button', {
          className: 'flex h-full min-w-0 items-center gap-1.5 self-stretch py-0.5 pl-8 pr-1',
          onClick: () => { haptic('tap'); onSessionClick(s.slug) },
          children: [
            jsx('span', {
              className: 'grid size-3.5 shrink-0 place-items-center',
              children: jsx('span', {
                className: 'size-1.5 rounded-full',
                style: { backgroundColor: qualityDotColor(s.quality) }
              })
            }),
            jsx('span', { className: 'min-w-0 flex-1 truncate text-sm leading-none text-(--ui-text-secondary)', children: s.title || s.slug }),
            jsx('span', { className: 'shrink-0 text-xs text-(--ui-text-quaternary)', children: s.date || '' })
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
  const [allPagesSectionOpen, setAllPagesSectionOpen] = useState(false)
  // activeNav removed — sidebar now shows unified Topics + All Pages sections,


  // Inject custom CSS for arbitrary values not compiled by Tailwind (plugin runtime classes)
  useEffect(() => {
    const styleId = 'hermes-wiki-plugin-styles'
    if (document.getElementById(styleId)) return
    const style = document.createElement('style')
    style.id = styleId
    style.textContent = `
      .pl-7 { padding-left: 1.75rem; }
      .pl-8 { padding-left: 2rem; }
      .px-2\.5 { padding-left: 0.625rem; padding-right: 0.625rem; }
      .w-\[600px\] { width: 600px; }
      .max-h-\[85vh\] { max-height: 85vh; }
      .grid-cols-\[minmax\(0\,1fr\)_auto\] { grid-template-columns: minmax(0, 1fr) auto; }
    `
    document.head.appendChild(style)
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    const [listResult, statsResult] = await Promise.all([
      wikiList(search ? { query: search } : {}),
      wikiStats()
    ])
    setPages(listResult.pages || [])
    setStats(statsResult)
    const topicResult = await topicList()
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
    const full = await topicGet(topic.slug)
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

  function handleCheck(type, slug, isChecked) {
    // type: 'page' | 'topic'. Store as `${type}:${slug}` to disambiguate.
    const key = `${type}:${slug}`
    setChecked(prev => {
      const next = new Set(prev)
      if (isChecked) next.add(key); else next.delete(key)
      return next
    })
  }

  function handleSelectAll() {
    const allKeys = [
      ...pages.map(p => `page:${p.slug}`),
      ...topics.map(t => `topic:${t.slug}`),
    ]
    if (checked.size === allKeys.length) {
      setChecked(new Set())
    } else {
      setChecked(new Set(allKeys))
    }
  }

  function toggleSelectMode() {
    setSelectMode(!selectMode)
    if (selectMode) setChecked(new Set())
  }

  // List view — dual-panel layout matching wiki-sidebar-mockup-4.html
  const sidebar = jsxs('div', {
    className: 'flex h-full w-64 shrink-0 min-w-0 flex-col overflow-hidden border-r border-(--ui-stroke-secondary) bg-(--ui-sidebar-surface-background, #1f1f1f)',
    children: [
      // ── Toolbar: select, export, delete, new, refresh ──
      jsxs('div', {
        className: 'flex shrink-0 items-center gap-1 border-b border-(--ui-stroke-secondary) px-2 py-1',
        children: [
          // Select mode toggle
          jsx(Tip, { label: selectMode ? 'Exit select' : 'Select',
            children: jsx('button', {
              className: cn('rounded p-1 hover:bg-(--chrome-action-hover)', selectMode && 'text-(--ui-accent)'),
              onClick: toggleSelectMode,
              children: jsx(Codicon, { name: selectMode ? 'arrow-left' : 'list-selection', className: 'size-4' })
            })
          }),
          // Select all (only in select mode)
          selectMode && (() => {
            const allKeys = [
              ...pages.map(p => `page:${p.slug}`),
              ...topics.map(t => `topic:${t.slug}`),
            ]
            const allSelected = checked.size === allKeys.length && allKeys.length > 0
            return jsx(Tip, {
              label: allSelected ? 'Deselect all' : 'Select all',
              children: jsx('button', {
                className: cn('rounded px-1.5 py-1 text-xs hover:bg-(--chrome-action-hover)',
                  allSelected && 'text-(--ui-accent)'),
                onClick: handleSelectAll,
                children: allSelected ? 'Deselect' : 'All'
              })
            })
          })(),
          // Export (only in select mode with selection)
          selectMode && checked.size > 0 && jsx(Tip, { label: `Export (${checked.size})`,
            children: jsx('button', {
              className: 'rounded p-1 text-(--ui-accent) hover:bg-(--chrome-action-hover)',
              onClick: () => setShowExportMenu(true),
              children: jsx(Codicon, { name: 'desktop-download', className: 'size-4' })
            })
          }),
          // Delete selected (only in select mode with selection)
          selectMode && checked.size > 0 && jsx(Tip, { label: `Delete (${checked.size})`,
            children: jsx('button', {
              className: 'rounded p-1 text-red-500 hover:bg-(--chrome-action-hover)',
              onClick: async () => {
                let pages = 0, topics = 0
                for (const key of checked) {
                  const [type, slug] = key.split(':')
                  if (type === 'page') { await wikiDelete(slug); pages++ }
                  else if (type === 'topic') { topics++ /* topic delete RPC not implemented */ }
                }
                host.notify({ kind: 'info', message: `Deleted ${pages} page(s)${topics ? `, skipped ${topics} topic(s) — needs topic.delete RPC` : ''}` })
                setChecked(new Set()); setSelectMode(false); refresh()
              },
              children: jsx(Codicon, { name: 'trash', className: 'size-4' })
            })
          }),
          jsx('div', { className: 'mx-1 h-4 w-px bg-(--ui-stroke-secondary)' }),
          // New page
          jsx(Tip, { label: 'New page',
            children: jsx('button', { className: 'rounded p-1 hover:bg-(--chrome-action-hover)',
              onClick: () => setShowNew(true),
              children: jsx(Codicon, { name: 'add', className: 'size-4' })
            })
          }),
          // Refresh
          jsx(Tip, { label: 'Refresh',
            children: jsx('button', { className: 'rounded p-1 hover:bg-(--chrome-action-hover)',
              onClick: refresh,
              children: jsx(Codicon, { name: 'refresh', className: 'size-4' })
            })
          })
        ]
      }),
      // ── Search ──
      jsxs('div', {
        className: 'shrink-0 px-3 pb-1.5 pt-1.5',
        children: jsxs('div', {
          className: 'flex h-7 items-center gap-1.5 rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-tertiary, rgba(255,255,255,0.04)) px-2',
          children: [
            jsx(Codicon, { name: 'search', className: 'size-3.5 shrink-0 text-(--ui-text-quaternary)' }),
            jsx('input', {
              type: 'text',
              placeholder: 'Search wiki...',
              className: 'flex-1 bg-transparent text-xs text-(--ui-text-primary) outline-none placeholder:text-(--ui-text-quaternary)',
              value: search,
              onChange: e => setSearch(e.target.value)
            })
          ]
        })
      }),
      // ── Content: 50/50 split — Topics (top) + All Pages (bottom) ──
      jsxs('div', {
        className: 'flex flex-1 flex-col overflow-hidden',
        children: [
          // Topics (top half)
          jsxs('div', {
            className: 'flex flex-1 flex-col overflow-hidden',
            children: [
              jsxs('div', {
                className: 'flex shrink-0 h-7 items-center gap-1.5 pl-7 pr-1 text-xs font-medium text-(--ui-text-quaternary) cursor-default select-none',
                onClick: () => setTopicsSectionOpen(!topicsSectionOpen),
                children: [
                  jsx('svg', { className: cn('size-3 shrink-0 transition-transform', topicsSectionOpen && 'rotate-90'), fill: 'currentColor', viewBox: '0 0 8 8',
                    children: jsx('path', { d: 'M1.5 0L6.5 4L1.5 8z' })
                  }),
                  jsx('span', { className: 'uppercase tracking-wide', children: 'Topics' }),
                  jsx('span', { className: 'text-(--ui-text-quaternary)', children: topics.length })
                ]
              }),
              topicsSectionOpen && jsx('div', {
                className: 'flex-1 overflow-y-auto overflow-x-hidden min-w-0',
                children: topics.map(t =>
                  jsx(TopicGroup, {
                    topic: t, expanded: expandedTopics.has(t.slug),
                    onToggle: toggleTopicExpand, onTopicClick: handleTopicClick,
                    onSessionClick: handleSessionFromTopic,
                    selectable: selectMode,
                    checked: checked.has(`topic:${t.slug}`),
                    onCheck: (slug, c) => handleCheck('topic', slug, c)
                  }, t.slug)
                )
              })
            ]
          }),
          // Divider
          jsx('div', { className: 'shrink-0 mx-2 h-px bg-(--ui-stroke-secondary)' }),
          // All Pages (bottom half)
          jsxs('div', {
            className: 'flex flex-1 flex-col overflow-hidden',
            children: [
              jsxs('div', {
                className: 'flex shrink-0 h-7 items-center gap-1.5 pl-7 pr-1 text-xs font-medium text-(--ui-text-quaternary) cursor-default select-none',
                onClick: () => setAllPagesSectionOpen(!allPagesSectionOpen),
                children: [
                  jsx('svg', { className: cn('size-3 shrink-0 transition-transform', allPagesSectionOpen && 'rotate-90'), fill: 'currentColor', viewBox: '0 0 8 8',
                    children: jsx('path', { d: 'M1.5 0L6.5 4L1.5 8z' })
                  }),
                  jsx('span', { className: 'uppercase tracking-wide', children: 'All Pages' }),
                  jsx('span', { className: 'text-(--ui-text-quaternary)', children: pages.length })
                ]
              }),
              allPagesSectionOpen && jsx('div', {
                className: 'flex-1 overflow-y-auto overflow-x-hidden min-w-0',
                children: pages.map(page =>
                  jsx(WikiListItem, { page, selected: selected?.slug === page.slug,
                    onClick: handleSelect,
                    selectable: selectMode,
                    checked: checked.has(`page:${page.slug}`),
                    onCheck: (slug, c) => handleCheck('page', slug, c)
                  }, page.slug)
                )
              })
            ]
          })
        ]
      }),
      // Export / New page dialogs
      showExportMenu && jsx(ExportMenu, { selectedSlugs: [...checked], onClose: () => setShowExportMenu(false) }),
      showNew && jsx(NewPageDialog, { onClose: () => setShowNew(false), onCreated: () => { setShowNew(false); refresh() } })
    ]
  })

  // Right panel — TopicDetail / WikiDetail / empty state
  let rightPanel
  if (view === 'topic-detail' && topicDetail) {
    const sessions = topicDetail.sessions || []
    const overview = topicDetail.overview || topicDetail.summary || ''
    const timeline = topicDetail.timeline || []
    const entities = topicDetail.entities || []
    rightPanel = jsxs('div', {
      className: 'flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-(--ui-bg-primary)',
      children: [
        // Header
        jsxs('div', {
          className: 'flex shrink-0 items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
          children: [
            jsx('button', {
              className: 'flex size-6 items-center justify-center rounded-md text-(--ui-text-secondary) hover:bg-(--chrome-action-hover) hover:text-foreground',
              onClick: handleBack,
              children: jsx(Codicon, { name: 'arrow-left', className: 'size-4' })
            }),
            jsx('span', { className: 'flex-1 truncate text-sm font-medium text-foreground', children: topicDetail.title || topicDetail.slug }),
            jsx(Badge, { variant: 'secondary', children: `${sessions.length} session${sessions.length !== 1 ? 's' : ''}` })
          ]
        }),
        // Body
        jsx('div', {
          className: 'flex-1 overflow-y-auto px-4 py-3',
          children: jsxs('div', { className: 'flex flex-col gap-4', children: [
            // Overview
            overview && jsxs('div', { children: [
              jsx('h2', { className: 'mb-1.5 text-xs font-medium text-(--ui-text-secondary)', children: 'Overview' }),
              jsx('p', { className: 'text-sm leading-7 text-(--ui-text-primary)', children: overview })
            ]}),
            // Timeline
            (timeline.length > 0 || sessions.length > 0) && jsxs('div', { children: [
              jsx('h2', { className: 'mb-1.5 text-xs font-medium text-(--ui-text-secondary)', children: 'Timeline' }),
              jsx('div', { className: 'flex flex-col', children:
                (timeline.length > 0 ? timeline : sessions).map((entry, i) => {
                  const s = typeof entry === 'string' ? { title: entry } : entry
                  return jsxs('button', {
                    className: 'flex min-h-8 items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-(--chrome-action-hover)',
                    onClick: s.slug ? () => { haptic('tap'); handleSessionFromTopic(s.slug) } : undefined,
                    children: [
                      jsx('span', { className: 'mt-0.5 shrink-0 text-xs text-(--ui-text-quaternary)', style: { minWidth: '40px' }, children: s.date || '' }),
                      jsx('div', { className: 'min-w-0 flex-1', children: [
                        jsx('span', { className: cn('text-sm', s.slug ? 'text-(--ui-accent) hover:underline cursor-pointer' : 'text-(--ui-text-primary)'), children: s.title || s.slug }),
                        s.description && jsx('p', { className: 'mt-0.5 text-xs text-(--ui-text-tertiary)', children: s.description })
                      ]})
                    ]
                  }, i)
                })
              })
            ]}),
            // Entities
            entities.length > 0 && jsxs('div', { children: [
              jsx('h2', { className: 'mb-1.5 text-xs font-medium text-(--ui-text-secondary)', children: 'Entities' }),
              jsx('div', { className: 'flex flex-wrap gap-1', children:
                entities.map((entity, i) =>
                  jsx('span', { key: i, className: 'inline-flex items-center rounded-sm bg-(--ui-bg-secondary) px-1.5 py-0.5 text-xs text-(--ui-text-secondary)', children: typeof entity === 'string' ? entity : entity.name || entity.title })
                )
              })
            ]})
          ]})
        })
      ]
    })
  } else if (view === 'session-detail' && detail) {
    rightPanel = jsx(WikiDetail, {
      page: detail,
      onBack: handleBack,
      onRefresh: () => { refresh(); if (selected) wikiGet(selected.slug).then(setDetail) }
    })
  } else {
    rightPanel = jsx('div', {
      className: 'flex h-full min-w-0 flex-1 items-center justify-center text-(--ui-text-quaternary)',
      children: 'Select a page or topic'
    })
  }

  // Dual-panel: sidebar + right panel
  return jsxs('div', {
    className: 'flex h-full w-full min-w-0 overflow-hidden',
    children: [sidebar, rightPanel]
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
