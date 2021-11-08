YCDL - The Youtube Channel Downloader
=====================================

YCDL creates an SQLite3 database of Youtube channels and their videos, and serves it out of a web server.

## YCDL solves three main problems:

### Metadata archive

The database acts as a permanent archive of video metadata including title, description, duration, view count, and more. Even if a video or channel is deleted from Youtube, you will still have this information. Perfect for keeping track of unlisted videos, too.

The thumbnails, however, are not stored in the database, but you can use `utilities\download_thumbnails.py` to download them.

Note: At this time, refreshing a channel in YCDL will update video titles, descriptions, and view counts with their current values. If you refresh a channel after they have changed their video's title or description you will lose the previous value.

### Easily watch every video on the channel

When I discover a channel, I like to watch through the videos over the course of weeks or months. Within Youtube's own interface, there is no good way to filter videos you've watched from videos you haven't. Scrolling through all of a channel's videos to find ones you haven't seen is tough.

In YCDL, videos start off as pending and you can mark them as ignore or download. The pending page always acts as your "to-watch" list.

On Youtube's subscription page, there is a button to hide a video from the list. I would often press this hide button after watching a video, only to find it come back a few days later. Don't get me started on live broadcasts or premieres -- hiding those was never reliable. YCDL makes watching my subscriptions much easier.

### Send video IDs to youtube-dl

