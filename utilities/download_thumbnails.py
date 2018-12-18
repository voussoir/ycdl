import logging
logging.basicConfig(level=logging.WARNING)

import bot3 as bot
import os
import traceback
import ycdl
import ycdl_repl
from voussoirkit import downloady


youtube_core = ycdl.ytapi.Youtube(bot.YOUTUBE_KEY)
youtube = ycdl.YCDL(youtube_core)

DIRECTORY = '.\\youtube thumbnails'

videos = ycdl_repl.youtube.get_videos()
for video in videos:
    try:
        thumbnail_path = os.path.join(DIRECTORY, video['id']) + '.jpg'
        if os.path.exists(thumbnail_path):
            continue
        result = downloady.download_file(video['thumbnail'], thumbnail_path)
        print(result)
    except Exception as e:
        traceback.print_exc()
