import gevent.monkey; gevent.monkey.patch_all()

import logging
logging.basicConfig()
logging.getLogger('ycdl').setLevel(logging.DEBUG)

import argparse
import gevent.pywsgi
import sys

from voussoirkit import pathclass

import bot
import ycdl

import ycdl_flask_entrypoint

HTTPS_DIR = pathclass.Path(__file__).parent.with_child('https')

def ycdl_flask_launch(create, port, refresh_rate, use_https):
    if use_https is None:
        use_https = port == 443

    if use_https:
        http = gevent.pywsgi.WSGIServer(
            listener=('0.0.0.0', port),
            application=ycdl_flask_entrypoint.site,
            keyfile=HTTPS_DIR.with_child('ycdl.key').absolute_path,
            certfile=HTTPS_DIR.with_child('ycdl.crt').absolute_path,
        )
    else:
        http = gevent.pywsgi.WSGIServer(
            listener=('0.0.0.0', port),
            application=ycdl_flask_entrypoint.site,
        )

    youtube_core = ycdl.ytapi.Youtube(bot.get_youtube_key())
    ycdl_flask_entrypoint.backend.common.init_ycdldb(youtube_core, create=create)

    if refresh_rate is not None:
        ycdl_flask_entrypoint.backend.common.start_refresher_thread(refresh_rate)

    message = f'Starting server on port {port}'
    if use_https:
        message += ' (https)'
    print(message)

    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass

def ycdl_flask_launch_argparse(args):
    if args.do_refresh:
        refresh_rate = args.refresh_rate
    else:
        refresh_rate = None

    return ycdl_flask_launch(
        create=args.create,
        port=args.port,
        refresh_rate=refresh_rate,
        use_https=args.use_https,
    )

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('port', nargs='?', type=int, default=5000)
    parser.add_argument('--dont_create', '--dont-create', '--no-create', dest='create', action='store_false', default=True)
    parser.add_argument('--no_refresh', '--no-refresh', dest='do_refresh', action='store_false', default=True)
    parser.add_argument('--refresh_rate', '--refresh-rate', dest='refresh_rate', type=int, default=60 * 60 * 6)
    parser.add_argument('--https', dest='use_https', action='store_true', default=None)
    parser.set_defaults(func=ycdl_flask_launch_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