YCDL does not perform the downloading of videos itself. [youtube-dl](https://github.com/ytdl-org/youtube-dl) is the tool for that. When you click on the download button, it will create an empty file called `xxxxxxxxxxx.ytqueue` in the directory specified by the `ycdl.json` config file. You should create a separate shell / Python script that watches for ytqueue files and calls youtube-dl with your preferred arguments.

The reason for this is that youtube-dl is extremely configurable. Every user might prefer a completely different set of arguments and formatting. Rather than attempting to provide an interface for that in YCDL, my goal is to get you the video IDs so you can pass them into your favorite youtube-dl configuration.

## Features

- Web interface with video embeds
- Commandline interface for scripted use
- "Sub-box" page where newest videos from all channels are listed in order
- Sort videos by date, duration, views, or random
- Background thread will refresh channels over time
- Automark channels as ignore or download
- Free yourself from Youtube's awful recommendation system

## Your API key

You are responsible for your own `youtube_credentials.py` file in a folder on your `PYTHONPATH`. This file must have a function `get_youtube_key`. YCDL will `import youtube_credentials` and call `youtube_credentials.get_youtube_key()` with no arguments. It should return a Youtube API key string. Here is how to get one:

1. Go to https://console.developers.google.com/.
2. Create a project using the menu in the upper left.
3. From the project's dashboard, click "Enable APIs and Services".
4. Search for and choose the latest YouTube Data API.
5. On the left bar, click "Credentials".
6. Click "Create credentials" and choose "API key". In my experience they all start with "AIzaSy".
7. Return this value from `get_youtube_key`.

## Setting up

YCDL has a core backend package and separate frontends that use it. These frontend applications will use `import ycdl` to access the backend code. Therefore, the `ycdl` package needs to be in the right place for Python to find it for `import`.

1. Run `pip install -r requirements.txt --upgrade`.

2. Make a new folder somewhere on your computer, and add this folder to your `PYTHONPATH` environment variable. For example, I might use `D:\pythonpath` or `~/pythonpath`. Close and re-open your Command Prompt / Terminal so it reloads the environment variables.

3. Place your `youtube_credentials.py` file inside that folder.

4. Run `python -c "import youtube_credentials; print(youtube_credentials)"` to confirm. If you see an ImportError or ModuleNotFoundError, double check your pythonpath.

5. Add a symlink to the ycdl folder into the same folder where you placed `youtube_credentials.py`:

    The repository you are looking at now is `D:\Git\YCDL` or `~/Git/YCDL`. You can see the folder called `ycdl`.

    Windows: `mklink /d fakepath realpath`  
    For example `mklink /d "D:\pythonpath\ycdl" "D:\Git\YCDL\ycdl"`

    Linux: `ln --symbolic realpath fakepath`  
    For example `ln --symbolic "~/Git/YCDL" "~/pythonpath/ycdl"`

6. Run `python -c "import ycdl; print(ycdl)"` to confirm.

## Running YCDL

In order to prevent the accidental creation of databases, you must first use `ycdl_cli.py init` to create your database.

### Running YCDL CLI

1. `cd` to the folder where you'd like to create the YCDL database.

2. Run `python frontends/ycdl_cli.py --help` to learn about the available commands.

3. Run `python frontends/ycdl_cli.py init` to create a database in the current directory.

Note: Do not `cd` into the frontends folder. Stay in the folder that contains your `_ycdl` database and specify the full path of the frontend launcher. For example:

    Windows:
    D:\somewhere> python D:\Git\YCDL\frontends\ycdl_cli.py

    Linux:
    /somewhere $ python /Git/YCDL/frontends/ycdl_cli.py

It is expected that you create a shortcut file or launch script so you don't have to type the whole filepath every time.

### Running YCDL Flask locally

1. Use `ycdl_cli init` to create the database in the desired directory.

2. Run `python frontends/ycdl_flask/ycdl_flask_dev.py [port]` to launch the flask server. Port defaults to 5000 if not provided.

3. Open your web browser to `localhost:<port>`.

Note: Do not `cd` into the frontends folder. Stay in the folder that contains your `_ycdl` database and specify the full path of the frontend launcher. For example:

    Windows:
    D:\somewhere> python D:\Git\YCDL\frontends\ycdl_flask\ycdl_flask_dev.py 5001

    Linux:
    /somewhere $ python /Git/YCDL/frontends/ycdl_flask/ycdl_flask_dev.py 5001

Add `--help` to learn the arguments.

It is expected that you create a shortcut file or launch script so you don't have to type the whole filepath every time.

### Running YCDL REPL

1. Use `ycdl_cli init` to create the database in the desired directory.

2. Run `python frontends/ycdl_repl.py` to launch the Python interpreter with the YCDLDB pre-loaded into a variable called `Y`. Try things like `Y.get_videos`.

Note: Do not `cd` into the frontends folder. Stay in the folder that contains your `_ycdl` database and specify the full path of the frontend launcher. For example:

    Windows:
    D:\somewhere> python D:\Git\YCDL\frontends\ycdl_repl.py

    Linux:
    /somewhere $ python /Git/YCDL/frontends/ycdl_repl.py

It is expected that you create a shortcut file or launch script so you don't have to type the whole filepath every time.

## Pairs well with...

### YCDL bookmarklet

Here is a javascript bookmarklet that you can click while on youtube.com to be redirected to the same URL on your YCDL server. Mainly for `/channel` and `/watch` URLs.

```Javascript
javascript:
document.location = document.location.href.replace('https://www.youtube.com', 'http://localhost:5000');
false;
```

Replace 5000 with the port on which you choose to run YCDL.

### uBlock Origin filters

I use the following filters to prevent annoying elements from appearing inside the embedded youtube player:

```
! This is the thing that pops up while the video is paused
youtube.com##.ytp-scroll-min.ytp-pause-overlay

! These are the recommendations that appear after the video is over
youtube.com##.ytp-suggestion-set
```

## Screenshots

![](https://user-images.githubusercontent.com/7299570/133191450-5ecf7ab2-fd22-4bcc-9d6b-eb29e23da7d9.png)

![](https://user-images.githubusercontent.com/7299570/133191359-94500650-ac27-4968-87de-f8b791733ebe.png)

![](https://user-images.githubusercontent.com/7299570/133191446-90d68bc7-26b3-4d0a-a0cf-cc8cea87b399.png)

![](https://user-images.githubusercontent.com/7299570/78462832-cb80c600-768a-11ea-9b86-529e1a22616c.png)

![](https://user-images.githubusercontent.com/7299570/133191451-e092bd12-feee-4d1a-b4b7-824f7a02856e.png)

![](https://user-images.githubusercontent.com/7299570/78462834-cc195c80-768a-11ea-942b-e89a3dabe64d.png)

## To do list

- Keep permanent record of titles and descriptions.
- Progress indicator for channel refresh.

## Mirrors

https://github.com/voussoir/ycdl

https://gitlab.com/voussoir/ycdl

https://codeberg.org/voussoir/ycdl
