You are integrating multiple conversation sessions that share the same topic into a single topic wiki page. The sessions below have already been individually distilled into structured wiki pages. Your job is NOT to summarize them again — it is to **integrate** them: identify cross-session patterns, deduplicate recurring decisions, trace how the topic evolved, and surface insights that only emerge when sessions are read together.

## Output Schema

Return strict JSON only:

```json
{
  "title": "Topic title (max 30 chars)",
  "language": "ISO 639-1 code (en/zh/ja/ko/de/fr/es)",
  "overview": "3-5 sentences describing what this topic is about, the core questions it spans across sessions, and why it matters",
  "cross_session_decisions": [
    "Decision X (validated across sessions 1, 3): chose Y because Z. Note when the same decision was independently reached in multiple sessions — that's a strong signal."
  ],
  "patterns_insights": [
    "Recurring pattern or shared insight observed across multiple sessions"
  ],
  "key_evolution": "How this topic evolved across sessions: what was the initial approach in the earliest session, what changed, what is the current state in the latest session. If the topic is stable across sessions, say so explicitly.",
  "timeline": [
    {"date": "YYYY-MM-DD", "title": "Session title", "slug": "session_slug_here"}
  ],
  "entities": ["Entity1", "Entity2"],
  "full_content": "Complete topic wiki page (see format below)"
}
```

## Rules

1. **Language**: Respond in the SAME LANGUAGE as the dominant session language (the language most sessions were written in).
   - All text fields (title, overview, cross_session_decisions, patterns_insights, key_evolution, full_content) must match.
   - entity names always in English.

2. **Integration focus** — the output MUST add value beyond concatenating individual sessions:
   - **cross_session_decisions**: only include decisions that appear in 2+ sessions, OR a single decisive session that resolves a debate seen in others. Reference which sessions by date.
   - **patterns_insights**: capture recurring themes, repeated mistakes, validated approaches. If sessions reach the same conclusion independently, that is a strong pattern.
   - **key_evolution**: explicitly call out progression. "Initially X, after session Y pivoted to Z, now W." Avoid vague "the topic has evolved" statements.
   - **timeline**: list all linked sessions chronologically (oldest first).

3. **DO NOT output** these fields — they are session-specific and do not belong on a topic page:
   - `quality` (session-level metric, not topic-level)
   - `content_type` (single session classification)
   - `background` (single session perspective)
   - `facts` (already extracted per-session; re-extracting here would duplicate facts into holographic memory)
   - `keywords` (use entities instead)

4. **full_content format** (Obsidian wiki style):

```markdown
---
topic: topic-slug-here
type: topic-aggregate
language: en
sessions: 5
updated: YYYY-MM-DD
---

# Topic Title

## Overview
3-5 sentences. What this topic covers, the core questions it spans, why it matters.

## Key Decisions Across Sessions
- **Decision name** (sessions 2026-07-15, 2026-07-23): chose X because Y. Validated by [details].
- **Decision name** (session 2026-07-20): made choice A when [context]. Superseded by later decision on 2026-07-23.

## Patterns & Insights
- Pattern: [description]. Observed in sessions [[2026-07-15_slug]] and [[2026-07-23_slug]].
- Insight: [description].

## Evolution
- 2026-07-15: [initial state / approach]
- 2026-07-20: [what changed]
- 2026-07-23: [current state]

## Sessions
- [[2026-07-15_session-title-1]] — 1-line summary
- [[2026-07-20_session-title-2]] — 1-line summary
- [[2026-07-23_session-title-3]] — 1-line summary

## Related Entities
- [[Entity1]]
- [[Entity2]]
- [[Entity3]]
```

5. **full_content requirements**:
   - Must reference individual sessions using `[[session_slug]]` syntax — readers should be able to navigate from any topic conclusion back to the original session.
   - `key_evolution` MUST be concrete with dates, not abstract.
   - At least 3 sections after Overview (Key Decisions / Patterns / Evolution). The "Sessions" list at the end is mandatory.

6. **timeline field**: ordered chronologically (oldest first), one entry per session. The `slug` field must match the session's wiki slug exactly so it can be linked.

7. **Skip integration if not meaningful**: if sessions are too sparse (only 2 sessions with no overlapping decisions/patterns), still produce a topic page but keep it minimal — just Overview + Sessions list. Do NOT fabricate cross-session insights.

8. **Entity deduplication**: merge entities that refer to the same thing (e.g. "Docker" and "Docker Compose" → ["Docker", "Docker Compose"] only if both are used distinctly; "PostgreSQL" and "postgres" → ["PostgreSQL"]).