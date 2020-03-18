'''
Run `python -i ycdl_repl.py to get an interpreter
session with these variables preloaded.
'''

import bot
import ycdl

youtube = ycdl.ytapi.Youtube(bot.get_youtube_key())
Y = ycdl.ycdldb.YCDLDB(youtube)
