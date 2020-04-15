import json
import logging
import os
import sqlite3
import traceback

from . import constants
from . import exceptions
from . import objects
from . import ytapi

from voussoirkit import cacheclass
from voussoirkit import configlayers
from voussoirkit import pathclass
from voussoirkit import sqlhelpers


def YOUTUBE_DL_COMMAND(video_id):
    path = f'{video_id}.ytqueue'
    open(path, 'w')

logging.basicConfig()
logging.getLogger('googleapiclient.discovery').setLevel(logging.WARNING)
logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARNING)
logging.getLogger('requests.packages.urllib3.util.retry').setLevel(logging.WARNING)


class YCDLDBCacheManagerMixin:
    _THING_CLASSES = {
        'channel':
        {
            'class': objects.Channel,
            'exception': exceptions.NoSuchChannel,
        },
        'video':
        {
            'class': objects.Video,
            'exception': exceptions.NoSuchVideo,
        },
    }

    def __init__(self):
        super().__init__()

    def get_cached_instance(self, thing_type, db_row):
        '''
        Check if there is already an instance in the cache and return that.
        Otherwise, a new instance is created, cached, and returned.

        Note that in order to call this method you have to already have a
        db_row which means performing some select. If you only have the ID,
        use get_thing_by_id, as there may already be a cached instance to save
        you the select.
        '''
        thing_map = self._THING_CLASSES[thing_type]

        thing_class = thing_map['class']
        thing_table = thing_class.table
        thing_cache = self.caches[thing_type]

        if isinstance(db_row, dict):
            thing_id = db_row['id']
        else:
            thing_index = constants.SQL_INDEX[thing_table]
            thing_id = db_row[thing_index['id']]

        try:
            thing = thing_cache[thing_id]
        except KeyError:
            thing = thing_class(self, db_row)
            thing_cache[thing_id] = thing
        return thing

    def get_thing_by_id(self, thing_type, thing_id):
        '''
        This method will first check the cache to see if there is already an
        instance with that ID, in which case we don't need to perform any SQL
        select. If it is not in the cache, then a new instance is created,
        cached, and returned.
        '''
        thing_map = self._THING_CLASSES[thing_type]

        thing_class = thing_map['class']
        if isinstance(thing_id, thing_class):
            # This could be used to check if your old reference to an object is
            # still in the cache, or re-select it from the db to make sure it
            # still exists and re-cache.
            # Probably an uncommon need but... no harm I think.
            thing_id = thing_id.id

        thing_cache = self.caches[thing_type]
        try:
            return thing_cache[thing_id]
        except KeyError:
            pass

        query = f'SELECT * FROM {thing_class.table} WHERE id == ?'
        bindings = [thing_id]
        thing_row = self.sql_select_one(query, bindings)
        if thing_row is None:
            raise thing_map['exception'](thing_id)
        thing = thing_class(self, thing_row)
        thing_cache[thing_id] = thing
        return thing

class YCDLDBChannelMixin:
    def __init__(self):
        super().__init__()

    def add_channel(
            self,
            channel_id,
            *,
            commit=True,
            download_directory=None,
            get_videos=False,
            name=None,
        ):
        try:
            return self.get_channel(channel_id)
        except exceptions.NoSuchChannel:
            pass

        if name is None:
            name = self.youtube.get_user_name(channel_id)

        if download_directory is not None:
            download_directory = pathclass.Path(download_directory).absolute_path

        data = {
            'id': channel_id,
            'name': name,
            'directory': download_directory,
            'automark': None,
        }
        self.sql_insert(table='channels', data=data)

        channel = self.get_cached_instance('channel', data)

        if get_videos:
            channel.refresh(commit=False)

        if commit:
            self.commit()
        return channel

    def get_channel(self, channel_id):
        return self.get_thing_by_id('channel', channel_id)

    def get_channels(self):
        query = 'SELECT * FROM channels'
        rows = self.sql_select(query)
        channels = [self.get_cached_instance('channel', row) for row in rows]
        channels.sort(key=lambda c: c.name)
        return channels

    def refresh_all_channels(self, force=False, skip_failures=False, commit=True):
        exceptions = []
        for channel in self.get_channels():
            try:
                channel.refresh(force=force, commit=commit)
            except Exception as exc:
                if skip_failures:
                    traceback.print_exc()
                    exceptions.append(exc)
                else:
                    raise
        if commit:
            self.commit()
        return exceptions

