import bs4
import logging
import requests

log = logging.getLogger(__name__)

def get_user_videos(uid):
    log.debug(f'Fetching RSS for {uid}.')
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={uid}'
    response = requests.get(url)
    response.raise_for_status()
    soup = bs4.BeautifulSoup(response.text, 'lxml')
    # find_all does not work on namespaced tags unless you add a limit paramter.
    video_ids = [v.text for v in soup.find_all('yt:videoid', limit=9999)]
    return video_ids
