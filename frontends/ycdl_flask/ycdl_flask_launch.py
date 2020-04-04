import logging
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

import gevent.monkey
gevent.monkey.patch_all()

import argparse
import gevent.pywsgi
import sys

import backend

def ycdl_flask_launch(port, refresh_rate):
    if port == 443:
        http = gevent.pywsgi.WSGIServer(
            listener=('', port),
            application=backend.site,
            keyfile='https\\flasksite.key',
            certfile='https\\flasksite.crt',
        )
    else:
        http = gevent.pywsgi.WSGIServer(
            listener=('0.0.0.0', port),
            application=backend.site,
        )

    if refresh_rate is not None:
        backend.common.start_refresher_thread(refresh_rate)

    print(f'Starting server on port {port}')
    http.serve_forever()

def ycdl_flask_launch_argparse(args):
    if args.do_refresh:
        refresh_rate = args.refresh_rate
    else:
        refresh_rate = None

    return ycdl_flask_launch(
        port=args.port,
        refresh_rate=refresh_rate,
    )

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('port', nargs='?', type=int, default=5000)
    parser.add_argument('--no_refresh', dest='do_refresh', action='store_false', default=True)
    parser.add_argument('--refresh_rate', dest='refresh_rate', type=int, default=60 * 60 * 6)
    parser.set_defaults(func=ycdl_flask_launch_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
