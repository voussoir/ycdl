import flask; from flask import request

from voussoirkit import flasktools
from voussoirkit import stringtools

import ycdl

from .. import common

site = common.site

@flasktools.required_fields(['video_ids', 'state'], forbid_whitespace=True)
@site.route('/mark_video_state', methods=['POST'])
def post_mark_video_state():
    video_ids = request.form['video_ids']
    video_ids = stringtools.comma_space_split(video_ids)
    state = request.form['state']

    try:
        videos = [common.ycdldb.get_video(id) for id in video_ids]
    except ycdl.exceptions.NoSuchVideo as exc:
        return flasktools.json_response(exc.jsonify(), status=404)

    try:
        with common.ycdldb.transaction:
            for video in videos:
                video.mark_state(state)
    except ycdl.exceptions.InvalidVideoState as exc:
        common.ycdldb.rollback()
        return flasktools.json_response(exc.jsonify(), status=400)

    return flasktools.json_response({'video_ids': video_ids, 'state': state})

@flasktools.required_fields(['video_ids'], forbid_whitespace=True)
@site.route('/start_download', methods=['POST'])
def post_start_download():
    video_ids = request.form['video_ids']
    video_ids = stringtools.comma_space_split(video_ids)

    try:
        videos = [common.ycdldb.get_video(id) for id in video_ids]
    except ycdl.exceptions.NoSuchVideo as exc:
        return flasktools.json_response(exc.jsonify(), status=404)

    with common.ycdldb.transaction:
        for video in videos:
            common.ycdldb.download_video(video)

    return flasktools.json_response({'video_ids': video_ids, 'state': 'downloaded'})
