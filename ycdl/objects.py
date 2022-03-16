import datetime
import googleapiclient.errors
import typing

from voussoirkit import pathclass
from voussoirkit import stringtools
from voussoirkit import vlogging
from voussoirkit import worms

log = vlogging.getLogger(__name__)

from . import constants
from . import exceptions
from . import ytrss

class ObjectBase(worms.Object):
    def __init__(self, ycdldb):
        super().__init__(ycdldb)
        self.ycdldb = ycdldb

class Channel(ObjectBase):
    table = 'channels'
    no_such_exception = exceptions.NoSuchChannel

    def __init__(self, ycdldb, db_row):
        super().__init__(ycdldb)

        self.id = db_row['id']
        self.name = db_row['name'] or self.id
        self.uploads_playlist = db_row['uploads_playlist']
        self.download_directory = self.normalize_download_directory(
            db_row['download_directory'],
            do_assert=False,
        )
        self.queuefile_extension = self.normalize_queuefile_extension(db_row['queuefile_extension'])
        self.automark = db_row['automark'] or 'pending'
        self.autorefresh = stringtools.truthystring(db_row['autorefresh'])

    def __repr__(self):
        return f'Channel:{self.id}'

    def __str__(self):
        return f'Channel:{self.id}:{self.name}'

    @staticmethod
    def normalize_autorefresh(autorefresh):
        if isinstance(autorefresh, (str, int)):
            autorefresh = stringtools.truthystring(autorefresh, none_set={})

        if not isinstance(autorefresh, bool):
            raise TypeError(f'autorefresh should be a boolean, not {autorefresh}.')

        return autorefresh

    @staticmethod
    def normalize_download_directory(
            download_directory,
            do_assert=True,
        ) -> typing.Optional[pathclass.Path]:
        if download_directory is None:
            return None

        if not isinstance(download_directory, (str, pathclass.Path)):
            raise TypeError(f'download_directory should be {str} or {pathclass.Path}, not {type(download_directory)}.')

        if isinstance(download_directory, str):
            download_directory = download_directory.strip()
            if not download_directory:
                return None

        download_directory = pathclass.Path(download_directory)
        download_directory.correct_case()

        if do_assert:
            download_directory.assert_is_directory()

        return download_directory

    @staticmethod
    def normalize_name(name):
        if name is None:
            return None

        if not isinstance(name, str):
            raise TypeError(f'name should be {str}, not {type(name)}.')

        name = name.strip()
        if not name:
            return None

        return name

    @staticmethod
    def normalize_queuefile_extension(queuefile_extension) -> typing.Optional[str]:
        if queuefile_extension is None:
            return None

        if not isinstance(queuefile_extension, str):
            raise TypeError(f'queuefile_extension should be {str}, not {type(queuefile_extension)}.')

        queuefile_extension = queuefile_extension.strip()
        if not queuefile_extension:
            return None

        return queuefile_extension

    def _rss_assisted_videos(self):
        '''
        RSS-assisted refresh will use the channel's RSS feed to find videos
        that are newer than the most recent video we have in the database.
        Then, these new videos can be queried using the regular API since the
        RSS doesn't contain all the attributes we need. This saves us from
        wasting any metered API calls in the case that the RSS has nothing new.

        Raises exceptions.RSSAssistFailed for any of these reasons:
        - The channel has no stored videos, so we don't have a reference point
          for the RSS assist.
        - The RSS did not contain the latest stored video (it has become deleted
          or unlisted), so we don't have a reference point.
        - The RSS fetch request experiences any HTTP error.
        - ytrss fails for any other reason.
        '''
        try:
            most_recent_video = self.get_most_recent_video_id()
        except exceptions.NoVideos as exc:
            raise exceptions.RSSAssistFailed(f'Channel has no videos to reference.') from exc

        # This might raise RSSAssistFailed.
        new_ids = ytrss.get_user_videos_since(self.id, most_recent_video)

        if not new_ids:
            return []
        videos = self.ycdldb.youtube.get_videos(new_ids)
        return videos

    @worms.transaction
    def delete(self):
        log.info('Deleting %s.', self)

        self.ycdldb.delete(table='videos', pairs={'author_id': self.id})
        self.ycdldb.delete(table='channels', pairs={'id': self.id})

    def get_most_recent_video_id(self) -> str:
        '''
        Return the ID of this channel's most recent video by publication date.

        Used primarily for the RSS assisted refresh where we check for videos
        newer than the stored videos.
        '''
        query = 'SELECT id FROM videos WHERE author_id == ? ORDER BY published DESC LIMIT 1'
        bindings = [self.id]
        row = self.ycdldb.select_one(query, bindings)
        if row is None:
            raise exceptions.NoVideos(self)
        return row[0]

    def has_pending(self) -> bool:
        '''
        Return True if this channel has any videos in the pending state.

        Used primarily for generating channel listings.
        '''
        query = 'SELECT 1 FROM videos WHERE author_id == ? AND state == "pending" LIMIT 1'
        bindings = [self.id]
        return self.ycdldb.select_one(query, bindings) is not None

    def jsonify(self):
        j = {
            'id': self.id,
            'name': self.name,
            'automark': self.automark,
        }
        return j

    @worms.transaction
    def refresh(self, *, force=False, rss_assisted=True):
        '''
        Fetch new videos on the channel.

        force:
            If True, all of the channel's videos will be re-downloaded.
            If False, we will first look for new videos, then refresh any
            individual videos that need special attention (unlisted, premieres,
            livestreams).

        rss_assisted:
            If True, we will use the RSS feed to look for new videos, so that
            we can save some API calls.
            If False, we will only use the tokened Youtube API.
            Has no effect when force=True.
        '''
        log.info('Refreshing %s.', self)

        if force or (not self.uploads_playlist):
            self.reset_uploads_playlist_id()

        if force or not rss_assisted:
            video_generator = self.ycdldb.youtube.get_playlist_videos(self.uploads_playlist)
        else:
            try:
                video_generator = self._rss_assisted_videos()
            except exceptions.RSSAssistFailed as exc:
                log.debug('Caught %s.', exc)
                video_generator = self.ycdldb.youtube.get_playlist_videos(self.uploads_playlist)

        seen_ids = set()

        try:
            for video in video_generator:
                seen_ids.add(video.id)
                status = self.ycdldb.ingest_video(video)

                if (not status['new']) and (not force):
                    break
        except googleapiclient.errors.HttpError as exc:
            raise exceptions.ChannelRefreshFailed(channel=self.id, exc=exc)

        # Now we will refresh some other IDs that may not have been refreshed
        # by the previous loop.
        refresh_ids = set()

        # 1. Videos which have become unlisted, therefore not returned by the
        # get_playlist_videos call. Take the set of all known ids minus those
        # refreshed by the earlier loop, the difference will be unlisted,
        # private, or deleted videos. At this time we have no special handling
        # for deleted videos, but they simply won't come back from ytapi.
        if force:
            known_ids = {v.id for v in self.ycdldb.get_videos(channel_id=self.id)}
            refresh_ids.update(known_ids.difference(seen_ids))

        # 2. Premieres or live events which may now be over but were not
        # included in the requested batch of IDs because they are not the most
        # recent.
        query = 'SELECT id FROM videos WHERE author_id == ? AND live_broadcast IS NOT NULL'
        bindings = [self.id]
        premiere_ids = self.ycdldb.select_column(query, bindings)
        refresh_ids.update(premiere_ids)

        if refresh_ids:
            log.debug('Refreshing %d ids separately.', len(refresh_ids))
            # We call ingest_video instead of insert_video so that
            # premieres / livestreams which have finished can be automarked.
            for video in self.ycdldb.youtube.get_videos(refresh_ids):
                self.ycdldb.ingest_video(video)

    def reset_uploads_playlist_id(self):
        '''
        Reset the stored uploads_playlist id with current data from the API.
        '''
        self.uploads_playlist = self.ycdldb.youtube.get_user_uploads_playlist_id(self.id)
        self.set_uploads_playlist_id(self.uploads_playlist)
        return self.uploads_playlist

    @worms.transaction
    def set_automark(self, state):
        self.ycdldb.assert_valid_state(state)

        pairs = {
            'id': self.id,
            'automark': state,
        }
        self.ycdldb.update(table='channels', pairs=pairs, where_key='id')
        self.automark = state

    @worms.transaction
    def set_autorefresh(self, autorefresh):
        autorefresh = self.normalize_autorefresh(autorefresh)

        pairs = {
            'id': self.id,
            'autorefresh': autorefresh,
        }
        self.ycdldb.update(table='channels', pairs=pairs, where_key='id')
        self.autorefresh = autorefresh

    @worms.transaction
    def set_download_directory(self, download_directory):
        download_directory = self.normalize_download_directory(download_directory)

        pairs = {
            'id': self.id,
            'download_directory': download_directory.absolute_path if download_directory else None,
        }
        self.ycdldb.update(table='channels', pairs=pairs, where_key='id')
        self.download_directory = download_directory

    @worms.transaction
    def set_name(self, name):
        name = self.normalize_name(name)

        pairs = {
            'id': self.id,
            'name': name,
        }
        self.ycdldb.update(table='channels', pairs=pairs, where_key='id')
        self.name = name

    @worms.transaction
    def set_queuefile_extension(self, queuefile_extension):
        queuefile_extension = self.normalize_queuefile_extension(queuefile_extension)

        pairs = {
            'id': self.id,
            'queuefile_extension': queuefile_extension,
        }
        self.ycdldb.update(table='channels', pairs=pairs, where_key='id')
        self.queuefile_extension = queuefile_extension

    @worms.transaction
    def set_uploads_playlist_id(self, playlist_id):
        log.debug('Setting %s upload playlist to %s.', self, playlist_id)
        if not isinstance(playlist_id, str):
            raise TypeError(f'Playlist id must be a string, not {type(playlist_id)}.')

        pairs = {
            'id': self.id,
            'uploads_playlist': playlist_id,
        }
        self.ycdldb.update(table='channels', pairs=pairs, where_key='id')
        self.uploads_playlist = playlist_id

