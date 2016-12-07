'''
I was having trouble making my Flask server perform the youtube-dl without
clogging up the other site activities. So instead I'll just have the server
export ytqueue files, which this script will download as a separate process.

Rather than maintaining a text file or database of IDs to be downloaded,
I'm fine with creating each ID as a file and letting the filesystem act
as the to-do list.
'''
import os
import time

YOUTUBE_DL = 'youtube-dlw https://www.youtube.com/watch?v={id}'

while True:
    print(time.strftime('%H:%M:%S'), 'Looking for files.')
    queue = [f for f in os.listdir() if f.endswith('.ytqueue')]
    for filename in queue:
        yt_id = filename.split('.')[0]
        command = YOUTUBE_DL.format(id=yt_id)
        exit_code = os.system(command)
        if exit_code == 0:
            os.remove(filename)
    time.sleep(10)
