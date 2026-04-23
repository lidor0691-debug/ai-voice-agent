# Business Context Template

Add as a **knowledge_item** with `category = "Business Context"` for each agent.

---

## Generic Template

```
שם העסק: [שם]
תחום: [תחום]

מה מוכרים:
- [מוצר/שירות 1]
- [מוצר/שירות 2]

מטרת ההמרה: [מה נחשב הצלחה — פגישה? רכישה? שיעור ניסיון? הצעת מחיר?]

סוגי לידים:
- [סוג 1 — מאיפה מגיעים, מה מחפשים]
- [סוג 2]

ליד חם:
- [מה הופך ליד לחם — ביקש הצעה? שאל על מחיר? ביקש לקבוע?]

מדדים חשובים:
- [מה צריך לעקוב אחריו — זמן תגובה? אחוז סגירה? שיעורי ניסיון?]

פעולות מומלצות:
- [מה לעשות כשיש ליד חדש]
- [מה לעשות כשליד לא עונה]
- [מה לעשות כשיש הזדמנות]

לא רלוונטי:
- [מה לא קשור לעסק — כדי שמאיה לא תבלבל]

טון ושפה:
- [איך העסק מדבר עם לקוחות — רשמי? חברי? מקצועי?]
```

---

## How to add for a new client

1. Go to Supabase → `knowledge_items` table
2. Insert a new row:
   - `agent_id`: the agent's UUID
   - `category`: `Business Context`
   - `title`: business name
   - `content`: filled template (see examples below)
   - `priority`: 100
   - `is_active`: true

Maya will automatically pick it up on the next assistant session.

---

## Examples

### BPM Dance Studio (agent: Maya BPM)

See live data in Supabase knowledge_items for agent `2145e5c9-52b2-451a-9aa9-6329a8293dc5`.

### Roi Insurance (agent: מאיה - Roi Insurance)

See live data in Supabase knowledge_items for agent `5e28e7ec-ec83-4683-af50-3749115cdec7`.
