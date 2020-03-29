'''
Do not execute this file directly.
Use ycdl_launch.py to start the server with gevent.
'''
import logging
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

import flask; from flask import request
import mimetypes
import os
import threading
import time

from voussoirkit import pathclass

import bot
import ycdl

from . import jinja_filters

root_dir = pathclass.Path(__file__).parent.parent

TEMPLATE_DIR = root_dir.with_child('templates')
STATIC_DIR = root_dir.with_child('static')
FAVICON_PATH = STATIC_DIR.with_child('favicon.png')

youtube_core = ycdl.ytapi.Youtube(bot.get_youtube_key())
ycdldb = ycdl.ycdldb.YCDLDB(youtube_core)

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
site.jinja_env.filters['seconds_to_hms'] = jinja_filters.seconds_to_hms
site.debug = True

####################################################################################################
####################################################################################################
####################################################################################################
####################################################################################################

def send_file(filepath):
    '''
    Range-enabled file sending.
    '''
    try:
        file_size = os.path.getsize(filepath)
    except FileNotFoundError:
        flask.abort(404)

    outgoing_headers = {}
    mimetype = mimetypes.guess_type(filepath)[0]
    if mimetype is not None:
        if 'text/' in mimetype:
            mimetype += '; charset=utf-8'
        outgoing_headers['Content-Type'] = mimetype

    if 'range' in request.headers:
        desired_range = request.headers['range'].lower()
        desired_range = desired_range.split('bytes=')[-1]

        int_helper = lambda x: int(x) if x.isdigit() else None
        if '-' in desired_range:
            (desired_min, desired_max) = desired_range.split('-')
            range_min = int_helper(desired_min)
            range_max = int_helper(desired_max)
        else:
            range_min = int_helper(desired_range)

        if range_min is None:
            range_min = 0
        if range_max is None:
            range_max = file_size

        # because ranges are 0-indexed
        range_max = min(range_max, file_size - 1)
        range_min = max(range_min, 0)

        range_header = 'bytes {min}-{max}/{outof}'.format(
            min=range_min,
            max=range_max,
            outof=file_size,
        )
        outgoing_headers['Content-Range'] = range_header
        status = 206
    else:
        range_max = file_size - 1
        range_min = 0
        status = 200

    outgoing_headers['Accept-Ranges'] = 'bytes'
    outgoing_headers['Content-Length'] = (range_max - range_min) + 1

    if request.method == 'HEAD':
        outgoing_data = bytes()
    else:
        outgoing_data = ycdl.helpers.read_filebytes(filepath, range_min=range_min, range_max=range_max)

    response = flask.Response(
        outgoing_data,
        status=status,
        headers=outgoing_headers,
    )
    return response

####################################################################################################
####################################################################################################
####################################################################################################
####################################################################################################

def refresher_thread(rate):
    while True:
        time.sleep(rate)
        print('Starting refresh job.')
        thread_kwargs = {'force': False, 'skip_failures': True}
        refresh_job = threading.Thread(target=ycdldb.refresh_all_channels, kwargs=thread_kwargs, daemon=True)
        refresh_job.start()

def start_refresher_thread(rate):
    print(f'Starting refresher thread, once per {rate} seconds.')
    refresher = threading.Thread(target=refresher_thread, args=[rate], daemon=True)
    refresher.start()
