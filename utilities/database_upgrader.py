import argparse
import os
import sqlite3
import sys

import bot
import ycdl

def upgrade_1_to_2(ycdldb):
    '''
    In this version, the `duration` column was added to the videos table.
    '''
    ycdldb.sql.execute('ALTER TABLE videos RENAME TO videos_old')
    ycdldb.sql.execute('''
        CREATE TABLE videos(
            id TEXT,
            published INT,
            author_id TEXT,
            title TEXT,
            description TEXT,
            duration INT,
            thumbnail TEXT,
            download TEXT
        )
    ''')
    ycdldb.sql.execute('''
        INSERT INTO videos SELECT
            id,
            published,
            author_id,
            title,
            description,
            NULL,
            thumbnail,
            download
        FROM videos_old
    ''')
    ycdldb.sql.execute('DROP TABLE videos_old')

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
    ycdldb.sql.execute('ALTER TABLE videos RENAME TO videos_old')
    ycdldb.sql.execute('''
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
        )
    ''')
    ycdldb.sql.execute('''
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
        FROM videos_old
    ''')
    ycdldb.sql.execute('DROP TABLE videos_old')

def upgrade_4_to_5(ycdldb):
    '''
    In this version, the `uploads_playlist` column was added to the channels table.
    '''
    ycdldb.sql.execute('ALTER TABLE channels RENAME TO channels_old')
    ycdldb.sql.execute('''
        CREATE TABLE channels(
            id TEXT,
            name TEXT,
            uploads_playlist TEXT,
            directory TEXT COLLATE NOCASE,
            automark TEXT
        )
    ''')
    ycdldb.sql.execute('''
        INSERT INTO channels SELECT
            id,
            name,
            NULL,
            directory,
            automark
        FROM channels_old
    ''')
    ycdldb.sql.execute('DROP TABLE channels_old')

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
    ycdldb.sql.execute('ALTER TABLE channels RENAME TO channels_old')
    ycdldb.sql.execute('''
        CREATE TABLE channels(
            id TEXT,
            name TEXT,
            uploads_playlist TEXT,
            download_directory TEXT COLLATE NOCASE,
            queuefile_extension TEXT COLLATE NOCASE,
            automark TEXT
        )
    ''')
    ycdldb.sql.execute('''
        INSERT INTO channels SELECT
            id,
            name,
            uploads_playlist,
            directory,
            NULL,
            automark
        FROM channels_old
    ''')
    ycdldb.sql.execute('DROP TABLE channels_old')

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
    ycdldb.sql.execute('CREATE INDEX index_video_author_state on videos(author_id, state)')
    ycdldb.sql.execute('CREATE INDEX index_video_state on videos(state)')
    ycdldb.sql.execute('CREATE INDEX index_video_state_published on videos(state, published)')

def upgrade_all(data_directory):
    '''
    Given the directory containing a ycdl database, apply all of the
    needed upgrade_x_to_y functions in order.
    '''
    youtube = ycdl.ytapi.Youtube(bot.get_youtube_key())
    ycdldb = ycdl.ycdldb.YCDLDB(youtube, data_directory, skip_version_check=True)

    cur = ycdldb.sql.cursor()

    cur.execute('PRAGMA user_version')
    current_version = cur.fetchone()[0]
    needed_version = ycdl.constants.DATABASE_VERSION

    if current_version == needed_version:
        print('Already up to date with version %d.' % needed_version)
        return

    for version_number in range(current_version + 1, needed_version + 1):
        print('Upgrading from %d to %d.' % (current_version, version_number))
        upgrade_function = 'upgrade_%d_to_%d' % (current_version, version_number)
        upgrade_function = eval(upgrade_function)

        try:
            ycdldb.sql.execute('BEGIN')
            upgrade_function(ycdldb)
        except Exception as exc:
            ycdldb.rollback()
            raise
        else:
            ycdldb.sql.cursor().execute('PRAGMA user_version = %d' % version_number)
            ycdldb.commit()

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
