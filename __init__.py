import os, sys, platform
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

plugin_info = {
    'version' : '1.0.0.0',
    'name' : __name__.split('.')[0],
    'category' : 'library',
    'developer' : 'soju6jan',
    'description' : 'DRM 영상 다운로드에 사용하는 라이브러리.<br>외부 유출 금지',
    'home' : f'https://github.com/soju6jan',
    'policy_level' : 5,
}

try:
    from Cryptodome.Random import get_random_bytes
except:
    os.system('pip install pycryptodomex')

try:
    if platform.system() == 'Linux':
        bin_path = os.path.join(os.path.dirname(__file__), 'bin', 'Linux')
        os.system(f"chmod 777 -R {bin_path}")
except:
    pass        

from .manager import WVDecryptManager
from .tool import WVTool
from .downloader import WVDownloader
from .ffmpeg import Ffmpeg
