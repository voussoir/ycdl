'''
This file is the WSGI entrypoint for remote / production use.
Note that YCDL currenty features no authentication, so using it remotely without
another kind of access control is probably a bad idea!

If you are using Gunicorn, for example:
gunicorn ycdl_flask_prod:site --bind "0.0.0.0:PORT" --access-logfile "-"
'''
import werkzeug.middleware.proxy_fix

import bot
import ycdl

import backend

backend.site.wsgi_app = werkzeug.middleware.proxy_fix.ProxyFix(backend.site.wsgi_app)

site = backend.site
site.debug = False

# NOTE: Consider adding a local .json config file.
youtube_core = ycdl.ytapi.Youtube(bot.get_youtube_key())
backend.common.init_ycdldb(youtube_core, create=False)
backend.common.start_refresher_thread(86400)
