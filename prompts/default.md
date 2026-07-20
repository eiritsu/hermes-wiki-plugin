Analyze the following conversation session and return strict JSON only.

## Output Schema

```json
{
  "title": "Concise session title (max 30 chars)",
  "language": "ISO 639-1 code (en/zh/ja/ko/de/fr/es)",
  "quality": 1-5,
  "content_type": "troubleshooting|development|research|planning|review|setup|migration|quickfix|discussion",
  "topics": ["topic-slug-1", "topic-slug-2"],
  "entities": ["Entity Name"],
  "keywords": ["keyword1", "keyword2"],
  "result": "One-sentence outcome",
  "background": "User's goal or context (2-3 sentences)",
  "decisions": ["Decision with reasoning"],
  "problems": ["Problem -> Solution (detailed)"],
  "full_content": "Complete Obsidian wiki page (see format below)"
}
```

## Rules

1. **Language**: Respond in the SAME LANGUAGE as the session content.
   - All text fields (title, result, background, decisions, problems, full_content) must match.
   - topic slugs, entity names, content_type always in English.

2. **Quality scoring**:
   - 5: Deep technical work, important decisions, transferable knowledge
   - 4: Substantial work, useful reference material
   - 3: Moderate value, some reusable content
   - 2: Simple Q&A, low reusability
   - 1: Noise, personal data, no transferable knowledge

3. **full_content format** (Obsidian wiki style):

```markdown
---
session_id: "session_id_here"
date: YYYY-MM-DD
tags: [topic1, topic2]
aliases: ["Alternative Title"]
---

# Title (YYYY-MM-DD)

## Background
2-3 sentences describing the user's goal or situation.

## Key Decisions
- Decision with reasoning
- Use [[Entity Name]] for cross-references to other entities

## Problems & Solutions
- Problem description
  - Root cause
  - Solution applied
  - Commands or code if applicable

## Result
Summary of what was accomplished and its impact.

## Related
- [[Related Topic 1]]
- [[Related Topic 2]]
- #tag1 #tag2
```

4. **full_content requirements**:
   - Must be substantial (at least 5-8 paragraphs for quality >= 3)
   - Include actual commands, code snippets, or technical details when relevant
   - Use `[[wiki-link]]` syntax to reference entities: `[[Docker]]`, `[[nginx]]`, `[[VPS Server]]`
   - Use `#tag` for topics: `#networking`, `#troubleshooting`
   - Include the YAML frontmatter block at the top
   - Write as if this page will be read by someone who wasn't in the conversation

5. **topics**: Max 3, lowercase kebab-case slugs. Example: `docker-networking`, `nginx-config`, `resume-editing`

6. **entities**: Named things that matter — tools, systems, people, services. Example: `Docker Compose`, `nginx`, `Cloudflare WARP`

7. **Skip**: If the session is mostly personal data editing (resume, personal documents) with no transferable technical knowledge, set quality=1 and keep full_content minimal.
