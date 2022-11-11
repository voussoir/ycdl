from voussoirkit import sqlhelpers

DATABASE_VERSION = 11

DB_INIT = f'''
CREATE TABLE IF NOT EXISTS channels(
    id TEXT,
    name TEXT,
    uploads_playlist TEXT,
    download_directory TEXT COLLATE NOCASE,
    queuefile_extension TEXT COLLATE NOCASE,
    automark TEXT,
    autorefresh INT,
    last_refresh INT
);
CREATE INDEX IF NOT EXISTS index_channel_id on channels(id);
----------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS videos(
    id TEXT,
    published INT,
    author_id TEXT,
    title TEXT,
    description TEXT,
    duration INT,
    views INT,
    thumbnail TEXT,
    live_broadcast TEXT,
    state TEXT
);
CREATE INDEX IF NOT EXISTS index_video_author_published on videos(author_id, published);
CREATE INDEX IF NOT EXISTS index_video_author_state_published on videos(author_id, state, published);
CREATE INDEX IF NOT EXISTS index_video_id on videos(id);
CREATE INDEX IF NOT EXISTS index_video_published on videos(published);
CREATE INDEX IF NOT EXISTS index_video_state_published on videos(state, published);
'''

SQL_COLUMNS = sqlhelpers.extract_table_column_map(DB_INIT)
SQL_INDEX = sqlhelpers.reverse_table_column_map(SQL_COLUMNS)

DEFAULT_DATADIR = '_ycdl'
DEFAULT_DBNAME = 'ycdl.db'
DEFAULT_CONFIGNAME = 'ycdl.json'

VIDEO_STATES = ['ignored', 'pending', 'downloaded']

DEFAULT_CONFIGURATION = {
    'download_directory': '.',
    'queuefile_extension': 'ytqueue',
}
