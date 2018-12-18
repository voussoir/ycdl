'''
Do not execute this file directly.
Use ycdl_launch.py to start the server with gevent.
'''
import logging
logging.getLogger('googleapicliet.discovery_cache').setLevel(logging.ERROR)

import datetime
import flask
from flask import request
import json
import mimetypes
import os
import traceback

import bot
import ycdl

from voussoirkit import pathclass

from . import jinja_filters

root_dir = pathclass.Path(__file__).parent.parent

TEMPLATE_DIR = root_dir.with_child('templates')
STATIC_DIR = root_dir.with_child('static')
FAVICON_PATH = STATIC_DIR.with_child('favicon.png')

youtube_core = ycdl.ytapi.Youtube(bot.YOUTUBE_KEY)
youtube = ycdl.YCDL(youtube_core)

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

def make_json_response(j, *args, **kwargs):
    dumped = json.dumps(j)
    response = flask.Response(dumped, *args, **kwargs)
    response.headers['Content-Type'] = 'application/json;charset=utf-8'
    return response

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

@site.route('/')
def root():
    return flask.render_template('root.html')

@site.route('/favicon.ico')
@site.route('/favicon.png')
def favicon():
    return flask.send_file(FAVICON_PATH.absolute_path)


@site.route('/channels')
def get_channels():
    channels = youtube.get_channels()
    for channel in channels:
        channel['has_pending'] = youtube.channel_has_pending(channel['id'])
    return flask.render_template('channels.html', channels=channels)

@site.route('/videos')
@site.route('/watch')
@site.route('/videos/<download_filter>')
@site.route('/channel/<channel_id>')
@site.route('/channel/<channel_id>/<download_filter>')
def get_channel(channel_id=None, download_filter=None):
    if channel_id is not None:
        try:
            youtube.add_channel(channel_id)
        except Exception:
            traceback.print_exc()
        channel = youtube.get_channel(channel_id)
    else:
        channel = None

    videos = youtube.get_videos(channel_id=channel_id, download_filter=download_filter)

    search_terms = request.args.get('q', '').lower().strip().replace('+', ' ').split()
    if search_terms:
        videos = [v for v in videos if all(term in v['title'].lower() for term in search_terms)]

    video_id = request.args.get('v', '')
    if video_id:
        youtube.insert_video(video_id)
        videos = [youtube.get_video(video_id)]

    limit = request.args.get('limit', None)
    if limit is not None:
        try:
            limit = int(limit)
            videos = videos[:limit]
        except ValueError:
            pass

    for video in videos:
        published = video['published']
        published = datetime.datetime.utcfromtimestamp(published)
        published = published.strftime('%Y %m %d')
        video['_published_str'] = published
    return flask.render_template(
        'channel.html',
        channel=channel,
        videos=videos,
        query_string='?' + request.query_string.decode('utf-8'),
    )

@site.route('/mark_video_state', methods=['POST'])
def post_mark_video_state():
    if 'video_id' not in request.form or 'state' not in request.form:
        flask.abort(400)
    video_id = request.form['video_id']
    state = request.form['state']
    try:
        youtube.mark_video_state(video_id, state)

    except ycdl.NoSuchVideo:
        traceback.print_exc()
        flask.abort(404)

    except ycdl.InvalidVideoState:
        flask.abort(400)

    return make_json_response({'video_id': video_id, 'state': state})

@site.route('/refresh_all_channels', methods=['POST'])
def post_refresh_all_channels():
    force = request.form.get('force', False)
    force = ycdl.helpers.truthystring(force)
    youtube.refresh_all_channels(force=force)
    return make_json_response({})

@site.route('/refresh_channel', methods=['POST'])
def post_refresh_channel():
    if 'channel_id' not in request.form:
        flask.abort(400)
    channel_id = request.form['channel_id']
    channel_id = channel_id.strip()
    if not channel_id:
        flask.abort(400)
    if not (len(channel_id) == 24 and channel_id.startswith('UC')):
        # It seems they have given us a username instead.
        try:
            channel_id = youtube.youtube.get_user_id(username=channel_id)
        except IndexError:
            flask.abort(404)

    force = request.form.get('force', False)
    force = ycdl.helpers.truthystring(force)
    youtube.refresh_channel(channel_id, force=force)
    return make_json_response({})

@site.route('/start_download', methods=['POST'])
def post_start_download():
    if 'video_id' not in request.form:
        flask.abort(400)
    video_id = request.form['video_id']
    try:
        youtube.download_video(video_id)
    except ycdl.ytapi.VideoNotFound:
        flask.abort(404)

    return make_json_response({'video_id': video_id, 'state': 'downloaded'})

if __name__ == '__main__':
    pass
