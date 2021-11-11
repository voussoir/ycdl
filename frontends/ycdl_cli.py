import argparse
import itertools
import sys
import traceback

from voussoirkit import betterhelp
from voussoirkit import interactive
from voussoirkit import pipeable
from voussoirkit import vlogging
from voussoirkit import operatornotify

import ycdl

log = vlogging.getLogger(__name__, 'ycdl_cli')

# HELPERS ##########################################################################################

def closest_db():
    return ycdl.ycdldb.YCDLDB.closest_ycdldb()

def get_channels_from_args(args):
    '''
    This function unifies channel IDs that are part of the command's argparser
    and channels that come from --channel_list listargs into a single stream
    of Channel objects.
    '''
    ycdldb = closest_db()
    channels = []

    if args.channel_list_args:
        channels.extend(_channel_list_argparse(args.channel_list_args))

    if args.channel_ids:
        channels.extend(ycdldb.get_channels_by_id(pipeable.input_many(args.channel_ids)))

    return channels

def get_videos_from_args(args):
    '''
    This function unifies video IDs that are part of the command's argparser
    and videos that come from --video_list listargs into a single stream
    of Video objects.
    '''
    ycdldb = closest_db()
    videos = []

    if args.video_list_args:
        videos.extend(_video_list_argparse(args.video_list_args))

    if args.video_ids:
        videos.extend(ycdldb.get_videos_by_id(pipeable.input_many(args.video_ids)))

    return videos

# ARGPARSE #########################################################################################

def add_channel_argparse(args):
    ycdldb = closest_db()
    ycdldb.add_channel(
        channel_id=args.channel_id,
        automark=args.automark,
        download_directory=args.download_directory,
        get_videos=args.get_videos,
        name=args.name,
        queuefile_extension=args.queuefile_extension,
    )

    if args.autoyes or interactive.getpermission('Commit?'):
        ycdldb.commit()

    return 0

def _channel_list_argparse(args):
    ycdldb = closest_db()
    channels = sorted(ycdldb.get_channels(), key=lambda c: c.name.lower())
    yield from channels

def channel_list_argparse(args):
    for channel in _channel_list_argparse(args):
        line = args.format.format(
            automark=channel.automark,
            autorefresh=channel.autorefresh,
            id=channel.id,
            name=channel.name,
            queuefile_extension=channel.queuefile_extension,
            uploads_playlist=channel.uploads_playlist,
        )
        pipeable.stdout(line)

    return 0

def delete_channel_argparse(args):
    ycdldb = closest_db()
    needs_commit = False

    for channel in get_channels_from_args(args):
        channel.delete()
        needs_commit = True

    if args.autoyes or interactive.getpermission('Commit?'):
        ycdldb.commit()

    return 0

def download_video_argparse(args):
    ycdldb = closest_db()
    needs_commit = False

    for video in get_videos_from_args(args):
        queuefile = ycdldb.download_video(
            video,
            download_directory=args.download_directory,
            force=args.force,
            queuefile_extension=args.queuefile_extension,
        )
        if queuefile is not None:
            needs_commit = True

    if not needs_commit:
        return 0

    if args.autoyes or interactive.getpermission('Commit?'):
        ycdldb.commit()

    return 0

def init_argparse(args):
    ycdldb = ycdl.ycdldb.YCDLDB(create=True)
    ycdldb.commit()
    pipeable.stdout(ycdldb.data_directory.absolute_path)
    return 0

def refresh_channels_argparse(args):
    needs_commit = False
    status = 0

    ycdldb = closest_db()
    if args.channels:
        channels = [ycdldb.get_channel(c) for c in args.channels]
        for channel in channels:
            try:
                channel.refresh(force=args.force)
                needs_commit = True
            except Exception as exc:
                log.warning(traceback.format_exc())
                status = 1
    else:
        excs = ycdldb.refresh_all_channels(force=args.force, skip_failures=True)
        needs_commit = True

    if not needs_commit:
        return status

    if args.autoyes or interactive.getpermission('Commit?'):
        ycdldb.commit()

    return status

def _video_list_argparse(args):
    ycdldb = closest_db()
    videos = ycdldb.get_videos(channel_id=args.channel_id, state=args.state, orderby=args.orderby)

    if args.limit is not None:
        videos = itertools.islice(videos, args.limit)

    yield from videos

def video_list_argparse(args):
    for video in _video_list_argparse(args):
        line = args.format.format(
            author_id=video.author_id,
            duration=video.duration,
            id=video.id,
            live_broadcast=video.live_broadcast,
            published=video.published,
            published_string=video.published_string,
            state=video.state,
            title=video.title,
            views=video.views,
        )
        pipeable.stdout(line)

    return 0

