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
        self.directory = db_row['directory']
        self.automark = db_row['automark'] or "pending"

    def has_pending(self):
        query = 'SELECT 1 FROM videos WHERE author_id == ? AND download == "pending" LIMIT 1'
        bindings = [self.id]
        return self.ycdldb.sql_select_one(query, bindings) is not None

    def refresh(self, force=False, commit=True):
        seen_ids = set()
        video_generator = self.ycdldb.youtube.get_user_videos(uid=self.id)
        self.ycdldb.log.debug('Refreshing channel: %s', self.id)
        for video in video_generator:
            seen_ids.add(video.id)
            status = self.ycdldb.insert_video(video, commit=False)

            video = status['video']
            if status['new'] and self.automark not in [None, "pending"]:
                if self.automark == 'downloaded':
                    self.ycdldb.download_video(video.id, commit=False)
                video.mark_state(self.automark, commit=False)

            if not force and not status['new']:
                break

        if force:
            known_videos = self.ycdldb.get_videos(channel_id=self.id)
            known_ids = {v.id for v in known_videos}
            refresh_ids = list(known_ids.difference(seen_ids))
            for video in self.ycdldb.youtube.get_video(refresh_ids):
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
        self.download = db_row['download']

    @property
    def author(self):
        try:
            return self.ycdldb.get_channel(self.author_id)
        except exceptions.NoSuchChannel:
            return None

    def mark_state(self, state, commit=True):
        '''
        Mark the video as ignored, pending, or downloaded.
        '''
        if state not in constants.VIDEO_STATES:
            raise exceptions.InvalidVideoState(state)

        pairs = {
            'id': self.id,
            'download': state,
        }
        self.download = state
        self.ycdldb.sql_update(table='videos', pairs=pairs, where_key='id')

        if commit:
            self.ycdldb.commit()
