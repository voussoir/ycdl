import datetime
import flask; from flask import request
import traceback

import ycdl

from . import common
from . import jsonify

site = common.site

@site.route('/')
def root():
    return flask.render_template('root.html')

@site.route('/favicon.ico')
@site.route('/favicon.png')
def favicon():
    return flask.send_file(common.FAVICON_PATH.absolute_path)

@site.route('/channels')
def get_channels():
    channels = common.ycdldb.get_channels()
    return flask.render_template('channels.html', channels=channels)

@site.route('/videos')
@site.route('/watch')
@site.route('/videos/<download_filter>')
@site.route('/channel/<channel_id>')
@site.route('/channel/<channel_id>/<download_filter>')
def get_channel(channel_id=None, download_filter=None):
    if channel_id is not None:
        try:
            common.ycdldb.add_channel(channel_id)
        except Exception:
            traceback.print_exc()
        channel = common.ycdldb.get_channel(channel_id)
    else:
        channel = None

    orderby = request.args.get('orderby', None)

    video_id = request.args.get('v', '')
    if video_id:
        common.ycdldb.insert_video(video_id)
        videos = [common.ycdldb.get_video(video_id)]
    else:
        videos = common.ycdldb.get_videos(
            channel_id=channel_id,
            download_filter=download_filter,
            orderby=orderby,
        )

    search_terms = request.args.get('q', '').lower().strip().replace('+', ' ').split()
    if search_terms:
        videos = [v for v in videos if all(term in v.title.lower() for term in search_terms)]

    limit = request.args.get('limit', None)
    if limit is not None:
        try:
            limit = int(limit)
            videos = videos[:limit]
        except ValueError:
            pass

    for video in videos:
        published = video.published
        published = datetime.datetime.utcfromtimestamp(published)
        published = published.strftime('%Y %m %d')
        video._published_str = published

    all_states = common.ycdldb.get_all_states()

    return flask.render_template(
        'channel.html',
        all_states=all_states,
        channel=channel,
        download_filter=download_filter,
        query_string='?' + request.query_string.decode('utf-8'),
        videos=videos,
    )

@site.route('/mark_video_state', methods=['POST'])
def post_mark_video_state():
    if 'video_ids' not in request.form or 'state' not in request.form:
        flask.abort(400)
    video_ids = request.form['video_ids']
    state = request.form['state']
    try:
        video_ids = video_ids.split(',')
        for video_id in video_ids:
            video = common.ycdldb.get_video(video_id)
            video.mark_state(state, commit=False)
        common.ycdldb.sql.commit()

    except ycdl.exceptions.NoSuchVideo:
        common.ycdldb.rollback()
        traceback.print_exc()
        flask.abort(404)

    except ycdl.exceptions.InvalidVideoState:
        common.ycdldb.rollback()
        flask.abort(400)

    return jsonify.make_json_response({'video_ids': video_ids, 'state': state})

@site.route('/refresh_all_channels', methods=['POST'])
def post_refresh_all_channels():
    force = request.form.get('force', False)
    force = ycdl.helpers.truthystring(force)
    common.ycdldb.refresh_all_channels(force=force)
    return jsonify.make_json_response({})

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
            channel_id = common.ycdldb.youtube.get_user_id(username=channel_id)
        except IndexError:
            flask.abort(404)

    force = request.form.get('force', False)
    force = ycdl.helpers.truthystring(force)
    channel = common.ycdldb.add_channel(channel_id, commit=False)
    channel.refresh(force=force)
    return jsonify.make_json_response({})

@site.route('/start_download', methods=['POST'])
def post_start_download():
    if 'video_ids' not in request.form:
        flask.abort(400)
    video_ids = request.form['video_ids']
    try:
        video_ids = video_ids.split(',')
        for video_id in video_ids:
            common.ycdldb.download_video(video_id, commit=False)
        common.ycdldb.sql.commit()

    except ycdl.ytapi.VideoNotFound:
        common.ycdldb.rollback()
        flask.abort(404)

    return jsonify.make_json_response({'video_ids': video_ids, 'state': 'downloaded'})
