import math

####################################################################################################

filter_functions = []
global_functions = []

def filter_function(function):
    filter_functions.append(function)
    return function

def global_function(function):
    global_functions.append(function)
    return function

def register_all(site):
    for function in filter_functions:
        site.jinja_env.filters[function.__name__] = function

    for function in global_functions:
        site.jinja_env.globals[function.__name__] = function

####################################################################################################

@filter_function
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
    if hours or minutes:
        parts.append(minutes)
    parts.append(seconds)
    hms = ':'.join(f'{part:02d}' for part in parts)
    return hms
