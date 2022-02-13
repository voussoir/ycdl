'''
This file is the gevent launcher for local / development use.
'''
import gevent.monkey; gevent.monkey.patch_all()

import argparse
import gevent.pywsgi
import os
import sys

from voussoirkit import betterhelp
from voussoirkit import operatornotify
from voussoirkit import pathclass
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'ycdl_flask_dev')

import ycdl
import backend

site = backend.site
site.debug = True

####################################################################################################

site = backend.site

HTTPS_DIR = pathclass.Path(__file__).parent.with_child('https')

def ycdl_flask_launch(
        *,
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

    try:
        backend.common.init_ycdldb()
    except ycdl.exceptions.NoClosestYCDLDB as exc:
        log.error(exc.error_message)
        log.error('Try `ycdl_cli.py init` to create the database.')
        return 1

    message = f'Starting server on port {port}, pid={os.getpid()}.'
    if use_https:
        message += ' (https)'
    log.info(message)

    if refresh_rate is None:
        log.info('No background refresher thread because --refresh-rate was not passed.')
    else:
        backend.common.start_refresher_thread(refresh_rate)

    try:
        http.serve_forever()
    except KeyboardInterrupt:
        log.info('Goodbye')
        return 0

def ycdl_flask_launch_argparse(args):
    return ycdl_flask_launch(
        localhost_only=args.localhost_only,
        port=args.port,
        refresh_rate=args.refresh_rate,
        use_https=args.use_https,
    )

@vlogging.main_decorator
@operatornotify.main_decorator(subject='YCDL', notify_every_line=True)
def main(argv):
    parser = argparse.ArgumentParser(
        description='''
        This file is the gevent launcher for local / development use.
        ''',
    )
    parser.add_argument(
        'port',
        nargs='?',
        type=int,
        default=5000,
        help='''
        Port number on which to run the server.
        ''',
    )
    parser.add_argument(
        '--https',
        dest='use_https',
        action='store_true',
        help='''
        If this flag is not passed, HTTPS will automatically be enabled if the port
        is 443. You can pass this flag to enable HTTPS on other ports.
        We expect to find ycdl.key and ycdl.crt in frontends/ycdl_flask/https.
        ''',
    )
    parser.add_argument(
        '--localhost_only',
        '--localhost-only',
        action='store_true',
        help='''
        If this flag is passed, only localhost will be able to access the server.
        Other users on the LAN will be blocked.
        ''',
    )
    parser.add_argument(
        '--refresh_rate',
        '--refresh-rate',
        type=int,
        default=None,
        help='''
        Starts a background thread that refreshes all channels once every X seconds.
        ''',
    )
    parser.set_defaults(func=ycdl_flask_launch_argparse)

    return betterhelp.go(parser, argv)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
