import flask; from flask import request

from .. import common

site = common.site

@site.route('/')
def root():
    return common.render_template(request, 'root.html')

@site.route('/favicon.ico')
@site.route('/favicon.png')
def favicon():
    return flask.send_file(common.FAVICON_PATH.absolute_path)
