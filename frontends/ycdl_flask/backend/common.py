'''
Do not execute this file directly.
Use ycdl_flask_dev.py or ycdl_flask_prod.py.
'''
import flask; from flask import request
import threading
import time

from voussoirkit import flasktools
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

# Request decorators ###############################################################################

@site.before_request
def before_request():
    ip = request.remote_addr
    request.is_localhost = ip == '127.0.0.1'
    if site.localhost_only and not request.is_localhost:
        flask.abort(403)

@site.after_request
def after_request(response):
    response = flasktools.gzip_response(request, response)
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
