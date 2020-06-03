var api = {};

/**************************************************************************************************/
api.channels = {};

api.channels.add_channel =
function add_channel(channel_id, callback)
{
    var url = "/add_channel";
    data = new FormData();
    data.append("channel_id", channel_id);
    return common.post(url, data, callback);
}

api.channels.refresh_channel =
function refresh_channel(channel_id, force, callback)
{
    var url = `/channel/${channel_id}/refresh`;
    data = new FormData();
    data.append("force", force)
    return common.post(url, data, callback);
}

api.channels.refresh_all_channels =
function refresh_all_channels(force, callback)
{
    var url = "/refresh_all_channels";
    data = new FormData();
    data.append("force", force)
    return common.post(url, data, callback);
}

api.channels.set_automark =
function set_automark(channel_id, state, callback)
{
    var url = `/channel/${channel_id}/set_automark`;
    data = new FormData();
    data.append("state", state);
    return common.post(url, data, callback);
}

/**************************************************************************************************/
api.videos = {};

api.videos.mark_state =
function mark_state(video_ids, state, callback)
{
    var url = "/mark_video_state";
    data = new FormData();
    data.append("video_ids", video_ids);
    data.append("state", state);
    return common.post(url, data, callback);
}

api.videos.start_download =
function start_download(video_ids, callback)
{
    var url = "/start_download";
    data = new FormData();
    data.append("video_ids", video_ids);
    return common.post(url, data, callback);
}
