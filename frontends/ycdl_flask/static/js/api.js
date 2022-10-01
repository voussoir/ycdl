var api = {};

/**************************************************************************************************/
api.channels = {};

api.channels.add_channel =
function add_channel(channel_id, callback)
{
    return http.post({
        url: "/add_channel",
        data: {"channel_id": channel_id},
        callback: callback,
    });
}

api.channels.delete_channel =
function delete_channel(channel_id, callback)
{
    return http.post({
        url: `/channel/${channel_id}/delete`,
        data: {},
        callback: callback,
    });
}

api.channels.refresh_channel =
function refresh_channel(channel_id, force, callback)
{
    return http.post({
        url: `/channel/${channel_id}/refresh`,
        data: {"force": force},
        callback: callback,
    });
}

api.channels.refresh_all_channels =
function refresh_all_channels(force, callback)
{
    return http.post({
        url: "/refresh_all_channels",
        data: {"force": force},
        callback: callback,
    });
}

api.channels.set_automark =
function set_automark(channel_id, state, callback)
{
    return http.post({
        url: `/channel/${channel_id}/set_automark`,
        data: {"state": state},
        callback: callback,
    });
}

api.channels.set_autorefresh =
function set_autorefresh(channel_id, autorefresh, callback)
{
    return http.post({
        url: `/channel/${channel_id}/set_autorefresh`,
        data: {"autorefresh": autorefresh},
        callback: callback,
    });
}

api.channels.set_download_directory =
function set_download_directory(channel_id, download_directory, callback)
{
    return http.post({
        url: `/channel/${channel_id}/set_download_directory`,
        data: {"download_directory": download_directory},
        callback: callback,
    });
}

api.channels.set_name =
function set_name(channel_id, name, callback)
{
    return http.post({
        url: `/channel/${channel_id}/set_name`,
        data: {"name": name},
        callback: callback,
    });
}

api.channels.set_queuefile_extension =
function set_queuefile_extension(channel_id, extension, callback)
{
    return http.post({
        url: `/channel/${channel_id}/set_queuefile_extension`,
        data: {"extension": extension},
        callback: callback,
    });
}

api.channels.show_download_directory =
function show_download_directory(channel_id, callback)
{
    return http.post({
        url: `/channel/${channel_id}/show_download_directory`,
        callback: callback,
    });
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
    return http.post({
        url: "/mark_video_state",
        data: {"video_ids": video_ids, "state": state},
        callback: callback,
    });
}

api.videos.start_download =
function start_download(video_ids, callback)
{
    return http.post({
        url: "/start_download",
        data: {"video_ids": video_ids},
        callback: callback,
    });
}
