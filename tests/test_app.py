import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

temporary = tempfile.TemporaryDirectory()
os.environ['TRILHA_DATA_DIR'] = temporary.name
from fastapi.testclient import TestClient
import core
import app
import video_cache


def sample(message_id=1, caption='#F01 Aula 1 - Comece aqui'):
    return SimpleNamespace(id=message_id, raw_text=caption, file=SimpleNamespace(
        name='intro.mp4', duration=120, size=1100000, mime_type='video/mp4'))


class FakeIterator:
    def __init__(self, data, chunk):
        self.data, self.chunk, self.index, self.closed = data, chunk, 0, False
    def __aiter__(self):
        return self
    async def __anext__(self):
        if self.index >= len(self.data):
            raise StopAsyncIteration
        result = self.data[self.index:self.index + self.chunk]
        self.index += self.chunk
        return result
    async def close(self):
        self.closed = True


class AppTests(unittest.TestCase):
    def setUp(self):
        for path in video_cache.CACHE_ROOT.glob('*'):
            if path.is_file():
                path.unlink()
        with core.db() as con:
            con.execute('DELETE FROM lessons')
            con.execute('DELETE FROM materials')
        core.upsert_lesson(core.lesson_from_message(sample(), -100123))
        self.headers = {'X-Trilha-Local': '1'}

    def test_ranges(self):
        for value, expected in [(None,(0,999,200)),('bytes=10-20',(10,20,206)),
                                ('bytes=990-',(990,999,206)),('bytes=-10',(990,999,206)),
                                ('bytes=0-9999',(0,999,206)),('bytes=-9999',(0,999,206))]:
            self.assertEqual(core.byte_range(value,1000),expected)
        for value in ['bytes=1000-','bytes=9-2','bytes=-0','bytes=-','bytes=0-2,5-6','garbage']:
            with self.assertRaises(ValueError): core.byte_range(value,1000)

    def test_hashtag_sort_and_modules(self):
        core.upsert_lesson(core.lesson_from_message(sample(2,'#F61 Live'), -100123))
        core.upsert_lesson(core.lesson_from_message(sample(3,'#f05 Introdução'), -100123))
        core.upsert_lesson(core.lesson_from_message(sample(4,'#F04 Mais um'), -100123))
        self.assertEqual([l['number'] for l in core.all_lessons()],[1,4,5,61])
        self.assertEqual([l['module'] for l in core.all_lessons()],['0.2','0.2','1','11'])
        self.assertIsNone(core.course_number(['#F142']))
        self.assertEqual(core.course_number(['#f1']),1)

    def test_progress_preserved_on_sync(self):
        with TestClient(app.app) as client:
            response = client.patch('/api/lessons/-100123_1',json={'position':43.2,'completed':True},headers=self.headers)
            self.assertEqual(response.status_code,200)
            core.upsert_lesson(core.lesson_from_message(sample(),-100123))
            lesson = client.get('/api/lessons').json()[0]
            self.assertTrue(lesson['completed'])
            self.assertEqual(lesson['position'],43.2)
            self.assertEqual(client.patch('/api/lessons/-100123_1',json={'position':-1},headers=self.headers).status_code,422)

    def test_local_access_and_empty_state(self):
        with TestClient(app.app) as client:
            self.assertEqual(client.get('/').status_code,200)
            self.assertEqual(client.get('/api/health').json()['version'],'1.4.0')
            self.assertEqual(len(client.get('/api/modules').json()),13)
            self.assertFalse(client.get('/api/status').json()['configured'])
            self.assertEqual(client.post('/api/sync').status_code,403)
            self.assertEqual(client.post('/api/sync',headers=self.headers).status_code,409)
            self.assertEqual(client.patch('/api/lessons/-100123_1',json={'completed':True},headers=self.headers|{'Origin':'https://evil.example'}).status_code,403)
            self.assertEqual(client.get('/',headers={'host':'evil.example'}).status_code,400)

    def test_telegram_stream_byte_accuracy(self):
        payload = bytes(range(256)) * 5000
        fake = SimpleNamespace()
        fake.get_messages = AsyncMock(return_value=SimpleNamespace(file=SimpleNamespace(size=len(payload),mime_type='video/mp4'),media='file'))
        streams = []
        def download(media, offset, request_size, chunk_size, limit):
            iterator = FakeIterator(payload[offset:offset + limit * chunk_size], chunk_size)
            streams.append(iterator)
            return iterator
        fake.iter_download = download
        with patch.object(app,'telegram',AsyncMock(return_value=fake)), TestClient(app.app) as client:
            for start,end in [(0,100),(524280,524310),(700001,1100001)]:
                response = client.get('/api/video/-100123_1',headers={'Range':f'bytes={start}-{end}'})
                self.assertEqual(response.status_code,206)
                self.assertEqual(response.content,payload[start:end+1])
                self.assertEqual(response.headers['Content-Range'],f'bytes {start}-{end}/{len(payload)}')
                self.assertTrue(streams[-1].closed)
            response = client.get('/api/video/-100123_1',headers={'Range':'bytes=-100'})
            self.assertEqual(response.content,payload[-100:])
            response = client.get('/api/video/-100123_1')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.content,payload)
            self.assertEqual(client.head('/api/video/-100123_1').headers['content-length'],str(len(payload)))
            self.assertEqual(client.get('/api/video/-100123_1',headers={'Range':'bytes=9999999-'}).status_code,416)

    def test_prepared_file_plays_without_telegram_and_supports_seek(self):
        row = core.all_lessons()[0]
        payload = bytes(range(256)) * 4296 + bytes(range(224))
        self.assertEqual(len(payload),row['size'])
        video_cache.CACHE_ROOT.mkdir(parents=True,exist_ok=True)
        path = video_cache.cache_path(row)
        path.write_bytes(payload)
        with patch.object(app,'telegram',AsyncMock(side_effect=AssertionError('Telegram should not be called'))), TestClient(app.app) as client:
            self.assertTrue(client.get('/api/cache/-100123_1').json()['ready'])
            response = client.get('/api/video/-100123_1',headers={'Range':'bytes=700000-700099'})
            self.assertEqual(response.status_code,206)
            self.assertEqual(response.content,payload[700000:700100])
            self.assertEqual(response.headers['x-trilha-source'],'local-cache')
            self.assertEqual(client.head('/api/video/-100123_1').headers['content-length'],str(len(payload)))

    def test_partial_file_is_not_served_and_cache_obeys_budget(self):
        row = core.all_lessons()[0]
        video_cache.CACHE_ROOT.mkdir(parents=True,exist_ok=True)
        path = video_cache.cache_path(row)
        path.write_bytes(b'incomplete')
        self.assertIsNone(video_cache.cached_video(row))
        with patch.object(video_cache,'MAX_BYTES',1000):
            video_cache.reserve_space(999)
            self.assertFalse(path.exists())
            with self.assertRaises(ValueError):
                video_cache.reserve_space(1001)

    def test_prepare_publishes_only_complete_download(self):
        import asyncio
        row = core.all_lessons()[0]
        video_cache.reserve_space(row['size'])
        async def download(message, file, progress_callback):
            from pathlib import Path
            Path(file).write_bytes(b'v' * row['size'])
            progress_callback(row['size'],row['size'])
        fake = SimpleNamespace(download_media=download)
        asyncio.run(app.prepare_video(row,object(),fake))
        self.assertIsNotNone(video_cache.cached_video(row))
        self.assertFalse(video_cache.cache_path(row).with_suffix('.part').exists())
        video_cache.cache_path(row).unlink()
        async def incomplete(message, file, progress_callback):
            from pathlib import Path
            Path(file).write_bytes(b'incomplete')
        asyncio.run(app.prepare_video(row,object(),SimpleNamespace(download_media=incomplete)))
        self.assertIsNone(video_cache.cached_video(row))
        self.assertIsNotNone(app.cache_job['error'])
        self.assertFalse(video_cache.cache_path(row).with_suffix('.part').exists())

    def test_courses_keep_catalog_progress_and_modules_separate(self):
        wise = core.lesson_from_message(sample(1,'#F01 First lesson\nModule 1 - Basics'), -100999, 'wise-up')
        core.upsert_lesson(wise)
        with TestClient(app.app) as client:
            original = client.get('/api/lessons?course_id=autodidata').json()
            added = client.get('/api/lessons?course_id=wise-up').json()
            self.assertEqual(len(original),1)
            self.assertEqual(len(added),1)
            self.assertNotEqual(original[0]['id'],added[0]['id'])
            self.assertEqual(original[0]['module'],'0.2')
            self.assertEqual(added[0]['number'],1)
            self.assertNotEqual(added[0]['module'],'0.2')
            self.assertEqual(client.get('/api/modules?course_id=wise-up').json()[0]['name'],'Cities · Nova York')
            client.patch('/api/lessons/-100999_1',json={'completed':True,'position':51},headers=self.headers)
            catalog = {c['id']:c for c in client.get('/api/courses').json()}
            self.assertEqual(catalog['wise-up']['completed'],1)
            self.assertEqual(catalog['autodidata']['completed'],0)
            self.assertEqual(catalog['autodidata']['total'],88)
            self.assertEqual(catalog['wise-up']['total'],519)
            self.assertFalse(client.get('/api/lessons?course_id=autodidata').json()[0]['completed'])
            self.assertEqual(client.get('/api/lessons?course_id=missing').status_code,404)

    def test_wise_up_headings_and_hashtags_over_88(self):
        item = core.lesson_from_message(sample(500,'#F202 1.Começando o Dia - Documentário\n\n-2.Travel\n7.Viajante'), -100999,'wise-up')
        core.upsert_lesson(item)
        self.assertEqual(core.all_lessons('wise-up')[0]['number'],202)
        self.assertEqual(item['group_name'],'Travel · Viajante')

    def test_wise_index_covers_519_codes_and_document_is_separate(self):
        modules = core.course_modules('wise-up')
        expected = [n for m in modules for n in range(m['start'],m['end']+1)]
        self.assertEqual(expected,list(range(1,520)))
        self.assertEqual(len(modules),24)
        document = sample(9,'#Doc001 Material de apoio')
        document.file.name = 'apoio.pdf'
        document.file.mime_type = 'application/pdf'
        core.upsert_material(document,-100999,'wise-up')
        self.assertFalse(core.is_video_message(document))
        document.file.name = 'video.mkv'
        document.file.mime_type = 'application/octet-stream'
        self.assertTrue(core.is_video_message(document))
        with TestClient(app.app) as client:
            self.assertEqual(len(client.get('/api/materials?course_id=wise-up').json()),1)
            self.assertEqual(client.get('/api/materials?course_id=autodidata').json(),[])
            self.assertEqual(client.get('/api/lessons?course_id=wise-up').json(),[])

    def test_support_material_download_streams_correct_file(self):
        material = sample(9,'#Doc001 Apoio')
        material.file.name = 'apostila.pdf'
        core.upsert_material(material,-100999,'wise-up')
        payload = b'PDF-test-content'
        fake = SimpleNamespace(get_messages=AsyncMock(return_value=SimpleNamespace(file=SimpleNamespace(size=len(payload)),media='document')),
                               iter_download=lambda media,request_size:FakeIterator(payload,524288))
        with patch.object(app,'telegram',AsyncMock(return_value=fake)), TestClient(app.app) as client:
            response = client.get('/api/materials/-100999_9/download')
            self.assertEqual(response.content,payload)
            self.assertIn('attachment;',response.headers['content-disposition'])
            self.assertIn('apostila.pdf',response.headers['content-disposition'])

    def test_vibe_index_and_progress_are_isolated(self):
        modules = core.course_modules('vibe-coding')
        numbers = [n for m in modules for n in range(m['start'], m['end'] + 1)]
        self.assertEqual(numbers, list(range(1, 225)))
        self.assertEqual(len(modules), 33)
        for number in (1, 24, 25, 107, 224):
            core.upsert_lesson(core.lesson_from_message(sample(number, f'#F{number:03} Aula'), -100777, 'vibe-coding'))
        with TestClient(app.app) as client:
            items = client.get('/api/lessons?course_id=vibe-coding').json()
            self.assertEqual([l['number'] for l in items], [1, 24, 25, 107, 224])
            self.assertIn('FitAI', items[2]['group_name'])
            client.patch('/api/lessons/' + items[0]['id'], json={'completed': True}, headers=self.headers)
            catalog = {c['id']: c for c in client.get('/api/courses').json()}
            self.assertEqual(catalog['vibe-coding']['total'], 224)
            self.assertEqual(catalog['vibe-coding']['completed'], 1)
            self.assertEqual(catalog['autodidata']['completed'], 0)
            self.assertNotIn('invite', catalog['vibe-coding'])

    def test_legacy_database_migration_preserves_position_and_completion(self):
        import sqlite3
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            con = sqlite3.connect(Path(directory)/'trilha.db')
            con.execute('''CREATE TABLE lessons(id TEXT PRIMARY KEY,message_id INTEGER,chat_id INTEGER,
                           title TEXT,caption TEXT,filename TEXT,tags TEXT,duration REAL,size INTEGER,
                           mime TEXT,sequence INTEGER,completed INTEGER DEFAULT 0,position REAL DEFAULT 0,
                           updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
            con.execute("INSERT INTO lessons(id,message_id,title,tags,completed,position) VALUES('old',1,'Minha aula','[]',1,42.5)")
            con.commit(); con.close()
            with patch.object(core,'DATA',Path(directory)):
                old = core.all_lessons()[0]
                self.assertEqual(old['course_id'],'autodidata')
                self.assertTrue(old['completed'])
                self.assertEqual(old['position'],42.5)
                self.assertEqual(len(core.course_catalog()),3)
if __name__ == '__main__':
    unittest.main()
