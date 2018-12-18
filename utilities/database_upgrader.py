import argparse
import os
import sqlite3
import sys

import ycdl

def upgrade_1_to_2(sql):
    '''
    In this version, a column `tagged_at` was added to the Photos table, to keep
    track of the last time the photo's tags were edited (added or removed).
    '''
    cur = sql.cursor()
    cur.executescript('''
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

def upgrade_all(database_filepath):
    '''
    Given the directory containing a phototagger database, apply all of the
    needed upgrade_x_to_y functions in order.
    '''
    sql = sqlite3.connect(database_filepath)

    cur = sql.cursor()

    cur.execute('PRAGMA user_version')
    current_version = cur.fetchone()[0]
    needed_version = ycdl.ycdl.DATABASE_VERSION

    if current_version == needed_version:
        print('Already up to date with version %d.' % needed_version)
        return

    for version_number in range(current_version + 1, needed_version + 1):
        print('Upgrading from %d to %d.' % (current_version, version_number))
        upgrade_function = 'upgrade_%d_to_%d' % (current_version, version_number)
        upgrade_function = eval(upgrade_function)
        upgrade_function(sql)
        sql.cursor().execute('PRAGMA user_version = %d' % version_number)
        sql.commit()
        current_version = version_number
    print('Upgrades finished.')


def upgrade_all_argparse(args):
    return upgrade_all(database_filepath=args.database_filepath)

def main(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument('database_filepath')
    parser.set_defaults(func=upgrade_all_argparse)

    args = parser.parse_args(argv)
    args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
