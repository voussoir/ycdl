import argparse
import os
import sqlite3
import sys

MIGRATE_QUERY = '''
INSERT INTO {tablename}
SELECT othertable.* FROM other.{tablename} othertable
LEFT JOIN {tablename} mytable ON mytable.id == othertable.id
WHERE mytable.id IS NULL AND {where_clause};
'''

def _migrate_helper(sql, tablename, where_clause='1==1'):
    query = MIGRATE_QUERY.format(tablename=tablename, where_clause=where_clause)
    print(query)

    oldcount = sql.execute('SELECT count(*) FROM %s' % tablename).fetchone()[0]
    sql.execute(query)
    sql.commit()

    newcount = sql.execute('SELECT count(*) FROM %s' % tablename).fetchone()[0]
    print('Gained %d items.' % (newcount - oldcount))

def merge_db(from_db_path, to_db_path, channel):
    to_db = sqlite3.connect(to_db_path)
    from_db = sqlite3.connect(from_db_path)

    to_version = to_db.execute('PRAGMA user_version').fetchone()[0]
    from_version = from_db.execute('PRAGMA user_version').fetchone()[0]

    if to_version != from_version:
        raise Exception(f'Databases have different versions: to={to_version}, from={from_version}.')

    to_db.execute('ATTACH DATABASE "%s" AS other' % from_db_path)
    if channel == '*':
        _migrate_helper(to_db, 'channels')
        _migrate_helper(to_db, 'videos')
    else:
        _migrate_helper(to_db, 'channels', where_clause=f'othertable.id == "{channel}"')
        _migrate_helper(to_db, 'videos', where_clause=f'othertable.author_id == "{channel}"')

def merge_db_argparse(args):
    return merge_db(args.from_db_path, args.to_db_path, args.channel)

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--from_db_path', dest='from_db_path', required=True)
    parser.add_argument('--to_db_path', dest='to_db_path', required=True)
    parser.add_argument('--channel', dest='channel', required=True)
    parser.set_defaults(func=merge_db_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
