import logging
logging.basicConfig(level=logging.WARNING)

import bot3 as bot
import os
import traceback
import ycdl
from voussoirkit import downloady


youtube_core = ycdl.ytapi.Youtube(bot.get_youtube_key())
ycdldb = ycdl.ycdldb.YCDLDB(youtube_core)

DIRECTORY = '.\\youtube thumbnails'

videos = ycdldb.get_videos()
for video in videos:
    try:
        thumbnail_path = os.path.join(DIRECTORY, video.id) + '.jpg'
        if os.path.exists(thumbnail_path):
            continue
        result = downloady.download_file(video.thumbnail, thumbnail_path)
        print(result)
    except Exception as e:
        traceback.print_exc()
