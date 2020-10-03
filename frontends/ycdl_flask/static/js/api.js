var api = {};

/**************************************************************************************************/
api.channels = {};

api.channels.add_channel =
function add_channel(channel_id, callback)
{
    const url = "/add_channel";
    const data = new FormData();
    data.append("channel_id", channel_id);
    return common.post(url, data, callback);
}

api.channels.delete_channel =
function delete_channel(channel_id, callback)
{
    const url = `/channel/${channel_id}/delete`;
    const data = new FormData();
    return common.post(url, data, callback);
}

api.channels.refresh_channel =
function refresh_channel(channel_id, force, callback)
{
    const url = `/channel/${channel_id}/refresh`;
    const data = new FormData();
    data.append("force", force)
    return common.post(url, data, callback);
}

api.channels.refresh_all_channels =
function refresh_all_channels(force, callback)
{
    const url = "/refresh_all_channels";
    const data = new FormData();
    data.append("force", force)
    return common.post(url, data, callback);
}

api.channels.set_automark =
function set_automark(channel_id, state, callback)
{
    const url = `/channel/${channel_id}/set_automark`;
    const data = new FormData();
    data.append("state", state);
    return common.post(url, data, callback);
}

api.channels.set_queuefile_extension =
function set_queuefile_extension(channel_id, extension, callback)
{
    const url = `/channel/${channel_id}/set_queuefile_extension`;
    const data = new FormData();
    data.append("extension", extension);
    return common.post(url, data, callback);
}

api.channels.callback_go_to_channels =
function callback_go_to_channels(response)
{
    if (response.meta.status === 200)
    {
        window.location.href = "/channels";
    }
    else
    {
        alert(JSON.stringify(response));
    }
}

/**************************************************************************************************/
api.videos = {};

api.videos.mark_state =
function mark_state(video_ids, state, callback)
{
    const url = "/mark_video_state";
    const data = new FormData();
    data.append("video_ids", video_ids);
    data.append("state", state);
    return common.post(url, data, callback);
}

api.videos.start_download =
function start_download(video_ids, callback)
{
    const url = "/start_download";
    const data = new FormData();
    data.append("video_ids", video_ids);
    return common.post(url, data, callback);
}
