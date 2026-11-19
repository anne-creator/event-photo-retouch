"""Download the attributed, checksum-pinned ONNX release assets."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import shutil
import tempfile
import urllib.request


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.add_argument('--from-dir',type=Path)
    a=p.parse_args();root=Path(__file__).resolve().parent.parent
    target=Path(os.environ.get('EVENT_PHOTO_MODELS',str(Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'event-photo-retouch/models'))).expanduser()
    target.mkdir(parents=True,exist_ok=True);manifest=json.loads((root/'models.json').read_text())
    for model in manifest['files']:
        path=target/model['name']
        if path.exists() and digest(path)==model['sha256']:continue
        if a.check:raise SystemExit(f'Missing or invalid model: {model["name"]}')
        fd,temporary=tempfile.mkstemp(prefix=path.name+'.',suffix='.download',dir=target)
        os.close(fd);temp=Path(temporary)
        try:
            if a.from_dir:shutil.copyfile(a.from_dir/model['name'],temp)
            else:
                print('Downloading '+model['name'],flush=True)
                req=urllib.request.Request(model['url'],headers={'User-Agent':'event-photo-retouch/0.2.0'})
                with urllib.request.urlopen(req,timeout=90) as response,temp.open('wb') as out:
                    shutil.copyfileobj(response,out,1024*1024)
            if digest(temp)!=model['sha256']:raise ValueError('Model checksum mismatch: '+model['name'])
            os.replace(temp,path)
        finally:
            if temp.exists():temp.unlink()
    print(json.dumps({'models':'verified','directory':str(target),'count':len(manifest['files'])}))


if __name__=='__main__':main()
