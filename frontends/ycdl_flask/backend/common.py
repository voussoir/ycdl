'''
Do not execute this file directly.
Use ycdl_flask_dev.py or ycdl_flask_prod.py.
'''
import flask; from flask import request
import functools
import threading
import time
import traceback

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

site.route = flasktools.decorate_and_route(
    flask_app=site,
    decorators=[
        flasktools.ensure_response_type,
        functools.partial(
            flasktools.give_theme_cookie,
            cookie_name='ycdl_theme',
            default_theme='slate',
        ),
    ],
)

def render_template(request, template_name, **kwargs):
    theme = request.cookies.get('ycdl_theme', None)

    response = flask.render_template(
        template_name,
        request=request,
        theme=theme,
        **kwargs,
    )
    return response

####################################################################################################

# These functions will be called by the launcher, flask_dev, flask_prod.

def init_ycdldb(*args, **kwargs):
    global ycdldb
    ycdldb = ycdl.ycdldb.YCDLDB.closest_ycdldb(*args, **kwargs)

def refresh_all_channels():
    with ycdldb.transaction:
        ycdldb.refresh_all_channels(force=False, skip_failures=True)

def refresher_thread(rate):
    global last_refresh
    while True:
        # If the user pressed the refresh button, the thread will wake from
        # sleep and find that it should go back to sleep for a little longer.
        while True:
            next_refresh = last_refresh + rate
            wait = next_refresh - time.time()
            if wait <= 0:
                break
            time.sleep(wait)

        log.info('Starting refresh job.')
        refresh_job = threading.Thread(
            target=refresh_all_channels,
            daemon=True,
        )
        refresh_job.start()
        last_refresh = time.time()

def ignore_shorts_thread(rate):
    last_commit_id = None
    while True:
        if ycdldb.last_commit_id == last_commit_id:
            # log.debug('Sleeping again due to no new commits.')
            time.sleep(5 * rate)
            continue

        last_commit_id = ycdldb.last_commit_id

        log.info('Starting shorts job.')
        videos = ycdldb.get_videos_by_sql('''
        SELECT * FROM videos
        LEFT JOIN channels ON channels.id = videos.author_id
        WHERE is_shorts IS NULL AND duration < 182 AND state = "pending" AND channels.ignore_shorts = 1
        ORDER BY published DESC
        LIMIT 10
        ''')
        videos = list(videos)
        if len(videos) == 0:
            time.sleep(rate)
            continue

        log.debug('Checking %d videos for shorts.', len(videos))

        with ycdldb.transaction:
            for video in videos:
                try:
                    is_shorts = ycdl.ytapi.video_is_shorts(video.id)
                except Exception as exc:
                    log.warning(traceback.format_exc())
                    continue
                video.is_shorts = is_shorts
                pairs = {'id': video.id, 'is_shorts': int(is_shorts)}
                if is_shorts:
                    pairs['state'] = 'ignored'
                    video.state = 'ignored'
                ycdldb.update(table=ycdl.objects.Video, pairs=pairs, where_key='id')
        time.sleep(rate)

def start_refresher_thread(rate):
    log.info('Starting refresher thread, once per %d seconds.', rate)
    refresher = threading.Thread(target=refresher_thread, args=[rate], daemon=True)
    refresher.start()

    shorts_killer = threading.Thread(target=ignore_shorts_thread, args=[60], daemon=True)
    shorts_killer.start()
