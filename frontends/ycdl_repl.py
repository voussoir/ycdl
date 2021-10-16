import argparse
import code
import sys

from voussoirkit import interactive
from voussoirkit import pipeable
from voussoirkit import vlogging

import ycdl

def yrepl_argparse(args):
    global Y

    try:
        Y = ycdl.ycdldb.YCDLDB.closest_ycdldb()
    except ycdl.exceptions.NoClosestYCDLDB as exc:
        pipeable.stderr(exc.error_message)
        pipeable.stderr('Try `ycdl_cli.py init` to create the database.')
        return 1

    if args.exec_statement:
        exec(args.exec_statement)
        Y.commit()
    else:
        while True:
            try:
                code.interact(banner='', local=dict(globals(), **locals()))
            except SystemExit:
                pass
            if len(Y.savepoints) == 0:
                break
            print('You have uncommited changes, are you sure you want to quit?')
            if interactive.getpermission():
                break

@vlogging.main_decorator
def main(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument('--exec', dest='exec_statement', default=None)
    parser.set_defaults(func=yrepl_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
