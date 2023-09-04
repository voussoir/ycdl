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
    with ycdldb.transaction:
        ycdldb.add_channel(
            channel_id=args.channel_id,
            automark=args.automark,
            download_directory=args.download_directory,
            get_videos=args.get_videos,
            name=args.name,
            queuefile_extension=args.queuefile_extension,
        )

        if not (args.autoyes or interactive.getpermission('Commit?')):
            ycdldb.rollback()

    return 0

def _channel_list_argparse(args):
    ycdldb = closest_db()
    channels = sorted(ycdldb.get_channels(), key=lambda c: c.name.lower())

    if args.automark:
        channels = [channel for channel in channels if channel.automark == args.automark]

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

    with ycdldb.transaction:
        for channel in get_channels_from_args(args):
            channel.delete()
            needs_commit = True

        if not needs_commit:
            return 0

        if not (args.autoyes or interactive.getpermission('Commit?')):
            ycdldb.rollback()

    return 0

def download_video_argparse(args):
    ycdldb = closest_db()
    needs_commit = False

    with ycdldb.transaction:
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

        if not (args.autoyes or interactive.getpermission('Commit?')):
            ycdldb.rollback()

    return 0

def ignore_shorts_argparse(args):
    ycdldb = closest_db()

    videos = ycdldb.get_videos_by_sql('''
    SELECT * FROM videos
    LEFT JOIN channels ON channels.id = videos.author_id
    WHERE is_shorts IS NULL AND duration < 62 AND state = "pending" AND channels.ignore_shorts = 1
    ORDER BY published DESC
    ''')
    videos = list(videos)
    if len(videos) == 0:
        log.info('No shorts candidates.')
        return 0

    while len(videos) > 0:
        count = 0
        with ycdldb.transaction:
            while len(videos) > 0:
                video = videos.pop()
                try:
                    is_shorts = ycdl.ytapi.video_is_shorts(video.id)
                except Exception as exc:
                    log.warning(traceback.format_exc())
                    continue

                pairs = {'id': video.id, 'is_shorts': int(is_shorts)}
                if is_shorts:
                    pairs['state'] = 'ignored'
                    video.state = 'ignored'
                    log.info('%s is shorts.', video.id)
                else:
                    log.info('%s is not shorts.', video.id)
                ycdldb.update(table=ycdl.objects.Video, pairs=pairs, where_key='id')
                count += 1

                # break every once in a while so the enclosing transaction
                # can commit our work so far.
                if count == 25:
                    break

def init_argparse(args):
    ycdldb = ycdl.ycdldb.YCDLDB(create=True)
    pipeable.stdout(ycdldb.data_directory.absolute_path)
    return 0

def refresh_channels_argparse(args):
    needs_commit = False
    status = 0

    ycdldb = closest_db()
    with ycdldb.transaction:
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

        if not (args.autoyes or interactive.getpermission('Commit?')):
            ycdldb.rollback()

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
            thumbnail=video.thumbnail,
            title=video.title,
            views=video.views,
        )
        pipeable.stdout(line)

    return 0

