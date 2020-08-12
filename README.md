Youtube Channel Downloader
==========================

YoutubeChannelDownloader creates an SQLite3 database of Youtube channels and their videos, and serves it out of a web server.

## YCDL solves three main problems:

### Metadata archive

The database acts as a permanent archive of video metadata including title, description, duration, view count, and more. Even if a video or channel is deleted from Youtube, you will still have this information. Perfect for never losing track of unlisted videos, too.

The thumbnails, however, are not stored in the database, but you can use `utilities\download_thumbnails.py` to download them.

Note: At this time, refreshing a channel in YCDL will update video titles, descriptions, and view counts with their current values. If you refresh a channel after they have changed their video's title or description you will lose the previous value.

### Easily watch every video on the channel

When I discover a channel, I like to watch through their videos over the course of weeks or months. Within Youtube's own interface, it becomes difficult to know which videos I've watched and which ones I haven't. Scrolling through all of a channel's videos is tough especially if there are many.

In YCDL, videos start off as pending and you can mark them as ignore or download, so the pending page is always your "to-watch" list.

On my Youtube subscription box, I would often press the "hide" button on videos only to find them come back a few days later, and hiding live broadcasts was never reliable. YCDL makes watching my subscriptions much easier.

### Send video IDs to youtube-dl

YCDL does not perform the downloading of videos itself. When you click on the download button, it will create an empty file called `xxxxxxxxxxx.ytqueue` in the directory specified by the `ycdl.json` config file. You can send this ID into youtube-dl in your preferred way.

## Features

- Web interface with video embeds
- "Sub-box" page where newest videos from all channels are listed in order
- Sort videos by date, duration, views, or random
- Background thread will refresh channels over time
- Automark channels as ignore or download

## Your API key

You are responsible for your own `bot.py` file, with a function `get_youtube_key`, called with no arguments, that returns a Youtube API key.

1. Go to https://console.developers.google.com/.
2. Create a project using the menu in the upper left.
3. From the project's dashboard, click "Enable APIs and Services".
4. Search for and choose the latest YouTube Data API.
5. On the left bar, click "Credentials".
6. Click "Create credentials" and choose "API key". In my experience they all start with "AIzaSy".
7. Return this value from `get_youtube_key` however you deem fit.

## Screenshots

![2020-04-04_15-27-15](https://user-images.githubusercontent.com/7299570/78462830-ca4f9900-768a-11ea-98c9-a4e622d3da62.png)

![2020-04-04_15-29-25](https://user-images.githubusercontent.com/7299570/78462831-cb80c600-768a-11ea-9ff0-517c231e0469.png)

![2020-04-04_15-36-05](https://user-images.githubusercontent.com/7299570/78462832-cb80c600-768a-11ea-9b86-529e1a22616c.png)

![2020-04-04_15-36-10](https://user-images.githubusercontent.com/7299570/78462833-cc195c80-768a-11ea-9cac-208b8c79cad9.png)

![2020-04-04_15-40-27](https://user-images.githubusercontent.com/7299570/78462834-cc195c80-768a-11ea-942b-e89a3dabe64d.png)

## To do list

- Keep permanent record of titles and descriptions.
- Progress indicator for channel refresh.
