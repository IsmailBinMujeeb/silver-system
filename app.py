from __future__ import annotations
import os, re, sqlite3, time
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename
import fitz

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / 'documents'
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'tender_search.db'
ALLOWED_EXTENSIONS = {'.pdf'}
DATA_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024


def connect_db():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=NORMAL')
    con.execute('PRAGMA temp_store=MEMORY')
    return con


def init_db():
    with connect_db() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL UNIQUE,
            filepath TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            modified_at REAL NOT NULL DEFAULT 0,
            page_count INTEGER NOT NULL DEFAULT 0,
            indexed_at REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'indexed',
            error TEXT
        )''')
        con.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(
            document_id UNINDEXED, filename UNINDEXED, page_number UNINDEXED,
            content, tokenize='unicode61 remove_diacritics 2'
        )''')


def index_pdf(path: Path):
    """Extract text page-by-page and replace this PDF's old index atomically."""
    stat = path.stat()
    with fitz.open(path) as pdf:
        page_texts = [(i + 1, page.get_text('text', sort=True).strip()) for i, page in enumerate(pdf)]
        page_count = len(pdf)
    with connect_db() as con:
        old = con.execute('SELECT id, file_size, modified_at FROM documents WHERE filename=?', (path.name,)).fetchone()
        if old and old['file_size'] == stat.st_size and abs(old['modified_at'] - stat.st_mtime) < 0.01:
            return {'filename': path.name, 'status': 'unchanged', 'pages': page_count, 'indexed_pages': None}
        if old:
            doc_id = old['id']
            con.execute('DELETE FROM pages WHERE document_id=?', (doc_id,))
            con.execute('''UPDATE documents SET filepath=?,file_size=?,modified_at=?,page_count=?,indexed_at=?,status='indexed',error=NULL WHERE id=?''',
                        (str(path.relative_to(BASE_DIR)), stat.st_size, stat.st_mtime, page_count, time.time(), doc_id))
        else:
            cur = con.execute('''INSERT INTO documents(filename,filepath,file_size,modified_at,page_count,indexed_at,status)
                                  VALUES(?,?,?,?,?,?, 'indexed')''',
                              (path.name, str(path.relative_to(BASE_DIR)), stat.st_size, stat.st_mtime, page_count, time.time()))
            doc_id = cur.lastrowid
        con.executemany('INSERT INTO pages(document_id,filename,page_number,content) VALUES(?,?,?,?)',
                        [(doc_id, path.name, page_no, text) for page_no, text in page_texts if text])
        con.commit()
    return {'filename': path.name, 'status': 'indexed', 'pages': page_count,
            'indexed_pages': sum(bool(t) for _, t in page_texts),
            'empty_pages': sum(not bool(t) for _, t in page_texts)}


def index_all():
    results = []
    for path in sorted(DOCS_DIR.iterdir()):
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS:
            try:
                results.append(index_pdf(path))
            except Exception as exc:
                with connect_db() as con:
                    con.execute('''INSERT INTO documents(filename,filepath,file_size,modified_at,status,error)
                                   VALUES(?,?,?,?,?,?) ON CONFLICT(filename) DO UPDATE SET status='error',error=excluded.error''',
                                (path.name, str(path.relative_to(BASE_DIR)), path.stat().st_size, path.stat().st_mtime, 'error', str(exc)[:1000]))
                results.append({'filename': path.name, 'status': 'error', 'error': str(exc)})
    return results


def build_match_query(q: str, mode: str):
    # FTS5's quoted phrase syntax safely treats the user's input as text, not operators.
    clean = re.sub(r'\s+', ' ', q).strip()
    if mode == 'all_words':
        tokens = re.findall(r'[\w]+', clean, flags=re.UNICODE)
        if not tokens:
            return ''
        return ' AND '.join('"' + t.replace('"', '""') + '"' for t in tokens)
    return '"' + clean.replace('"', '""') + '"'


@app.get('/')
def home():
    return render_template('index.html')


@app.get('/api/stats')
def stats():
    with connect_db() as con:
        docs = con.execute('SELECT COUNT(*) FROM documents WHERE status="indexed"').fetchone()[0]
        pages = con.execute('SELECT COUNT(*) FROM pages').fetchone()[0]
        errors = con.execute('SELECT COUNT(*) FROM documents WHERE status="error"').fetchone()[0]
        total = con.execute('SELECT COALESCE(SUM(file_size),0) FROM documents').fetchone()[0]
    return jsonify({'documents': docs, 'indexed_pages': pages, 'errors': errors, 'bytes': total})


@app.get('/api/search')
def search():
    q = request.args.get('q', '').strip()
    mode = request.args.get('mode', 'phrase')
    try:
        limit = min(max(int(request.args.get('limit', 100)), 1), 500)
        offset = max(int(request.args.get('offset', 0)), 0)
    except ValueError:
        return jsonify({'error': 'limit and offset must be integers'}), 400
    if not q:
        return jsonify({'query': q, 'total': 0, 'results': [], 'elapsed_ms': 0})
    if len(q) > 300:
        return jsonify({'error': 'Search text must be 300 characters or fewer.'}), 400
    match_query = build_match_query(q, mode)
    if not match_query:
        return jsonify({'query': q, 'total': 0, 'results': [], 'elapsed_ms': 0})
    started = time.perf_counter()
    try:
        with connect_db() as con:
            total = con.execute('SELECT COUNT(*) FROM pages WHERE pages MATCH ?', (match_query,)).fetchone()[0]
            rows = con.execute('''SELECT filename, CAST(page_number AS INTEGER) AS page_number,
                       snippet(pages, 3, '<mark>', '</mark>', ' … ', 22) AS snippet
                       FROM pages WHERE pages MATCH ? ORDER BY filename COLLATE NOCASE, CAST(page_number AS INTEGER)
                       LIMIT ? OFFSET ?''', (match_query, limit, offset)).fetchall()
    except sqlite3.OperationalError as exc:
        # A phrase containing punctuation only can produce no valid FTS expression.
        return jsonify({'error': f'Could not search that input. Try a shorter keyword or phrase. Details: {exc}', 'results': []}), 400
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    return jsonify({'query': q, 'mode': mode, 'total': total, 'limit': limit, 'offset': offset,
                    'elapsed_ms': elapsed, 'results': [dict(r) for r in rows]})


@app.post('/api/reindex')
def reindex():
    results = index_all()
    return jsonify({'results': results, 'stats': stats().get_json()})


@app.post('/api/upload')
def upload():
    files = request.files.getlist('files')
    if not files or not any(f.filename for f in files):
        return jsonify({'error': 'Choose at least one PDF file.'}), 400
    output = []
    for f in files:
        if not f.filename:
            continue
        name = secure_filename(f.filename)
        if not name or Path(name).suffix.lower() != '.pdf':
            output.append({'filename': f.filename, 'status': 'skipped', 'error': 'Only PDF files are supported.'})
            continue
        dest = DOCS_DIR / name
        f.save(dest)
        try:
            output.append(index_pdf(dest))
        except Exception as exc:
            output.append({'filename': name, 'status': 'error', 'error': str(exc)})
    return jsonify({'results': output, 'stats': stats().get_json()})


@app.get('/documents/<path:filename>')
def serve_document(filename):
    # Only serve PDFs from the designated documents directory.
    return send_from_directory(DOCS_DIR, filename, as_attachment=False, mimetype='application/pdf')


init_db()
if __name__ == '__main__':
    # Index documents once on startup; unchanged files are skipped using size + modified time.
    print('Checking/indexing tender PDFs...')
    print(index_all())
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False)
