def chunk_sequence(sequence, chunk_length, allow_incomplete=True):
    '''
    Given a sequence, yield lists of length `chunk_length`.

    allow_incomplete:
        If True, allow the final chunk to be shorter if the
        given sequence is not an exact multiple of `chunk_length`.
        If False, the incomplete chunk will be discarded.
    '''
    import itertools
    iterator = iter(sequence)
    while True:
        chunk = list(itertools.islice(iterator, chunk_length))
        if not chunk:
            break
        if len(chunk) == chunk_length or allow_incomplete:
            yield chunk

def truthystring(s):
    if isinstance(s, (bool, int)) or s is None:
        return s
    s = s.lower()
    if s in {'1', 'true', 't', 'yes', 'y', 'on'}:
        return True
    if s in {'null', 'none'}:
        return None
    return False
