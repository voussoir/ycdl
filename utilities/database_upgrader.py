import argparse
import sys

import ycdl

class Migrator:
    '''
    Many of the upgraders involve adding columns. ALTER TABLE ADD COLUMN only
    allows adding at the end, which I usually don't prefer. In order to add a
    column in the middle, you must rename the table, create a new one, transfer
    the data, and drop the old one. But, foreign keys and indices will still
    point to the old table, which causes broken foreign keys and dropped
    indices. So, the only way to prevent all that is to regenerate all affected
    tables and indices. Rather than parsing relationships to determine the
    affected tables, this implementation just regenerates everything.

    It's kind of horrible but it allows me to have the columns in the order I
    want instead of just always appending. Besides, modifying collations cannot
    be done in-place either.

    If you want to truly remove a table or index and not have it get
    regenerated, just do that before instantiating the Migrator.
    '''
    def __init__(self, ycdldb):
        self.ycdldb = ycdldb

        query = 'SELECT name, sql FROM sqlite_master WHERE type == "table"'
        self.tables = {
            name: {'create': sql, 'transfer': f'INSERT INTO {name} SELECT * FROM {name}_old'}
            for (name, sql) in self.ycdldb.select(query)
        }

        # The user may be adding entirely new tables derived from the data of
        # old ones. We'll need to skip new tables for the rename and drop_old
        # steps. So we track which tables already existed at the beginning.
        self.existing_tables = set(self.tables)

        query = 'SELECT name, sql FROM sqlite_master WHERE type == "index" AND name NOT LIKE "sqlite_%"'
        self.indices = list(self.ycdldb.select(query))

    def go(self):
        # This loop is split in many parts, because otherwise if table A
        # references table B and table A is completely reconstructed, it will
        # be pointing to the version of B which has not been reconstructed yet,
        # which is about to get renamed to B_old and then A's reference will be
        # broken.
        self.ycdldb.pragma_write('foreign_keys', 'OFF')
        for (name, table) in self.tables.items():
            if name not in self.existing_tables:
                continue
            self.ycdldb.execute(f'ALTER TABLE {name} RENAME TO {name}_old')

        for (name, table) in self.tables.items():
            self.ycdldb.execute(table['create'])

        for (name, table) in self.tables.items():
            self.ycdldb.execute(table['transfer'])

        for (name, query) in self.tables.items():
            if name not in self.existing_tables:
                continue
            self.ycdldb.execute(f'DROP TABLE {name}_old')

        for (name, query) in self.indices:
            self.ycdldb.execute(query)
        self.ycdldb.pragma_write('foreign_keys', 'ON')

def upgrade_1_to_2(ycdldb):
    '''
    In this version, the `duration` column was added to the videos table.
    '''
    m = Migrator(ycdldb)

    m.tables['videos']['create'] = '''
    CREATE TABLE videos(
        id TEXT,
        published INT,
        author_id TEXT,
        title TEXT,
        description TEXT,
        duration INT,
        thumbnail TEXT,
        download TEXT
    );
    '''
    m.tables['videos']['transfer'] = '''
    INSERT INTO videos SELECT
        id,
        published,
        author_id,
        title,
        description,
        NULL,
        thumbnail,
        download
    FROM videos_old;
    '''

    m.go()

def upgrade_2_to_3(ycdldb):
    '''
    In this version, the `automark` column was added to the channels table, where
    you can set channels to automatically mark videos as ignored or downloaded.
    '''
    ycdldb.sql.execute('ALTER TABLE channels ADD COLUMN automark TEXT')

def upgrade_3_to_4(ycdldb):
    '''
    In this version, the `views` column was added to the videos table.
    '''
    m = Migrator(ycdldb)

    m.tables['videos']['create'] = '''
    CREATE TABLE videos(
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
    '''
    m.tables['videos']['transfer'] = '''
    INSERT INTO videos SELECT
        id,
        published,
        author_id,
        title,
        description,
        duration,
        NULL,
        thumbnail,
        download
    FROM videos_old;
    '''

    m.go()

