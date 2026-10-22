import asyncio
import contextlib
import json
import logging
import math
import re
from urllib.parse import quote
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from telethon import TelegramClient, errors, functions, types, utils
from telethon.crypto import aes
from core import ROOT, DATA, MODULES, all_lessons, byte_range, db, lesson_from_message, settings, upsert_lesson, get_course, course_modules, course_catalog, course_materials, upsert_material, is_video_message
from video_cache import cache_path, cached_video, reserve_space

client = None
client_lock = asyncio.Lock()
sync_task = None
sync_status = {'running': False, 'count': 0, 'error': None, 'done': False, 'course_id': None}
course_lock = asyncio.Lock()
cache_task = None
prepare_lock = asyncio.Lock()
cache_job = {'id': None, 'running': False, 'downloaded': 0, 'total': 0, 'error': None}


@asynccontextmanager
async def lifespan(app):
    with db():
        pass
    yield
    if cache_task and not cache_task.done():
        cache_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cache_task
    if sync_task and not sync_task.done():
        sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sync_task
    if client:
        await client.disconnect()


app = FastAPI(title='Trilha · Seus cursos', lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', 'testserver'])


@app.middleware('http')
async def local_guard(request: Request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if request.headers.get('x-trilha-local') != '1':
            return Response('Requisição local inválida', status_code=403)
        origin = request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:8765', 'http://localhost:8765'):
            return Response('Origem inválida', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
    return response


async def telegram():
    global client
    async with client_lock:
        cfg = settings()
        if not cfg.get('api_id') or not (DATA / 'telegram.session').exists():
            raise HTTPException(409, 'Execute conectar.bat para conectar sua conta ao Telegram.')
        if client is None:
            client = TelegramClient(str(DATA / 'telegram'), cfg['api_id'], cfg['api_hash'], flood_sleep_threshold=0)
        try:
            if not client.is_connected():
                await client.connect()
            if not await client.is_user_authorized():
                raise HTTPException(409, 'A sessão expirou. Feche o servidor e execute conectar.bat novamente.')
        except (OSError, ConnectionError):
            raise HTTPException(503, 'Não foi possível conectar ao Telegram. Verifique sua internet.')
        return client


@app.get('/api/status')
def status(course_id: str = 'autodidata'):
    cfg = settings()
    course = require_course(course_id)
    state = sync_status if sync_status['course_id'] == course_id else {'running':False,'count':0,'error':None,'done':False,'course_id':course_id}
    return {'configured': bool(cfg.get('api_id') and (DATA / 'telegram.session').exists()),
            'connected': bool(course['chat_id']), 'course_id': course_id,
            'chat_title': course['name'], 'sync': state}


@app.get('/api/health')
def health():
    return {'app': 'trilha', 'version': '1.4.0', 'ready': True, 'accelerated': aes.cryptg is not None}


def require_course(course_id):
    course = get_course(course_id)
    if not course:
        raise HTTPException(404, 'Curso não encontrado')
    return course


@app.get('/api/courses')
def courses():
    return course_catalog()


@app.get('/api/materials')
def materials(course_id: str = 'autodidata'):
    require_course(course_id)
    return course_materials(course_id)


@app.get('/api/materials/{material_id}/download')
async def material_download(material_id: str):
    with db() as con:
        row = con.execute('SELECT * FROM materials WHERE id=?',(material_id,)).fetchone()
    if not row:
        raise HTTPException(404,'Material não encontrado')
    tg = await telegram()
    try:
        message = await tg.get_messages(row['chat_id'],ids=row['message_id'])
    except errors.RPCError:
        raise HTTPException(502,'Não foi possível acessar este material no Telegram.')
    if not message or not message.file:
        raise HTTPException(404,'O arquivo não está mais disponível no canal.')
    async def stream_material():
        iterator = tg.iter_download(message.media,request_size=524288)
        try:
            async for chunk in iterator:
                yield bytes(chunk)
        finally:
            await iterator.close()
    return StreamingResponse(stream_material(),media_type='application/octet-stream',headers={
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(row['filename'],safe=''),
        'Content-Length':str(message.file.size)})


async def resolve_course(course):
    if course['chat_id']:
        return course
    async with course_lock:
        course = require_course(course['id'])
        if course['chat_id']:
            return course
        if not course['invite']:
            raise HTTPException(409,'Configure o convite deste curso com configurar-cursos.bat antes de sincronizar.')
        tg = await telegram()
        invite_hash = course['invite'].rstrip('/').rsplit('/',1)[-1].removeprefix('+')
        try:
            result = await tg(functions.messages.CheckChatInviteRequest(invite_hash))
            if isinstance(result, types.ChatInviteAlready):
                chat = result.chat
            else:
                joined = await tg(functions.messages.ImportChatInviteRequest(invite_hash))
                chat = joined.chats[0]
            chat_id = utils.get_peer_id(chat)
        except errors.InviteRequestSentError:
            raise HTTPException(409, 'O canal exige aprovação. A solicitação foi enviada; sincronize novamente depois que ela for aprovada.')
        except (errors.InviteHashExpiredError, errors.InviteHashInvalidError):
            raise HTTPException(409, 'O convite do curso está inválido ou expirou. É necessário um convite atualizado.')
        except errors.FloodWaitError as exc:
            raise HTTPException(429, f'O Telegram solicitou uma pausa de {exc.seconds} segundos.')
        except errors.RPCError:
            raise HTTPException(502, 'Não foi possível acessar o canal do curso pela sua conta.')
        with db() as con:
            existing = con.execute('SELECT id FROM courses WHERE chat_id=? AND id<>?',(chat_id,course['id'])).fetchone()
            if existing:
                raise HTTPException(409, 'Esse canal já está associado a outro curso.')
            con.execute('UPDATE courses SET chat_id=? WHERE id=?',(chat_id,course['id']))
        return require_course(course['id'])


def find_lesson(lesson_id):
    with db() as con:
        row = con.execute('SELECT * FROM lessons WHERE id=?', (lesson_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Aula não encontrada')
    return dict(row)


@app.get('/api/cache/{lesson_id}')
def cache_status(lesson_id: str):
    row = find_lesson(lesson_id)
    active = cache_job['id'] == lesson_id
    return {'ready': cached_video(row) is not None,
            'running': active and cache_job['running'],
            'downloaded': cache_job['downloaded'] if active else 0,
            'total': row['size'], 'error': cache_job['error'] if active else None}


async def prepare_video(row, message, tg):
    path = cache_path(row)
    partial = path.with_suffix('.part')
    try:
        def progress(done, total):
            cache_job.update(downloaded=done, total=total)
        await tg.download_media(message, file=str(partial), progress_callback=progress)
        if partial.stat().st_size != row['size']:
            raise ValueError('O arquivo mudou ou ficou incompleto. Sincronize o canal e tente novamente.')
        partial.replace(path)
    except errors.FloodWaitError as exc:
        cache_job['error'] = f'O Telegram pediu uma pausa de {exc.seconds} segundos. Tente preparar novamente depois.'
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logging.warning('Video preparation failed: %s', type(exc).__name__)
        cache_job['error'] = 'Não foi possível preparar a aula. Confira a conexão, o espaço livre e tente novamente.'
    finally:
        cache_job['running'] = False
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)


@app.post('/api/cache/{lesson_id}')
async def prepare(lesson_id: str):
    async with prepare_lock:
        return await begin_prepare(lesson_id)


async def begin_prepare(lesson_id):
    global cache_task
    row = find_lesson(lesson_id)
    if cached_video(row):
        return {'ready': True, 'running': False}
    if cache_task and not cache_task.done():
        if cache_job['id'] == lesson_id:
            return {'ready': False, 'running': True}
        raise HTTPException(409, 'Outra aula está sendo preparada. Aguarde o download terminar.')
    tg = await telegram()
    try:
        message = await tg.get_messages(row['chat_id'], ids=row['message_id'])
    except errors.FloodWaitError as exc:
        raise HTTPException(429, f'O Telegram pediu uma pausa de {exc.seconds} segundos.')
    except (errors.RPCError, OSError):
        raise HTTPException(502, 'Não foi possível abrir esta aula no Telegram. Tente novamente.')
    if not message or not message.file:
        raise HTTPException(404, 'O vídeo foi removido do Telegram.')
    if message.file.size != row['size']:
        raise HTTPException(409, 'O vídeo mudou no Telegram. Sincronize o canal antes de preparar a aula.')
    try:
        reserve_space(row['size'])
    except ValueError as exc:
        raise HTTPException(413, str(exc))
    except OSError as exc:
        raise HTTPException(507, str(exc))
    cache_job.update(id=lesson_id, running=True, downloaded=0, total=row['size'], error=None)
    cache_task = asyncio.create_task(prepare_video(row, message, tg))
    return {'ready': False, 'running': True}


@app.get('/api/lessons')
def lessons(course_id: str = 'autodidata'):
    require_course(course_id)
    return all_lessons(course_id)


@app.get('/api/modules')
def modules(course_id: str = 'autodidata'):
    require_course(course_id)
    return course_modules(course_id)


class Progress(BaseModel):
    position: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    completed: bool | None = None


@app.patch('/api/lessons/{lesson_id}')
def progress(lesson_id: str, body: Progress):
    with db() as con:
        row = con.execute('SELECT * FROM lessons WHERE id=?', (lesson_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Aula não encontrada')
        values, fields = [], []
        if body.position is not None:
            fields.append('position=?')
            values.append(body.position)
        if body.completed is not None:
            fields.append('completed=?')
            values.append(int(body.completed))
        if fields:
            con.execute(f"UPDATE lessons SET {','.join(fields)},updated_at=CURRENT_TIMESTAMP WHERE id=?", values + [lesson_id])
    return {'ok': True}


async def synchronize(course):
    sync_status.update(running=True, count=0, error=None, done=False, course_id=course['id'])
    try:
        tg = await telegram()
        course = await resolve_course(course)
        chat_id = course['chat_id']
        # Import only metadata; video bytes are fetched on playback.
        async for message in tg.iter_messages(chat_id):
            file = message.file
            if not file:
                continue
            if not is_video_message(message):
                if re.search(r'#doc\d+\b',message.raw_text or '',re.I):
                    upsert_material(message,chat_id,course['id'])
                continue
            upsert_lesson(lesson_from_message(message, chat_id, course['id']))
            sync_status['count'] += 1
        sync_status['done'] = True
        with db() as con:
            con.execute('UPDATE courses SET synced_at=CURRENT_TIMESTAMP WHERE id=?',(course['id'],))
    except errors.FloodWaitError as exc:
        sync_status['error'] = f'O Telegram pediu uma pausa. Tente novamente em {exc.seconds} segundos.'
    except HTTPException as exc:
        sync_status['error'] = str(exc.detail)
    except Exception as exc:
        logging.warning('Sync failed: %s', type(exc).__name__)
        sync_status['error'] = 'Não foi possível ler o canal. Confira a conexão e se sua conta ainda tem acesso.'
    finally:
        sync_status['running'] = False


@app.post('/api/sync')
async def sync(course_id: str = 'autodidata'):
    global sync_task
    course = require_course(course_id)
    if sync_task and not sync_task.done():
        if sync_status['course_id'] != course_id:
            raise HTTPException(409, 'Outro curso está sendo sincronizado. Aguarde a importação terminar.')
        return {'ok': True, 'running': True}
    await telegram()
    sync_status.update(running=True, count=0, error=None, done=False, course_id=course_id)
    sync_task = asyncio.create_task(synchronize(course))
    return {'ok': True, 'running': True}


@app.get('/api/export')
def export(course_id: str = 'autodidata'):
    require_course(course_id)
    payload = json.dumps({'version': 2, 'course_id':course_id, 'lessons': all_lessons(course_id)}, ensure_ascii=False, indent=2)
    return Response(payload, media_type='application/json', headers={'Content-Disposition': 'attachment; filename="trilha-progresso.json"'})


@app.api_route('/api/video/{lesson_id}', methods=['GET', 'HEAD'])
async def video(lesson_id: str, request: Request):
    row = find_lesson(lesson_id)
    local = cached_video(row)
    if local:
        local.touch()
        return FileResponse(local, media_type=row['mime'], headers={'X-Trilha-Source': 'local-cache'})
    tg = await telegram()
    try:
        message = await tg.get_messages(row['chat_id'], ids=row['message_id'])
        if not message or not message.file:
            raise HTTPException(404, 'O vídeo foi removido do Telegram.')
    except errors.FloodWaitError as exc:
        raise HTTPException(429, 'O Telegram solicitou uma pausa.', headers={'Retry-After': str(exc.seconds)})
    except errors.RPCError:
        raise HTTPException(502, 'Não foi possível abrir este vídeo no Telegram.')
    size = message.file.size
    try:
        start, end, code = byte_range(request.headers.get('range'), size)
    except ValueError:
        return Response(status_code=416, headers={'Content-Range': f'bytes */{size}'})
    headers = {'Accept-Ranges': 'bytes', 'Content-Length': str(end - start + 1), 'X-Trilha-Source': 'telegram'}
    if code == 206:
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    mime = message.file.mime_type or 'video/mp4'
    if request.method == 'HEAD':
        return Response(status_code=code, headers=headers, media_type=mime)
    chunk = 524288
    aligned = start // chunk * chunk
    iterator = tg.iter_download(message.media, offset=aligned, request_size=chunk,
                                chunk_size=chunk, limit=math.ceil((end - aligned + 1) / chunk))

    async def stream():
        remaining, skip = end - start + 1, start - aligned
        try:
            async for part in iterator:
                data = bytes(part)
                if skip:
                    data, skip = data[skip:], 0
                data = data[:remaining]
                if data:
                    yield data
                    remaining -= len(data)
                if remaining <= 0:
                    break
        finally:
            await iterator.close()
    return StreamingResponse(stream(), status_code=code, headers=headers, media_type=mime)


@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')


app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

if __name__ == '__main__':
    import uvicorn
    import sys
    uvicorn.run('app:app', host='127.0.0.1', port=8765, reload='--reload' in sys.argv)