@operatornotify.main_decorator(subject='ycdl_cli')
@vlogging.main_decorator
def main(argv):
    parser = argparse.ArgumentParser(
        description='''
        This is the command-line interface for YCDL, so that you can automate your
        database and integrate it into other scripts.
        ''',
    )
    subparsers = parser.add_subparsers()

    ################################################################################################

    p_add_channel = subparsers.add_parser(
        'add_channel',
        aliases=['add-channel'],
        description='''
        Add a channel to the database.
        ''',
    )
    p_add_channel.examples = [
        'UCFhXFikryT4aFcLkLw2LBLA',
        'UCFhXFikryT4aFcLkLw2LBLA --automark downloaded',
        'UCLx053rWZxCiYWsBETgdKrQ --name LGR',
    ]
    p_add_channel.add_argument(
        'channel_id',
    )
    p_add_channel.add_argument(
        '--automark',
        default='pending',
        help='''
        Set the channel's automark to this value, which should be 'pending',
        'downloaded', or 'ignored'.
        ''',
    )
    p_add_channel.add_argument(
        '--download_directory',
        '--download-directory',
        default=None,
        help='''
        Set the channel's download directory to this path, which must
        be a directory.
        ''',
    )
    p_add_channel.add_argument(
        '--name',
        default=None,
        help='''
        Override the channel's own name with a name of your choosing.
        ''',
    )
    p_add_channel.add_argument(
        '--no_videos',
        '--no-videos',
        dest='get_videos',
        action='store_false',
        help='''
        By default, the channel's videos will be fetched right away. Add this
        argument if you don't want to do that yet.

        You should run refresh_channels later.
        ''',
    )
    p_add_channel.add_argument(
        '--queuefile_extension',
        '--queuefile-extension',
        type=str,
        default=None,
        help='''
        Set the queuefile extension for all videos downloaded from this channel.
        ''',
    )
    p_add_channel.add_argument(
        '--yes',
        dest='autoyes',
        action='store_true',
        help='''
        Commit the database without prompting.
        ''',
    )
    p_add_channel.set_defaults(func=add_channel_argparse)

    ################################################################################################

    p_channel_list = subparsers.add_parser(
        'channel_list',
        aliases=['channel-list'],
        description='''
        Print all channels in the database.

        Note: If you want to use this in a command pipeline, please specify
        --format instead of relying on the default.
        ''',
    )
    p_channel_list.examples = [
        '',
        ['--format', '{id} automark={automark}'],
        '--automark downloaded',
    ]
    p_channel_list.add_argument(
        '--format',
        default='{id}:{name}',
        help='''
        A string like "{id}: {name}" to format the attributes of the channel.
        The available attributes are id, name, automark, autorefresh,
        uploads_playlist, queuefile_extension.

        If you are using --channel_list as listargs for another command, then
        this argument is not relevant.
        ''',
    )
    p_channel_list.add_argument(
        '--automark',
        help='''
        Only show channels with this automark, pending, downloaded, or ignored.
        ''',
    )
    p_channel_list.set_defaults(func=channel_list_argparse)

    ################################################################################################

    p_delete_channel = subparsers.add_parser(
        'delete_channel',
        aliases=['delete-channel'],
        description='''
        Delete a channel and all its videos from the database.
        ''',
    )
    p_delete_channel.examples = [
        {'args': 'UCOYBuFGi8T3NM5fNAptCLCw', 'comment': 'Delete one channel'},
        {'args': 'UCOYBuFGi8T3NM5fNAptCLCw UCmu9PVIZBk-ZCi-Sk2F2utA', 'comment': 'Delete many channels'},
        {'args': '--channel-list --automark ignored', 'comment': 'Delete all channels that use the ignored automark'},
    ]
    p_delete_channel.add_argument(
        'channel_ids',
        nargs='*',
        help='''
        One or more channel IDs to delete.

        Uses pipeable to support !c clipboard, !i stdin lines of IDs.
        ''',
    )
    p_delete_channel.add_argument(
        '--yes',
        dest='autoyes',
        action='store_true',
        help='''
        Commit the database without prompting.
        ''',
    )
    p_delete_channel.add_argument(
        '--channel_list',
        '--channel-list',
        dest='channel_list_args',
        nargs='...',
        help='''
        All remaining arguments will go to the channel_list command to generate
        the list of channels to delete. Do not worry about --format.
        See channel_list --help for help.
        ''',
    )
    p_delete_channel.set_defaults(func=delete_channel_argparse)

    ################################################################################################

    p_download_video = subparsers.add_parser(
        'download_video',
        aliases=['download-video'],
        description='''
        Create the queuefiles for one or more videos.

        The video will have its state set to "downloaded".
        ''',
    )
    p_download_video.examples = [
         {'args': 'thOifuHs6eY', 'comment': 'Download one video'},
         {'args': 'yJ-oASr_djo vHuFizITMdA --force', 'comment': 'Force download many videos'},
         {'args': '--video_list --channel UCvBv3PCvD9v-IKKTkd94XPg', 'comment': 'Download all videos from this channel'},
         {'args': '--force --video_list --state downloaded', 'comment': 'Force re-download all videos that have already been downloaded'},
    ]
    p_download_video.add_argument(
        'video_ids',
        nargs='*',
        help='''
        Uses pipeable to support !c clipboard, !i stdin lines of IDs.
        ''',
    )
    p_download_video.add_argument(
        '--download_directory',
        '--download-directory',
        default=None,
        help='''
        By default, the queuefile will be placed in the channel's
        download_directory if it has one, or the download_directory in the
        ycdl.json config file. You can pass this argument to override both
        of those and use a specific directory.
        ''',
    )
    p_download_video.add_argument(
        '--force',
        action='store_true',
        help='''
        By default, a video that is already marked as downloaded will not be
        downloaded again. You can add this to make the queuefiles for those
        videos anyway.
        ''',
    )
    p_download_video.add_argument(
        '--queuefile_extension',
        '--queuefile-extension',
        default=None,
        help='''
        By default, the queuefile extension is taken from the channel or the
        config file. You can pass this argument to override both of those.
        ''',
    )
    p_download_video.add_argument(
        '--yes',
        dest='autoyes',
        action='store_true',
        help='''
        Commit the database without prompting.
        ''',
    )
    p_download_video.add_argument(
        '--video_list',
        '--video-list',
        dest='video_list_args',
        nargs='...',
        help='''
        All remaining arguments will go to the video_list command to generate the
        list of channels to delete. Do not worry about --format.
        See video_list --help for help.
        ''',
    )
    p_download_video.set_defaults(func=download_video_argparse)

    ################################################################################################

    p_ignore_shorts = subparsers.add_parser(
        'ignore_shorts',
        aliases=['ignore-shorts'],
        description='''
        Queries the Youtube API to figure out which videos are shorts, and marks
        them as ignored.
        ''',
    )
    p_ignore_shorts.set_defaults(func=ignore_shorts_argparse)

    ################################################################################################

    p_init = subparsers.add_parser(
        'init',
        description='''
        Create a new YCDL database in the current directory.
        ''',
    )
    p_init.set_defaults(func=init_argparse)

    ################################################################################################

    p_refresh_channels = subparsers.add_parser(
        'refresh_channels',
        aliases=['refresh-channels'],
        description='''
        Refresh some or all channels in the database.

        New videos will have their state marked with the channel's automark value,
        and queuefiles will be created for channels with automark=downloaded.
        ''',
    )
    p_refresh_channels.examples = [
        '--force',
        '--channels UC1_uAIS3r8Vu6JjXWvastJg',
    ]
    p_refresh_channels.add_argument(
        '--channels',
        nargs='*',
        help='''
        Any number of channel IDs.
        If omitted, all channels will be refreshed.
        ''',
    )
    p_refresh_channels.add_argument(
        '--force',
        action='store_true',
        help='''
        If omitted, only new videos are found.
        If included, channels are refreshed completely. This may be slow and
        cost a lot of API calls.
        ''',
    )
    p_refresh_channels.add_argument(
        '--yes',
        dest='autoyes',
        action='store_true',
        help='''
        Commit the database without prompting.
        ''',
    )
    p_refresh_channels.set_defaults(func=refresh_channels_argparse)

    ################################################################################################

    p_video_list = subparsers.add_parser(
        'video_list',
        aliases=['video-list'],
        description='''
        Print videos in the database.

        Note: If you want to use this in a command pipeline, please specify
        --format instead of relying on the default.
        ''',
    )
    p_video_list.examples = [
        '--state pending --limit 100',
        '--channel UCzIiTeduaanyEboRfwJJznA --orderby views',
        '--channel UC6nSFpj9HTCZ5t-N3Rm3-HA --format "{thumbnail} {id}.jpg" | threaded_dl !i 1 {basename}'
    ]
    p_video_list.add_argument(
        '--channel',
        dest='channel_id',
        default=None,
        help='''
        A channel ID to list videos from.
        ''',
    )
    p_video_list.add_argument(
        '--format',
        default='{published_string}:{id}:{title}',
        help='''
        A string like "{published_string}:{id} {title}" to format the
        attributes of the video. The available attributes are author_id,
        duration, id, live_broadcast, published, published_string, state,
        title, views, thumbnail.
        ''',
    )
    p_video_list.add_argument(
        '--limit',
        type=int,
        default=None,
        help='''
        Only show up to this many results.
        ''',
    )
    p_video_list.add_argument(
        '--orderby',
        default=None,
        help='''
        Order the results by published, views, duration, or random.
        ''',
    )
    p_video_list.add_argument(
        '--state',
        default=None,
        help='''
        Only show videos with this state, pending, downloaded, or ignored.
        ''',
    )
    p_video_list.set_defaults(func=video_list_argparse)

    ##

    def postprocessor(args):
        if hasattr(args, 'video_list_args'):
            args.video_list_args = p_video_list.parse_args(args.video_list_args)
        if hasattr(args, 'channel_list_args'):
            args.channel_list_args = p_channel_list.parse_args(args.channel_list_args)
        return args

    try:
        return betterhelp.go(parser, argv, args_postprocessor=postprocessor)
    except ycdl.exceptions.NoClosestYCDLDB as exc:
        pipeable.stderr(exc.error_message)
        pipeable.stderr('Try `ycdl_cli.py init` to create the database.')
        return 1

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
