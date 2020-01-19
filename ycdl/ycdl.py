import logging
import os
import sqlite3
import traceback

from . import helpers
from . import ytapi

from voussoirkit import sqlhelpers


def YOUTUBE_DL_COMMAND(video_id):
    path = 'D:\\Incoming\\ytqueue\\{id}.ytqueue'.format(id=video_id)
    open(path, 'w')

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)
logging.getLogger('googleapiclient.discovery').setLevel(logging.WARNING)
logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARNING)
logging.getLogger('requests.packages.urllib3.util.retry').setLevel(logging.WARNING)

DATABASE_VERSION = 4
DB_INIT = '''
PRAGMA count_changes = OFF;
PRAGMA cache_size = 10000;
PRAGMA user_version = {user_version};
CREATE TABLE IF NOT EXISTS channels(
    id TEXT,
    name TEXT,
    directory TEXT COLLATE NOCASE,
    automark TEXT
);
CREATE TABLE IF NOT EXISTS videos(
    id TEXT,
    published INT,
    author_id TEXT,
    title TEXT,
    description TEXT,
    duration INT,
    views INT,
    thumbnail TEXT,
    download TEXT
);

CREATE INDEX IF NOT EXISTS index_channel_id on channels(id);
CREATE INDEX IF NOT EXISTS index_video_author on videos(author_id);
CREATE INDEX IF NOT EXISTS index_video_author_download on videos(author_id, download);
CREATE INDEX IF NOT EXISTS index_video_id on videos(id);
CREATE INDEX IF NOT EXISTS index_video_published on videos(published);
CREATE INDEX IF NOT EXISTS index_video_download on videos(download);
'''.format(user_version=DATABASE_VERSION)

SQL_CHANNEL_COLUMNS = [
    'id',
    'name',
    'directory',
    'automark',
]

SQL_VIDEO_COLUMNS = [
    'id',
    'published',
    'author_id',
    'title',
    'description',
    'duration',
    'views',
    'thumbnail',
    'download',
]

SQL_CHANNEL = {key:index for (index, key) in enumerate(SQL_CHANNEL_COLUMNS)}
SQL_VIDEO = {key:index for (index, key) in enumerate(SQL_VIDEO_COLUMNS)}

DEFAULT_DBNAME = 'ycdl.db'

ERROR_DATABASE_OUTOFDATE = 'Database is out-of-date. {current} should be {new}.'


def assert_is_abspath(path):
    '''
    TO DO: Determine whether this is actually correct.
    '''
    if os.path.abspath(path) != path:
        raise ValueError('Not an abspath')


class InvalidVideoState(Exception):
    pass

class NoSuchVideo(Exception):
    pass

