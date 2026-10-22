"""Storage and HTTP byte-range helpers, independent of Telegram."""
import json
import os
import re
import sqlite3
import hashlib
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('TRILHA_DATA_DIR', ROOT / 'data'))
INVITE = os.environ.get('TRILHA_AUTODIDATA_INVITE', '')
WISE_INVITE = os.environ.get('TRILHA_WISE_UP_INVITE', '')
MODULES = [
    ('0.2', 'Comece aqui', 1, 4), ('1', 'Introdução', 5, 6),
    ('2', 'Começando pra valer', 7, 11), ('3', 'Honing in', 12, 19),
    ('4', 'Otimizando', 20, 24), ('5', 'DOMINANDO a leitura', 25, 28),
    ('6', 'DOMINANDO a escuta', 29, 31), ('7', 'DOMINANDO a escrita', 32, 36),
    ('8', 'DOMINANDO a fala', 37, 40), ('9', 'Steadfast', 41, 43),
    ('10', 'Bônus · Milhas + Anti-Procrastinação', 44, 48),
    ('11', 'Lives com membros', 49, 87), ('12', 'Agradecimento', 88, 88),
]
WISE_MODULES = [
    ('Cities · Nova York',1,15), ('Cities · São Francisco',16,30),
    ('Cities · Miami',31,45), ('Cities · Filadélfia',46,60),
    ('Travel · Parques Temáticos',61,84), ('Travel · Dirigindo',85,105),
    ('Travel · Transportes',106,126), ('Travel · Aeroporto',127,153),
    ('Travel · Restaurantes',154,177), ('Travel · Hotel',178,201),
    ('Travel · Viajante',202,225), ('Travel · Esportes e Jogos',226,255),
    ('Travel · Compras',256,282), ('Travel · Pé na Estrada',283,303),
    ('Business · Dados e Tecnologia',304,324), ('Business · Habilidades de Negócio',325,348),
    ('Business · Inovação',349,369), ('Business · Negociação',370,390),
    ('Business · Cultura Corporativa',391,411), ('Business · Gestão de Projetos',412,435),
    ('Business · Gestão de Pessoas',436,456), ('Business · Gestão de Crise',457,477),
    ('Business · Comunicação Empresarial',478,498), ('Business · Indústria do Entretenimento',499,519),
]


VIBE_MODULES = [
    ('Fundamentos · Engenharia de Prompt · Técnicas avançadas', 1, 7),
    ('Ferramentas · Lovable · Fundamentos', 8, 24),
    ('Ferramentas · Codex · FitAI', 25, 26),
    ('Projetos · Antigravity · Conclusão', 27, 27),
    ('Projetos · Lovable · Introdução', 28, 28),
    ('Projetos · Lovable · SaaS MarketLens', 29, 49),
    ('Projetos · Lovable · Blog com pagamento e deploy', 50, 51),
    ('Projetos · Lovable · Corretor de Redações, n8n e Stripe', 52, 71),
    ('Projetos · Lovable · Conclusão', 72, 72),
    ('Bônus · n8n · Fundamentos', 73, 84),
    ('Bônus · n8n · Primeiro workflow', 85, 88),
    ('Bônus · n8n · Planilhas e Slack', 89, 92),
    ('Bônus · n8n · Agente Analisador de Currículo', 93, 98),
    ('Bônus · n8n · Nós de IA', 99, 101),
    ('Bônus · n8n · Economizar com as IAs', 102, 102),
    ('Bônus · n8n · Conclusão', 103, 103),
    ('Bônus · Google AI Studio · Novidades Antigravity', 104, 106),
    ('Bônus · Git e GitHub · Introdução', 107, 116),
    ('Bônus · Git e GitHub · Git fundamental', 117, 134),
    ('Bônus · Git e GitHub · Branches', 135, 147),
    ('Bônus · Git e GitHub · Compartilhamento e atualização', 148, 155),
    ('Bônus · Git e GitHub · Análise e inspeção', 156, 160),
    ('Bônus · Git e GitHub · Administração', 161, 167),
    ('Bônus · Git e GitHub · Melhorando os commits', 168, 170),
    ('Bônus · Git e GitHub · Explorando o GitHub', 171, 183),
    ('Bônus · Git e GitHub · Markdown', 184, 193),
    ('Bônus · Git e GitHub · Portfólio com GitHub Pages', 194, 202),
    ('Bônus · Git e GitHub · Encerramento', 203, 203),
    ('Bônus · Engenharia de Prompt · Introdução', 204, 206),
    ('Bônus · Engenharia de Prompt · Fundamentos', 207, 211),
    ('Bônus · Engenharia de Prompt · Estratégias', 212, 216),
    ('Bônus · Engenharia de Prompt · Técnicas avançadas', 217, 223),
    ('Bônus · Engenharia de Prompt · Conclusão', 224, 224),
]
INDEXED_MODULES = {'wise-up': WISE_MODULES, 'vibe-coding': VIBE_MODULES}