DOCSTRING = '''
YCDL CLI
========

{add_channel}

{channel_list}

{delete_channel}

{download_video}

{init}

{refresh_channels}

{video_list}

You can add --yes to avoid the "Commit?" prompt on commands that modify the db.

TO SEE DETAILS ON EACH COMMAND, RUN
> ycdl_cli.py <command> --help
'''

SUB_DOCSTRINGS = dict(
add_channel='''
add_channel:
    Add a channel to the database.

    > ycdl_cli.py add_channel channel_id <flags>

    flags:
    --automark X:
        Set the channel's automark to this value, which should be 'pending',
        'downloaded', or 'ignored'.

    --download_directory X:
        Set the channel's download directory to this path, which must
        be a directory.

    --name X:
        Override the channel's own name with a name of your choosing.

    --no_videos:
        By default, the channel's videos will be fetched right away.
        Add this argument if you don't want to do that yet.

    --queuefile_extension X:
        Set the queuefile extension for all videos downloaded from this channel.

    Examples:
    > ycdl_cli.py add_channel UCFhXFikryT4aFcLkLw2LBLA
''',

channel_list='''
channel_list:
    Print all channels in the database.

    Note: If you want to use this in a command pipeline, please specify
    --format instead of relying on the default.

    > ycdl_cli.py channel_list <flags>

    flags:
    --format X:
        A string like "{id}: {name}" to format the attributes of the channel.
        The available attributes are id, name, automark, autorefresh,
        uploads_playlist, queuefile_extension.

        If you are using --channel_list as listargs for another command, then
        this argument is not relevant.

    > ycdl_cli.py channel_list

    Examples:
    > ycdl_cli.py channel_list
    > ycdl_cli.py channel_list --format "{id} automark={automark}"
''',

delete_channel='''
delete_channel:
    Delete a channel and all its videos from the database.

    You can pass multiple channel IDs.
    Uses pipeable to support !c clipboard, !i stdin.

    > ycdl_cli.py delete_channel channel_id [channel_id channel_id...]
    > ycdl_cli.py delete_channel --channel_list listargs

    Examples:
    # Delete one channel
    > ycdl_cli.py delete_channel UCOYBuFGi8T3NM5fNAptCLCw

    # Delete many channels
    > ycdl_cli.py delete_channel UCOYBuFGi8T3NM5fNAptCLCw UCmu9PVIZBk-ZCi-Sk2F2utA

    # Delete all channels in the database
    > ycdl_cli.py delete_channel --channel-list

    See ycdl_cli.py channel_list --help for help with listargs.
''',

download_video='''
download_video:
    Create the queuefiles for one or more videos.

    They will be placed in the channel's download_directory if it has one, or
    else the download_directory in the ycdl.json config file. The video will
    have its state set to "downloaded".

    Uses pipeable to support !c clipboard, !i stdin.

    > ycdl_cli.py download_video video_id [video_id video_id...] <flags>
    > ycdl_cli.py download_video <flags> --video_list listargs

    flags:
    --download_directory X:
        By default, the queuefile will be placed in the channel's
        download_directory if it has one, or the download_directory in the
        ycdl.json config file. You can pass this argument to override both
        of those.

    --force:
        By default, a video that is already marked as downloaded will not be
        downloaded again. You can add this to make the queuefiles for those
        videos anyway.

    --queuefile_extension X:
        By default, the queuefile extension is taken from the channel or the
        config file. You can pass this argument to override both of those.

    Examples:
    # Download one video
    > ycdl_cli.py download_video thOifuHs6eY

    # Force download many videos
    > ycdl_cli.py download_video yJ-oASr_djo vHuFizITMdA --force

    # Download all videos from this channel
    > ycdl_cli.py download_video --video_list --channel UCvBv3PCvD9v-IKKTkd94XPg

    # Force re-download all videos that have already been downloaded
    > ycdl_cli.py download_video --force --video_list --state downloaded

    See ycdl_cli.py video_list --help for help with listargs.
''',

init='''
init:
    Create a new YCDL database in the current directory.

    > ycdl_cli.py init
''',

refresh_channels='''
refresh_channels:
    Refresh some or all channels in the database.

    New videos will have their state marked with the channel's automark value,
    and queuefiles will be created for channels with automark=downloaded.

    > ycdl_cli.py refresh_channels <flags>

    flags:
    --channels X Y Z:
        Any number of channel IDs.
        If omitted, all channels will be refreshed.

    --force:
        If omitted, only new videos are found.
        If included, channels are refreshed completely. This may be slow and
        cost a lot of API calls.

    Examples:
    > ycdl_cli.py refresh_channels --force
    > ycdl_cli.py refresh_channels --channels UC1_uAIS3r8Vu6JjXWvastJg
''',

video_list='''
video_list:
    Print videos in the database.

    Note: If you want to use this in a command pipeline, please specify
    --format instead of relying on the default.

    > ycdl_cli.py video_list <flags>

    flags:
    --channel X:
        A channel ID to list videos from.

    --format X:
        A string like "{published_string}:{id} {title}" to format the
        attributes of the video. The available attributes are author_id,
        duration, id, live_broadcast, published, published_string, state,
        title, views.

    --limit X:
        Only show up to X results.

    --orderby X:
        Order the results by published, views, duration, or random.

    --state X:
        Only show videos with this state.

    Examples:
    > ycdl_cli.py video_list --state pending --limit 100
    > ycdl_cli.py video_list --channel UCzIiTeduaanyEboRfwJJznA --orderby views
''',
)