def upgrade_4_to_5(ycdldb):
    '''
    In this version, the `uploads_playlist` column was added to the channels table.
    '''
    m = Migrator(ycdldb)

    m.tables['channels']['create'] = '''
    CREATE TABLE channels(
        id TEXT,
        name TEXT,
        uploads_playlist TEXT,
        directory TEXT COLLATE NOCASE,
        automark TEXT
    );
    '''
    m.tables['channels']['transfer'] = '''
    INSERT INTO channels SELECT
        id,
        name,
        NULL,
        directory,
        automark
    FROM channels_old;
    '''

    m.go()

    rows = ycdldb.sql.execute('SELECT id FROM channels').fetchall()
    channels = [row[0] for row in rows]
    for channel in channels:
        try:
            uploads_playlist = ycdldb.youtube.get_user_uploads_playlist_id(channel)
        except ycdl.ytapi.ChannelNotFound:
            continue
        print(f'{channel} has playlist {uploads_playlist}.')
        ycdldb.sql.execute(
            'UPDATE channels SET uploads_playlist = ? WHERE id = ?',
            [uploads_playlist, channel]
        )

def upgrade_5_to_6(ycdldb):
    '''
    In this version, the `directory` column of the channels table was renamed
    to `download_directory` to be in line with the default config's name for
    the same value, and the `queuefile_extension` column was added.
    '''
    m = Migrator(ycdldb)

    m.tables['channels']['create'] = '''
    CREATE TABLE channels(
        id TEXT,
        name TEXT,
        uploads_playlist TEXT,
        download_directory TEXT COLLATE NOCASE,
        queuefile_extension TEXT COLLATE NOCASE,
        automark TEXT
    );
    '''
    m.tables['channels']['transfer'] = '''
    INSERT INTO channels SELECT
        id,
        name,
        uploads_playlist,
        directory,
        NULL,
        automark
    FROM channels_old;
    '''

    m.go()

def upgrade_6_to_7(ycdldb):
    '''
    In this version, the `download` column of the videos table was renamed to
    `state`. The vocabulary throughout the rest of the program had already
    evolved and the database column was behind the times.
    '''
    ycdldb.sql.execute('ALTER TABLE videos RENAME COLUMN download TO state')
    ycdldb.sql.execute('DROP INDEX IF EXISTS index_video_author_download')
    ycdldb.sql.execute('DROP INDEX IF EXISTS index_video_download')
    ycdldb.sql.execute('DROP INDEX IF EXISTS index_video_download_published')
    # /videos/state?orderby=published
    ycdldb.sql.execute('CREATE INDEX index_video_state_published on videos(state, published)')

def upgrade_7_to_8(ycdldb):
    '''
    In this version, indexes were optimized by adding indexes that satisfy the
    major use cases, and deleting indexes that are redundant in the presence of
    another multi-column index.
    '''
    # /channel?orderby=published
    ycdldb.sql.execute('''
        CREATE INDEX IF NOT EXISTS index_video_author_published on videos(author_id, published);
    ''')
    # /channel/state?orderby=published
    ycdldb.sql.execute('''
        CREATE INDEX IF NOT EXISTS index_video_author_state_published
        on videos(author_id, state, published);
    ''')
    # Redundant due to (author, published)
    ycdldb.sql.execute('DROP INDEX IF EXISTS index_video_author')
    # Redundant due to (author, state, published)
    ycdldb.sql.execute('DROP INDEX IF EXISTS index_video_author_state')
    # Redundant due to (state, published)
    ycdldb.sql.execute('DROP INDEX IF EXISTS index_video_state')

def upgrade_8_to_9(ycdldb):
    '''
    In this version, the `live_broadcast` column was added to the videos table.
    '''
    m = Migrator(ycdldb)

    m.tables['videos']['create'] = '''
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
    '''
    m.tables['videos']['transfer'] = '''
    INSERT INTO videos SELECT
        id,
        published,
        author_id,
        title,
        description,
        duration,
        views,
        thumbnail,
        NULL,
        state
    FROM videos_old;
    '''

    m.go()

