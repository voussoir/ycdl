import googleapiclient.discovery
import isodate
import typing

from voussoirkit import gentools
from voussoirkit import vlogging

def int_none(x):
    if x is None:
        return None
    return int(x)

class ChannelNotFound(Exception):
    pass

class VideoNotFound(Exception):
    pass

class Video:
    def __init__(self, data):
        self.id = data['id']

        snippet = data['snippet']
        content_details = data['contentDetails']
        statistics = data['statistics']

        self.title = snippet.get('title', '[untitled]')
        self.description = snippet.get('description', '')
        self.author_id = snippet['channelId']
        self.author_name = snippet.get('channelTitle', self.author_id)

        # Something like '2016-10-01T21:00:01'
        self.published_string = snippet['publishedAt']
        self.published = isodate.parse_datetime(self.published_string).timestamp()
        self.live_broadcast = snippet['liveBroadcastContent']
        if self.live_broadcast == 'none':
            self.live_broadcast = None
        self.tags = snippet.get('tags', [])

        # Something like 'PT10M25S'
        self.duration = isodate.parse_duration(content_details['duration']).seconds
        self.views = int_none(statistics.get('viewCount', None))
        self.likes = int_none(statistics.get('likeCount', 0))
        self.dislikes = int_none(statistics.get('dislikeCount'))
        self.comment_count = int_none(statistics.get('commentCount'))

        thumbnails = snippet['thumbnails']
        ranker = lambda key: thumbnails[key]['width'] * thumbnails[key]['height']
        best_thumbnail = max(thumbnails, key=ranker)
        self.thumbnail = thumbnails[best_thumbnail]

    def __str__(self):
        return 'Video:%s' % self.id

class Youtube:
    def __init__(self, key):
        self.youtube = googleapiclient.discovery.build(
            cache_discovery=False,
            developerKey=key,
            serviceName='youtube',
            version='v3',
        )
        self.log = vlogging.getLogger(__name__)

    def _playlist_paginator(self, playlist_id):
        page_token = None
        while True:
            response = self.youtube.playlistItems().list(
                maxResults=50,
                pageToken=page_token,
                part='contentDetails',
                playlistId=playlist_id,
            ).execute()

            yield from response['items']

            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break

    def get_playlist_videos(self, playlist_id) -> typing.Iterable[Video]:
        paginator = self._playlist_paginator(playlist_id)
        video_ids = (item['contentDetails']['videoId'] for item in paginator)
        videos = self.get_videos(video_ids)
        return videos

    def get_related_videos(self, video_id, count=50) -> typing.Iterable[Video]:
        if isinstance(video_id, Video):
            video_id = video_id.id

        results = self.youtube.search().list(
            part='id',
            relatedToVideoId=video_id,
            type='video',
            maxResults=count,
        ).execute()

        related = [rel['id']['videoId'] for rel in results['items']]
        videos = self.get_videos(related)
        return videos

    def get_user_id(self, username) -> str:
        user = self.youtube.channels().list(part='snippet', forUsername=username).execute()
        if not user.get('items'):
            raise ChannelNotFound(f'username: {username}')
        return user['items'][0]['id']

    def get_user_name(self, uid) -> str:
        user = self.youtube.channels().list(part='snippet', id=uid).execute()
        if not user.get('items'):
            raise ChannelNotFound(f'uid: {uid}')
        return user['items'][0]['snippet']['title']

    def get_user_uploads_playlist_id(self, uid) -> str:
        user = self.youtube.channels().list(part='contentDetails', id=uid).execute()
        if not user.get('items'):
            raise ChannelNotFound(f'uid: {uid}')
        return user['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    def get_user_videos(self, uid) -> typing.Iterable[Video]:
        yield from self.get_playlist_videos(self.get_user_uploads_playlist_id(uid))

    def get_video(self, video_id) -> Video:
        try:
            video = next(self.get_videos([video_id]))
            return video
        except StopIteration:
            raise VideoNotFound(video_id) from None

    def get_videos(self, video_ids) -> typing.Iterable[Video]:
        chunks = gentools.chunk_generator(video_ids, 50)
        total_snippets = 0
        for chunk in chunks:
            self.log.debug('Requesting batch of %d video ids.', len(chunk))
            self.log.loud(chunk)
            chunk = ','.join(chunk)
            data = self.youtube.videos().list(
                part='id,contentDetails,snippet,statistics',
                id=chunk,
            ).execute()
            snippets = data['items']
            self.log.debug('Got batch of %d snippets.', len(snippets))
            total_snippets += len(snippets)
            self.log.loud(snippets)
            for snippet in snippets:
                try:
                    video = Video(snippet)
                    yield video
                except KeyError as exc:
                    self.log.warning(f'KEYERROR: {exc} not in {snippet}')
        self.log.debug('Finished getting a total of %d snippets.', total_snippets)