class Video(ObjectBase):
    table = 'videos'
    no_such_exception = exceptions.NoSuchVideo

    def __init__(self, ycdldb, db_row):
        super().__init__(ycdldb)

        self.id = db_row['id']
        self.published = db_row['published']
        self.author_id = db_row['author_id']
        self.title = db_row['title']
        self.description = db_row['description']
        self.duration = db_row['duration']
        self.views = db_row['views']
        self.thumbnail = db_row['thumbnail']
        self.live_broadcast = db_row['live_broadcast']
        self.state = db_row['state']

    def __repr__(self):
        return f'Video:{self.id}'

    @property
    def author(self):
        try:
            return self.ycdldb.get_channel(self.author_id)
        except exceptions.NoSuchChannel:
            return None

    @worms.transaction
    def delete(self):
        log.info('Deleting %s.', self)

        self.ycdldb.delete(table='videos', pairs={'id': self.id})

    def jsonify(self):
        j = {
            'id': self.id,
            'published': self.published,
            'author_id': self.author_id,
            'title': self.title,
            'description': self.description,
            'duration': self.duration,
            'views': self.views,
            'thumbnail': self.thumbnail,
            'state': self.state,
        }
        return j

    @worms.transaction
    def mark_state(self, state):
        '''
        Mark the video as ignored, pending, or downloaded.

        Note: Marking as downloaded will not create the queue file, this only
        updates the database. See yclddb.download_video.
        '''
        self.ycdldb.assert_valid_state(state)

        log.info('Marking %s as %s.', self, state)

        pairs = {
            'id': self.id,
            'state': state,
        }
        self.state = state
        self.ycdldb.update(table='videos', pairs=pairs, where_key='id')

    @property
    def published_string(self):
        published = self.published
        published = datetime.datetime.utcfromtimestamp(published)
        published = published.strftime('%Y-%m-%d')
        return published
