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
    ycdldb.sql.executescript('''
        ALTER TABLE videos RENAME TO videos_old;
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
        DROP TABLE videos_old;
    ''')

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
    ycdldb.sql.executescript('''
        ALTER TABLE videos RENAME TO videos_old;
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
        DROP TABLE videos_old;
    ''')


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
        upgrade_function(ycdldb)
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