DOCSTRING = betterhelp.add_previews(DOCSTRING, SUB_DOCSTRINGS)

@operatornotify.main_decorator(subject='ycdl_cli')
@vlogging.main_decorator
def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers()

    primary_args = []
    video_list_args = []
    channel_list_args = []
    mode = primary_args
    for arg in argv:
        if 0:
            pass
        elif arg in {'--channel_list', '--channel-list'}:
            mode = channel_list_args
        elif arg in {'--video_list', '--video-list'}:
            mode = video_list_args
        else:
            mode.append(arg)

    p_add_channel = subparsers.add_parser('add_channel', aliases=['add-channel'])
    p_add_channel.add_argument('channel_id')
    p_add_channel.add_argument('--automark', default='pending')
    p_add_channel.add_argument('--download_directory', '--download-directory', default=None)
    p_add_channel.add_argument('--name', default=None)
    p_add_channel.add_argument('--no_videos', '--no-videos', dest='get_videos', action='store_false')
    p_add_channel.add_argument('--queuefile_extension', '--queuefile-extension', default=None)
    p_add_channel.add_argument('--yes', dest='autoyes', action='store_true')
    p_add_channel.set_defaults(func=add_channel_argparse)

    p_channel_list = subparsers.add_parser('channel_list', aliases=['channel-list'])
    p_channel_list.add_argument('--format', default='{id}:{name}')
    p_channel_list.set_defaults(func=channel_list_argparse)

    p_delete_channel = subparsers.add_parser('delete_channel', aliases=['delete-channel'])
    p_delete_channel.add_argument('channel_ids', nargs='*')
    p_delete_channel.add_argument('--yes', dest='autoyes', action='store_true')
    p_delete_channel.set_defaults(func=delete_channel_argparse)

    p_download_video = subparsers.add_parser('download_video', aliases=['download-video'])
    p_download_video.add_argument('video_ids', nargs='*')
    p_download_video.add_argument('--download_directory', '--download-directory', default=None)
    p_download_video.add_argument('--force', action='store_true')
    p_download_video.add_argument('--queuefile_extension', '--queuefile-extension', default=None)
    p_download_video.add_argument('--yes', dest='autoyes', action='store_true')
    p_download_video.set_defaults(func=download_video_argparse)

    p_init = subparsers.add_parser('init')
    p_init.set_defaults(func=init_argparse)

    p_refresh_channels = subparsers.add_parser('refresh_channels', aliases=['refresh-channels'])
    p_refresh_channels.add_argument('--channels', nargs='*')
    p_refresh_channels.add_argument('--force', action='store_true')
    p_refresh_channels.add_argument('--yes', dest='autoyes', action='store_true')
    p_refresh_channels.set_defaults(func=refresh_channels_argparse)

    p_video_list = subparsers.add_parser('video_list', aliases=['video-list'])
    p_video_list.add_argument('--channel', dest='channel_id', default=None)
    p_video_list.add_argument('--format', default='{published_string}:{id}:{title}')
    p_video_list.add_argument('--limit', type=int, default=None)
    p_video_list.add_argument('--orderby', default=None)
    p_video_list.add_argument('--state', default=None)
    p_video_list.set_defaults(func=video_list_argparse)

    ##

    def postprocessor(args):
        args.video_list_args = p_video_list.parse_args(video_list_args)
        args.channel_list_args = p_channel_list.parse_args(channel_list_args)
        return args

    try:
        return betterhelp.subparser_main(
            primary_args,
            parser,
            main_docstring=DOCSTRING,
            sub_docstrings=SUB_DOCSTRINGS,
            args_postprocessor=postprocessor,
        )
    except ycdl.exceptions.NoClosestYCDLDB as exc:
        pipeable.stderr(exc.error_message)
        pipeable.stderr('Try `ycdl_cli.py init` to create the database.')
        return 1

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
