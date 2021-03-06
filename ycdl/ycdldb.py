import json
import os
import sqlite3
import traceback

from . import constants
from . import exceptions
from . import objects
from . import ytapi
from . import ytrss

from voussoirkit import cacheclass
from voussoirkit import configlayers
from voussoirkit import pathclass
from voussoirkit import sqlhelpers
from voussoirkit import vlogging

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

    def get_things(self, thing_type):
        '''
        Yield things, unfiltered, in whatever order they appear in the database.
        '''
        thing_map = self._THING_CLASSES[thing_type]
        table = thing_map['class'].table
        query = f'SELECT * FROM {table}'

        things = self.sql_select(query)
        for thing_row in things:
            thing = self.get_cached_instance(thing_type, thing_row)
            yield thing

    def get_things_by_sql(self, thing_type, query, bindings=None):
        '''
        Use an arbitrary SQL query to select things from the database.
        Your query select *, all the columns of the thing's table.
        '''
        thing_rows = self.sql_select(query, bindings)
        for thing_row in thing_rows:
            yield self.get_cached_instance(thing_type, thing_row)

class YCDLDBChannelMixin:
    def __init__(self):
        super().__init__()

    def add_channel(
            self,
            channel_id,
            *,
            commit=True,
            download_directory=None,
            queuefile_extension=None,
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

        self.log.info('Adding channel %s %s', channel_id, name)

        data = {
            'id': channel_id,
            'name': name,
            'uploads_playlist': self.youtube.get_user_uploads_playlist_id(channel_id),
            'download_directory': download_directory,
            'queuefile_extension': queuefile_extension,
            'automark': "pending",
        }
        self.sql_insert(table='channels', data=data)

        channel = objects.Channel(self, data)
        self.caches['channel'][channel_id] = channel

        if get_videos:
            channel.refresh(commit=False)

        if commit:
            self.commit()
        return channel

    def get_channel(self, channel_id):
        return self.get_thing_by_id('channel', channel_id)

    def get_channels(self):
        return self.get_things(thing_type='channel')

    def get_channels_by_sql(self, query, bindings=None):
        return self.get_things_by_sql('channel', query, bindings)

    def _rss_assisted_refresh(self, skip_failures=False, commit=True):
        '''
        Youtube provides RSS feeds for every channel. These feeds do not
        require the API token and seem to have generous ratelimits, or
        perhaps no ratelimits at all.

        This RSS-assisted refresh will cut down on tokened API calls by:
        1. Getting video IDs from the free RSS feed instead of the tokened
           playlistItems endpoint.
        2. Batching video IDs from multiple channels and requesting them
           together, instead of requesting each channel's videos separately in
           less-than-full batches. In retrospect, this improvement could be
           applied to the non-RSS refresh method too. If this RSS experiment
           turns out to be bad, I can at least go ahead with that.

        The RSS has two limitations:
        1. It does not contain all the properties I want to store, otherwise
           I'd happily use that data directly instead of passing the ID batches
           into ytapi.
        2. It only returns the latest 15 videos, and of course does not
           paginate. So, for any channel with more than 14 new videos, we'll
           do a traditional refresh.
        '''
        excs = []

        def traditional(channel):
            try:
                channel.refresh(rss_assisted=False)
            except Exception as exc:
                if skip_failures:
                    excs.append(exc)
                else:
                    raise

        def assisted(channel):
            try:
                most_recent_video = channel.get_most_recent_video_id()
                new_ids = ytrss.get_user_videos_since(channel.id, most_recent_video)
                yield from new_ids
            except (exceptions.NoVideos, exceptions.RSSAssistFailed) as exc:
                self.log.debug(
                    'RSS assist for %s failed "%s", using traditional refresh.',
                    channel.id,
                    exc.error_message
                )
                traditional(channel)

        new_ids = (id for channel in self.get_channels() for id in assisted(channel))
        for video in self.youtube.get_videos(new_ids):
            self.ingest_video(video, commit=False)

        if commit:
            self.commit()

        return excs

    def refresh_all_channels(
            self,
            *,
            force=False,
            rss_assisted=True,
            skip_failures=False,
            commit=True,
        ):
        self.log.info('Refreshing all channels.')

        if rss_assisted and not force:
            return self._rss_assisted_refresh(skip_failures=skip_failures, commit=commit)

        excs = []
        for channel in self.get_channels():
            try:
                channel.refresh(force=force, commit=commit)
            except Exception as exc:
                if skip_failures:
                    self.log.warning(exc)
                    excs.append(exc)
                else:
                    raise
        if commit:
            self.commit()

        return excs

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
        self.log.loud('%s %s', query, bindings)
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
        Create the queuefile within the channel's associated directory, or
        the default directory from the config file.
        '''
        if isinstance(video, objects.Video):
            pass
        elif isinstance(video, ytapi.Video):
            video = self.get_video(video.id)
        elif isinstance(video, str):
            video = self.get_video(video)
        else:
            raise TypeError(video)

        if video.state != 'pending' and not force:
            self.log.debug('%s does not need to be downloaded.', video.id)
            return

        try:
            channel = self.get_channel(video.author_id)
            download_directory = channel.download_directory or self.config['download_directory']
            extension = channel.queuefile_extension or self.config['queuefile_extension']
        except exceptions.NoSuchChannel:
            download_directory = self.config['download_directory']
            extension = self.config['queuefile_extension']

        download_directory = pathclass.Path(download_directory)
        queuefile = download_directory.with_child(video.id).replace_extension(extension)

        self.log.info('Creating %s.', queuefile.absolute_path)

        download_directory.makedirs(exist_ok=True)
        queuefile.touch()

        video.mark_state('downloaded', commit=False)

        if commit:
            self.commit()

    def get_video(self, video_id):
        return self.get_thing_by_id('video', video_id)

    def get_videos(self, channel_id=None, *, state=None, orderby=None):
        wheres = []
        orderbys = []

        bindings = []
        if channel_id is not None:
            wheres.append('author_id')
            bindings.append(channel_id)

        if state is not None:
            wheres.append('state')
            bindings.append(state)

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

        self.log.debug('%s %s', query, bindings)
        explain = self.sql_execute('EXPLAIN QUERY PLAN ' + query, bindings)
        self.log.debug('\n'.join(str(x) for x in explain.fetchall()))

        rows = self.sql_select(query, bindings)
        for row in rows:
            yield self.get_cached_instance('video', row)

    def get_videos_by_sql(self, query, bindings=None):
        return self.get_things_by_sql('video', query, bindings)

    def insert_playlist(self, playlist_id, commit=True):
        video_generator = self.youtube.get_playlist_videos(playlist_id)
        results = [self.insert_video(video, commit=False) for video in video_generator]

        if commit:
            self.commit()

        return results

    def ingest_video(self, video, commit=True):
        '''
        Call `insert_video`, and additionally use the channel's automark to
        mark this video's state.
        '''
        status = self.insert_video(video, commit=False)

        if not status['new']:
            return status

        video = status['video']
        author = video.author

        if not author:
            return status

        if author.automark in [None, 'pending']:
            return status

        if author.automark == 'downloaded':
            if video.live_broadcast is not None:
                self.log.debug(
                    'Not downloading %s because live_broadcast=%s.',
                    video.id,
                    video.live_broadcast,
                )
                return status
            # download_video contains a call to mark_state.
            self.download_video(video.id, commit=False)
        else:
            video.mark_state(author.automark, commit=False)

        if commit:
            self.commit()

        return status

    def insert_video(self, video, *, add_channel=True, commit=True):
        if not isinstance(video, ytapi.Video):
            video = self.youtube.get_video(video)

        if add_channel:
            self.add_channel(video.author_id, get_videos=False, commit=False)

        try:
            existing = self.get_video(video.id)
            existing_live_broadcast = existing.live_broadcast
            download_status = existing.state
        except exceptions.NoSuchVideo:
            existing = None
            existing_live_broadcast = None
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
            'live_broadcast': video.live_broadcast,
            'state': download_status,
        }

        if existing:
            self.log.loud('Updating Video %s.', video.id)
            self.sql_update(table='videos', pairs=data, where_key='id')
        else:
            self.log.loud('Inserting Video %s.', video.id)
            self.sql_insert(table='videos', data=data)

        # Override the cached copy with the new copy so that the cache contains
        # updated information (view counts etc.).
        video = objects.Video(self, data)
        self.caches['video'][video.id] = video

        if commit:
            self.commit()

        # For the benefit of ingest_video, which will only apply the channel's
        # automark to newly released videos, let's consider the video to be
        # new if live_broadcast has changed to be None since last time.
        # This way, premieres and livestreams can be automarked by the next
        # refresh after they've ended.
        is_new = (
            (existing is None) or
            (existing_live_broadcast is not None and video.live_broadcast is None)
        )
        return {'new': is_new, 'video': video}

class YCDLDB(
        YCDLDBCacheManagerMixin,
        YCDLDBChannelMixin,
        YCDLDBVideoMixin,
        YCDLSQLMixin,
    ):
    def __init__(
            self,
            youtube,
            create=True,
            data_directory=None,
            log_level=vlogging.NOTSET,
            skip_version_check=False,
        ):
        super().__init__()
        self.youtube = youtube

        # DATA DIR PREP
        if data_directory is None:
            data_directory = constants.DEFAULT_DATADIR

        self.data_directory = pathclass.Path(data_directory)

        if self.data_directory.exists and not self.data_directory.is_dir:
            raise exceptions.BadDataDirectory(self.data_directory.absolute_path)

        # LOGGING
        self.log = vlogging.getLogger(f'{__name__}:{self.data_directory.absolute_path}')
        self.log.setLevel(log_level)
        self.youtube.log.setLevel(log_level)

        # DATABASE
        self.database_filepath = self.data_directory.with_child(constants.DEFAULT_DBNAME)
        existing_database = self.database_filepath.exists
        if not existing_database and not create:
            msg = f'"{self.database_filepath.absolute_path}" does not exist and create is off.'
            raise FileNotFoundError(msg)

        self.data_directory.makedirs(exist_ok=True)
        self.sql = sqlite3.connect(self.database_filepath.absolute_path)

        if existing_database:
            if not skip_version_check:
                self._check_version()
            self._load_pragmas()
        else:
            self._first_time_setup()

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
                filepath=self.data_directory,
            )

    def _first_time_setup(self):
        self.log.info('Running first-time database setup.')
        self.sql.executescript(constants.DB_INIT)
        self.commit()

    def _load_pragmas(self):
        self.log.debug('Reloading pragmas.')
        self.sql.executescript(constants.DB_PRAGMAS)
        self.commit()

    def get_all_states(self):
        '''
        Get a list of all the different states that are currently in use in
        the database.
        '''
        # Note: This function was added while I was considering the addition of
        # arbitrarily many states for user-defined purposes, but I kind of went
        # back on that so I'm not sure if it will be useful.
        query = 'SELECT DISTINCT state FROM videos'
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
        with self.config_filepath.open('w', encoding='utf-8') as handle:
            handle.write(json.dumps(self.config, indent=4, sort_keys=True))