class YCDLSQLMixin:
    def __init__(self):
        super().__init__()
        self._cached_sql_tables = None

    def assert_table_exists(self, table):
        if not self._cached_sql_tables:
            self._cached_sql_tables = self.get_sql_tables()
        if table not in self._cached_sql_tables:
            raise exceptions.BadTable(table)

    def commit(self, message=None):
        if message is not None:
            self.log.debug('Committing - %s.', message)

        self.sql.commit()

    def get_sql_tables(self):
        query = 'SELECT name FROM sqlite_master WHERE type = "table"'
        cur = self.sql_execute(query)
        tables = set(row[0] for row in cur.fetchall())
        return tables

    def rollback(self):
        self.log.debug('Rolling back.')
        self.sql_execute('ROLLBACK')

    def sql_delete(self, table, pairs):
        self.assert_table_exists(table)
        (qmarks, bindings) = sqlhelpers.delete_filler(pairs)
        query = f'DELETE FROM {table} {qmarks}'
        self.sql_execute(query, bindings)

    def sql_execute(self, query, bindings=[]):
        if bindings is None:
            bindings = []
        cur = self.sql.cursor()
        #self.log.log(1, f'{query} {bindings}')
        cur.execute(query, bindings)
        return cur

    def sql_insert(self, table, data):
        self.assert_table_exists(table)
        column_names = constants.SQL_COLUMNS[table]
        (qmarks, bindings) = sqlhelpers.insert_filler(column_names, data)

        query = f'INSERT INTO {table} VALUES({qmarks})'
        self.sql_execute(query, bindings)

    def sql_select(self, query, bindings=None):
        cur = self.sql_execute(query, bindings)
        while True:
            fetch = cur.fetchone()
            if fetch is None:
                break
            yield fetch

    def sql_select_one(self, query, bindings=None):
        cur = self.sql_execute(query, bindings)
        return cur.fetchone()

    def sql_update(self, table, pairs, where_key):
        self.assert_table_exists(table)
        (qmarks, bindings) = sqlhelpers.update_filler(pairs, where_key=where_key)
        query = f'UPDATE {table} {qmarks}'
        self.sql_execute(query, bindings)

class YCDLDBVideoMixin:
    def __init__(self):
        super().__init__()

    def download_video(self, video, commit=True, force=False):
        '''
        Execute the `YOUTUBE_DL_COMMAND`, within the channel's associated
        directory if applicable.
        '''
        if isinstance(video, ytapi.Video):
            video_id = video.id
        else:
            video_id = video

        video = self.get_video(video_id)
        if video.download != 'pending' and not force:
            print('That video does not need to be downloaded.')
            return

        try:
            channel = self.get_channel(video.author_id)
            download_directory = channel.directory
            download_directory = download_directory or self.config['download_directory']
        except exceptions.NoSuchChannel:
            download_directory = self.config['download_directory']

        os.makedirs(download_directory, exist_ok=True)

        current_directory = os.getcwd()
        os.chdir(download_directory)
        self.youtube_dl_function(video_id)
        os.chdir(current_directory)

        video.mark_state('downloaded', commit=False)

        if commit:
            self.commit()

    def get_video(self, video_id):
        return self.get_thing_by_id('video', video_id)

    def get_videos(self, channel_id=None, *, download_filter=None, orderby=None):
        wheres = []
        orderbys = []

        bindings = []
        if channel_id is not None:
            wheres.append('author_id')
            bindings.append(channel_id)

        if download_filter is not None:
            wheres.append('download')
            bindings.append(download_filter)

        if wheres:
            wheres = [x + ' == ?' for x in wheres]
            wheres = ' AND '.join(wheres)
            wheres = ' WHERE ' + wheres
        else:
            wheres = ''

        if orderby is not None:
            orderby = orderby.lower()
            if orderby == 'random':
                orderby = 'random()'
            if orderby in ['views', 'duration', 'random()']:
                orderbys.append(f'{orderby} DESC')
        orderbys.append('published DESC')

        if orderbys:
            orderbys = ', '.join(orderbys)
            orderbys = ' ORDER BY ' + orderbys

        query = 'SELECT * FROM videos' + wheres + orderbys
        rows = self.sql_select(query, bindings)
        videos = [self.get_cached_instance('video', row) for row in rows]
        return videos

    def insert_playlist(self, playlist_id, commit=True):
        video_generator = self.youtube.get_playlist_videos(playlist_id)
        results = [self.insert_video(video, commit=False) for video in video_generator]

        if commit:
            self.commit()

        return results

    def insert_video(self, video, *, add_channel=True, commit=True):
        if not isinstance(video, ytapi.Video):
            video = self.youtube.get_video(video)

        if add_channel:
            self.add_channel(video.author_id, get_videos=False, commit=False)

        try:
            existing = self.get_video(video.id)
            download_status = existing.download
        except exceptions.NoSuchVideo:
            existing = None
            download_status = 'pending'

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
            self.sql_update(table='videos', pairs=data, where_key='id')
        else:
            self.sql_insert(table='videos', data=data)

        video = self.get_cached_instance('video', data)

        if commit:
            self.commit()

        return {'new': not existing, 'video': video}

