import os, sys, traceback, requests, shutil, json, xmltodict, time

from base64 import b64encode, b64decode
from support.base import get_logger, d
from support.base.file import SupportFile
from mpegdash.parser import MPEGDASHParser
from .tool import WVTool

class WVDownloader:
    default_headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'accept-language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
    }

    def __init__(self, config):
        self.config = config
        self.license_url = config['license_url']
        self.mpd_url = config.get('mpd_url', None)
        self.mpd_base_url = self.mpd_url[:self.mpd_url.rfind('/')+1]
        self.code = config.get('code', str(int(time.time())))
        self.logger = config.get('logger', get_logger(self.__class__.__name__))
        self.streaming_protocol = config.get('streaming_protocol', 'dash')
        self.mpd_headers = config.get('mpd_headers', self.default_headers)
        self.mpd = None   
        self.download_list = {'video':[], 'audio':[], 'text':[]}
        self.key= []
        tmp = self.config.get('folder_tmp', os.path.join(os.getcwd(), 'tmp'))
        self.temp_dir = os.path.join(tmp, self.code)
        
        self.output_filepath = config.get('output_filepath')
        if self.output_filepath == None:
            output_dir = self.config.get('folder_output', os.path.join(os.getcwd(), 'output'))
            output_filename = config.get('output_filename', f"{self.code}.mkv")
            self.output_filepath = os.path.join(output_dir, output_filename)
        self.output_format = self.output_filepath.split('.')[-1]
        self.filepath_last = os.path.join(self.temp_dir, f'{self.code}.{self.output_format}')

    def download(self):
        try:
            if os.path.exists(self.output_filepath):
                self.logger.debug(f"{self.output_filepath} FILE EXIST")
                return
            os.makedirs(self.temp_dir, exist_ok=True)
            os.makedirs(os.path.dirname(self.output_filepath), exist_ok=True)
            self.prepare()
            if self.streaming_protocol == 'hls':
                ret = self.download_m3u8()
            elif self.streaming_protocol == 'dash':
                if self.mpd == None:
                    self.get_mpd()
                if self.mpd is not None:
                    self.analysis_mpd()
                self.make_download_info()
                ret = self.download_mpd()
            if ret and self.config.get('clean', True):
                self.clean()
            return ret
        except Exception as e: 
            self.logger.error(f'Exception:{str(e)}')
            self.logger.error(traceback.format_exc())
        finally:
            pass
        return False
    

    def get_mpd(self):
        if self.mpd_url == None:
            self.logger.error('mpd url is not set!')
        text = requests.get(self.mpd_url, headers=self.mpd_headers).text
        self.mpd = MPEGDASHParser.parse(text)
        self.pssh = self.get_pssh_mpd(text)
        self.do_make_key()
        

    def analysis_mpd(self):
        self.adaptation_set = {'video':[], 'audio':[], 'text':[]}
        for period in self.mpd.periods:
            for adaptation_set in period.adaptation_sets:
                item_adaptation_set = {'representation':[]}
                item_adaptation_set['lang'] = adaptation_set.lang
                item_adaptation_set['contentType'] = adaptation_set.content_type
                if item_adaptation_set['contentType'] is None and adaptation_set.mime_type is not None:
                    item_adaptation_set['contentType'] = adaptation_set.mime_type.split('/')[0]
                item_adaptation_set['maxBandwidth']= adaptation_set.max_bandwidth
                if adaptation_set.segment_templates is not None:
                    item_adaptation_set['segment_templates'] = adaptation_set.segment_templates[0].to_dict()
                    item_adaptation_set['segment_templates']['segment_timeline'] = adaptation_set.segment_templates[0].segment_timelines
                    item_adaptation_set['segment_templates']['start_number'] = adaptation_set.segment_templates[0].start_number
                    if adaptation_set.segment_templates[0].segment_timelines is not None:
                        timelines = []
                        for tmp in adaptation_set.segment_templates[0].segment_timelines[0].Ss:
                            timelines.append({'t':tmp.t, 'd':tmp.d, 'r':tmp.r})
                        item_adaptation_set['segment_templates']['segment_timeline'] = timelines
                else:
                    item_adaptation_set['segment_templates'] = {}
                for representation in adaptation_set.representations:
                    # 티빙
                    if item_adaptation_set['contentType'] is None and representation.mime_type is not None:
                        item_adaptation_set['contentType'] = representation.mime_type.split('/')[0]

                    item_representation = {'ct':item_adaptation_set['contentType'], 'cenc':False if adaptation_set.content_protections == None else True}
                    item_representation['lang'] = adaptation_set.lang
                    item_representation['contentType'] = item_adaptation_set['contentType']
                    if representation.segment_templates is not None:
                        # 카카오 무료
                        #logger.debug(representation.segment_templates)
                        item_representation['segment_templates'] = representation.segment_templates[0].to_dict()
                        item_representation['segment_templates']['segment_timeline'] = representation.segment_templates[0].segment_timelines
                        item_representation['segment_templates']['start_number'] = representation.segment_templates[0].start_number
                        if representation.segment_templates[0].segment_timelines is not None:
                            timelines = []
                            for tmp in representation.segment_templates[0].segment_timelines[0].Ss:
                                timelines.append({'t':tmp.t, 'd':tmp.d, 'r':tmp.r})
                            item_representation['segment_templates']['segment_timeline'] = timelines
                    else:
                        item_representation['segment_templates'] = item_adaptation_set['segment_templates']
                    item_representation['bandwidth'] = representation.bandwidth
                    item_representation['codecs'] = representation.codecs
                    item_representation['codec_name'] = representation.codecs
                    if item_representation['codecs'] is not None:
                        if item_representation['codecs'].startswith('avc1'):
                            item_representation['codec_name'] = 'H.264'
                        elif item_representation['codecs'].startswith('mp4a.40.2'):
                            item_representation['codec_name'] = 'AAC'

                    item_representation['height'] = representation.height
                    item_representation['width'] = representation.width
                    item_representation['mimeType'] = representation.mime_type
                    if item_representation['mimeType'] == None:
                        item_representation['mimeType'] = adaptation_set.mime_type
                    item_representation['id'] = representation.id
                    if representation.base_urls is not None:
                        if representation.base_urls[0].base_url_value.startswith('http'):
                            # 쿠팡 자막
                            item_representation['url'] = representation.base_urls[0].base_url_value
                        else:
                            item_representation['url'] = '%s%s' % (self.mpd_base_url, representation.base_urls[0].base_url_value)
                    else:
                        item_representation['url'] = None
                    item_adaptation_set['representation'].append(item_representation)
                self.adaptation_set[item_adaptation_set['contentType']].append(item_adaptation_set)


    # 오버라이딩 할 수 있음.
    def make_download_info(self):
        try:
            for ct in ['video', 'audio']:
                max_band = 0
                max_item = None
                for adaptation_set in self.adaptation_set[ct]:
                    for item in adaptation_set['representation']:
                        if item['bandwidth'] > max_band:
                            max_band = item['bandwidth']
                            max_item = item
                self.download_list[ct].append(self.make_filepath(max_item))                      
            #logger.warning(d(self.adaptation_set['text']))
            # 왓챠는 TEXT  adaptation_set이 여러개
            #if len(self.adaptation_set['text']) > 0:
            for adaptation_set in self.adaptation_set['text']:
                if adaptation_set['representation'] is not None:
                    for item in adaptation_set['representation']:
                        item['url'] = item['url'].replace('&amp;', '&')
                        self.download_list['text'].append(self.make_filepath(item))
        except Exception as e: 
            self.logger.error('Exception:%s', e)
            self.logger.error(traceback.format_exc())


    def make_filepath(self, representation):
        if  representation['contentType'] == 'text':
            force = representation.get('force', False)
            representation['filepath_download'] = os.path.join(self.temp_dir, '{code}.{lang}{force}.{ext}'.format(code=self.code, lang=representation['lang'], force='.force' if force else '', ext=representation['mimeType'].split('/')[1]))
            representation['filepath_merge'] = os.path.join(self.temp_dir, '{code}.{lang}{force}.srt'.format(code=self.code, lang=representation['lang'], force='.force' if force else ''))
        else:
            representation['filepath_download'] = os.path.join(self.temp_dir, '{code}.{contentType}.{lang}.{bandwidth}.original.mp4'.format(code=self.code, contentType=representation['contentType'], lang=representation['lang'] if representation['lang'] is not None else '', bandwidth=representation['bandwidth'])).replace('..', '.')
            representation['filepath_merge'] = representation['filepath_download'].replace('.original.mp4', '.decrypt.mp4')
            representation['filepath_dump'] = representation['filepath_merge'].replace('.mp4', '.dump.txt')
            representation['filepath_info'] = representation['filepath_merge'].replace('.mp4', '.info.json')
        return representation


    def download_mpd(self):
        try:
            self.merge_option = ['-o', '"%s"' % self.filepath_last]
            self.merge_option_etc = []
            self.merge_option_mp4 = []
            self.audio_codec = ''
            for ct in ['video', 'audio']:
                for item in self.download_list[ct]:
                    if item['url'] is not None:
                        if os.path.exists(item['filepath_download']) == False:
                            WVTool.aria2c_download(item['url'], item['filepath_download'], segment=False)
                    else:
                        self.download_segment(item)

                    if os.path.exists(item['filepath_download']) and os.path.exists(item['filepath_dump']) == False:
                        WVTool.mp4dump(item['filepath_download'], item['filepath_dump'])

                    if os.path.exists(item['filepath_merge']) == False:
                        text = SupportFile.read(item['filepath_dump'])
                        if text.find('default_KID = [') == -1:
                            self.logger.debug('KID 없음')
                            shutil.copy(item['filepath_download'], item['filepath_merge'])
                        else:
                            kid = text.split('default_KID = [')[1].split(']')[0].replace(' ', '')
                            key = self.find_key(kid)
                            WVTool.mp4decrypt(item['filepath_download'], item['filepath_merge'], kid, key)

                    if os.path.exists(item['filepath_merge']) and os.path.exists(item['filepath_info']) == False:
                        WVTool.mp4info(item['filepath_merge'], item['filepath_info'])
                    
                    if ct == 'audio':
                        if item['lang'] != None:
                            self.merge_option += ['--language', '0:%s' % item['lang']]
                        self.audio_codec += item['codec_name'] + '.'
                    self.merge_option += ['"%s"' % item['filepath_merge']]
                    self.merge_option_mp4 += ['-i', '"%s"' % item['filepath_merge']]

            if self.download_list['text']:
                self.merge_option_mp4 += ['-map', '0']

            for idx, item in enumerate(self.download_list['text']):
                map_cmd = ['-map',  '0']
                if os.path.exists(item['filepath_download']) == False:
                    self.logger.warning(f"자막 url : {item['url']}")
                    WVTool.aria2c_download(item['url'], item['filepath_download'], headers=self.mpd_headers if self.mpd_base_url is not None and item['url'].startswith(self.mpd_base_url) else {})
                if os.path.exists(item['filepath_download']) and os.path.exists(item['filepath_merge']) == False:
                    if item['mimeType'] == 'text/ttml':
                        WVTool.ttml2srt(item['filepath_download'], item['filepath_merge'])
                    elif item['mimeType'] == 'text/vtt':
                        WVTool.vtt2srt(item['filepath_download'], item['filepath_merge'])
                    elif item['mimeType'] == 'text/vtt/netflix':
                        sub = SupportFile.read_file(item['filepath_download'])
                        for idx, tmp in enumerate(sub.split('\n')):
                            if tmp == '1':
                                break
                        new_sub = '\n'.join(sub.split('\n')[idx:])
                        SupportFile.write_file(item['filepath_download'], new_sub)
                        WVTool.vtt2srt(item['filepath_download'], item['filepath_merge'])
                if os.path.exists(item['filepath_merge']) == False:
                    continue
                if item['lang'] == 'ko':
                    self.merge_option += ['--language', '"0:%s"' % item['lang']]
                    #self.merge_option += ['--forced-track', '"0:yes"']
                    if item.get('force', False):
                        self.merge_option += ['--forced-track', '"0:yes"']
                    else:
                        self.merge_option += ['--default-track', '"0:yes"']
                    self.merge_option += ['"%s"' % item['filepath_merge']]
                else:
                    self.merge_option_etc += ['--language', '"0:%s"' % item['lang']]
                    if item.get('force', False):
                        self.merge_option_etc += ['--forced-track', '"0:yes"']
                    self.merge_option_etc += ['"%s"' % item['filepath_merge']]
                
                self.merge_option_mp4 += ['-map', (idx+1), f'-metadata:s:s:{idx}', f"language={item['lang']}"]

            """
            if self.meta['content_type'] == 'show':
                self.output_filename = u'{title}.S{season_number}E{episode_number}.{quality}p.WEB-DL.{audio_codec}{video_codec}.SW{site}.mkv'.format(
                    title = SupportFile.text_for_filename(self.meta['title']).strip(),
                    season_number = str(self.meta['season_number']).zfill(2),
                    episode_number = str(self.meta['episode_number']).zfill(2),
                    quality = self.download_list['video'][0]['height'],
                    audio_codec = self.audio_codec,
                    video_codec = self.download_list['video'][0]['codec_name'],
                    site = self.name_on_filename,
                )
            else:
                self.output_filename = u'{title}.{quality}p.WEB-DL.{audio_codec}{video_codec}.SW{site}.mkv'.format(
                    title = SupportFile.text_for_filename(self.meta['title']).strip(),
                    quality = self.download_list['video'][0]['height'],
                    audio_codec = self.audio_codec,
                    video_codec = self.download_list['video'][0]['codec_name'],
                    site = self.name_on_filename,
                )
            #logger.warning(self.output_filename)
            self.filepath_output = os.path.join(self.output_dir, self.output_filename)
            #logger.warning(d(self.merge_option + self.merge_option_etc))
            """
            self.merge_option_mp4 += ['-c:v', 'copy', '-c:s', 'copy', self.filepath_last]
            if os.path.exists(self.output_filepath) == False:
                if self.output_format == 'mkv':
                    WVTool.mkvmerge(self.merge_option + self.merge_option_etc)
                elif self.output_format == 'mp4':
                    WVTool.ffmpeg_merge(self.merge_option_mp4)
                shutil.move(self.filepath_last, self.output_filepath)
                #self.add_log(f'파일 생성: {self.output_filename}')
            return True
        except Exception as e: 
            self.logger.error('Exception:%s', e)
            self.logger.error(traceback.format_exc())

        return False


    def download_segment(self, item):
        if self.mpd.base_urls == None:
            prefix = self.mpd_base_url
            headers = self.mpd_headers
        else:
            # 쿠팡만. 다른 url로 요청하기 때문에 host 같은 헤더가 문제 발생
            prefix = self.mpd.base_urls[0].base_url_value
            headers = {}
        url = f"{prefix}{item['segment_templates']['initialization'].replace('&amp;', '&').replace('$RepresentationID$', item['id']).replace('$Bandwidth$', str(item['bandwidth']))}"
        init_filepath = os.path.join(self.temp_dir, f"{self.code}_{item['ct']}_init.m4f")
        WVTool.aria2c_download(url, init_filepath, headers=headers)

        start = 0
        if 'start_number' in item['segment_templates'] and item['segment_templates']['start_number'] is not None:
            start = int(item['segment_templates']['start_number'])
        if item['segment_templates']['segment_timeline']:
            timevalue = 0
            for timeline in item['segment_templates']['segment_timeline']:
                duration = timeline['d']
                repeat = (timeline.get('r') if timeline.get('r') is not None else 0) + 1
                for i in range(0, repeat):
                    url = f"{prefix}{item['segment_templates']['media'].replace('&amp;', '&').replace('$RepresentationID$', item['id']).replace('$Number$', str(start)).replace('$Number%06d$', str(start).zfill(6)).replace('$Bandwidth$', str(item['bandwidth'])).replace('$Time$', str(timevalue))}"
                    filepath = os.path.join(self.temp_dir, f"{self.code}_{item['ct']}_{str(start).zfill(5)}.m4f")
                    WVTool.aria2c_download(url, filepath, headers=headers)
                    timevalue += duration
                    start += 1
        else:
            # 카카오, 쿠팡(.replace('&amp;', '&'))
            for i in range(start, 5000):
                url = f"{prefix}{item['segment_templates']['media'].replace('&amp;', '&').replace('$RepresentationID$', item['id']).replace('$Number$', str(i)).replace('$Number%06d$', str(i).zfill(6)).replace('$Bandwidth$', str(item['bandwidth']))}"
                filepath = os.path.join(self.temp_dir, f"{self.code}_{item['ct']}_{str(i).zfill(5)}.m4f")
                if WVTool.aria2c_download(url, filepath, headers=headers) == False:
                    break
        WVTool.concat(init_filepath, os.path.join(self.temp_dir, f"{self.code}_{item['ct']}_0*.m4f"), item['filepath_download'])


    def clean(self):
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e: 
            self.logger.error(f'Exception:{str(e)}')
            self.logger.error(traceback.format_exc())


    def do_make_key(self):
        try:
            from .manager import WVDecryptManager
            wv = WVDecryptManager(self.pssh)
            widevine_license = requests.post(url=self.license_url, data=wv.get_challenge(), headers=self.config['license_headers'])
            license_b64 = b64encode(widevine_license.content)
            correct, keys = wv.get_result(license_b64)
            if correct:
                for key in keys:
                    tmp = key.split(':')
                    self.key.append({'kid':tmp[0], 'key':tmp[1]})
        except Exception as e: 
            self.logger.error(f'Exception:{str(e)}')
            self.logger.error(traceback.format_exc())


    def get_pssh_mpd(self, text):
        xml = xmltodict.parse(text)
        mpd = json.loads(json.dumps(xml))
        tracks = mpd['MPD']['Period']['AdaptationSet']
        for video_tracks in tracks:
            if video_tracks.get('@mimeType') == 'video/mp4' or video_tracks.get('@contentType') == 'video':
                for t in video_tracks["ContentProtection"]:
                    if t['@schemeIdUri'].lower() == "urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed":
                        if 'cenc:pssh' in t:
                            return t["cenc:pssh"]

        for video_tracks in tracks:
                for t in video_tracks["ContentProtection"]:
                    if t['@schemeIdUri'].lower() == "urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed":
                        if 'cenc:pssh' in t:
                            return t["cenc:pssh"]
                        elif 'ns2:pssh' in t:
                            return t['ns2:pssh']

    def get_pssh_m3u8(self, text):
        tmps = text.split('\n')
        for t in tmps:
            if t.startswith('#EXT-X-KEY:METHOD=SAMPLE-AES') and t.lower().find('urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed') != -1:
                return t.split('base64,')[1].split('"')[0]



    def find_key(self, kid):
        for key in reversed(self.key):
            if kid == key['kid']:
                return key['key']


    def prepare(self):
        pass