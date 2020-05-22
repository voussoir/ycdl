def channel(c):
    j = {
        'id': c.id,
        'name': c.name,
        'automark': c.automark,
    }
    return j

def exception(e):
    j = {
        'type': 'error',
        'error_type': e.error_type,
        'error_message': e.error_message,
    }
    return j

def video(v):
    j = {
        'id': v.id,
        'published': v.published,
        'author_id': v.author_id,
        'title': v.title,
        'description': v.description,
        'duration': v.duration,
        'views': v.views,
        'thumbnail': v.thumbnail,
        'download': v.download,
    }
    return j
