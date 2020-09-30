'''
This file is the WSGI entrypoint for remote / production use.

If you are using Gunicorn, for example:
gunicorn ycdl_flask_prod:site --bind "0.0.0.0:PORT" --access-logfile "-"
'''
import werkzeug.middleware.proxy_fix

import bot
import ycdl

import backend

backend.site.wsgi_app = werkzeug.middleware.proxy_fix.ProxyFix(backend.site.wsgi_app)

site = backend.site

# NOTE: Consider adding a local .json config file.
youtube_core = ycdl.ytapi.Youtube(bot.get_youtube_key())
backend.common.init_ycdldb(youtube_core, create=False)
backend.common.start_refresher_thread(86400)
