from voussoirkit import sqlhelpers

DATABASE_VERSION = 5
DB_VERSION_PRAGMA = f'''
PRAGMA user_version = {DATABASE_VERSION};
'''

DB_PRAGMAS = f'''
PRAGMA count_changes = OFF;
PRAGMA cache_size = 10000;
'''

DB_INIT = f'''
BEGIN;
----------------------------------------------------------------------------------------------------
{DB_PRAGMAS}
{DB_VERSION_PRAGMA}
CREATE TABLE IF NOT EXISTS channels(
    id TEXT,
    name TEXT,
    uploads_playlist TEXT,
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
CREATE INDEX IF NOT EXISTS index_video_download_published on videos(download, published);
----------------------------------------------------------------------------------------------------
COMMIT;
'''

SQL_COLUMNS = sqlhelpers.extract_table_column_map(DB_INIT)
SQL_INDEX = sqlhelpers.reverse_table_column_map(SQL_COLUMNS)

DEFAULT_DATADIR = '.'
DEFAULT_DBNAME = 'ycdl.db'
DEFAULT_CONFIGNAME = 'ycdl.json'

VIDEO_STATES = ['ignored', 'pending', 'downloaded']

DEFAULT_CONFIGURATION = {
    'download_directory': '.',
    'queuefile_extension': 'ytqueue',
}
