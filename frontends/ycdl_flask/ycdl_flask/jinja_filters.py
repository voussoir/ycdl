import math

def seconds_to_hms(seconds):
    '''
    Convert integer number of seconds to an hh:mm:ss string.
    Only the necessary fields are used.
    '''
    if seconds is None:
        return '???'

    seconds = math.ceil(seconds)
    (minutes, seconds) = divmod(seconds, 60)
    (hours, minutes) = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(hours)
    if minutes:
        parts.append(minutes)
    parts.append(seconds)
    hms = ':'.join(f'{part:02d}' for part in parts)
    return hms
