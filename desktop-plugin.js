/**
 * hermes-wiki desktop plugin — Wiki viewer/editor in the sidebar.
 *
 * Registers a "Wiki" nav item in the sidebar and a full-page route
 * with list + detail view, search, create, edit, and delete.
 *
 * Data flows through gateway JSON-RPC: wiki.list, wiki.get, wiki.create,
 * wiki.update, wiki.delete, wiki.stats.
 */

import { cn, haptic, host, Tip, useValue, Codicon, Badge, Button, SearchField, ScrollArea, EmptyState, Separator, Tooltip, ConfirmDialog } from '@hermes/plugin-sdk'
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'
import { useState, useEffect, useCallback, useRef } from 'react'
import { ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'

// ── Gateway RPC helpers ────────────────────────────────────────────────

async function wikiList(params = {}) {
  try {
    const result = await host.request('wiki.list', params)
    return result
  } catch (e) {
    return { pages: [], count: 0 }
  }
}

async function wikiGet(slug) {
  try {
    return await host.request('wiki.get', { slug })
  } catch (e) {
    return null
  }
}

async function wikiCreate(params) {
  return host.request('wiki.create', params)
}

async function wikiUpdate(params) {
  return host.request('wiki.update', params)
}

async function wikiDelete(slug) {
  return host.request('wiki.delete', { slug })
}

async function wikiStats() {
  try {
    return await host.request('wiki.stats', {})
  } catch (e) {
    return { total: 0, by_type: {}, avg_quality: 0 }
  }
}

// ── Quality badge color ────────────────────────────────────────────────

function qualityColor(q) {
  if (q >= 5) return 'var(--ui-accent)'
  if (q >= 4) return 'var(--ui-text-secondary)'
  if (q >= 3) return 'var(--ui-text-tertiary)'
  return 'var(--ui-text-quaternary)'
}

// ── Wiki page list item ────────────────────────────────────────────────

function WikiListItem({ page, selected, onClick }) {
  const q = page.quality
  return jsxs('button', {
    className: cn(
      'flex w-full items-start gap-2 px-3 py-2 text-left text-sm transition-colors',
      'hover:bg-(--chrome-action-hover)',
      selected && 'bg-(--chrome-action-hover)'
    ),
    onClick: () => { haptic('tap'); onClick(page) },
    children: [
      jsxs('div', {
        className: 'flex min-w-0 flex-1 flex-col gap-0.5',
        children: [
          jsxs('div', {
            className: 'flex items-center gap-1.5',
            children: [
              jsx('span', {
                className: 'truncate font-medium',
                children: page.title || page.slug
              }),
              q != null && jsx('span', {
                className: 'shrink-0 rounded px-1 text-[0.625rem]',
                style: { color: qualityColor(q), backgroundColor: 'var(--ui-bg-secondary)' },
                children: q
              })
            ]
          }),
          jsx('span', {
            className: 'truncate text-xs text-(--ui-text-tertiary)',
            children: page.date || ''
          }),
          page.summary && jsx('span', {
            className: 'line-clamp-2 text-xs text-(--ui-text-quaternary)',
            children: page.summary.slice(0, 80)
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
  const [topics, setTopics] = useState(
    Array.isArray(page?.topics) ? page.topics.join(', ') : (page?.topics || '')
  )
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
      await wikiUpdate({
        slug: page.slug,
        title,
        full_content: content,
        topics: topics.split(',').map(t => t.trim()).filter(Boolean),
        summary: content.slice(0, 200)
      })
      host.notify({ kind: 'info', message: 'Wiki page saved' })
      setEditing(false)
      onRefresh()
    } catch (e) {
      host.notify({ kind: 'error', message: `Save failed: ${e.message}` })
    }
    setSaving(false)
  }

  async function handleDelete() {
    try {
      await wikiDelete(page.slug)
      host.notify({ kind: 'info', message: 'Wiki page deleted' })
      setShowDeleteConfirm(false)
      onBack()
      onRefresh()
    } catch (e) {
      host.notify({ kind: 'error', message: `Delete failed: ${e.message}` })
    }
  }

  return jsxs('div', {
    className: 'flex h-full flex-col',
    children: [
      // Toolbar
      jsxs('div', {
        className: 'flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
        children: [
          jsx('button', {
            className: 'rounded p-1 hover:bg-(--chrome-action-hover)',
            onClick: onBack,
            children: jsx(Codicon, { name: 'arrow-left' })
          }),
          jsx('span', {
            className: 'flex-1 truncate text-sm font-medium',
            children: page.title
          }),
          page.quality != null && jsx(Badge, {
            variant: 'secondary',
            children: `Q${page.quality}`
          }),
          jsx(Separator, { orientation: 'vertical', className: 'h-4' }),
          jsx(Tooltip, {
            label: editing ? 'Cancel' : 'Edit',
            children: jsx('button', {
              className: cn('rounded p-1 hover:bg-(--chrome-action-hover)', editing && 'text-(--ui-accent)'),
              onClick: () => { setEditing(!editing); if (editing) { setTitle(page.title); setContent(page.full_content || '') } },
              children: jsx(Codicon, { name: editing ? 'close' : 'edit' })
            })
          }),
          editing && jsx(Tooltip, {
            label: saving ? 'Saving...' : 'Save',
            children: jsx('button', {
              className: 'rounded p-1 text-(--ui-accent) hover:bg-(--chrome-action-hover)',
              onClick: handleSave,
              disabled: saving,
              children: jsx(Codicon, { name: saving ? 'loading' : 'check' })
            })
          }),
          jsx(Tooltip, {
            label: 'Delete',
            children: jsx('button', {
              className: 'rounded p-1 text-red-500 hover:bg-(--chrome-action-hover)',
              onClick: () => setShowDeleteConfirm(true),
              children: jsx(Codicon, { name: 'trash' })
            })
          })
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
            jsx(Fragment, {
              children: page.topics.map(t =>
                jsx(Badge, { variant: 'outline', className: 'text-[0.625rem]', children: t }, t)
              )
            })
        ]
      }),
      // Content
      jsx('div', {
        className: 'flex-1 overflow-y-auto px-4 py-3',
        children: editing
          ? jsxs('div', {
              className: 'flex flex-col gap-3',
              children: [
                jsxs('div', {
                  children: [
                    jsx('label', { className: 'mb-1 block text-xs text-(--ui-text-tertiary)', children: 'Title' }),
                    jsx('input', {
                      className: 'w-full rounded border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) px-2 py-1 text-sm',
                      value: title,
                      onChange: e => setTitle(e.target.value)
                    })
                  ]
                }),
                jsxs('div', {
                  children: [
                    jsx('label', { className: 'mb-1 block text-xs text-(--ui-text-tertiary)', children: 'Topics (comma-separated)' }),
                    jsx('input', {
                      className: 'w-full rounded border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) px-2 py-1 text-sm',
                      value: topics,
                      onChange: e => setTopics(e.target.value)
                    })
                  ]
                }),
                jsxs('div', {
                  className: 'flex-1',
                  children: [
                    jsx('label', { className: 'mb-1 block text-xs text-(--ui-text-tertiary)', children: 'Content (Markdown)' }),
                    jsx('textarea', {
                      className: 'h-[400px] w-full resize-none rounded border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) px-2 py-1 font-mono text-sm',
                      value: content,
                      onChange: e => setContent(e.target.value)
                    })
                  ]
                })
              ]
            })
          : jsx('div', {
              className: 'prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap text-sm',
              children: page.full_content || page.summary || 'No content'
            })
      }),
      // Delete confirmation
      showDeleteConfirm && jsx(ConfirmDialog, {
        open: true,
        title: 'Delete Wiki Page',
        description: `Are you sure you want to delete "${page.title}"? This cannot be undone.`,
        confirmLabel: 'Delete',
        variant: 'destructive',
        onConfirm: handleDelete,
        onCancel: () => setShowDeleteConfirm(false)
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
    if (!title.trim()) {
      host.notify({ kind: 'error', message: 'Title is required' })
      return
    }
    setSaving(true)
    try {
      const slug = new Date().toISOString().slice(0, 10) + '_' +
        title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40)
      await wikiCreate({
        slug,
        title,
        full_content: content,
        topics: topics.split(',').map(t => t.trim()).filter(Boolean),
        summary: content.slice(0, 200),
        page_type: 'manual',
        date: new Date().toISOString().slice(0, 10)
      })
      host.notify({ kind: 'info', message: 'Wiki page created' })
      onCreated()
    } catch (e) {
      host.notify({ kind: 'error', message: `Create failed: ${e.message}` })
    }
    setSaving(false)
  }

  return jsx('div', {
    className: 'fixed inset-0 z-50 flex items-center justify-center bg-black/50',
    onClick: e => { if (e.target === e.currentTarget) onClose() },
    children: jsxs('div', {
      className: 'w-[600px] max-h-[80vh] overflow-y-auto rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) p-4 shadow-xl',
      children: [
        jsx('h2', {
          className: 'mb-4 text-lg font-medium',
          children: 'New Wiki Page'
        }),
        jsxs('div', {
          className: 'flex flex-col gap-3',
          children: [
            jsxs('div', {
              children: [
                jsx('label', { className: 'mb-1 block text-xs text-(--ui-text-tertiary)', children: 'Title *' }),
                jsx('input', {
                  className: 'w-full rounded border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) px-2 py-1 text-sm',
                  value: title,
                  onChange: e => setTitle(e.target.value),
                  placeholder: 'Page title',
                  autoFocus: true
                })
              ]
            }),
            jsxs('div', {
              children: [
                jsx('label', { className: 'mb-1 block text-xs text-(--ui-text-tertiary)', children: 'Topics (comma-separated)' }),
                jsx('input', {
                  className: 'w-full rounded border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) px-2 py-1 text-sm',
                  value: topics,
                  onChange: e => setTopics(e.target.value),
                  placeholder: 'docker, nginx, ssl'
                })
              ]
            }),
            jsxs('div', {
              children: [
                jsx('label', { className: 'mb-1 block text-xs text-(--ui-text-tertiary)', children: 'Content (Markdown)' }),
                jsx('textarea', {
                  className: 'h-[300px] w-full resize-none rounded border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) px-2 py-1 font-mono text-sm',
                  value: content,
                  onChange: e => setContent(e.target.value),
                  placeholder: '# Page Title\n\nWrite your wiki page here...'
                })
              ]
            }),
            jsxs('div', {
              className: 'flex justify-end gap-2',
              children: [
                jsx(Button, {
                  variant: 'secondary',
                  onClick: onClose,
                  children: 'Cancel'
                }),
                jsx(Button, {
                  onClick: handleCreate,
                  disabled: saving,
                  children: saving ? 'Creating...' : 'Create'
                })
              ]
            })
          ]
        })
      ]
    })
  })
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

  const refresh = useCallback(async () => {
    setLoading(true)
    const [listResult, statsResult] = await Promise.all([
      wikiList(search ? { query: search } : {}),
      wikiStats()
    ])
    setPages(listResult.pages || [])
    setStats(statsResult)
    setLoading(false)
  }, [search])

  useEffect(() => { refresh() }, [refresh])

  async function handleSelect(page) {
    setSelected(page)
    const full = await wikiGet(page.slug)
    setDetail(full)
  }

  function handleBack() {
    setSelected(null)
    setDetail(null)
  }

  // Detail view
  if (selected) {
    return jsx(WikiDetail, {
      page: detail,
      onBack: handleBack,
      onRefresh: () => { refresh(); if (selected) wikiGet(selected.slug).then(setDetail) }
    })
  }

  // List view
  return jsxs('div', {
    className: 'flex h-full flex-col',
    children: [
      // Header
      jsxs('div', {
        className: 'flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
        children: [
          jsx(Codicon, { name: 'book', className: 'text-(--ui-accent)' }),
          jsx('span', {
            className: 'flex-1 text-sm font-medium',
            children: 'Wiki'
          }),
          stats && jsxs(Badge, {
            variant: 'secondary',
            children: [stats.total, ' pages']
          }),
          jsx(Tooltip, {
            label: 'New page',
            children: jsx('button', {
              className: 'rounded p-1 hover:bg-(--chrome-action-hover)',
              onClick: () => setShowNew(true),
              children: jsx(Codicon, { name: 'add' })
            })
          }),
          jsx(Tooltip, {
            label: 'Refresh',
            children: jsx('button', {
              className: 'rounded p-1 hover:bg-(--chrome-action-hover)',
              onClick: refresh,
              children: jsx(Codicon, { name: 'refresh' })
            })
          })
        ]
      }),
      // Search
      jsx('div', {
        className: 'px-3 py-2',
        children: jsx(SearchField, {
          value: search,
          onChange: setSearch,
          placeholder: 'Search wiki pages...',
          className: 'w-full'
        })
      }),
      // Page list
      jsx('div', {
        className: 'flex-1 overflow-y-auto',
        children: loading
          ? jsx('div', {
              className: 'flex items-center justify-center py-8 text-(--ui-text-quaternary)',
              children: 'Loading...'
            })
          : pages.length === 0
            ? jsx(EmptyState, {
                icon: 'book',
                title: search ? 'No results' : 'No wiki pages yet',
                description: search
                  ? 'Try a different search term'
                  : 'Wiki pages are auto-generated from conversations, or create one manually'
              })
            : jsx(ScrollArea, {
                children: pages.map(page =>
                  jsx(WikiListItem, {
                    page,
                    selected: selected?.slug === page.slug,
                    onClick: handleSelect
                  }, page.slug)
                )
              })
      }),
      // New page dialog
      showNew && jsx(NewPageDialog, {
        onClose: () => setShowNew(false),
        onCreated: () => { setShowNew(false); refresh() }
      })
    ]
  })
}

// ── Plugin registration ────────────────────────────────────────────────

export default {
  id: 'hermes-wiki',
  name: 'Hermes Wiki',
  register(ctx) {
    // Sidebar nav item (below Artifacts/产物)
    ctx.register({
      id: 'wiki-nav',
      area: SIDEBAR_NAV_AREA,
      data: {
        codicon: 'book',
        label: 'Wiki',
        path: '/wiki'
      }
    })

    // Full-page route
    ctx.register({
      id: 'wiki-page',
      area: ROUTES_AREA,
      data: { path: '/wiki' },
      render: () => jsx(WikiPage, {})
    })
  }
}
