import json
import sqlite3

from voussoirkit import cacheclass
from voussoirkit import configlayers
from voussoirkit import pathclass
from voussoirkit import vlogging
from voussoirkit import worms

log = vlogging.getLogger(__name__)

from . import constants
from . import exceptions
from . import objects
from . import ytapi
from . import ytrss

import youtube_credentials

class YCDLDBChannelMixin:
    def __init__(self):
        super().__init__()

    @worms.transaction
    def add_channel(
            self,
            channel_id,
            *,
            automark='pending',
            download_directory=None,
            queuefile_extension=None,
            get_videos=False,
            name=None,
        ):
        '''
        Raises exceptions.InvalidVideoState if automark is not
        one of constants.VIDEO_STATES.
        Raises TypeError if name is not a string.
        Raises TypeError if queuefile_extension is not a string.
        Raises pathclass.NotDirectory is download_directory is not an existing
        directory (via objects.Channel.normalize_download_directory).
        '''
        try:
            return self.get_channel(channel_id)
        except exceptions.NoSuchChannel:
            pass

        self.assert_valid_state(automark)

        name = objects.Channel.normalize_name(name)
        if name is None:
            name = self.youtube.get_user_name(channel_id)

        download_directory = objects.Channel.normalize_download_directory(download_directory)
        download_directory = download_directory.absolute_path if download_directory else None
        queuefile_extension = objects.Channel.normalize_queuefile_extension(queuefile_extension)

        log.info('Adding channel %s %s', channel_id, name)

        data = {
            'id': channel_id,
            'name': name,
            'uploads_playlist': self.youtube.get_user_uploads_playlist_id(channel_id),
            'download_directory': download_directory,
            'queuefile_extension': queuefile_extension,
            'automark': automark,
            'autorefresh': True,
        }
        self.insert(table='channels', data=data)

        channel = objects.Channel(self, data)

        if get_videos:
            channel.refresh()

        return channel

    def get_channel(self, channel_id):
        return self.get_object_by_id(objects.Channel, channel_id)

    def get_channels(self):
        return self.get_objects(objects.Channel)

    def get_channels_by_id(self, channel_ids):
        return self.get_objects_by_id(objects.Channel, channel_ids, raise_for_missing=True)

    def get_channels_by_sql(self, query, bindings=None):
        return self.get_objects_by_sql(objects.Channel, query, bindings)

    @worms.transaction
    def _rss_assisted_refresh(self, channels, skip_failures=False):
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
                    log.warning(exc)
                    excs.append(exc)
                else:
                    raise

        def assisted(channel):
            try:
                most_recent_video = channel.get_most_recent_video_id()
                new_ids = ytrss.get_user_videos_since(channel.id, most_recent_video)
                yield from new_ids
            except (exceptions.NoVideos, exceptions.RSSAssistFailed) as exc:
                log.debug(
                    'RSS assist for %s failed "%s", using traditional refresh.',
                    channel.id,
                    exc.error_message
                )
                traditional(channel)

        new_ids = (id for channel in channels for id in assisted(channel))
        for video in self.youtube.get_videos(new_ids):
            self.ingest_video(video)

        return excs

    @worms.transaction
    def refresh_all_channels(
            self,
            *,
            force=False,
            rss_assisted=True,
            skip_failures=False,
        ):
        log.info('Refreshing all channels.')

        channels = self.get_channels_by_sql('SELECT * FROM channels WHERE autorefresh == 1')

        if rss_assisted and not force:
            return self._rss_assisted_refresh(channels, skip_failures=skip_failures)

        excs = []
        for channel in channels:
            try:
                channel.refresh(force=force)
            except Exception as exc:
                if skip_failures:
                    log.warning(exc)
                    excs.append(exc)
                else:
                    raise
        return excs

