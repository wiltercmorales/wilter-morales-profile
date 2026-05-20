"""
update_pubs.py — Actualiza publicaciones en index.html usando la API de Scopus.

La API key se lee desde la variable de entorno SCOPUS_API_KEY.
NUNCA incluir la key directamente en este archivo.

Configuración en GitHub:
  Settings → Secrets and variables → Actions → New repository secret
  Name: SCOPUS_API_KEY
  Value: <tu API key>
"""
import re, json, os, sys
from urllib.request import urlopen, Request
from urllib.error import URLError
from html import escape
from datetime import date

# ── Configuración ──────────────────────────────────────────────────────────
AUTHOR_ID  = "57218322803"   # Scopus Author ID (público, sin problema)
AF_ID      = "60105305"      # Affiliation ID UPeU (público)
HTML_FILE  = "index.html"

API_KEY = os.environ.get("SCOPUS_API_KEY", "")
if not API_KEY:
    print("ERROR: Variable de entorno SCOPUS_API_KEY no definida.")
    print("  Local: set SCOPUS_API_KEY=tu_key  (Windows) o export SCOPUS_API_KEY=tu_key (Linux/Mac)")
    print("  GitHub Actions: agregar como Repository Secret con nombre SCOPUS_API_KEY")
    sys.exit(1)

# ── Helpers ────────────────────────────────────────────────────────────────

def fetch_scopus(start=0):
    url = "https://api.elsevier.com/content/search/scopus"
    params = (
        f"?query=AU-ID({AUTHOR_ID})"
        f"&count=25&start={start}"
        f"&field=dc:title,prism:publicationName,prism:coverDate,dc:creator,"
        f"author,prism:doi,subtypeDescription"
    )
    req = Request(url + params, headers={
        "X-ELS-APIKey": API_KEY,
        "Accept": "application/json",
    })
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def guess_category(title, journal):
    t = (title + " " + journal).lower()
    if any(k in t for k in ["validat", "psychometric", "invariance", "confirmatory", "adaptation", "afe", "cfa"]):
        return "Validación"
    if any(k in t for k in ["mediat", "structural", "path model", "latent", "sem "]):
        return "SEM y mediación"
    if any(k in t for k in ["predictor", "regression", "logistic", "linear model"]):
        return "Regresiones"
    if any(k in t for k in ["meta-anal", "meta anal", "systematic review", "prisma"]):
        return "Meta-análisis"
    if any(k in t for k in ["network anal", "centrality", "community detect"]):
        return "Análisis de redes"
    if any(k in t for k in ["artificial intel", "machine learn", "ai depend", "chatgpt"]):
        return "IA aplicada"
    if any(k in t for k in ["mental health", "depress", "anxiety", "burnout", "stress"]):
        return "Salud mental"
    if any(k in t for k in ["covid", "pandemic", "nutrition", "obesity", "diet", "public health"]):
        return "Salud pública"
    return "Otros"

# ── Leer HTML actual ───────────────────────────────────────────────────────
with open(HTML_FILE, "r", encoding="utf-8") as f:
    html = f.read()

existing_dois = set(re.findall(r'https://doi\.org/([^\s"]+)', html))
print(f"DOIs existentes en HTML: {len(existing_dois)}")

# ── Obtener todas las publicaciones de Scopus ──────────────────────────────
print(f"Consultando Scopus para autor {AUTHOR_ID}...")
all_items = []
start = 0
while True:
    try:
        data = fetch_scopus(start)
    except URLError as e:
        print(f"Error de red: {e}"); sys.exit(0)

    results = data.get("search-results", {})
    items   = results.get("entry", [])
    total   = int(results.get("opensearch:totalResults", 0))

    if not items:
        break
    all_items.extend(items)
    start += len(items)
    if start >= total:
        break
    print(f"  Obtenidos {start}/{total}...")

print(f"Total Scopus: {len(all_items)}")

# ── Identificar nuevos artículos ───────────────────────────────────────────
new_articles = []
for item in all_items:
    doi = (item.get("prism:doi") or "").strip().lower()
    if not doi or doi in existing_dois:
        continue

    title    = item.get("dc:title", "Sin título")
    date_str = item.get("prism:coverDate", str(date.today().year))
    year     = date_str[:4] if date_str else str(date.today().year)
    journal  = item.get("prism:publicationName", "Journal")
    authors_raw = item.get("author", [])
    authors  = "; ".join(
        f"{a.get('surname','')} {(a.get('given-name') or a.get('initials',''))[:1]}."
        for a in authors_raw[:6]
    ) + ("..." if len(authors_raw) > 6 else "")
    doc_type = item.get("subtypeDescription", "Article")
    category = guess_category(title, journal)

    new_articles.append({
        "doi": doi, "title": title, "year": year,
        "journal": journal, "authors": authors,
        "type": doc_type, "category": category,
    })

if not new_articles:
    print("No hay publicaciones nuevas. index.html está al día.")
    sys.exit(0)

print(f"Publicaciones nuevas encontradas: {len(new_articles)}")

# ── Construir tarjetas HTML ───────────────────────────────────────────────
nums = list(map(int, re.findall(r'<b>#(\d+)</b>', html)))
next_num = max(nums, default=0) + 1

new_cards = []
for i, pub in enumerate(sorted(new_articles, key=lambda x: x["year"], reverse=True)):
    n = next_num + i
    card = (
        f'    <article class="pub" data-category="{pub["category"]}" '
        f'data-year="{pub["year"]}" data-text="{escape((pub["title"]+" "+pub["authors"]+" "+pub["journal"]+" "+pub["doi"]).lower())}">\n'
        f'      <a href="https://doi.org/{escape(pub["doi"])}" target="_blank" rel="noopener">\n'
        f'        <div class="publine"><b>#{n:03d}</b><span>{pub["category"]}</span></div>\n'
        f'        <h3>{escape(pub["title"])}</h3>\n'
        f'        <p>{escape(pub["authors"])}</p>\n'
        f'        <small>{escape(pub["journal"])} · {pub["year"]} · {pub["type"]}</small>\n'
        f'        <small>DOI: {escape(pub["doi"])}</small>\n'
        f'        <strong>Abrir documento →</strong>\n'
        f'      </a>\n'
        f'    </article>'
    )
    new_cards.append(card)

html = html.replace('<div class="publist">\n', '<div class="publist">\n' + "\n".join(new_cards) + "\n", 1)

# ── Actualizar contadores ─────────────────────────────────────────────────
total_new = len(nums) + len(new_articles)
html = re.sub(r'(data-category="Todos">Todos\s*<b>)\d+(</b>)', rf'\g<1>{total_new}\2', html)
html = re.sub(r'(<strong>)\d+(</strong>\s*<small>Documentos en Scopus)', rf'\g<1>{total_new}\2', html)
html = re.sub(r'(<strong>)\d+(</strong>\s*<small>Artículos enlazados)', rf'\g<1>{total_new}\2', html)

with open(HTML_FILE, "w", encoding="utf-8", newline="\n") as f:
    f.write(html)

print(f"Listo. Agregados {len(new_articles)} artículo(s). Total: {total_new}")
