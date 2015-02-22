#
# TvplexendChannel.bundle - A Tvheadend Channel Plugin for PLEX Media Server
# Copyright (C) 2015 Patrick Gaubatz <patrick@gaubatz.at>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

#
# Constants
#


NAME = 'Tvheadend'
PREFIX = '/video/tvplexend'


#
# Plugin Hooks
#


def Start():
    ObjectContainer.title1 = NAME


def ValidatePrefs():
    if not Prefs['url']:
        Log.Error('You need to provide the URL of your Tvheadend server')
        return False

    if Prefs['username'] and Prefs['password']:
        u = Prefs['username']
        p = Prefs['password']
        Dict['auth'] = 'Basic ' + String.Encode(u + ':' + p)

    try:
        info = Tvheadend.ServerInfo()
        if not info:
            Log.Error('URL, Username, or Password are wrong')
            return False

        if info['api_version'] < 15:
            Log.Error('Tvheadend server too old')
            return False

    except TvplexendException as e:
        Log.Error(str(e))
        return False

    Log.Info('Successfully connected to Tvheadend server')


@handler(PREFIX, NAME, thumb='icon-default.png', art='art-default.png')
def MainMenu():
    try:
        Tvheadend.ServerInfo()

    except TvplexendException as e:
        return ObjectContainer(header=L('error'), message=str(e))

    return ObjectContainer(
        objects=[
            DirectoryObject(key=Callback(ChannelList), title=L('livetv')),
            DirectoryObject(key=Callback(RecordingList), title=L('rec')),
            PrefsObject(title=L('settings'))
        ]
    )


#
# Live TV
#


@route(PREFIX + '/channels')
def ChannelList():
    try:
        oc = ObjectContainer(title2=L('livetv'))

        channels = Tvheadend.Channels()
        channels.sort(key=lambda channel: channel['number'])
        maxNum = max(channels, key=lambda channel: channel['number'])['number']

        Dict['channels'] = dict()
        Dict['channelNumPadding'] = len(str(maxNum))
        Dict['epg'] = Tvheadend.EPG(len(channels))

        for channel in channels:
            id = channel['uuid']
            Dict['channels'][id] = channel
            oc.add(Channel(channelId=id))

        return oc

    except TvplexendException as e:
        return ObjectContainer(header=L('error'), message=str(e))


@route(PREFIX + '/channels/{channelId}')
def Channel(channelId, container=False):
    channel = Dict['channels'][channelId]
    epg = Dict['epg'][channelId] if channelId in Dict['epg'] else dict()

    title = channel['name']
    summary = ''
    tagline = None
    thumb = None
    duration = None

    if Client.Platform == ClientPlatform.Android and 'title' in epg:
        title = '%s (%s)' % (title, epg['title'])

    if Prefs['displayChannelsNumbers']:
        chanNum = str(channel['number']).zfill(Dict['channelNumPadding'])
        title = '%s. %s' % (chanNum, title)

    if 'description' in epg:
        summary = epg['description']

    if 'title' in epg:
        tagline = epg['title']

    if Prefs['displayChannelIcons'] and 'icon_public_url' in channel:
        thumb = Prefs['url'] + '/' + channel['icon_public_url']

    if 'start' in epg and 'stop' in epg:
        start = Datetime.FromTimestamp(epg['start']).strftime('%H:%M')
        stop = Datetime.FromTimestamp(epg['stop']).strftime('%H:%M')
        summary = '- %s %s %s %s %s\n\n%s' % (
            L('airing'), L('from'), start, L('to'), stop, summary
        )
        duration = (epg['stop'] - epg['start']) * 1000

    return TvplexendObject(
        rating_key=PREFIX + '/channels/' + channelId,
        title=title,
        summary=summary,
        tagline=tagline,
        thumb=thumb,
        duration=duration,
        callback=Callback(Channel, channelId=channelId, container=True),
        streamCallback=Callback(StreamChannel, channelId=channelId),
        container=container
    )


