"""
update_pubs.py — Auto-update publications in index.html
Uses CrossRef API (free, no key) via ORCID.
Run locally or via GitHub Actions.
"""
import re, json, sys
from urllib.request import urlopen, Request
from urllib.error import URLError
from html import escape
from datetime import date

ORCID       = "0000-0003-1208-9121"
AUTHOR_NAME = "Morales-García W.C."
HTML_FILE   = "index.html"
MAILTO      = "wiltermorales@upeu.edu.pe"   # polite API usage

# ── helpers ────────────────────────────────────────────────────────────────

def fetch_json(url):
    req = Request(url, headers={"User-Agent": f"ProfileUpdater/1.0 (mailto:{MAILTO})"})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def format_authors(authors):
    parts = []
    for a in authors:
        family = a.get("family", "")
        given  = a.get("given", "")
        if family:
            parts.append(f"{family} {given[:1]}." if given else family)
    return "; ".join(parts[:6]) + ("..." if len(parts) > 6 else "")

def guess_category(title, journal):
    t = (title + " " + journal).lower()
    if any(k in t for k in ["validat", "psychometric", "invariance", "confirmatory", "afe", "cfa", "adaptation"]):
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
    if any(k in t for k in ["mental health", "depress", "anxiety", "burnout", "stress", "wellbeing"]):
        return "Salud mental"
    if any(k in t for k in ["covid", "pandemic", "nutrition", "obesity", "diet", "public health"]):
        return "Salud pública"
    return "Otros"

# ── read current index.html ────────────────────────────────────────────────

with open(HTML_FILE, "r", encoding="utf-8") as f:
    html = f.read()

# Extract existing DOIs
existing_dois = set(re.findall(r'https://doi\.org/([^\s"]+)', html))
print(f"Existing DOIs in HTML: {len(existing_dois)}")

# ── fetch from CrossRef via ORCID ──────────────────────────────────────────

url = (
    f"https://api.crossref.org/works"
    f"?filter=orcid:{ORCID}"
    f"&rows=200&cursor=*"
    f"&select=DOI,title,published,container-title,author,type"
    f"&mailto={MAILTO}"
)
print(f"Fetching CrossRef for ORCID {ORCID}...")
try:
    data = fetch_json(url)
except URLError as e:
    print(f"Network error: {e}"); sys.exit(0)

items = data.get("message", {}).get("items", [])
print(f"CrossRef returned {len(items)} items")

# ── identify new publications ──────────────────────────────────────────────

new_articles = []
for item in items:
    doi = item.get("DOI", "").strip().lower()
    if not doi or doi in existing_dois:
        continue
    title_list = item.get("title", [])
    title = title_list[0] if title_list else "Sin título"
    year_parts = item.get("published", {}).get("date-parts", [[]])
    year = str(year_parts[0][0]) if year_parts and year_parts[0] else str(date.today().year)
    journal_list = item.get("container-title", [])
    journal = journal_list[0] if journal_list else "Journal"
    authors = item.get("author", [])
    authors_str = format_authors(authors)
    doc_type = item.get("type", "journal-article").replace("-", " ").title()
    category = guess_category(title, journal)
    new_articles.append({
        "doi": doi, "title": title, "year": year,
        "journal": journal, "authors": authors_str,
        "type": doc_type, "category": category,
    })

if not new_articles:
    print("No new publications found. index.html is up to date.")
    sys.exit(0)

print(f"Found {len(new_articles)} new publication(s): adding to index.html")

# ── find current highest article number ───────────────────────────────────

nums = list(map(int, re.findall(r'<b>#(\d+)</b>', html)))
next_num = max(nums, default=0) + 1

# ── build new article cards ────────────────────────────────────────────────

new_cards = []
for i, pub in enumerate(sorted(new_articles, key=lambda x: x["year"], reverse=True)):
    n = next_num + i
    doi_escaped = escape(pub["doi"])
    title_escaped = escape(pub["title"])
    authors_escaped = escape(pub["authors"])
    journal_escaped = escape(pub["journal"])
    search_text = f"{pub['title']} {pub['authors']} {pub['journal']} {pub['doi']}".lower()
    card = (
        f'    <article class="pub" data-category="{pub["category"]}" '
        f'data-year="{pub["year"]}" data-text="{escape(search_text)}">\n'
        f'      <a href="https://doi.org/{doi_escaped}" target="_blank" rel="noopener">\n'
        f'        <div class="publine"><b>#{n:03d}</b><span>{pub["category"]}</span></div>\n'
        f'        <h3>{title_escaped}</h3>\n'
        f'        <p>{authors_escaped}</p>\n'
        f'        <small>{journal_escaped} · {pub["year"]} · {pub["type"]}</small>\n'
        f'        <small>DOI: {doi_escaped}</small>\n'
        f'        <strong>Abrir documento →</strong>\n'
        f'      </a>\n'
        f'    </article>'
    )
    new_cards.append(card)

new_block = "\n".join(new_cards) + "\n"

# Insert before the first existing article
html = html.replace('<div class="publist">\n', '<div class="publist">\n' + new_block, 1)

# ── update total count in "Todos" button ──────────────────────────────────

total_new = len(nums) + len(new_articles)
html = re.sub(
    r'(data-category="Todos">Todos\s*<b>)\d+(<\/b>)',
    rf'\g<1>{total_new}\2',
    html
)

# ── update metrics ────────────────────────────────────────────────────────

html = re.sub(
    r'(<strong>)\d+(</strong>\s*<small>Documentos en Scopus)',
    rf'\g<1>{total_new}\2',
    html
)
html = re.sub(
    r'(<strong>)\d+(</strong>\s*<small>Artículos enlazados)',
    rf'\g<1>{total_new}\2',
    html
)

# ── write result ───────────────────────────────────────────────────────────

with open(HTML_FILE, "w", encoding="utf-8", newline="\n") as f:
    f.write(html)

print(f"Done. Added {len(new_articles)} article(s). Total: {total_new}")
