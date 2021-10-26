import flask; from flask import request

from voussoirkit import flasktools

import ycdl

from .. import common

site = common.site

@flasktools.required_fields(['video_ids', 'state'], forbid_whitespace=True)
@site.route('/mark_video_state', methods=['POST'])
def post_mark_video_state():
    video_ids = request.form['video_ids']
    state = request.form['state']
    try:
        video_ids = video_ids.split(',')
        for video_id in video_ids:
            video = common.ycdldb.get_video(video_id)
            video.mark_state(state, commit=False)
        common.ycdldb.commit()

    except ycdl.exceptions.NoSuchVideo as exc:
        common.ycdldb.rollback()
        return flasktools.json_response(exc.jsonify(), status=404)

    except ycdl.exceptions.InvalidVideoState as exc:
        common.ycdldb.rollback()
        return flasktools.json_response(exc.jsonify(), status=400)

    return flasktools.json_response({'video_ids': video_ids, 'state': state})

@flasktools.required_fields(['video_ids'], forbid_whitespace=True)
@site.route('/start_download', methods=['POST'])
def post_start_download():
    video_ids = request.form['video_ids']
    try:
        video_ids = video_ids.split(',')
        for video_id in video_ids:
            common.ycdldb.download_video(video_id, commit=False)
        common.ycdldb.commit()

    except ycdl.ytapi.VideoNotFound:
        common.ycdldb.rollback()
        flask.abort(404)

    return flasktools.json_response({'video_ids': video_ids, 'state': 'downloaded'})
