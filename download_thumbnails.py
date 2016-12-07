import os
import ycdl_easy
from voussoirkit import downloady

DIRECTORY = 'C:\\users\\owner\\youtube thumbnails'

videos = ycdl_easy.youtube.get_videos()
for video in videos:
    thumbnail_path = os.path.join(DIRECTORY, video['id']) + '.jpg'
    if os.path.exists(thumbnail_path):
        continue
    result = downloady.download_file(video['thumbnail'], thumbnail_path)
    print(result)