class YCDLDBVideoMixin:
    def __init__(self):
        super().__init__()

    @worms.transaction
    def download_video(
            self,
            video,
            *,
            download_directory=None,
            force=False,
            queuefile_extension=None,
        ):
        '''
        Create the queuefile within the channel's associated directory, or
        the default directory from the config file.

        download_directory:
            By default, the queuefile will be placed in the channel's
            download_directory if it has one, or the download_directory in the
            ycdl.json config file. You can pass this argument to override both
            of those.

        force:
            By default, a video that is already marked as downloaded will not be
            downloaded again. You can add this to make the queuefiles for those
            videos anyway.

        queuefile_extension:
            By default, the queuefile extension is taken from the channel or the
            config file. You can pass this argument to override both of those.
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
            log.debug('%s does not need to be downloaded.', video)
            return

        try:
            channel = self.get_channel(video.author_id)
        except exceptions.NoSuchChannel:
            channel = None

        if download_directory is not None:
            download_directory = pathclass.Path(download_directory)
        elif channel is not None:
            download_directory = channel.download_directory or self.config['download_directory']
        else:
            download_directory = self.config['download_directory']

        if queuefile_extension is not None:
            pass
        elif channel is not None:
            queuefile_extension = channel.queuefile_extension or self.config['queuefile_extension']
        else:
            queuefile_extension = self.config['queuefile_extension']

        download_directory = pathclass.Path(download_directory)
        queuefile = download_directory.with_child(video.id).replace_extension(queuefile_extension)

        def create_queuefile():
            log.info('Creating %s.', queuefile.absolute_path)

            download_directory.makedirs(exist_ok=True)
            queuefile.touch()

        self.on_commit_queue.append({'action': create_queuefile})
        video.mark_state('downloaded')
        return queuefile

    def get_video(self, video_id):
        return self.get_object_by_id(objects.Video, video_id)

    def get_videos_by_id(self, video_ids):
        return self.get_objects_by_id(objects.Video, video_ids, raise_for_missing=True)

    def get_videos(self, channel_id=None, *, state=None, orderby=None):
        wheres = []
        orderbys = []

        bindings = []
        if channel_id is not None:
            wheres.append('author_id')
            bindings.append(channel_id)

        if state is not None:
            self.assert_valid_state(state)
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

        log.debug('%s %s', query, bindings)
        explain = self.execute('EXPLAIN QUERY PLAN ' + query, bindings)
        log.debug('\n'.join(str(x) for x in explain.fetchall()))

        rows = self.select(query, bindings)
        for row in rows:
            yield self.get_cached_instance(objects.Video, row)

    def get_videos_by_sql(self, query, bindings=None):
        return self.get_objects_by_sql(objects.Video, query, bindings)

    @worms.transaction
    def insert_playlist(self, playlist_id):
        video_generator = self.youtube.get_playlist_videos(playlist_id)
        results = [self.insert_video(video) for video in video_generator]

        return results

    @worms.transaction
    def ingest_video(self, video):
        '''
        Call `insert_video`, and additionally use the channel's automark to
        mark this video's state.
        '''
        status = self.insert_video(video)

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
                log.debug(
                    'Not downloading %s because live_broadcast=%s.',
                    video.id,
                    video.live_broadcast,
                )
                return status
            # download_video contains a call to mark_state.
            self.download_video(video.id)
        else:
            video.mark_state(author.automark)

        return status

    @worms.transaction
    def insert_video(self, video, *, add_channel=True):
        if not isinstance(video, ytapi.Video):
            video = self.youtube.get_video(video)

        if add_channel:
            self.add_channel(video.author_id, get_videos=False)

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
            log.loud('Updating Video %s.', video)
            self.update(table='videos', pairs=data, where_key='id')
        else:
            log.loud('Inserting Video %s.', video)
            self.insert(table='videos', data=data)

        # Override the cached copy with the new copy so that the cache contains
        # updated information (view counts etc.).
        video = objects.Video(self, data)
        self.caches[objects.Video][video.id] = video

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
        YCDLDBChannelMixin,
        YCDLDBVideoMixin,
        worms.DatabaseWithCaching,
    ):
    def __init__(
            self,
            youtube=None,
            *,
            create=False,
            data_directory=None,
            skip_version_check=False,
        ):
        super().__init__()
        if youtube is None:
            youtube = ytapi.Youtube(youtube_credentials.get_youtube_key())
        self.youtube = youtube

        # DATA DIR PREP
        if data_directory is None:
            data_directory = constants.DEFAULT_DATADIR

        self.data_directory = pathclass.Path(data_directory)

        if self.data_directory.exists and not self.data_directory.is_dir:
            raise exceptions.BadDataDirectory(self.data_directory.absolute_path)

        # DATABASE
        self._init_sql(create=create, skip_version_check=skip_version_check)

        # CONFIG
        self.config_filepath = self.data_directory.with_child(constants.DEFAULT_CONFIGNAME)
        self.load_config()

        # WORMS
        self._init_column_index()
        self._init_caches()

    def _check_version(self):
        '''
        Compare database's user_version against constants.DATABASE_VERSION,
        raising exceptions.DatabaseOutOfDate if not correct.
        '''
        existing = self.execute('PRAGMA user_version').fetchone()[0]
        if existing != constants.DATABASE_VERSION:
            raise exceptions.DatabaseOutOfDate(
                existing=existing,
                new=constants.DATABASE_VERSION,
                filepath=self.data_directory,
            )

    def _init_caches(self):
        self.caches = {
            objects.Channel: cacheclass.Cache(maxlen=20_000),
            objects.Video: cacheclass.Cache(maxlen=50_000),
        }

    def _init_column_index(self):
        self.COLUMNS = constants.SQL_COLUMNS
        self.COLUMN_INDEX = constants.SQL_INDEX

    def _init_sql(self, create, skip_version_check):
        self.database_filepath = self.data_directory.with_child(constants.DEFAULT_DBNAME)
        existing_database = self.database_filepath.exists
        if not existing_database and not create:
            msg = f'"{self.database_filepath.absolute_path}" does not exist and create is off.'
            raise FileNotFoundError(msg)

        self.data_directory.makedirs(exist_ok=True)
        self.sql = sqlite3.connect(self.database_filepath)

        if existing_database:
            if not skip_version_check:
                self._check_version()
            self._load_pragmas()
        else:
            self._first_time_setup()

    def _first_time_setup(self):
        log.info('Running first-time database setup.')
        self.executescript(constants.DB_INIT)
        self.commit()

    def _load_pragmas(self):
        log.debug('Reloading pragmas.')
        self.executescript(constants.DB_PRAGMAS)
        self.commit()

    @classmethod
    def closest_ycdldb(cls, youtube=None, path='.', *args, **kwargs):
        '''
        Starting from the given path and climbing upwards towards the filesystem
        root, look for an existing YCDL data directory and return the
        YCDLDB object. If none exists, raise exceptions.NoClosestYCDLDB.
        '''
        path = pathclass.Path(path)
        starting = path

        while True:
            possible = path.with_child(constants.DEFAULT_DATADIR)
            if possible.is_dir:
                break
            parent = path.parent
            if path == parent:
                raise exceptions.NoClosestYCDLDB(starting.absolute_path)
            path = parent

        path = possible
        ycdldb = cls(
            youtube=youtube,
            data_directory=path,
            create=False,
            *args,
            **kwargs,
        )
        log.debug('Found closest YCDLDB at %s.', path)
        return ycdldb

    @staticmethod
    def assert_valid_state(state):
        if state not in constants.VIDEO_STATES:
            raise exceptions.InvalidVideoState(state)

    def get_all_states(self):
        '''
        Get a list of all the different states that are currently in use in
        the database.
        '''
        # Note: This function was added while I was considering the addition of
        # arbitrarily many states for user-defined purposes, but I kind of went
        # back on that so I'm not sure if it will be useful.
        query = 'SELECT DISTINCT state FROM videos'
        states = self.select(query)
        states = [row[0] for row in states]
        return sorted(states)

    def load_config(self):
        (config, needs_rewrite) = configlayers.load_file(
            filepath=self.config_filepath,
            default_config=constants.DEFAULT_CONFIGURATION,
        )
        self.config = config

        if needs_rewrite:
            self.save_config()

    def save_config(self):
        with self.config_filepath.open('w', encoding='utf-8') as handle:
            handle.write(json.dumps(self.config, indent=4, sort_keys=True))