def course_number(tags, max_number=88):
    for tag in tags:
        match = re.fullmatch(r'#f0*(\d+)', tag, re.I)
        if match and int(match.group(1)) >= 1 and (max_number is None or int(match.group(1)) <= max_number):
            return int(match.group(1))
    return None


@contextmanager
def db():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA / 'trilha.db', timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('''CREATE TABLE IF NOT EXISTS lessons (
        id TEXT PRIMARY KEY, message_id INTEGER, chat_id INTEGER,
        title TEXT, caption TEXT, filename TEXT, tags TEXT, file_id TEXT,
        duration REAL, size INTEGER, mime TEXT, sequence INTEGER,
        completed INTEGER DEFAULT 0, position REAL DEFAULT 0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    if 'file_id' not in {row[1] for row in con.execute('PRAGMA table_info(lessons)')}:
        con.execute('ALTER TABLE lessons ADD COLUMN file_id TEXT')
    columns = {row[1] for row in con.execute('PRAGMA table_info(lessons)')}
    if 'course_id' not in columns:
        con.execute("ALTER TABLE lessons ADD COLUMN course_id TEXT NOT NULL DEFAULT 'autodidata'")
    if 'group_name' not in columns:
        con.execute("ALTER TABLE lessons ADD COLUMN group_name TEXT NOT NULL DEFAULT 'Aulas'")
    con.execute('CREATE INDEX IF NOT EXISTS lessons_course ON lessons(course_id, message_id)')
    con.execute('''CREATE TABLE IF NOT EXISTS materials (
        id TEXT PRIMARY KEY, course_id TEXT NOT NULL, chat_id INTEGER, message_id INTEGER,
        title TEXT, filename TEXT, mime TEXT, size INTEGER, tags TEXT)''')
    con.execute('''CREATE TABLE IF NOT EXISTS courses (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, invite TEXT NOT NULL,
        chat_id INTEGER, layout TEXT NOT NULL DEFAULT 'generic',
        description TEXT DEFAULT '', synced_at TEXT)''')
    cfg = settings()
    con.execute('INSERT OR IGNORE INTO courses(id,name,invite,chat_id,layout,description) VALUES(?,?,?,?,?,?)',
                ('autodidata', 'Autodidata Fluente', cfg.get('invite') or INVITE, cfg.get('chat_id'), 'autodidata', 'Aprenda no seu ritmo · 88 aulas no índice'))
    con.execute('INSERT OR IGNORE INTO courses(id,name,invite,layout,description) VALUES(?,?,?,?,?)',
                ('wise-up', 'WISE UP Online · Flávio Augusto', cfg.get('wise_invite') or WISE_INVITE, 'indexed', 'Inglês · 109h 2min e 173,1 GB informados no catálogo'))
    con.execute("UPDATE courses SET layout='indexed' WHERE id='wise-up' AND layout<>'indexed'")
    con.execute('INSERT OR IGNORE INTO courses(id,name,invite,layout,description) VALUES(?,?,?,?,?)',
                ('vibe-coding', 'Formação Vibe Coding – Hora de Codar',
                 cfg.get('vibe_invite') or os.environ.get('TRILHA_VIBE_CODING_INVITE', ''),
                 'indexed', '224 aulas no índice · 18h 47min e 8,2 GB informados no catálogo'))
    if cfg.get('chat_id'):
        con.execute("UPDATE courses SET chat_id=? WHERE id='autodidata' AND chat_id IS NULL", (cfg['chat_id'],))
    try:
        with con:
            yield con
    finally:
        con.close()


def settings():
    path = DATA / 'config.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def save_settings(value):
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'config.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def byte_range(header, size):
    if size <= 0:
        raise ValueError('Arquivo vazio')
    if not header:
        return 0, size - 1, 200
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header.strip())
    if not match or not any(match.groups()):
        raise ValueError('Intervalo inválido')
    left, right = match.groups()
    if not left:
        suffix = int(right)
        if suffix <= 0:
            raise ValueError('Intervalo inválido')
        return max(0, size - suffix), size - 1, 206
    start, end = int(left), min(int(right), size - 1) if right else size - 1
    if start >= size or end < start:
        raise ValueError('Intervalo inválido')
    return start, end, 206


def lesson_from_message(message, chat_id, course_id='autodidata'):
    file = message.file
    caption = message.raw_text or ''
    filename = file.name or f'Aula {message.id}'
    title = next((re.sub(r'#\w+', '', line).strip(' -–•') for line in caption.splitlines()
                  if re.sub(r'#\w+', '', line).strip(' -–•')), filename)
    tags = sorted(set(re.findall(r'#\w+', caption.lower())))
    number = re.search(r'(?:aula|parte|lesson|video|vídeo)\s*[._:#-]?\s*(\d+)', title, re.I)
    if not number:
        number = re.match(r'^(\d+)[\s._-]', filename)
    group_name = infer_group(caption)

    return dict(id=f'{chat_id}_{message.id}', message_id=message.id, chat_id=chat_id,
                course_id=course_id, group_name=group_name,
                title=title[:300], caption=caption, filename=filename,
                file_id=str(getattr(getattr(message, 'document', None), 'id', '') or ''),
                tags=json.dumps(tags, ensure_ascii=False), duration=file.duration or 0,
                size=file.size or 0, mime=file.mime_type or 'video/mp4',
                sequence=int(number.group(1)) if number else None)


def infer_group(caption):
    for line in caption.splitlines():
        clean = re.sub(r'#\w+', '', line).strip(' -–•=')
        if re.match(r'^(?:m[oó]dulo|unidade|n[ií]vel|level|unit|module|section|se[cç][aã]o)\b', clean, re.I):
            return clean[:100]
    lines = [line.strip() for line in caption.splitlines() if line.strip()]
    headings = [line.lstrip('- ').strip() for line in lines[1:] if re.match(r'^-?\s*\d+[.)]\s*\S',line)]
    if headings:
        return ' · '.join(re.sub(r'^\d+[.)]\s*','',line) for line in headings[-2:])[:100]
    return 'Aulas'


def upsert_lesson(item):
    cols = list(item)
    with db() as con:
        con.execute(f"INSERT INTO lessons ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) "
                    f"ON CONFLICT(id) DO UPDATE SET {','.join(f'{c}=excluded.{c}' for c in cols if c != 'id')}",
                    list(item.values()))


def is_video_message(message):
    file = message.file
    return bool(file and ((file.mime_type or '').startswith('video/') or getattr(message,'video',None)
                         or Path(file.name or '').suffix.lower() in {'.mp4','.m4v','.mkv','.mov','.webm','.avi','.wmv','.mpg','.mpeg'}))


def upsert_material(message, chat_id, course_id):
    file = message.file
    with db() as con:
        con.execute('''INSERT INTO materials(id,course_id,chat_id,message_id,title,filename,mime,size,tags)
                       VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                       title=excluded.title,filename=excluded.filename,mime=excluded.mime,size=excluded.size,tags=excluded.tags''',
                    (f'{chat_id}_{message.id}',course_id,chat_id,message.id,(message.raw_text or file.name or 'Material')[:300],
                     file.name or f'material-{message.id}',file.mime_type or 'application/octet-stream',file.size or 0,
                     json.dumps(re.findall(r'#\w+',message.raw_text or ''),ensure_ascii=False)))


def course_materials(course_id):
    with db() as con:
        return [dict(row) for row in con.execute('SELECT * FROM materials WHERE course_id=? ORDER BY message_id',(course_id,))]


def all_lessons(course_id='autodidata'):
    with db() as con:
        result = [dict(row) | {'tags': json.loads(row['tags']), 'completed': bool(row['completed'])}
                  for row in con.execute('SELECT * FROM lessons WHERE course_id=? ORDER BY message_id', (course_id,))]
    for row in result:
        if course_id == 'autodidata':
            row['number'] = course_number(row['tags'])
            row['module'] = next((code for code, name, start, end in MODULES
                                  if row['number'] and start <= row['number'] <= end), 'extras')
        else:
            row['number'] = course_number(row['tags'], None)
            if course_id in INDEXED_MODULES and row['number']:
                row['group_name'] = next((name for name,start,end in INDEXED_MODULES[course_id] if start <= row['number'] <= end),row['group_name'])
            row['module'] = group_code(row['group_name'])
    return sorted(result, key=lambda r: (r['number'] or 9999999, r['message_id']))


def group_code(name):
    return 'g-' + hashlib.sha256(name.encode()).hexdigest()[:12]


def get_course(course_id):
    with db() as con:
        row = con.execute('SELECT * FROM courses WHERE id=?', (course_id,)).fetchone()
    return dict(row) if row else None


def course_modules(course_id):
    if course_id == 'autodidata':
        return [dict(code=code, name=name, start=start, end=end, total=end-start+1) for code, name, start, end in MODULES]
    if course_id in INDEXED_MODULES:
        return [dict(code=group_code(name),name=name,start=start,end=end,total=end-start+1) for name,start,end in INDEXED_MODULES[course_id]]
    with db() as con:
        rows = con.execute('SELECT group_name,COUNT(*) AS total FROM lessons WHERE course_id=? GROUP BY group_name ORDER BY MIN(message_id)', (course_id,)).fetchall()
    return [dict(code=group_code(row['group_name']), name=row['group_name'], total=row['total']) for row in rows]


def course_catalog():
    with db() as con:
        courses = [dict(row) for row in con.execute('SELECT * FROM courses ORDER BY rowid')]
    for course in courses:
        items = all_lessons(course['id'])
        course['lesson_count'] = len(items)
        course['total'] = 88 if course['layout'] == 'autodidata' else max(end for _, _, end in INDEXED_MODULES[course['id']]) if course['id'] in INDEXED_MODULES else len(items)
        course['completed'] = (sum(all(l['completed'] for l in items if l['number'] == n)
                                   for n in {l['number'] for l in items if l['number']})
                               if course['layout'] in ('autodidata','indexed') else sum(l['completed'] for l in items))
        course['missing_numbers'] = ([n for n in range(1,course['total']+1) if n not in {l['number'] for l in items}]
                                     if course['layout'] in ('autodidata','indexed') and course['synced_at'] else [])
        course['material_count'] = len(course_materials(course['id']))
        course['duration'] = sum(l['duration'] or 0 for l in items)
        course['size'] = sum(l['size'] or 0 for l in items)
        course['connected'] = bool(course['chat_id'])
        course.pop('invite', None)
    return courses