def upgrade_9_to_10(ycdldb):
    '''
    In this version, the `autorefresh` column was added to the channels table.
    '''
    m = Migrator(ycdldb)

    m.tables['channels']['create'] = '''
    CREATE TABLE IF NOT EXISTS channels(
        id TEXT,
        name TEXT,
        uploads_playlist TEXT,
        download_directory TEXT COLLATE NOCASE,
        queuefile_extension TEXT COLLATE NOCASE,
        automark TEXT,
        autorefresh INT
    );
    '''
    m.tables['channels']['transfer'] = '''
    INSERT INTO channels SELECT
        id,
        name,
        uploads_playlist,
        download_directory,
        queuefile_extension,
        automark,
        1
    FROM channels_old;
    '''

    m.go()

def upgrade_10_to_11(ycdldb):
    '''
    In this version, the `last_refresh` column was added to the channels table.
    '''
    m = Migrator(ycdldb)

    m.tables['channels']['create'] = '''
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
    '''
    m.tables['channels']['transfer'] = '''
    INSERT INTO channels SELECT
        id,
        name,
        uploads_playlist,
        download_directory,
        queuefile_extension,
        automark,
        autorefresh,
        NULL
    FROM channels_old;
    '''

    m.go()

def upgrade_11_to_12(ycdldb):
    '''
    In this version, the `ignore_shorts` column was added to the channels table
    and `is_shorts` was added to the videos table.
    '''
    m = Migrator(ycdldb)

    m.tables['channels']['create'] = '''
    CREATE TABLE IF NOT EXISTS channels(
        id TEXT,
        name TEXT,
        uploads_playlist TEXT,
        download_directory TEXT COLLATE NOCASE,
        queuefile_extension TEXT COLLATE NOCASE,
        automark TEXT,
        autorefresh INT,
        last_refresh INT,
        ignore_shorts INT NOT NULL
    );
    '''
    m.tables['channels']['transfer'] = '''
    INSERT INTO channels SELECT
        id,
        name,
        uploads_playlist,
        download_directory,
        queuefile_extension,
        automark,
        autorefresh,
        last_refresh,
        1
    FROM channels_old;
    '''
    m.tables['videos']['create'] = '''
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
        state TEXT,
        is_shorts INT
    );
    '''
    m.tables['videos']['transfer'] = '''
    INSERT INTO videos SELECT
        id,
        published,
        author_id,
        title,
        description,
        duration,
        views,
        thumbnail,
        live_broadcast,
        state,
        NULL
    FROM videos_old;
    '''

    m.go()

def upgrade_all(data_directory):
    '''
    Given the directory containing a ycdl database, apply all of the
    needed upgrade_x_to_y functions in order.
    '''
    ycdldb = ycdl.ycdldb.YCDLDB(data_directory, skip_version_check=True)

    current_version = ycdldb.pragma_read('user_version')
    needed_version = ycdl.constants.DATABASE_VERSION

    if current_version == needed_version:
        print('Already up to date with version %d.' % needed_version)
        return

    for version_number in range(current_version + 1, needed_version + 1):
        print('Upgrading from %d to %d.' % (current_version, version_number))
        upgrade_function = 'upgrade_%d_to_%d' % (current_version, version_number)
        upgrade_function = eval(upgrade_function)

        with ycdldb.transaction:
            ycdldb.pragma_write('foreign_keys', 'ON')
            upgrade_function(ycdldb)
            ycdldb.pragma_write('user_version', version_number)

        current_version = version_number
    print('Upgrades finished.')

def upgrade_all_argparse(args):
    return upgrade_all(data_directory=args.data_directory)

def main(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument('data_directory')
    parser.set_defaults(func=upgrade_all_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
