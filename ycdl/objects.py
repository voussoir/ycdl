from . import constants
from . import exceptions

def normalize_db_row(db_row, table):
    if isinstance(db_row, (list, tuple)):
        db_row = dict(zip(constants.SQL_COLUMNS[table], db_row))
    return db_row

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
        self.download_directory = db_row['download_directory']
        self.queuefile_extension = db_row['queuefile_extension']
        self.automark = db_row['automark'] or "pending"

    def delete(self, commit=True):
        self.ycdldb.sql_delete(table='videos', pairs={'author_id': self.id})
        self.ycdldb.sql_delete(table='channels', pairs={'id': self.id})

        if commit:
            self.ycdldb.commit()

    def has_pending(self):
        query = 'SELECT 1 FROM videos WHERE author_id == ? AND state == "pending" LIMIT 1'
        bindings = [self.id]
        return self.ycdldb.sql_select_one(query, bindings) is not None

    def refresh(self, force=False, commit=True):
        self.ycdldb.log.debug('Refreshing channel: %s', self.id)

        if not self.uploads_playlist:
            self.uploads_playlist = self.ycdldb.youtube.get_user_uploads_playlist_id(self.id)
            self.set_uploads_playlist_id(self.uploads_playlist)

        seen_ids = set()
        video_generator = self.ycdldb.youtube.get_playlist_videos(self.uploads_playlist)
        for video in video_generator:
            seen_ids.add(video.id)
            status = self.ycdldb.ingest_video(video, commit=False)

            if not (force or status['new']):
                break

        if force:
            # If some videos have become unlisted, then they will not have been
            # refreshed by the previous loop. So, take the set of all known ids
            # minus those refreshed by the loop, and try to refresh them.
            # Of course, it's possible they were deleted.
            known_ids = {v.id for v in self.ycdldb.get_videos(channel_id=self.id)}
            refresh_ids = list(known_ids.difference(seen_ids))
            for video in self.ycdldb.youtube.get_videos(refresh_ids):
                self.ycdldb.insert_video(video, commit=False)

        if commit:
            self.ycdldb.commit()

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

    def set_uploads_playlist_id(self, playlist_id, commit=True):
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
        self.state = db_row['state']

    @property
    def author(self):
        try:
            return self.ycdldb.get_channel(self.author_id)
        except exceptions.NoSuchChannel:
            return None

    def delete(self, commit=True):
        self.ycdldb.sql_delete(table='videos', pairs={'id': self.id})

        if commit:
            self.ycdldb.commit()

    def mark_state(self, state, commit=True):
        '''
        Mark the video as ignored, pending, or downloaded.
        '''
        if state not in constants.VIDEO_STATES:
            raise exceptions.InvalidVideoState(state)

        pairs = {
            'id': self.id,
            'state': state,
        }
        self.state = state
        self.ycdldb.sql_update(table='videos', pairs=pairs, where_key='id')

        if commit:
            self.ycdldb.commit()
