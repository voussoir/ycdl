import os
import traceback

from voussoirkit import downloady

import ycdl

ycdldb = ycdl.ycdldb.YCDLDB()

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
