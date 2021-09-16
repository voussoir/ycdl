import datetime
import typing

from voussoirkit import pathclass
from voussoirkit import stringtools

from . import constants
from . import exceptions
from . import ytrss

def normalize_db_row(db_row, table) -> dict:
    '''
    Raises KeyError if table is not one of the recognized tables.

    Raises TypeError if db_row is not the right type.
    '''
    if isinstance(db_row, dict):
        return db_row

    if isinstance(db_row, (list, tuple)):
        return dict(zip(constants.SQL_COLUMNS[table], db_row))

    raise TypeError(f'db_row should be {dict}, {list}, or {tuple}, not {type(db_row)}.')

class Base:
    def __init__(self, ycdldb):
        super().__init__()
        self.ycdldb = ycdldb

class Channel(Base):
    table = 'channels'

    def __init__(self, ycdldb, db_row):
        super().__init__(ycdldb)
        db_row = normalize_db_row(db_row, self.table)

        self.id = db_row['id']
        self.name = db_row['name']
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
        '''
        try:
            most_recent_video = self.get_most_recent_video_id()
        except exceptions.NoVideos as exc:
            raise exceptions.RSSAssistFailed(f'Channel has no videos to reference.') from exc
        new_ids = ytrss.get_user_videos_since(self.id, most_recent_video)
        videos = self.ycdldb.youtube.get_videos(new_ids)
        return videos

    def delete(self, commit=True):
        self.ycdldb.log.info('Deleting %s.', self)

        self.ycdldb.sql_delete(table='videos', pairs={'author_id': self.id})
        self.ycdldb.sql_delete(table='channels', pairs={'id': self.id})

        if commit:
            self.ycdldb.commit()

    def get_most_recent_video_id(self):
        query = 'SELECT id FROM videos WHERE author_id == ? ORDER BY published DESC LIMIT 1'
        bindings = [self.id]
        row = self.ycdldb.sql_select_one(query, bindings)
        if row is None:
            raise exceptions.NoVideos(self)
        return row[0]

    def has_pending(self):
        query = 'SELECT 1 FROM videos WHERE author_id == ? AND state == "pending" LIMIT 1'
        bindings = [self.id]
        return self.ycdldb.sql_select_one(query, bindings) is not None

    def jsonify(self):
        j = {
            'id': self.id,
            'name': self.name,
            'automark': self.automark,
        }
        return j

    def refresh(self, *, force=False, rss_assisted=True, commit=True):
        self.ycdldb.log.info('Refreshing %s.', self.id)

        if force or (not self.uploads_playlist):
            self.reset_uploads_playlist_id()

        if force or not rss_assisted:
            video_generator = self.ycdldb.youtube.get_playlist_videos(self.uploads_playlist)
        else:
            try:
                video_generator = self._rss_assisted_videos()
            except exceptions.RSSAssistFailed as exc:
                self.ycdldb.log.debug('Caught %s.', exc)
                video_generator = self.ycdldb.youtube.get_playlist_videos(self.uploads_playlist)

        seen_ids = set()
        for video in video_generator:
            seen_ids.add(video.id)
            status = self.ycdldb.ingest_video(video, commit=False)

            if (not status['new']) and (not force):
                break

        # Now we will refresh some other IDs that may not have been refreshed
        # by the previous loop.
        refresh_ids = set()

        # 1. Videos which have become unlisted, therefore not returned by the
        # get_playlist_videos call. Take the set of all known ids minus those
        # refreshed by the earlier  loop, the difference will be unlisted,
        # private, or deleted videos. At this time we have no special handling
        # for deleted videos, but they simply won't come back from ytapi.
        if force:
            known_ids = {v.id for v in self.ycdldb.get_videos(channel_id=self.id)}
            refresh_ids.update(known_ids.difference(seen_ids))

        # 2. Premieres or live events which may now be over but were not
        # included in the requested batch of IDs because they are not the most
        # recent.
        query = 'SELECT * FROM videos WHERE live_broadcast IS NOT NULL'
        videos = self.ycdldb.get_videos_by_sql(query)
        refresh_ids.update(v.id for v in videos)

        if refresh_ids:
            self.ycdldb.log.debug('Refreshing %d ids separately.', len(refresh_ids))

        # We call ingest_video instead of insert_video so that
        # premieres / livestreams which have finished can be automarked.
        for video_id in self.ycdldb.youtube.get_videos(refresh_ids):
            self.ycdldb.ingest_video(video_id, commit=False)

        if commit:
            self.ycdldb.commit()

    def reset_uploads_playlist_id(self):
        '''
        Reset the stored uploads_playlist id with current data from the API.
        '''
        self.uploads_playlist = self.ycdldb.youtube.get_user_uploads_playlist_id(self.id)
        self.set_uploads_playlist_id(self.uploads_playlist)
        return self.uploads_playlist

    def set_automark(self, state, commit=True):
        if state not in constants.VIDEO_STATES:
            raise exceptions.InvalidVideoState(state)

        pairs = {
            'id': self.id,
            'automark': state,
        }
        self.ycdldb.sql_update(table='channels', pairs=pairs, where_key='id')
        self.automark = state

        if commit:
            self.ycdldb.commit()

    def set_autorefresh(self, autorefresh, commit=True):
        autorefresh = self.normalize_autorefresh(autorefresh)

        pairs = {
            'id': self.id,
            'autorefresh': autorefresh,
        }
        self.ycdldb.sql_update(table='channels', pairs=pairs, where_key='id')
        self.autorefresh = autorefresh

        if commit:
            self.ycdldb.commit()

    def set_download_directory(self, download_directory, commit=True):
        download_directory = self.normalize_download_directory(download_directory)

        pairs = {
            'id': self.id,
            'download_directory': download_directory.absolute_path if download_directory else None,
        }
        self.ycdldb.sql_update(table='channels', pairs=pairs, where_key='id')
        self.download_directory = download_directory

        if commit:
            self.ycdldb.commit()

    def set_queuefile_extension(self, queuefile_extension, commit=True):
        queuefile_extension = self.normalize_queuefile_extension(queuefile_extension)

        pairs = {
            'id': self.id,
            'queuefile_extension': queuefile_extension,
        }
        self.ycdldb.sql_update(table='channels', pairs=pairs, where_key='id')
        self.queuefile_extension = queuefile_extension

        if commit:
            self.ycdldb.commit()

    def set_uploads_playlist_id(self, playlist_id, commit=True):
        self.ycdldb.log.debug('Setting %s upload playlist to %s.', self.id, playlist_id)
        if not isinstance(playlist_id, str):
            raise TypeError(f'Playlist id must be a string, not {type(playlist_id)}.')

        pairs = {
            'id': self.id,
            'uploads_playlist': playlist_id,
        }
        self.ycdldb.sql_update(table='channels', pairs=pairs, where_key='id')
        self.uploads_playlist = playlist_id

        if commit:
            self.ycdldb.commit()

class Video(Base):
    table = 'videos'

    def __init__(self, ycdldb, db_row):
        super().__init__(ycdldb)
        db_row = normalize_db_row(db_row, self.table)

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

    def delete(self, commit=True):
        self.ycdldb.log.info('Deleting %s.', self)

        self.ycdldb.sql_delete(table='videos', pairs={'id': self.id})

        if commit:
            self.ycdldb.commit()

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

    def mark_state(self, state, commit=True):
        '''
        Mark the video as ignored, pending, or downloaded.
        '''
        if state not in constants.VIDEO_STATES:
            raise exceptions.InvalidVideoState(state)

        self.ycdldb.log.info('Marking %s as %s.', self, state)

        pairs = {
            'id': self.id,
            'state': state,
        }
        self.state = state
        self.ycdldb.sql_update(table='videos', pairs=pairs, where_key='id')

        if commit:
            self.ycdldb.commit()

    @property
    def published_string(self):
        published = self.published
        published = datetime.datetime.utcfromtimestamp(published)
        published = published.strftime('%Y-%m-%d')
        return published