@route(PREFIX + '/channels/{channelId}/livestream')
def StreamChannel(channelId):
    return Redirect(Prefs['url'] + '/stream/channel/' + channelId)


#
# Recordings
#


@route(PREFIX + '/recordings')
def RecordingList():
    try:
        oc = ObjectContainer(title2=L('rec'))

        Dict['recordings'] = dict()

        for recording in Tvheadend.Recordings():
            id = recording['uuid']
            Dict['recordings'][id] = recording
            oc.add(Recording(recId=id))

        return oc

    except TvplexendException as e:
        return ObjectContainer(header=L('error'), message=str(e))


@route(PREFIX + '/recordings/{recId}')
def Recording(recId, container=False):
    recording = Dict['recordings'][recId]

    startDateTime = Datetime.FromTimestamp(recording['start'])
    stopDateTime = Datetime.FromTimestamp(recording['stop'])

    day = startDateTime.strftime('%d.%m.%Y')
    start = startDateTime.strftime('%H:%M')
    stop = stopDateTime.strftime('%H:%M')

    summary = '- %s\n- %s %s %s %s %s %s\n\n%s' % (
        recording['channelname'],
        L('aired_on'), day, L('from'), start, L('to'), stop,
        recording['disp_description']
    )

    return TvplexendObject(
        rating_key=PREFIX + '/recordings/' + recId,
        title=recording['disp_title'],
        summary=summary,
        tagline=recording['channelname'],
        duration=recording['duration'] * 1000,
        callback=Callback(Recording, recId=recId, container=True),
        streamCallback=Callback(StreamRecording, recId=recId),
        container=container
    )


@route(PREFIX + '/recordings/{recId}/stream')
def StreamRecording(recId):
    return Redirect(Prefs['url'] + '/dvrfile/' + recId)


#
# Utilities
#

def TvplexendObject(rating_key, title, summary, callback, streamCallback,
                    container, tagline=None, duration=None, thumb=None):

    vco = VideoClipObject(
        key=callback,
        rating_key=rating_key,
        title=title,
        summary=summary,
        items=[
            MediaObject(
                optimized_for_streaming=True,
                video_codec=VideoCodec.H264,
                audio_codec=AudioCodec.AAC,
                parts=[
                    PartObject(key=streamCallback)
                ]
            )
        ]
    )

    if tagline:
        vco.tagline = tagline

    if duration:
        vco.duration = duration

    if thumb:
        vco.thumb = thumb

    if container:
        return ObjectContainer(objects=[vco])

    return vco


class Tvheadend(object):
    @staticmethod
    def ServerInfo():
        return Tvheadend.fetch('/api/serverinfo')

    @staticmethod
    def Channels():
        channels = Tvheadend.fetch('/api/channel/grid?start=0&limit=999999')
        return channels['entries']

    @staticmethod
    def EPG(channelCount):
        entries = Tvheadend.fetch(
            '/api/epg/events/grid',
            values=dict(start=0, limit=channelCount)
        )['entries']
        return dict((channel['channelUuid'], channel) for channel in entries)

    @staticmethod
    def Recordings():
        return Tvheadend.fetch('/api/dvr/entry/grid_finished')['entries']

    @staticmethod
    def fetch(path, headers=dict(), values=None):
        url = Prefs['url'] + path

        if 'auth' in Dict:
            headers['Authorization'] = Dict['auth']

        try:
            return JSON.ObjectFromURL(url=url, headers=headers, values=values)

        except Ex.HTTPError as e:
            Log.Error('An HTTP error occured: ' + repr(e))
            if e.code == 401 or e.code == 403:
                raise TvplexendException(L('error_auth'))
            else:
                raise TvplexendException(L('error_net'))

        except Exception as e:
            Log.Exception('An exception occured: ' + repr(e))
            raise TvplexendException(L('error_net'))


class TvplexendException(Exception):
    pass
