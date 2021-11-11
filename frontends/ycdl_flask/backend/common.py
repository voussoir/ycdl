'''
Do not execute this file directly.
Use ycdl_flask_dev.py or ycdl_flask_prod.py.
'''
import flask; from flask import request
import threading
import time

from voussoirkit import flasktools
from voussoirkit import pathclass
from voussoirkit import vlogging

log = vlogging.getLogger(__name__)

import ycdl

from . import jinja_filters

# Flask init #######################################################################################

# __file__ = .../ycdl_flask/backend/common.py
# root_dir = .../ycdl_flask
root_dir = pathclass.Path(__file__).parent.parent

TEMPLATE_DIR = root_dir.with_child('templates')
STATIC_DIR = root_dir.with_child('static')
FAVICON_PATH = STATIC_DIR.with_child('favicon.png')
BROWSER_CACHE_DURATION = 180

site = flask.Flask(
    __name__,
    template_folder=TEMPLATE_DIR.absolute_path,
    static_folder=STATIC_DIR.absolute_path,
)
site.config.update(
    SEND_FILE_MAX_AGE_DEFAULT=BROWSER_CACHE_DURATION,
    TEMPLATES_AUTO_RELOAD=True,
)
site.jinja_env.add_extension('jinja2.ext.do')
site.jinja_env.trim_blocks = True
site.jinja_env.lstrip_blocks = True
jinja_filters.register_all(site)
site.debug = True
site.localhost_only = False

# This timestamp indicates the last time that all channels got a refresh.
# If the user clicks the "refresh all channels" button, we can update this
# timestamp so that the background refresher thread knows that it can wait
# a little longer.
# I chose the initial value as time.time() instead of 0 because when I'm
# testing the server and restarting it often, I don't want it making a bunch of
# network requests and/or burning API calls every time.
last_refresh = time.time()

# Request decorators ###############################################################################

@site.before_request
def before_request():
    request.is_localhost = (request.remote_addr == '127.0.0.1')
    if site.localhost_only and not request.is_localhost:
        flask.abort(403)

@site.after_request
def after_request(response):
    response = flasktools.gzip_response(request, response)
    return response

####################################################################################################

# These functions will be called by the launcher, flask_dev, flask_prod.

def init_ycdldb(*args, **kwargs):
    global ycdldb
    ycdldb = ycdl.ycdldb.YCDLDB.closest_ycdldb(*args, **kwargs)

def refresher_thread(rate):
    global last_refresh
    while True:
        next_refresh = last_refresh + rate
        wait = next_refresh - time.time()
        if wait > 0:
            time.sleep(wait)
            continue
        log.info('Starting refresh job.')
        thread_kwargs = {'force': False, 'skip_failures': True}
        refresh_job = threading.Thread(
            target=ycdldb.refresh_all_channels,
            kwargs=thread_kwargs,
            daemon=True,
        )
        refresh_job.start()
        last_refresh = time.time()

def start_refresher_thread(rate):
    log.info('Starting refresher thread, once per %d seconds.', rate)
    refresher = threading.Thread(target=refresher_thread, args=[rate], daemon=True)
    refresher.start()
