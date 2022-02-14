import os, traceback, shutil, json, time, re

from requests.sessions import default_headers
from base64 import b64encode, b64decode
from support.base import get_logger, d
from support.base.file import SupportFile
from support.base.string import SupportString
from .tool import WVTool, FFMPEG

from datetime import datetime
import threading, subprocess, platform

logger = get_logger()


class Ffmpeg(object):
    instance_list = []
    idx = 1

    def __init__(self, url, filename, plugin_id=None, listener=None, max_pf_count=0, call_plugin=None, temp_path=None, save_path=None, proxy=None, headers=None, is_mp3=False):
        self.thread = None
        self.url = url
        self.filename = filename
        self.plugin_id = plugin_id
        self.listener = listener
        self.max_pf_count = max_pf_count
        self.call_plugin = call_plugin
        self.process = None
        self.temp_path = temp_path
        if self.temp_path == None:
            self.temp_path = os.path.join(os.getcwd(), 'tmp')

        self.save_path = save_path
        self.proxy = proxy
        self.temp_fullpath = os.path.join(self.temp_path, filename)
        self.save_fullpath = os.path.join(self.save_path, filename)
        self.log_thread = None
        self.status = "READY"
        self.duration = 0
        self.duration_str = ''
        self.current_duration = 0
        self.percent = 0
        self.current_pf_count = 0
        self.idx = str(Ffmpeg.idx)
        Ffmpeg.idx += 1
        self.current_bitrate = ''
        self.current_speed = ''
        self.start_time = None
        self.end_time = None
        self.download_time = None
        self.start_event = threading.Event()
        self.exist = False
        self.filesize = 0
        self.filesize_str = ''
        self.download_speed = ''
        self.headers = headers
        self.is_mp3 = is_mp3

        
    def start(self):
        self.thread = threading.Thread(target=self.thread_fuction, args=())
        self.thread.start()
        self.start_time = datetime.now()
        return self.get_data()
    
    def start_and_wait(self):
        self.start()
        self.thread.join(timeout=60*70)
        return self.get_data()

    def stop(self):
        try:
            self.status = "USER_STOP"
            self.kill()
        except Exception as exception:
            logger.error('Exception:%s', exception)
            logger.error(traceback.format_exc())
    
    def kill(self):
        try:
            if self.process is not None and self.process.poll() is None:
                import psutil
                process = psutil.Process(self.process.pid)
                for proc in process.children(recursive=True):
                    proc.kill()
                process.kill()
        except Exception as exception:
            logger.error('Exception:%s', exception)
            logger.error(traceback.format_exc())
            

    def thread_fuction(self):
        try:
            if os.path.exists(self.save_fullpath):
                self.status = "ALREADY_DOWNLOADING"
                return

            if self.proxy is None:
                if self.headers is None:
                    
                    command = [FFMPEG, '-y', '-i', self.url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc']
                else:
                    headers_command = []
                    for key, value in self.headers.items():
                        if key.lower() == 'user-agent':
                            headers_command.append('-user_agent')
                            headers_command.append(value)
                            
                        else:
                            headers_command.append('-headers')
                            if platform.system() == 'Windows':
                                headers_command.append('\'%s:%s\''%(key,value))
                            else:
                                headers_command.append(f'{key}:{value}')
                    command = [FFMPEG, '-y'] + headers_command + ['-i', self.url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc']
            else:
                command = [FFMPEG, '-y', '-http_proxy', self.proxy, '-i', self.url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc']

            if platform.system() == 'Windows':
                now = str(datetime.now()).replace(':', '').replace('-', '').replace(' ', '-')
                filename = ('%s' % now) + '.mp4'
                if self.is_mp3:
                    filename = filename.replace('.mp4', '.mp3')
                self.temp_fullpath = os.path.join(self.temp_path, filename)
                command.append(self.temp_fullpath)
            else:
                command.append(self.temp_fullpath)
                
            
            if self.is_mp3:
                new_command = []
                for tmp in command:
                    if tmp not in ['-bsf:a', 'aac_adtstoasc']:
                        new_command.append(tmp)
                command = new_command
            logger.warning(' '.join(command))
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf8')

            self.status = "READY"
            self.log_thread = threading.Thread(target=self.log_thread_fuction, args=())
            self.log_thread.start()
            self.start_event.wait(timeout=60)

            if self.log_thread is None:
                if self.status == "READY":
                    self.status = "ERROR"
                self.kill()
            elif self.status == "READY":
                self.status = "ERROR"
                self.kill()
            else:
                process_ret = self.process.wait(timeout=60*60)
                if process_ret is None:
                    if self.status != "COMPLETED" and self.status != "USER_STOP" and self.status != "PF_STOP":
                        self.status = "TIME_OVER"
                        self.kill()
                else:
                    if self.status == "DOWNLOADING":
                        self.status = "FORCE_STOP"
            self.end_time = datetime.now()
            self.download_time = self.end_time - self.start_time
            try:
                if self.status == "COMPLETED":
                    os.makedirs(self.save_path, exist_ok=True)
                    shutil.move(self.temp_fullpath, self.save_fullpath)
                    self.filesize = os.stat(self.save_fullpath).st_size
                else:
                    if os.path.exists(self.temp_fullpath):
                        os.remove(self.temp_fullpath)
            except Exception as exception:
                logger.error('Exception:%s', exception)
                logger.error(traceback.format_exc())

            arg = {'type':'last', 'status':self.status, 'data' : self.get_data()}
            self.send_to_listener(**arg)
            self.process = None
            self.thread = None

        except Exception as exception:
            logger.error('Exception:%s', exception)
            logger.error(traceback.format_exc())
            try:
                self.status = "EXCEPTION"
                arg = {'type':'last', 'status':self.status, 'data' : self.get_data()}
                self.send_to_listener(**arg)
            except Exception as exception:
                logger.error('Exception:%s', exception)
                logger.error(traceback.format_exc())
            

    def log_thread_fuction(self):
        with self.process.stdout:
            iter_arg =  ''
            for line in iter(self.process.stdout.readline, iter_arg):
                print(line)
                try:
                    if self.status == "READY":
                        if line.find('Server returned 404 Not Found') != -1 or line.find('Unknown error') != -1:
                            self.status = "WRONG_URL"
                            self.start_event.set()
                        elif line.find('No such file or directory') != -1:
                            self.status = "WRONG_DIRECTORY"
                            self.start_event.set()
                        else:
                            match = re.compile(r'Duration\:\s(\d{2})\:(\d{2})\:(\d{2})\.(\d{2})\,\sstart').search(line)
                            if match:
                                self.duration_str = '%s:%s:%s' % ( match.group(1), match.group(2), match.group(3))
                                self.duration = int(match.group(4))
                                self.duration += int(match.group(3)) * 100
                                self.duration += int(match.group(2)) * 100 * 60
                                self.duration += int(match.group(1)) * 100 * 60 * 60
                                if match:
                                    self.status = "READY"
                                    arg = {'type':'status_change', 'status':self.status, 'data' : self.get_data()}
                                    self.send_to_listener(**arg)
                                continue
                            match = re.compile(r'time\=(\d{2})\:(\d{2})\:(\d{2})\.(\d{2})\sbitrate\=\s*(?P<bitrate>\d+).*?[$|\s](\s?speed\=\s*(?P<speed>.*?)x)?').search(line)
                            if match:
                                self.status = "DOWNLOADING"
                                arg = {'type':'status_change', 'status':self.status, 'data' : self.get_data()}
                                self.send_to_listener(**arg)
                                self.start_event.set()
                    elif self.status == "DOWNLOADING":
                        if line.find('PES packet size mismatch') != -1:
                            self.current_pf_count += 1
                            if self.current_pf_count > self.max_pf_count:
                                self.status = "PF_STOP"
                                self.kill()
                            continue
                        if line.find('HTTP error 403 Forbidden') != -1:
                            self.status = "HTTP_FORBIDDEN"
                            self.kill()
                            continue
                        match = re.compile(r'time\=(\d{2})\:(\d{2})\:(\d{2})\.(\d{2})\sbitrate\=\s*(?P<bitrate>\d+).*?[$|\s](\s?speed\=\s*(?P<speed>.*?)x)?').search(line)
                        if match: 
                            self.current_duration = int(match.group(4))
                            self.current_duration += int(match.group(3)) * 100
                            self.current_duration += int(match.group(2)) * 100 * 60
                            self.current_duration += int(match.group(1)) * 100 * 60 * 60
                            try:
                                self.percent = int(self.current_duration * 100 / self.duration)
                            except Exception as exception:
                                logger.error('Exception:%s', exception)
                                logger.error(traceback.format_exc())
                                
                            self.current_bitrate = match.group('bitrate')
                            self.current_speed = match.group('speed')
                            self.download_time = datetime.now() - self.start_time
                            arg = {'type':'normal', 'status':self.status, 'data' : self.get_data()}
                            self.send_to_listener(**arg)
                            continue
                        match = re.compile(r'video\:\d*kB\saudio\:\d*kB').search(line)
                        if match:
                            self.status = "COMPLETED"
                            self.end_time = datetime.now()
                            self.download_time = self.end_time - self.start_time
                            self.percent = 100
                            arg = {'type':'status_change', 'status':self.status, 'data' : self.get_data()}
                            self.send_to_listener(**arg)
                            continue

                except Exception as exception:
                    logger.error('Exception:%s', exception)
                    logger.error(traceback.format_exc())
        self.start_event.set()
        self.log_thread = None
        
    def get_data(self):
        data = {
            'url' : self.url,
            'filename' : self.filename,
            'max_pf_count' : self.max_pf_count,
            'call_plugin' : self.call_plugin,
            'temp_path' : self.temp_path,
            'save_path' : self.save_path,
            'temp_fullpath' : self.temp_fullpath,
            'save_fullpath' : self.save_fullpath,
            'status' : self.status,
            'duration' : self.duration,
            'duration_str' : self.duration_str,
            'current_duration' : self.current_duration,
            'percent' : self.percent,
            'current_pf_count' : self.current_pf_count,
            'idx' : self.idx,
            'current_bitrate' : self.current_bitrate,
            'current_speed' : self.current_speed,
            'start_time' : '' if self.start_time is None else str(self.start_time).split('.')[0][5:],
            'end_time' : '' if self.end_time is None else str(self.end_time).split('.')[0][5:],
            'download_time' : '' if self.download_time is None else '%02d:%02d' % (self.download_time.seconds/60, self.download_time.seconds%60),
            'exist' : os.path.exists(self.save_fullpath),
        }                        
        if self.status == "COMPLETED":
            data['filesize'] = self.filesize
            data['filesize_str'] = SupportString.human_size(self.filesize)
            if self.download_time.seconds != 0:
                data['download_speed'] = SupportString.human_size(self.filesize/self.download_time.seconds, suffix='Bytes/Second')
            else:
                data['download_speed'] = '--'
        return data

    def send_to_listener(self, **arg):
        if self.listener is not None:
            arg['plugin_id'] = self.plugin_id
            self.listener(**arg)          

