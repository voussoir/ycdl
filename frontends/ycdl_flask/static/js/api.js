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

/**************************************************************************************************/
api.videos = {};
