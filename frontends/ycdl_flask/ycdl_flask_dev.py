'''
This file is the gevent launcher for local / development use.

Simply run it on the command line:
python ycdl_flask_dev.py [port]
'''
import gevent.monkey; gevent.monkey.patch_all()

import logging
handler = logging.StreamHandler()
log_format = '{levelname}:ycdl.{module}.{funcName}: {message}'
handler.setFormatter(logging.Formatter(log_format, style='{'))
logging.getLogger().addHandler(handler)

import argparse
import gevent.pywsgi
import os
import sys

from voussoirkit import operatornotify
from voussoirkit import pathclass
from voussoirkit import vlogging

import ycdl
import youtube_credentials
import backend

site = backend.site
site.debug = True

####################################################################################################

site = backend.site

HTTPS_DIR = pathclass.Path(__file__).parent.with_child('https')
LOG_LEVEL = vlogging.NOTSET

def ycdl_flask_launch(
        *,
        create,
        localhost_only,
        port,
        refresh_rate,
        use_https,
    ):
    if use_https is None:
        use_https = port == 443

    if use_https:
        http = gevent.pywsgi.WSGIServer(
            listener=('0.0.0.0', port),
            application=site,
            keyfile=HTTPS_DIR.with_child('ycdl.key').absolute_path,
            certfile=HTTPS_DIR.with_child('ycdl.crt').absolute_path,
        )
    else:
        http = gevent.pywsgi.WSGIServer(
            listener=('0.0.0.0', port),
            application=site,
        )

    if localhost_only:
        site.localhost_only = True

    youtube_core = ycdl.ytapi.Youtube(youtube_credentials.get_youtube_key())
    backend.common.init_ycdldb(youtube_core, create=create, log_level=LOG_LEVEL)
    ycdl.ytrss.log.setLevel(LOG_LEVEL)

    if refresh_rate is not None:
        backend.common.start_refresher_thread(refresh_rate)

    message = f'Starting server on port {port}, pid={os.getpid()}.'
    if use_https:
        message += ' (https)'
    print(message)

    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass

def ycdl_flask_launch_argparse(args):
    return ycdl_flask_launch(
        create=args.create,
        localhost_only=args.localhost_only,
        port=args.port,
        refresh_rate=args.refresh_rate,
        use_https=args.use_https,
    )

@operatornotify.main_decorator(subject='YCDL', notify_every_line=True)
def main(argv):
    global LOG_LEVEL
    (LOG_LEVEL, argv) = vlogging.get_level_by_argv(argv)

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('port', nargs='?', type=int, default=5000)
    parser.add_argument('--dont_create', '--dont-create', '--no-create', dest='create', action='store_false', default=True)
    parser.add_argument('--https', dest='use_https', action='store_true', default=None)
    parser.add_argument('--localhost_only', '--localhost-only', dest='localhost_only', action='store_true')
    parser.add_argument('--refresh_rate', '--refresh-rate', dest='refresh_rate', type=int, default=None)
    parser.set_defaults(func=ycdl_flask_launch_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
