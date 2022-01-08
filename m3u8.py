import os, sys, traceback, requests, shutil, json, xmltodict, time, re

from requests.sessions import default_headers
from base64 import b64encode, b64decode
from support.base import get_logger, d
from support.base.file import SupportFile
from .tool import WVTool

class Downloader_m3u8:
    default_headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'accept-language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
    }

    def __init__(self, config):
        self.config = config

        self.url = config['url']
        self.code = config.get('code', str(int(time.time())))
        self.logger = config.get('logger', get_logger(self.__class__.__name__))
        self.download_list = []
        self.headers = config.get('headers', self.default_headers)

        tmp = self.config.get('folder_tmp', os.path.join(os.getcwd(), 'tmp'))
        self.temp_dir = os.path.join(tmp, self.code)
        #os.makedirs(self.temp_dir, exist_ok=True)
        
        self.output_filepath = config.get('output_filepath')
        if self.output_filepath == None:
            output_dir = self.config.get('folder_output', os.path.join(os.getcwd(), 'output'))
            output_filename = config.get('output_filename', f"{self.code}.mkv")
            self.output_filepath = os.path.join(output_dir, output_filename)
        #os.makedirs(os.path.dirname(self.output_filepath), exist_ok=True)


    def download(self):
        try:
            #self.logger.debug(u'공통 처리')
            if os.path.exists(self.output_filepath):
                self.logger.debug(f"{self.output_filepath} FILE EXIST")
                return
            os.makedirs(self.temp_dir, exist_ok=True)
            os.makedirs(os.path.dirname(self.output_filepath), exist_ok=True)
            self.prepare()
            ret = self.download_m3u8()
            #self.clean()
            return True
        except Exception as e: 
            self.logger.error(f'Exception:{str(e)}')
            self.logger.error(traceback.format_exc())
        finally:
            #self.logger.info("다운로드 종료")
            pass
        return False
    

    def download_m3u8(self):
        try:
            m3u8_base_url = None

            current_url = self.config['url']
            data = requests.get(current_url, headers=self.headers).text
            m3u8_base_url = current_url[:current_url.rfind('/')+1]

            if 'BANDWIDTH' in data:
                current_bandwidth = 0
                current_url = None
                for line in data.split('\n'):
                    self.logger.warning(line)
                    if 'BANDWIDTH' in line:
                        match = re.search(r'BANDWIDTH=(\d+)', line)
                        if match:
                            bandwidth = int(match.group(1))
                            if bandwidth > current_bandwidth:
                                current_url = None
                    if line.startswith('#') or line.strip() == '':
                        continue
                    if current_url == None:
                        current_url = line
                        if line.startswith('http') == False:
                            current_url = m3u8_base_url + line

                data = requests.get(current_url, headers=self.headers).text
            
            self.logger.debug(current_url)

            url_list = []
            for line in data.split('\n'):
                if line.startswith('#') == False:
                    if line.startswith('http') == False:
                        url_list.append(m3u8_base_url + line)
                    else:
                        url_list.append(line)

            self.logger.debug(url_list)
            for idx, url in enumerate(url_list):
                filepath = os.path.join(self.temp_dir, f"{self.code}_video_{str(idx).zfill(5)}.ts")
                self.logger.debug(filepath)
                WVTool.aria2c_download(url, filepath)
            #dummy_filepath = os.path.join(self.temp_dir, f"{self.code}_video_dummy.ts")
            #ToolFile.write_file(dummy_filepath, '')
            WVTool.concat(None, os.path.join(self.temp_dir, f"{self.code}_video_0*.ts"), self.output_filepath)
                
            return True
        except Exception as e: 
            self.logger.error('Exception:%s', e)
            self.logger.error(traceback.format_exc())


    def clean(self):
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e: 
            self.logger.error(f'Exception:{str(e)}')
            self.logger.error(traceback.format_exc())
   

    def prepare(self):
        pass