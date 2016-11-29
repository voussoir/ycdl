'''
Run `python -i ycdl_easy.py to get an interpreter
session with these variables preloaded.
'''

import bot
import ycdl
import ytapi

youtube_core = ytapi.Youtube(bot.YOUTUBE_KEY)
youtube = ycdl.YCDL(youtube_core)
