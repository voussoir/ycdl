import flask; from flask import request
import itertools
import time

from voussoirkit import flasktools
from voussoirkit import pathclass
from voussoirkit import stringtools

import ycdl

from .. import common

site = common.site

def _get_or_insert_video(video_id):
    try:
        video = common.ycdldb.get_video(video_id)
    except ycdl.exceptions.NoSuchVideo:
        video = common.ycdldb.insert_video(video_id)['video']
    return video

@site.route('/all_channels.json')
def get_all_channel_names():
    all_channels = {channel.id: channel.name for channel in common.ycdldb.get_channels()}
    response = {'channels': all_channels}
    return flasktools.json_response(response)

@site.route('/channels')
def get_channels():
    channels = common.ycdldb.get_channels()
    return flask.render_template('channels.html', channels=channels)

def _render_videos_listing(videos, channel, state, orderby):
    search_terms = request.args.get('q', '').lower().strip().replace('+', ' ').split()
    if search_terms:
        lowered = ((video, video.title.lower()) for video in videos)
        videos = (
            video for (video, title) in lowered
            if all(term in title for term in search_terms)
        )

    limit = request.args.get('limit', None)
    if limit is not None:
        try:
            limit = int(limit)
            videos = itertools.islice(videos, limit)
        except ValueError:
            pass

    if not isinstance(videos, list):
        videos = list(videos)

    all_states = common.ycdldb.get_all_states()

    return flask.render_template(
        'channel.html',
        all_states=all_states,
        channel=channel,
        state=state,
        orderby=orderby,
        videos=videos,
    )

@site.route('/channel/<channel_id>')
@site.route('/channel/<channel_id>/<state>')
def get_channel(channel_id, state=None):
    try:
        channel = common.ycdldb.add_channel(channel_id, commit=True)
    except ycdl.ytapi.ChannelNotFound:
        flask.abort(404)

    orderby = request.args.get('orderby', None)

    videos = common.ycdldb.get_videos(
        channel_id=channel.id,
        orderby=orderby,
        state=state,
    )
    return _render_videos_listing(videos, channel=channel, state=state, orderby=orderby)

@site.route('/videos')
@site.route('/videos/<state>')
def get_videos(state=None):
    orderby = request.args.get('orderby', None)

    videos = common.ycdldb.get_videos(
        orderby=orderby,
        state=state,
    )
    return _render_videos_listing(videos, channel=None, state=state, orderby=orderby)

@site.route('/watch')
def get_watch():
    video_id = request.args.get('v', '')
    if not video_id:
        return flask.redirect('/')

    try:
        video = _get_or_insert_video(video_id)
    except ycdl.ytapi.VideoNotFound:
        flask.abort(404)

    videos = [video]
    return _render_videos_listing(videos, channel=None, state=None, orderby=None)

@flasktools.required_fields(['channel_id'], forbid_whitespace=True)
@site.route('/add_channel', methods=['POST'])
def post_add_channel():
    channel_id = request.form['channel_id']
    if not (len(channel_id) == 24 and channel_id.startswith('UC')):
        # It seems they have given us a username instead.
        try:
            channel_id = common.ycdldb.youtube.get_user_id(username=channel_id)
        except ycdl.ytapi.ChannelNotFound:
            return flasktools.json_response({}, status=404)

    channel = common.ycdldb.add_channel(channel_id, get_videos=True, commit=True)
    return flasktools.json_response(channel.jsonify())

@site.route('/channel/<channel_id>/delete', methods=['POST'])
def post_delete_channel(channel_id):
    try:
        channel = common.ycdldb.get_channel(channel_id)
    except ycdl.exceptions.NoSuchChannel as exc:
        return flasktools.json_response(exc.jsonify(), status=404)

    channel.delete(commit=True)
    response = {'id': channel.id, 'deleted': channel.deleted}
    return flasktools.json_response(response)

@site.route('/channel/<channel_id>/refresh', methods=['POST'])
def post_refresh_channel(channel_id):
    force = request.form.get('force', False)
    force = stringtools.truthystring(force, False)
    try:
        channel = common.ycdldb.get_channel(channel_id)
    except ycdl.exceptions.NoSuchChannel as exc:
        return flasktools.json_response(exc.jsonify(), status=404)

    channel.refresh(force=force, commit=True)
    return flasktools.json_response(channel.jsonify())

@site.route('/refresh_all_channels', methods=['POST'])
def post_refresh_all_channels():
    force = request.form.get('force', False)
    force = stringtools.truthystring(force, False)
    common.ycdldb.refresh_all_channels(force=force, skip_failures=True, commit=True)
    common.last_refresh = time.time()
    return flasktools.json_response({})

@flasktools.required_fields(['state'], forbid_whitespace=True)
@site.route('/channel/<channel_id>/set_automark', methods=['POST'])
def post_set_automark(channel_id):
    state = request.form['state']
    channel = common.ycdldb.get_channel(channel_id)

    try:
        channel.set_automark(state, commit=True)
    except ycdl.exceptions.InvalidVideoState as exc:
        return flasktools.json_response(exc.jsonify(), status=400)

    response = {'id': channel.id, 'automark': channel.automark}
    return flasktools.json_response(response)

@flasktools.required_fields(['autorefresh'], forbid_whitespace=True)
@site.route('/channel/<channel_id>/set_autorefresh', methods=['POST'])
def post_set_autorefresh(channel_id):
    autorefresh = request.form['autorefresh']
    channel = common.ycdldb.get_channel(channel_id)

    try:
        autorefresh = stringtools.truthystring(autorefresh)
        channel.set_autorefresh(autorefresh, commit=True)
    except (ValueError, TypeError):
        flask.abort(400)

    response = {'id': channel.id, 'autorefresh': channel.autorefresh}
    return flasktools.json_response(response)

@flasktools.required_fields(['download_directory'], forbid_whitespace=False)
@site.route('/channel/<channel_id>/set_download_directory', methods=['POST'])
def post_set_download_directory(channel_id):
    download_directory = request.form['download_directory']
    channel = common.ycdldb.get_channel(channel_id)

    try:
        channel.set_download_directory(download_directory, commit=True)
    except pathclass.NotDirectory:
        exc = {
            'error_type': 'NOT_DIRECTORY',
            'error_message': f'"{download_directory}" is not a directory.',
        }
        return flasktools.json_response(exc, status=400)

    abspath = channel.download_directory.absolute_path if channel.download_directory else None
    response = {'id': channel.id, 'download_directory': abspath}
    return flasktools.json_response(response)

@flasktools.required_fields(['name'], forbid_whitespace=False)
@site.route('/channel/<channel_id>/set_name', methods=['POST'])
def post_set_name(channel_id):
    name = request.form['name']
    channel = common.ycdldb.get_channel(channel_id)

    channel.set_name(name, commit=True)

    response = {'id': channel.id, 'name': channel.name}
    return flasktools.json_response(response)

@flasktools.required_fields(['extension'], forbid_whitespace=False)
@site.route('/channel/<channel_id>/set_queuefile_extension', methods=['POST'])
def post_set_queuefile_extension(channel_id):
    extension = request.form['extension']
    channel = common.ycdldb.get_channel(channel_id)

    channel.set_queuefile_extension(extension, commit=True)

    response = {'id': channel.id, 'queuefile_extension': channel.queuefile_extension}
    return flasktools.json_response(response)
