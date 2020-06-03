var api = {};

/**************************************************************************************************/
api.channels = {};

api.channels.refresh_channel =
function refresh_channel(channel_id, force, callback)
{
    var url = `/channel/${channel_id}/refresh`;
    data = new FormData();
    data.append("force", force)
    return common.post(url, data, callback);
}

/**************************************************************************************************/
api.videos = {};
