'''
Run `python -i ycdl_repl.py to get an interpreter
session with these variables preloaded.
'''
import logging
logging.basicConfig()
logging.getLogger('ycdl').setLevel(logging.DEBUG)

import ycdl
import youtube_credentials

youtube = ycdl.ytapi.Youtube(youtube_credentials.get_youtube_key())
Y = ycdl.ycdldb.YCDLDB(youtube)
