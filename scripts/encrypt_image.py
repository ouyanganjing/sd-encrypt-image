
import base64
import io
from pathlib import Path
from modules import shared,script_callbacks,scripts as md_scripts
from modules.api import api
from modules.shared import opts
from scripts.core.core import encrypt_image,get_sha256,dencrypt_image
from PIL import PngImagePlugin,_util
from PIL import Image as PILImage
from io import BytesIO
from typing import Optional
from fastapi import FastAPI
from gradio import Blocks
from fastapi import FastAPI, Request, Response
import sys

repo_dir = md_scripts.basedir()
password = getattr(shared.cmd_opts, 'encrypt_pass', None)

if PILImage.Image.__name__ != 'EncryptedImage':
    super_open = PILImage.open
    super_encode_pil_to_base64 = api.encode_pil_to_base64
    
    class EncryptedImage(PILImage.Image):
        __name__ = "EncryptedImage"
        def save(self, fp, format=None, **params):
            filename = ""
            if isinstance(fp, Path):
                filename = str(fp)
            elif _util.is_path(fp):
                filename = fp
            elif fp == sys.stdout:
                try:
                    fp = sys.stdout.buffer
                except AttributeError:
                    pass
            if not filename and hasattr(fp, "name") and _util.is_path(fp.name):
                # only set the name for metadata purposes
                filename = fp.name
            
            if not filename or not password:
                # 如果没有密码或不保存到硬盘，直接保存
                super().save(fp, format = format, **params)
                return
            
            if 'Encrypt' in self.info and self.info['Encrypt'] == 'pixel_shuffle':
                super().save(fp, format = format, **params)
                return
            
            encrypt_image(self, get_sha256(password))
            self.format = PngImagePlugin.PngImageFile.format
            if self.info:
                self.info['Encrypt'] = 'pixel_shuffle'
            pnginfo = params.get('pnginfo', PngImagePlugin.PngInfo())
            pnginfo.add_text('Encrypt', 'pixel_shuffle')
            params.update(pnginfo=pnginfo)
            super().save(fp, format=self.format, **params)

            
    def open(fp,*args, **kwargs):
        image = super_open(fp,*args, **kwargs)
        if password and image.format.lower() == PngImagePlugin.PngImageFile.format.lower():
            pnginfo = image.info or {}
            if 'Encrypt' in pnginfo and pnginfo["Encrypt"] == 'pixel_shuffle':
                dencrypt_image(image, get_sha256(password))
                pnginfo["Encrypt"] = None
                return image
        return image
    
    def encode_pil_to_base64(image:PILImage.Image):
        with io.BytesIO() as output_bytes:
            image.save(output_bytes, format="PNG", quality=opts.jpeg_quality)
            pnginfo = image.info or {}
            
            if 'Encrypt' in pnginfo and pnginfo["Encrypt"] == 'pixel_shuffle':
                dencrypt_image(image,get_sha256(password))
                pnginfo["Encrypt"] = None
            bytes_data = output_bytes.getvalue()
        return base64.b64encode(bytes_data)
    
    if password:
        PILImage.Image = EncryptedImage
        PILImage.open = open
        api.encode_pil_to_base64 = encode_pil_to_base64
        

def on_app_started(demo: Optional[Blocks], app: FastAPI):
    @app.middleware("http")
    async def image_dencrypt(req: Request, call_next):
        endpoint:str = req.scope.get('path', 'err')
        if endpoint.startswith('/file='):
            file_path = endpoint[6:]
            ex = file_path[file_path.rindex('.'):].lower()
            if ex in ['.png','.jpg','.jpeg','.webp','.abcd']:
                image = PILImage.open(file_path)
                if image.format.lower() == PngImagePlugin.PngImageFile.format.lower():
                    pnginfo = image.info or {}
                    if 'Encrypt' in pnginfo:
                        buffered = BytesIO()
                        image.save(buffered, format=PngImagePlugin.PngImageFile.format)
                        decrypted_image_data = buffered.getvalue()
                        response: Response = Response(content=decrypted_image_data, media_type="image/png")
                        return response
        res: Response = await call_next(req)
        return res

if password:
    script_callbacks.on_app_started(on_app_started)
    print('图片加密已经启动 加密方式 1')
else:
    print('图片加密插件已安装，但缺少密码参数未启动')