class YCDLDB(
        YCDLDBCacheManagerMixin,
        YCDLDBChannelMixin,
        YCDLDBVideoMixin,
        YCDLSQLMixin,
    ):
    def __init__(
            self,
            youtube,
            data_directory=None,
            youtube_dl_function=None,
            skip_version_check=False,
        ):
        super().__init__()
        self.youtube = youtube

        # DATA DIR PREP
        if data_directory is None:
            data_directory = constants.DEFAULT_DATADIR

        self.data_directory = pathclass.Path(data_directory)

        # LOGGING
        self.log = logging.getLogger(__name__)
        self.log.setLevel(logging.DEBUG)

        # DATABASE
        self.database_filepath = self.data_directory.with_child(constants.DEFAULT_DBNAME)
        existing_database = self.database_filepath.exists
        self.sql = sqlite3.connect(self.database_filepath.absolute_path)

        if existing_database:
            if not skip_version_check:
                self._check_version()
            self._load_pragmas()
        else:
            self._first_time_setup()

        # DOWNLOAD COMMAND
        if youtube_dl_function:
            self.youtube_dl_function = youtube_dl_function
        else:
            self.youtube_dl_function = YOUTUBE_DL_COMMAND

        # CONFIG
        self.config_filepath = self.data_directory.with_child(constants.DEFAULT_CONFIGNAME)
        self.load_config()

        self.caches = {
            'channel': cacheclass.Cache(maxlen=20_000),
            'video': cacheclass.Cache(maxlen=50_000),
        }

    def _check_version(self):
        '''
        Compare database's user_version against constants.DATABASE_VERSION,
        raising exceptions.DatabaseOutOfDate if not correct.
        '''
        existing = self.sql.execute('PRAGMA user_version').fetchone()[0]
        if existing != constants.DATABASE_VERSION:
            raise exceptions.DatabaseOutOfDate(
                existing=existing,
                new=constants.DATABASE_VERSION,
                filepath=self.database_filepath,
            )

    def _first_time_setup(self):
        self.log.debug('Running first-time database setup.')
        self.sql.executescript(constants.DB_INIT)
        self.commit()

    def _load_pragmas(self):
        self.log.debug('Reloading pragmas.')
        self.sql.executescript(constants.DB_PRAGMAS)
        self.commit()

    def get_all_states(self):
        '''
        Get a list of all the different `download` states that are currently in
        use in the database.
        '''
        # Note: This function was added while I was considering the addition of
        # arbitrarily many states for user-defined purposes, but I kind of went
        # back on that so I'm not sure if it will be useful.
        query = 'SELECT DISTINCT download FROM videos'
        states = self.sql_select(query)
        states = [row[0] for row in states]
        return sorted(states)

    def load_config(self):
        (config, needs_rewrite) = configlayers.load_file(
            filepath=self.config_filepath,
            defaults=constants.DEFAULT_CONFIGURATION,
        )
        self.config = config

        if needs_rewrite:
            self.save_config()

    def save_config(self):
        with open(self.config_filepath.absolute_path, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps(self.config, indent=4, sort_keys=True))
