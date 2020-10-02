import bs4
import logging
import requests

from . import exceptions

log = logging.getLogger(__name__)

def _get_user_videos(uid):
    log.debug(f'Fetching RSS for {uid}.')
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={uid}'
    response = requests.get(url)
    response.raise_for_status()
    soup = bs4.BeautifulSoup(response.text, 'lxml')
    # find_all does not work on namespaced tags unless you add a limit paramter.
    video_ids = [v.text for v in soup.find_all('yt:videoid', limit=9999)]
    return video_ids

def get_user_videos(uid):
    try:
        return _get_user_videos(uid)
    except Exception:
        raise exceptions.RSSAssistFailed(f'Failed to fetch RSS videos.') from exc

def get_user_videos_since(uid, most_recent_video):
    video_ids = get_user_videos(uid)
    try:
        index = video_ids.index(most_recent_video)
    except ValueError:
        raise exceptions.RSSAssistFailed(f'RSS didn\'t contain {most_recent_video}.')
    return video_ids[:index]
