# virus-lab

**מטפסי התחייבות לנתונים מובנים** — מנוע שקורא טפסים סרוקים, מצולמים וכתובים ביד, מחלץ את השדות, מסמן בעצמו איפה הוא לא בטוח, ושומר רשומה לכל התחייבות לבדיקה ולאישור בתוך המערכת.

אתגר בשיתוף **המעבדה המרכזית לנגיפים, משרד הבריאות** · האקתון AI קוד פתוח 2026

> **סטטוס:** המערכת עובדת ופרוסה ב־[virus-lab-e0zp.onrender.com](https://virus-lab-e0zp.onrender.com). תוצאות המדידה מול טבלת האמת יתווספו ב[בדיקות ומדידה](#בדיקות-ומדידה-).
>
> לפי הנחיות האתגר המעודכנות (18.10), התוצר הוא רשומות שנשמרות במסד נתונים, עם אישור, חיפוש וסינון. ייצוא לקובץ הוא תוספת (CSV ו־JSON). פירוט: [docs/SPEC.md, סעיף 0](docs/SPEC.md).

---

## הבעיה

המעבדה מקבלת כל יום דגימות מקופות החולים ומבתי החולים, ועם כל דגימה טופס התחייבות — כל מוסד בפורמט אחר, חלקם בכתב יד, עם מדבקות וחותמות. היום מישהי מקלידה את כולם לאקסל ידנית.

## מה המערכת עושה

1. **מעלים** PDF ותמונות — קובץ אחד או ערימה
2. **המערכת מפצלת לעמודים**, מיישרת עמוד מסובב, ומצרפת עמוד המשך לטופס שלו
3. **מחלצת** לכל טופס: שם פרטי, שם משפחה, ת״ז, מספרים מרכזיים, תאריך קבלת הדגימה, גורם שולח, מספרי התחייבות וסוג הטופס
4. **מסמנת לבדיקה** כל שדה שלא בטוח, עם סיבה — ושדה שלא נמצא נשאר ריק, לא מנוחש
5. **שומרת רשומה לכל התחייבות** במסד הנתונים, כממתינה, מיד אחרי הקריאה
6. **מתקנים או מאשרים ערך** במקום, עם העמוד המקורי ליד; השרת מחשב את הסימון מחדש
7. **מאשרים רשומה** (האישור נחסם כל עוד יש בה שדה מסומן), או את כל המוכנות בלחיצה אחת
8. **חוזרים לרשומות:** חיפוש, סינון, ממתין מול מאושר, וייצוא CSV או JSON של מה שסונן

---

## איך זה עובד

```
UploadPanel ──POST /api/v1/extract──► FastAPI         (קובץ אחד בכל בקשה)
                                        │
  ingest → orient → extract → assemble → apply_rules → group → save_form
  קובץ      יישור    Gemini    פלט המודל   נרמול, ולידציה  עמודי    טופס אחד =
  →עמודים   כיוון    +סכימה    → החוזה     ומה דורש בדיקה  המשך     טרנזקציה אחת
                                                                      │
                                                                  PostgreSQL
                                                    רשומות · תמונת כל עמוד · יומן פעולות
                                                                      │
ReviewPage (טבלה + DocumentPreview) ◄── הרשומות שנשמרו ◄──────────────┤
   │ PATCH /records/{id}          תיקון/אישור ערך → apply_rules מחדש (שדה משותף: גם באחיות)
   │ POST  /records/{id}/approve  אישור רשומה → נחסם אם נשאר שדה מסומן
   └ POST  /records/approve       "אשרי את כל המוכנות"                │
RecordsPage ── GET /records          חיפוש, סינון, מונים ◄────────────┤
            └─ GET /records/export   CSV / JSON של מה שסונן ◄──────────┘
```

- **השמירה היא חלק מהחילוץ:** כל טופס נשמר ברגע שידוע שהעמוד הבא לא ממשיך אותו. כך העלאה ארוכה שנקטעת באמצע לא מאבדת את הטפסים שכבר נקראו
- **הקובץ שהועלה לא נשמר:** הוא נקרא בזיכרון בלבד. נשמרות הרשומות ותמונה מוקטנת ודחוסה של כל עמוד, בשביל התצוגה ליד הטבלה

### עקרונות התכנון

| עיקרון | למה |
|---|---|
| **כל עמוד נשלח כתמונה נפרדת למודל ראייה** (`gemini-3.8-flash`, Structured Output) | הדוגמאות סרוקות בלי שכבת טקסט; עמוד שנכשל לא מפיל את השאר; כל ערך מקושר לעמוד המקור |
| **ההחלטה מה דורש בדיקה נקבעת בקוד, לא במודל** | בניסויים המודל סימן ערכים שגויים כ"נמצא" ואף המציא הסבר. הקוד בודק ספרת ביקורת, תאריכים, רשימת שולחים ושדות חסרים |
| **נקודת כניסה אחת לכללים** (`apply_rules`, פונקציה טהורה) | אותם כללים רצים אחרי החילוץ, אחרי כל תיקון ולפני כל אישור — בלי לשכפל אותם ב־frontend |
| **השרת לא סומך על הלקוח** | הלקוח שולח רק ערכים ו־`confirmed`. השרת מחשב את הסימונים מחדש, ולא מאשר רשומה שנשאר בה שדה מסומן |
| **הערך שהמודל קרא לא נדרס** (`raw`), והתיקון והאישור נשמרים בנפרד | תמיד אפשר לראות מה נקרא במקור ומה שינתה המשתמשת |
| **ספק ה־AI מאחורי ממשק** (`ExtractionProvider`) | אפשר להחליף מודל בשורת הגדרה, לפתח ולבדוק עם נתוני דמה בלי מכסה ובלי רשת |
| **שלושה מבני נתונים נפרדים:** פלט המודל, הטופס הפנימי, הרשומה | רק `assemble.py` מכיר את פלט המודל, ולכן שיפור ה־prompt לא שובר את הכללים ואת ה־API |
| **רשומה לכל התחייבות, ב־PostgreSQL** | זו היחידה שנבדקת, מאושרת ומיוצאת. כמה מרכזיים של אותו טופס נשארים באותה רשומה, בלי צירופים |
| **טופס נשמר בטרנזקציה אחת, ולכל רשומה `version`** | כשל באמצע לא משאיר חצי טופס במסד, ושני חלונות פתוחים לא דורסים זה את התיקונים של זה |
| **הקובץ המקורי לא נשמר** | פרטיות: ההעלאה נקראת בזיכרון ולא נכתבת לדיסק. נשמרות רק הרשומות ותמונה דחוסה של כל עמוד |
| **חוזה אחד בין השרת לדף** (`schemas/api.py`) | ממנו נוצרים `openapi.json` והטיפוסים של ה־frontend, וה־CI נכשל אם אחד מהם לא מעודכן |
| **בלי OCR נוסף** | הטעויות שמדדנו היו בחירת מספר שגוי, לא קריאת ספרות שגויה — OCR לא פותר את זה |

האיפיון המלא — הגדרת כל שדה, כללי השורות, מדיניות הבדיקה וחוזה ה־API: **[docs/SPEC.md](docs/SPEC.md)**

---

## טכנולוגיות

| שכבה | טכנולוגיה |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | Python 3.13, FastAPI, Pydantic |
| AI | Google Gemini (`google-genai`), מודל `gemini-3.8-flash` |
| עיבוד מסמכים | PyMuPDF |
| מסד נתונים | PostgreSQL 17, psycopg 3 (async) עם connection pool |
| ייצוא | CSV ו־JSON, מספריית התקן של Python |
| פריסה | Docker (image אחד לשרת ולדף), Render (Frankfurt), GitHub Actions |

---

## מבנה הריפו

```
virus-lab/
├── backend/
│   ├── app/
│   │   ├── api/            # health, extract, records: רק קריאת הבקשה וקריאה לשכבה שמתחת
│   │   ├── schemas/        # api.py (החוזה), extraction.py (פלט המודל)
│   │   ├── pipeline/       # ingest, orient, assemble, group (עמודי המשך), service
│   │   ├── extraction/     # providers: gemini, fake, cached + prompts/
│   │   ├── rules/          # engine (apply_rules), normalize, validators, review_policy, records, senders.yaml
│   │   ├── storage/        # schema.sql, db (pool וסכמה), repo (SQL בלבד), service (שמירה), review (תיקון ואישור)
│   │   ├── export/         # records_export: CSV ו־JSON
│   │   └── i18n/           # he.yaml: ההודעות למשתמשת
│   ├── scripts/            # seed_demo, wipe_data, export_openapi
│   ├── tests/              # unit, contract, fixtures
│   └── eval/               # ground_truth.csv, metrics, run_eval
├── frontend/src/
│   ├── api/                # client, schema.d.ts (נוצר מ־OpenAPI)
│   ├── features/           # upload, preview, review, records
│   └── shared/             # layout, ui (tokens, רכיבים משותפים)
├── docs/                   # SPEC.md (איפיון), PLAN-DEV-B.md, GUIDELINES-V2-CHANGES.md
├── Dockerfile, render.yaml # השרת החי
├── docker-compose.yml      # Postgres מקומי
└── PLAN.md                 # תוכנית עבודה
```

---

## התקנה והרצה

### דרישות מקדימות

- Python 3.13
- Node.js 22
- Docker Desktop (בשביל Postgres מקומי)
- מפתח Gemini API מ־[Google AI Studio](https://aistudio.google.com/)

> הפקודות למטה ל־Windows PowerShell. ב־macOS/Linux: `python3` במקום `py -3.13`, ו־`.venv/bin/python` במקום `.\.venv\Scripts\python.exe`.

### Backend 🚧

```powershell
docker compose up -d db         # מהשורש: Postgres 17 מקומי, ועוד מסד לבדיקות (virus_lab_test)
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env          # ואז להדביק את המפתחות ב־GEMINI_API_KEYS
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

בדיקה: `http://localhost:8000/api/health` מחזיר `{"status": "ok", ...}`. תיעוד ה־API: `http://localhost:8000/docs`.

**אין כניסה:** כל מי שפותח את האתר יכול להשתמש בו, בלי משתמש וסיסמה (הוחלט ב־21.10).

ב־Windows צריך להשאיר את `--reload`: בלעדיו uvicorn רץ על event loop ש־psycopg לא תומך בו במצב async. `docker compose down -v` מוחק את כל הנתונים המקומיים.

### Frontend 🚧

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

פותחים `http://localhost:5173`.

### בדיקות לפני PR (אותן בדיקות שה־CI מריץ)

```powershell
# backend/ (pytest צריך את ה־Postgres מ־docker compose)
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.export_openapi --check   # אחרי שינוי בחוזה: בלי --check, ואז npm run gen:api

# frontend/
npm run lint
npm run build
npm test
```

### עבודה בלי מפתח ובלי מכסה

```powershell
# backend/.env
EXTRACTION_PROVIDER=fake
```

השרת מחזיר תוצאות שמורות מ־`tests/fixtures/` — מתאים לפיתוח הממשק ולבדיקות.

### פריסה (Render)

השרת החי הוא image אחד של Docker ([Dockerfile](Dockerfile)): Node בונה את `frontend/dist`, ו־FastAPI מגיש גם את ה־API וגם את הדף מאותה כתובת, כך שאין CORS. [render.yaml](render.yaml) מגדיר את השרת ואת ה־Postgres, שניהם בתוכנית החינמית ובפרנקפורט. כל מיזוג ל־`main` נפרס אוטומטית.

**פעם ראשונה:**

1. ב־Render: **New → Blueprint**, ובוחרים את הריפו. ל־Render צריכה להיות גישה לריפו דרך ה־GitHub App שלו, ואת זה מאשרת בעלת הריפו.
2. Render מבקש את הערכים שלא נמצאים בריפו:
   - `GEMINI_API_KEYS`: המפתחות, מופרדים בפסיקים.
   - `FRONTEND_ORIGIN`: הכתובת הציבורית, בדיוק ובלי `/` בסוף, למשל `https://virus-lab-e0zp.onrender.com`. בקשה שמשנה נתונים ומגיעה מכתובת אחרת נדחית (`403`).
3. בדיקה: `https://<הכתובת>/api/health` מחזיר `"status": "ok"` ו־`"extraction_provider": "gemini"`. השרת יוצר את הטבלאות בעלייה הראשונה, ומשדרג מסד מגרסה קודמת בלי למחוק רשומות.
4. **השרת לא נרדם:** השרת פונה לכתובת הציבורית של עצמו כל 10 דקות ([app/keep_alive.py](backend/app/keep_alive.py)), בלי הגדרה נוספת. בלוגים של Render מופיעה בקשת `GET /api/health` כל 10 דקות. כדי שזה יישאר בתוך 750 השעות החינמיות בחודש, זה צריך להיות השרת החינמי היחיד ב־workspace.

**בדיקה מקומית של ה־image:**

```powershell
docker build -t virus-lab .
docker run --rm -p 8000:8000 -e EXTRACTION_PROVIDER=fake -e FRONTEND_ORIGIN=http://localhost:8000 virus-lab
```

ה־CI בונה את ה־image ובודק שהוא מגיש את ה־API ואת הדף (job `docker`).

---

## משתני סביבה

### `backend/.env`

| משתנה | ברירת מחדל | תיאור |
|---|---|---|
| `GEMINI_API_KEYS` | — | **חובה** כש־`EXTRACTION_PROVIDER=gemini`. מפתח אחד לכל פרויקט ב־Google, מופרדים בפסיקים. כשהמכסה היומית של מפתח נגמרת, עוברים למפתח הבא. לא נכנס ל־Git |
| `GEMINI_API_KEY` | — | השם הישן למפתח יחיד. עדיין נקרא, ונוסף אחרי `GEMINI_API_KEYS` |
| `GEMINI_MODEL` | `gemini-3.8-flash` | החלפת מודל בלי שינוי קוד |
| `GEMINI_THINKING` | `low` | `low` / `medium` / `high` |
| `EXTRACTION_PROVIDER` | `gemini` | `gemini` / `fake` 🚧 |
| `EXTRACTION_CACHE` | `false` | מטמון לפיתוח בלבד, על קובצי דוגמה בלבד: עמוד ש־Gemini כבר קרא (אותו מודל ואותו prompt) נלקח מ־`backend/.cache/` בלי פנייה חדשה. לא בשרת החי |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | הכתובת של הדף: CORS בפיתוח, ובדיקת ה־`Origin` (CSRF) על בקשה שמשנה נתונים. בשרת החי: הכתובת הציבורית |
| `ENV` | `development` | `production` בשרת החי (מ־`render.yaml`): HSTS, ובלי `/docs` ו־`/openapi.json` |
| `DATABASE_URL` | — | Postgres. מקומית: מ־`docker compose`, כמו ב־`.env.example`. בשרת החי: ה־Internal URL של Render, שמגיע מ־`render.yaml`. בלעדיו השרת עולה, אבל העלאה ורשומות מחזירות `503` |
| `STATIC_DIR` | ריק | תיקיית ה־frontend הבנוי, ש־FastAPI מגיש. מוגדר רק ב־image של Docker. בפיתוח Vite מגיש את הדף |
| `KEEP_ALIVE_URL` | ריק | הכתובת הציבורית שהשרת פונה אליה (`/api/health`) כדי ש־Render לא ירדים אותו. כשהוא ריק משתמשים ב־`RENDER_EXTERNAL_URL`, ש־Render מגדיר בעצמו. בלי שניהם (מקומית ובטסטים) הפנייה כבויה |
| `KEEP_ALIVE_INTERVAL_S` | `600` | כל כמה שניות לפנות. לפחות 60. Render מרדים שרת חינמי אחרי 15 דקות בלי בקשות מבחוץ |
| `MAX_FILE_MB` | `20` | גודל קובץ מקסימלי 🚧 |
| `MAX_CONCURRENCY` | `4` | עמודים שמעובדים במקביל 🚧 |

### `frontend/.env.local`

| משתנה | ברירת מחדל | תיאור |
|---|---|---|
| `VITE_API_BASE_URL` | ריק | ריק בפיתוח: הבקשות הולכות ל־`/api`, וה־proxy של Vite מעביר אותן ל־`http://localhost:8000`. ממלאים רק כשה־frontend וה־backend בכתובות שונות. **לא לשים כאן מפתחות** — כל `VITE_*` מגיע לדפדפן |

---

## API

| Method | Path | תיאור |
|---|---|---|
| `GET` | `/api/health` | בדיקת חיים |
| `POST` | `/api/v1/extract` | `multipart/form-data` עם `files` → הרשומות שנשמרו כממתינות, והעמודים שנכשלו |
| `GET` | `/api/v1/records` | רשימה עם חיפוש (`q`), סינון, מיון, דפדוף ומונים של ממתין ומאושר |
| `GET` | `/api/v1/records/{id}` | רשומה אחת עם כל השדות |
| `PATCH` | `/api/v1/records/{id}` | תיקון או אישור של ערכים. מחזיר את הרשומה ואת האחיות שהשתנו |
| `POST` | `/api/v1/records/{id}/approve` | אישור רשומה, או `409 review_required` עם השדות החוסמים |
| `POST` | `/api/v1/records/approve` | אישור של כל המוכנות: מה אושר, ומה דולג ולמה |
| `DELETE` | `/api/v1/records/{id}` | מחיקה של רשומה ממתינה |
| `GET` | `/api/v1/records/export` | `format=csv\|json`, עם אותם מסננים כמו הרשימה |
| `GET` | `/api/v1/pages/{page_id}/image` | תמונת העמוד לתצוגה ליד הטבלה |
| `GET` | `/api/v1/senders` | הרשימה הסגורה של הגורמים השולחים |

כל בקשה שמשנה נתונים חייבת להגיע מהדף של האתר (בדיקת `Origin`). שגיאות מוחזרות כ־`application/problem+json`. החוזה המלא ודוגמאות: [docs/SPEC.md §9](docs/SPEC.md#9-חוזה-api).

---

## בדיקות ומדידה 🚧

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest                # בדיקות יחידה וחוזה
.\.venv\Scripts\python.exe eval\run_eval.py         # מדידה מול טבלת האמת
```

### תוצאות

> יתמלא אחרי ההרצה על 10–15 טפסים מול `eval/ground_truth.csv`. נדווח דיוק לפי שדה, כיסוי, **שגיאות שלא סומנו לבדיקה**, נכונות מספר השורות וזמן לעמוד.

### מה כבר נמדד (ניסוי ראשוני, 8 עמודים)

נקודת התחלה בלבד — מול קריאה ידנית ולא מול טבלת אמת מאומתת:

- **מספר מרכזי:** נכון ב־7 מתוך 8, כולל עמודים עם 2 ו־3 מרכזיים. המודל לא התבלבל במדבקות של מעבדות אחרות
- **מספר התחייבות:** זוהה נכון גם בכינויים "דרישה", "מספר דגימה" ו"אסמכתא"
- **הטעויות:** כולן בחירת מספר שגוי (מספר "מקרה" במקום ת״ז, שם האב במקום שם המטופל) — לא קריאת ספרות שגויה
- **עמודים מסובבים:** איבדו שדות בכתב יד; נוספה לולאת תיקון כיוון
- **זמן:** 4–9 שניות לעמוד ב־`thinking=low`. `medium` היה איטי פי 4 בלי שיפור

---

## מגבלות ידועות

- **שמות:** בטפסי הדוגמה הוחלפו בשרבוט, ולכן הדיוק בשמות לא נמדד
- **סימון בטוש צהוב:** כמעט כל שדות הדוגמה מסומנים בצהוב, והמודל נעזר בזה. בטפסים בלי סימון הדיוק עשוי להיות נמוך יותר
- **טופס רב־עמודי:** כל עמוד מטופל כטופס נפרד
- **מכסה:** ב־free tier של Gemini יש 20 בקשות ביום לפרויקט — לא מספיק לשימוש אמיתי
- **אין ניסיון חוזר לעמוד בודד:** עמוד שנכשל, או שלא נקרא כי המכסה נגמרה באמצע קובץ, מוצג ברשימת העמודים שנכשלו. שליחה חוזרת של כל הקובץ תיצור פעמיים את הרשומות של העמודים שכבר נשמרו
- **העלאה שנקטעה:** אחרי שגיאת רשת או שגיאת שרת באמצע העלאה אי אפשר לדעת אילו עמודים נשמרו, ולכן אין "נסי שוב". בודקים במסך הרשומות לפני שמעלים שוב
- **הסבר המודל (`evidence`)** אינו הוכחה; תמיד לבדוק מול העמוד המקורי
- **צילומי iPhone בפורמט HEIC** לא נתמכים; יש לשמור כ־JPG
- **אין כניסה (הוחלט ב־21.10):** כל מי שיש לו את הקישור יכול להעלות קבצים (ולצרוך מהמכסה של Gemini), לתקן, לאשר, למחוק ולייצא רשומות. ביומן הפעולות נרשם מה נעשה ומתי, אבל לא מי עשה את זה

## מה נדרש כדי שהמעבדה תשתמש בזה

1. **כניסה עם משתמשים** — לפני שמעלים טפסים אמיתיים, ובשביל לדעת מי אישר כל רשומה
2. **חשבון בתשלום** אצל ספק ה־AI — כדי שהקלט לא ישמש לאימון, ובשביל מכסה מספקת
3. **אישור אבטחת מידע** של הארגון לשליחת מידע רפואי לספק חיצוני, או מעבר למודל שרץ בתוך הרשת
4. **מדידה על טפסים אמיתיים** (בלי סימון צהוב), בהשתתפות הצוות
5. **פורמט האקסל המדויק** שהמעבדה עובדת איתו
6. **ניהול הרשימה הסגורה** של גורמים שולחים על ידי המעבדה

---

## פרטיות ואבטחה

- עובדות **רק עם קובצי הדוגמה של האתגר**, שבהם הפרטים האישיים שונו
- הקובץ שהועלה עובר **בזיכרון בלבד** ולא נשמר. נשמרות רק הרשומות ותמונה דחוסה של כל עמוד, ב־PostgreSQL מנוהל של Render (Frankfurt, האיחוד האירופי). פירוט ב־[SPEC 11.1](docs/SPEC.md#111-פרטיות-ואבטחה)
- הלוגים לא מכילים שמות, ת״ז או תוכן טפסים: ה־access log נכתב בלי ה־query של החיפוש, ושגיאה לא צפויה נרשמת רק לפי הסוג והנתיב, בלי ההודעה וה־traceback
- **בלי כניסה:** האתר פתוח לכל מי שיש לו את הקישור (הוחלט ב־21.10). בקשה שמשנה נתונים חייבת להגיע מהדף של האתר עצמו (בדיקת `Origin`), כך שאתר אחר לא יכול לשלוח שינויים דרך הדפדפן של מי שגולש בו
- **כותרות:** CSP שמתיר רק את האתר עצמו, `nosniff`, `no-referrer`, איסור הטמעה במסגרת, ו־HSTS בשרת החי. תשובות ה־API לא נשמרות במטמון (`no-store`)
- **בשרת החי** (`ENV=production`): אין `/docs` ואין `/openapi.json`
- **מחיקה בפקודה אחת:** `python -m scripts.wipe_data` מוחק את כל העמודים, התמונות והרשומות
- מפתח ה־API רק ב־`backend/.env` ובמשתני הסביבה של Render; הקבצים `.env` ותוצאות הניסויים מוחרגים מ־Git

### בדיקה לפני הגשה

```powershell
curl.exe -I https://<הכתובת>/                       # CSP, nosniff, no-referrer, X-Frame-Options, HSTS
curl.exe -s -o NUL -w "%{http_code}" https://<הכתובת>/docs           # 404
curl.exe -s -o NUL -w "%{http_code}" -X DELETE https://<הכתובת>/api/v1/records/x  # 403: לא מהדף של האתר
```

ואחר כך, בלוגים של Render: חיפוש לפי ת״ז במסך הרשומות לא משאיר את המספר בלוג.

### נתוני הדגמה

```powershell
# backend/, מול ה־External Database URL מעמוד ה־DB ב־Render
$env:DATABASE_URL = "<External Database URL>?sslmode=require"
.\.venv\Scripts\python.exe -m scripts.seed_demo "<תיקיית קובצי הדוגמה>"   # רק קובצי הדוגמה של האתגר
.\.venv\Scripts\python.exe -m scripts.wipe_data                          # להתחיל מחדש
Remove-Item Env:DATABASE_URL
```

`seed_demo` קורא כל קובץ כמו העלאה באתר ושומר את הרשומות כממתינות. `EXTRACTION_CACHE=true` חוסך מכסה על עמודים ש־Gemini כבר קרא.

---

## עבודה בצוות

| | אחריות |
|---|---|
| **מפתחת A** | קליטת קבצים, עיבוד עמודים, חילוץ AI, `assemble`, `UploadPanel`, `DocumentPreview` |
| **מפתחת B** | נרמול, ולידציה, מדיניות בדיקה (`apply_rules`), `validate`, שורות ו־Excel, `ResultsTable`, ייצוא |
| **משותף** | חוזה ה־API (`schemas/api.py`), טבלת האמת, בדיקות קצה לקצה |

- ענף לכל משימה (`feature/<name>`), מיזוג ל־`main` רק דרך Pull Request
- שינוי בחוזה — רק ב־PR משותף שמעדכן את שני הצדדים
- תוכנית העבודה והחלטות פתוחות: [PLAN.md](PLAN.md)
