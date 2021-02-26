'''
Do not execute this file directly.
Use ycdl_flask_launch.py to start the server with gevent.
'''
import flask; from flask import request
import gzip
import io
import mimetypes
import os
import threading
import time

from voussoirkit import pathclass

import ycdl

from . import jinja_filters

# Flask init #######################################################################################

root_dir = pathclass.Path(__file__).parent.parent

TEMPLATE_DIR = root_dir.with_child('templates')
STATIC_DIR = root_dir.with_child('static')
FAVICON_PATH = STATIC_DIR.with_child('favicon.png')

site = flask.Flask(
    __name__,
    template_folder=TEMPLATE_DIR.absolute_path,
    static_folder=STATIC_DIR.absolute_path,
)
site.config.update(
    SEND_FILE_MAX_AGE_DEFAULT=180,
    TEMPLATES_AUTO_RELOAD=True,
)
site.jinja_env.add_extension('jinja2.ext.do')
site.jinja_env.trim_blocks = True
site.jinja_env.lstrip_blocks = True
jinja_filters.register_all(site)
site.debug = True
site.localhost_only = False

####################################################################################################

@site.before_request
def before_request():
    ip = request.remote_addr
    request.is_localhost = ip == '127.0.0.1'
    if site.localhost_only and not request.is_localhost:
        flask.abort(403)

gzip_minimum_size = 500
gzip_maximum_size = 5 * 2**20
gzip_level = 3
@site.after_request
def after_request(response):
    '''
    Thank you close.io.
    https://github.com/closeio/Flask-gzip
    '''
    accept_encoding = request.headers.get('Accept-Encoding', '')

    bail = False
    bail = bail or response.status_code < 200
    bail = bail or response.status_code >= 300
    bail = bail or response.direct_passthrough
    bail = bail or int(response.headers.get('Content-Length', 0)) > gzip_maximum_size
    bail = bail or len(response.get_data()) < gzip_minimum_size
    bail = bail or 'gzip' not in accept_encoding.lower()
    bail = bail or 'Content-Encoding' in response.headers

    if bail:
        return response

    gzip_buffer = io.BytesIO()
    gzip_file = gzip.GzipFile(mode='wb', compresslevel=gzip_level, fileobj=gzip_buffer)
    gzip_file.write(response.get_data())
    gzip_file.close()
    response.set_data(gzip_buffer.getvalue())
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(response.get_data())

    return response

####################################################################################################
####################################################################################################
####################################################################################################
####################################################################################################

def init_ycdldb(*args, **kwargs):
    global ycdldb
    ycdldb = ycdl.ycdldb.YCDLDB(*args, **kwargs)

def refresher_thread(rate):
    while True:
        time.sleep(rate)
        print('Starting refresh job.')
        thread_kwargs = {'force': False, 'skip_failures': True}
        refresh_job = threading.Thread(
            target=ycdldb.refresh_all_channels,
            kwargs=thread_kwargs,
            daemon=True,
        )
        refresh_job.start()

def start_refresher_thread(rate):
    print(f'Starting refresher thread, once per {rate} seconds.')
    refresher = threading.Thread(target=refresher_thread, args=[rate], daemon=True)
    refresher.start()
