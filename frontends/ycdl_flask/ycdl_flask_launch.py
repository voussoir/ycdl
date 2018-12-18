import logging
logging.getLogger('googleapicliet.discovery_cache').setLevel(logging.ERROR)

import gevent.monkey
gevent.monkey.patch_all()

import gevent.pywsgi
import sys

import ycdl_flask

if len(sys.argv) == 2:
    port = int(sys.argv[1])
else:
    port = 5000

if port == 443:
    http = gevent.pywsgi.WSGIServer(
        listener=('', port),
        application=ycdl_flask.site,
        keyfile='https\\flasksite.key',
        certfile='https\\flasksite.crt',
    )
else:
    http = gevent.pywsgi.WSGIServer(
        listener=('0.0.0.0', port),
        application=ycdl_flask.site,
    )


print('Starting server on port %d' % port)
http.serve_forever()
