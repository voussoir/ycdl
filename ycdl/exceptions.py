import re

def pascal_to_loudsnakes(text):
    '''
    NoSuchPhoto -> NO_SUCH_PHOTO
    '''
    match = re.findall(r'[A-Z][a-z]*', text)
    text = '_'.join(match)
    text = text.upper()
    return text

class ErrorTypeAdder(type):
    '''
    During definition, the Exception class will automatically receive a class
    attribute called `error_type` which is just the class's name as a string
    in the loudsnake casing style. NoSuchPhoto -> NO_SUCH_PHOTO.

    This is used for serialization of the exception object and should
    basically act as a status code when displaying the error to the user.

    Thanks Unutbu
    http://stackoverflow.com/a/18126678
    '''
    def __init__(cls, name, bases, clsdict):
        type.__init__(cls, name, bases, clsdict)
        cls.error_type = pascal_to_loudsnakes(name)

class YCDLException(Exception, metaclass=ErrorTypeAdder):
    '''
    Base type for all of the YCDL exceptions.
    Subtypes should have a class attribute `error_message`. The error message
    may contain {format} strings which will be formatted using the
    Exception's constructor arguments.
    '''
    error_message = ''

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.given_args = args
        self.given_kwargs = kwargs
        self.error_message = self.error_message.format(*args, **kwargs)
        self.args = (self.error_message, args, kwargs)

    def __str__(self):
        return self.error_type + '\n' + self.error_message

# NO SUCH ##########################################################################################

class NoSuchChannel(YCDLException):
    error_message = 'Channel {} does not exist.'

class NoSuchVideo(YCDLException):
    error_message = 'Video {} does not exist.'

class NoVideos(YCDLException):
    error_message = 'Channel {} has no videos.'

# VIDEO ERRORS #####################################################################################

class InvalidVideoState(YCDLException):
    error_message = '{} is not a valid state.'

# RSS ERRORS #######################################################################################

class RSSAssistFailed(YCDLException):
    error_message = '{}'

# SQL ERRORS #######################################################################################

class BadSQL(YCDLException):
    pass

class BadTable(BadSQL):
    error_message = 'Table "{}" does not exist.'

# GENERAL ERRORS ###################################################################################

class BadDataDirectory(YCDLException):
    '''
    Raised by YCDLDB __init__ if the requested data_directory is invalid.
    '''
    error_message = 'Bad data directory "{}"'

OUTOFDATE = '''
Database is out of date. {existing} should be {new}.
Please run utilities\\database_upgrader.py "{filepath.absolute_path}"
'''.strip()
class DatabaseOutOfDate(YCDLException):
    error_message = OUTOFDATE