class YCDL:
    def __init__(self, youtube, database_filename=None, youtube_dl_function=None):
        self.youtube = youtube
        if database_filename is None:
            database_filename = DEFAULT_DBNAME

        existing_database = os.path.exists(database_filename)
        self.sql = sqlite3.connect(database_filename)
        self.cur = self.sql.cursor()

        if existing_database:
            self.cur.execute('PRAGMA user_version')
            existing_version = self.cur.fetchone()[0]
            if existing_version != DATABASE_VERSION:
                message = ERROR_DATABASE_OUTOFDATE
                message = message.format(current=existing_version, new=DATABASE_VERSION)
                print(message)
                raise SystemExit

        if youtube_dl_function:
            self.youtube_dl_function = youtube_dl_function
        else:
            self.youtube_dl_function = YOUTUBE_DL_COMMAND

        statements = DB_INIT.split(';')
        for statement in statements:
            self.cur.execute(statement)
        self.sql.commit()

    def add_channel(
            self,
            channel_id,
            *,
            commit=True,
            download_directory=None,
            get_videos=False,
            name=None,
        ):
        if self.get_channel(channel_id) is not None:
            return

        if name is None:
            name = self.youtube.get_user_name(channel_id)

        data = [None] * len(SQL_CHANNEL)
        data[SQL_CHANNEL['id']] = channel_id
        data[SQL_CHANNEL['name']] = name
        if download_directory is not None:
            assert_is_abspath(download_directory)
        data[SQL_CHANNEL['directory']] = download_directory

        self.cur.execute('INSERT INTO channels VALUES(?, ?, ?, ?)', data)

        if get_videos:
            self.refresh_channel(channel_id, commit=False)

        if commit:
            self.sql.commit()

        return data

    def channel_has_pending(self, channel_id):
        query = 'SELECT 1 FROM videos WHERE author_id == ? AND download == "pending" LIMIT 1'
        self.cur.execute(query, [channel_id])
        return self.cur.fetchone() is not None

    def download_video(self, video, commit=True, force=False):
        '''
        Execute the `YOUTUBE_DL_COMMAND`, within the channel's associated
        directory if applicable.
        '''
        # This logic is a little hazier than I would like, but it's all in the
        # interest of minimizing unnecessary API calls.
        if isinstance(video, ytapi.Video):
            video_id = video.id
        else:
            video_id = video
        self.cur.execute('SELECT * FROM videos WHERE id == ?', [video_id])
        video_row = self.cur.fetchone()
        if video_row is None:
            # Since the video was not in the db, we may not know about the channel either.
            if not isinstance(video, ytapi.Video):
                print('get video')
                video = self.youtube.get_video(video)
            channel_id = video.author_id
            self.cur.execute('SELECT * FROM channels WHERE id == ?', [channel_id])
            if self.cur.fetchone() is None:
                print('add channel')
                self.add_channel(channel_id, get_videos=False, commit=False)
            video_row = self.insert_video(video, commit=False)['row']
        else:
            channel_id = video_row[SQL_VIDEO['author_id']]

        if video_row[SQL_VIDEO['download']] != 'pending' and not force:
            print('That video does not need to be downloaded.')
            return

        current_directory = os.getcwd()
        download_directory = self.get_channel(channel_id)['directory']
        download_directory = download_directory or current_directory

        os.makedirs(download_directory, exist_ok=True)
        os.chdir(download_directory)

        self.youtube_dl_function(video_id)

        os.chdir(current_directory)

        self.cur.execute('UPDATE videos SET download = "downloaded" WHERE id == ?', [video_id])
        if commit:
            self.sql.commit()

    def get_channel(self, channel_id):
        self.cur.execute('SELECT * FROM channels WHERE id == ?', [channel_id])
        fetch = self.cur.fetchone()
        if not fetch:
            return None
        fetch = {key: fetch[SQL_CHANNEL[key]] for key in SQL_CHANNEL}
        return fetch

    def get_channels(self):
        self.cur.execute('SELECT * FROM channels')
        channels = self.cur.fetchall()
        channels = [{key: channel[SQL_CHANNEL[key]] for key in SQL_CHANNEL} for channel in channels]
        channels.sort(key=lambda x: x['name'].lower())
        return channels

    def get_video(self, video_id):
        self.cur.execute('SELECT * FROM videos WHERE id == ?', [video_id])
        video = self.cur.fetchone()
        video = {key: video[SQL_VIDEO[key]] for key in SQL_VIDEO}
        return video

    def get_videos(self, channel_id=None, download_filter=None):
        wheres = []
        bindings = []
        if channel_id is not None:
            wheres.append('author_id')
            bindings.append(channel_id)

        if download_filter is not None:
            wheres.append('download')
            bindings.append(download_filter)

        if wheres:
            wheres = [x + ' == ?' for x in wheres]
            wheres = ' WHERE ' + ' AND '.join(wheres)
        else:
            wheres = ''

        query = 'SELECT * FROM videos' + wheres
        self.cur.execute(query, bindings)
        videos = self.cur.fetchall()
        if not videos:
            return []

        videos = [{key: video[SQL_VIDEO[key]] for key in SQL_VIDEO} for video in videos]
        videos.sort(key=lambda x: x['published'], reverse=True)
        return videos

    def insert_video(self, video, *, add_channel=True, commit=True):
        if not isinstance(video, ytapi.Video):
            video = self.youtube.get_video(video)

        if add_channel:
            self.add_channel(video.author_id, get_videos=False, commit=False)
        self.cur.execute('SELECT * FROM videos WHERE id == ?', [video.id])

        fetch = self.cur.fetchone()
        existing = fetch is not None

        download_status = 'pending' if not existing else fetch[SQL_VIDEO['download']]

        data = {
            'id': video.id,
            'published': video.published,
            'author_id': video.author_id,
            'title': video.title,
            'description': video.description,
            'duration': video.duration,
            'views': video.views,
            'thumbnail': video.thumbnail['url'],
            'download': download_status,
        }

        if existing:
            (qmarks, bindings) = sqlhelpers.update_filler(data, where_key='id')
            query = f'UPDATE videos {qmarks}'
        else:
            (qmarks, bindings) = sqlhelpers.insert_filler(SQL_VIDEO_COLUMNS, data)
            query = f'INSERT INTO videos VALUES({qmarks})'

        self.cur.execute(query, bindings)

        if commit:
            self.sql.commit()

        return {'new': not existing, 'row': data}

    def mark_video_state(self, video_id, state, commit=True):
        '''
        Mark the video as ignored, pending, or downloaded.
        '''
        if state not in ['ignored', 'pending', 'downloaded']:
            raise InvalidVideoState(state)
        self.cur.execute('SELECT * FROM videos WHERE id == ?', [video_id])
        if self.cur.fetchone() is None:
            raise NoSuchVideo(video_id)
        self.cur.execute('UPDATE videos SET download = ? WHERE id == ?', [state, video_id])
        if commit:
            self.sql.commit()

    def refresh_all_channels(self, force=False, skip_failures=False, commit=True):
        exceptions = []
        for channel in self.get_channels():
            try:
                self.refresh_channel(channel, force=force, commit=commit)
            except Exception as exc:
                if skip_failures:
                    traceback.print_exc()
                    exceptions.append(exc)
                else:
                    raise
        if commit:
            self.sql.commit()
        return exceptions

    def refresh_channel(self, channel, force=False, commit=True):
        if isinstance(channel, str):
            channel = self.get_channel(channel)

        seen_ids = set()
        video_generator = self.youtube.get_user_videos(uid=channel['id'])
        log.debug('Refreshing channel: %s', channel['id'])
        for video in video_generator:
            seen_ids.add(video.id)
            status = self.insert_video(video, commit=False)

            if status['new'] and channel['automark'] is not None:
                self.mark_video_state(video.id, channel['automark'], commit=False)
                if channel['automark'] == 'downloaded':
                    self.download_video(video.id, commit=False)

            if not force and not status['new']:
                break

        if force:
            known_videos = self.get_videos(channel_id=channel['id'])
            known_ids = {v['id'] for v in known_videos}
            refresh_ids = list(known_ids.difference(seen_ids))
            for video in self.youtube.get_video(refresh_ids):
                self.insert_video(video, commit=False)

        if commit:
            self.sql.commit()
