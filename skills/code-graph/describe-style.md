# describe-style — writing component descriptions

Descriptions are read by people with limited time and working memory
(style distilled from the i-have-adhd skill). Every description stored via
`set_description` follows these rules:

1. **First line = what it does, as an action.** "Routes intents to rule domains." Not "This module is responsible for…".
2. **Numbered steps for behavior**, one bounded action each, max 5.
3. **Link neighbors** with `codegraph://` URIs in `links` — the callers/callees a reader will want next.
4. **State the one non-obvious constraint** (the WHY) if there is one; skip narration of the obvious.
5. **Under 80 words.** If it needs more, the component probably needs splitting — say that instead.

Example body:

```
Routes an agent intent to rule domains by keyword and path glob.

1. Lowercases the intent
2. Unions domains from every matching router rule
3. Falls back to default domains when nothing fires

Constraint: domains are free-form strings; unknown domains must not raise.
```
