from pywidevine.decrypt.wvdecryptcustom import WvDecrypt
from pywidevine.cdm import deviceconfig

class WVDecryptManager:
    version = '1.0'
   
    def __init__(self, pssh):
        self.wvdecrypt = WvDecrypt(init_data_b64=pssh, cert_data_b64=None, device=deviceconfig.device_android_generic)

    def get_challenge(self):
        return self.wvdecrypt.get_challenge()
    
    def get_result(self, license):
        self.wvdecrypt.update_license(license)
        return self.wvdecrypt.start_process()

    