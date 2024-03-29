import bs4
# Importing so that if lxml is not installed, you get an ImportError right
# away instead of when bs4 tries to parse.
import lxml
import requests
import traceback

from voussoirkit import vlogging

from . import exceptions

log = vlogging.getLogger(__name__)

session = requests.Session()

def _get_user_videos(channel_id):
    log.info(f'Fetching RSS for {channel_id}.')
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
    response = session.get(url)
    response.raise_for_status()
    soup = bs4.BeautifulSoup(response.text, 'lxml')
    # find_all does not work on namespaced tags unless you add a limit paramter.
    video_ids = [v.text for v in soup.find_all('yt:videoid', limit=9999)]
    log.loud('RSS got %s.', video_ids)
    return video_ids

def get_user_videos(channel_id) -> list[str]:
    '''
    Return the list of video ids from the channel.
    Expect a maximum of 15 results.
    '''
    try:
        return _get_user_videos(channel_id)
    except Exception as exc:
        log.warning(traceback.format_exc())
        raise exceptions.RSSAssistFailed(f'Failed to fetch RSS videos ({exc}).') from exc

def get_user_videos_since(channel_id, video_id) -> list[str]:
    '''
    Return the list of video ids that are more recently released than the
    reference id.
    '''
    # Let RSSAssistFailed raise.
    video_ids = get_user_videos(channel_id)

    try:
        index = video_ids.index(video_id)
    except ValueError:
        raise exceptions.RSSAssistFailed(f'RSS didn\'t contain {video_id}.')
    video_ids = video_ids[:index]
    log.loud('Since %s: %s', video_id, str(video_ids))
    return video_ids
