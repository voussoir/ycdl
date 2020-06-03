var common = {};

common.post_example =
function post_example(key, value, callback)
{
    var url = "/postexample";
    data = new FormData();
    data.append(key, value);
    return post(url, data, callback);    
}

common.null_callback =
function null_callback()
{
    return;
}

common._request =
function _request(method, url, callback)
{
    var request = new XMLHttpRequest();
    request.onreadystatechange = function()
    {
        if (request.readyState == 4)
        {
            if (callback != null)
            {
                var response = {
                    "data": JSON.parse(request.responseText),
                    "meta": {}
                };
                response["meta"]["request_url"] = url;
                response["meta"]["status"] = request.status;
                callback(response);
            }
        }
    };
    var asynchronous = true;
    request.open(method, url, asynchronous);
    return request;
}

common.get =
function get(url, callback)
{
    request = common._request("GET", url, callback);
    request.send();
}

common.post =
function post(url, data, callback)
{
    request = common._request("POST", url, callback);
    request.send(data);
}

common.bind_box_to_button =
function bind_box_to_button(box, button)
{
    box.onkeydown=function()
    {
        if (event.keyCode == 13)
        {
            button.click();
        }
    };
}
common.entry_with_history_hook =
function entry_with_history_hook(box, button)
{
    //console.log(event.keyCode);
    if (box.entry_history === undefined)
    {box.entry_history = [];}
    if (box.entry_history_pos === undefined)
    {box.entry_history_pos = -1;}
    if (event.keyCode == 13)
    {
        /* Enter */
        box.entry_history.push(box.value);
        button.click();
        box.value = "";
    }
    else if (event.keyCode == 38)
    {

        /* Up arrow */
        if (box.entry_history.length == 0)
        {return}
        if (box.entry_history_pos == -1)
        {
            box.entry_history_pos = box.entry_history.length - 1;
        }
        else if (box.entry_history_pos > 0)
        {
            box.entry_history_pos -= 1;
        }
        box.value = box.entry_history[box.entry_history_pos];
    }
    else if (event.keyCode == 27)
    {
        box.value = "";
    }
    else
    {
        box.entry_history_pos = -1;
    }
}

common.init_atag_merge_params =
function init_atag_merge_params()
{
    /*
    To create an <a> tag where the ?parameters written on the href are merged
    with the parameters of the current page URL, give it the class
    "merge_params". If the URL and href contain the same parameter, the href
    takes priority.

    Example:
        URL: ?filter=hello&orderby=score
        href: "?orderby=date"
        Result: "?filter=hello&orderby=date"
    */
    var as = Array.from(document.getElementsByClassName("merge_params"));
    page_params = new URLSearchParams(window.location.search);
    as.forEach(function(a){
        var a_params = new URLSearchParams(a.search);
        var new_params = new URLSearchParams();
        page_params.forEach(function(value, key) {new_params.set(key, value); });
        a_params.forEach(function(value, key) {new_params.set(key, value); });
        a.search = new_params.toString();
        a.classList.remove("merge_params");
    });
}

common.on_pageload =
function on_pageload()
{
    common.init_atag_merge_params();
}
document.addEventListener("DOMContentLoaded", common.on_pageload);
