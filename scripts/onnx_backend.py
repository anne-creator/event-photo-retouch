"""Independent CPU inference for the attributed ModelScope ONNX model assets.

No third-party adapter source is bundled. RetinaFace prior decoding follows the
published model contract; skin finishing uses the ABPN blend-layer formulation.
"""
from dataclasses import dataclass
from pathlib import Path
import os
import math
import numpy as np
import cv2
import onnxruntime as ort


def model_directory():
    if os.environ.get('EVENT_PHOTO_MODELS'):
        return Path(os.environ['EVENT_PHOTO_MODELS']).expanduser()
    return Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache')))/'event-photo-retouch/models'


def session(path):
    if not Path(path).is_file():
        raise FileNotFoundError(f'Missing model {Path(path).name}; run scripts/download_models.py')
    options=ort.SessionOptions()
    options.intra_op_num_threads=max(1,min(4,os.cpu_count() or 1))
    return ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])


@dataclass
class Face:
    bbox: list
    score: float
    landmarks: list


class FaceDetector:
    def __init__(self, directory=None):
        self.net=session(Path(directory or model_directory())/'face_detector.onnx')

    def detect(self,rgb,threshold=.5):
        h,w=rgb.shape[:2];scale=min(1,1024/max(h,w))
        rh,rw=round(h*scale),round(w*scale)
        small=cv2.resize(rgb,(rw,rh),interpolation=cv2.INTER_LINEAR)
        ph,pw=math.ceil(rh/32)*32,math.ceil(rw/32)*32
        data=np.zeros((1,3,ph,pw),np.float32)
        data[0,:,:rh,:rw]=(small[:,:,::-1].astype(np.float32)/255).transpose(2,0,1)
        values=self.net.run(None,{self.net.get_inputs()[0].name:data})
        names=[o.name for o in self.net.get_outputs()]
        outputs=dict(zip(names,values));loc=outputs['loc'][0];scores=outputs['conf'][0,:,1]
        landmarks=outputs['landms'][0]
        anchors=[]
        for stride,sizes in [(8,(16,32)),(16,(64,128)),(32,(256,512))]:
            for y in range(math.ceil(ph/stride)):
                for x in range(math.ceil(pw/stride)):
                    for size in sizes:anchors.append([(x+.5)*stride/pw,(y+.5)*stride/ph,size/pw,size/ph])
        anchors=np.asarray(anchors,np.float32)
        if len(anchors)!=len(loc):raise ValueError('Detector output does not match pinned prior contract')
        keep=np.flatnonzero(scores>=threshold)
        a=anchors[keep];p=loc[keep]
        center=a[:,:2]+p[:,:2]*.1*a[:,2:]
        size=a[:,2:]*np.exp(p[:,2:]*.2)
        boxes=np.concatenate([center-size/2,center+size/2],axis=1)*np.array([pw,ph,pw,ph])/scale
        points=landmarks[keep].reshape(-1,5,2)
        points=(a[:,None,:2]+points*.1*a[:,None,2:])*np.array([pw,ph])/scale
        order=np.argsort(scores[keep])[::-1];selected=[]
        while order.size:
            k=order[0];selected.append(k)
            if len(order)==1:break
            others=order[1:]
            low=np.maximum(boxes[k,:2],boxes[others,:2]);high=np.minimum(boxes[k,2:],boxes[others,2:])
            wh=np.maximum(high-low,0);intersection=wh[:,0]*wh[:,1]
            sizes=np.maximum(boxes[:,2:]-boxes[:,:2],0);area=sizes[:,0]*sizes[:,1]
            iou=intersection/np.maximum(area[k]+area[others]-intersection,1e-6)
            order=others[iou<=.4]
        return [Face(boxes[k].tolist(),float(scores[keep[k]]),points[k].tolist()) for k in selected]


class SkinRetoucher:
    def __init__(self,model_dir=None,retouch_degree=.3,whitening_degree=0,enable_local=False):
        if whitening_degree or enable_local:raise ValueError('Whitening and generated inpainting are not supported')
        self.directory=Path(model_dir or model_directory());self.degree=retouch_degree
        self.detector=FaceDetector(self.directory)
        self.skin=session(self.directory/'model.onnx')
        self.generator=session(self.directory/'retouch_generator.onnx')

    def _detect_faces(self,rgb):return self.detector.detect(rgb)

    def _run_skin_mask(self,rgb):
        h,w=rgb.shape[:2];factor=min(1,800/max(h,w))
        x=cv2.resize(rgb,(round(w*factor),round(h*factor)),interpolation=cv2.INTER_LINEAR)
        return self.skin.run(None,{self.skin.get_inputs()[0].name:x.astype(np.float32)})[0]

    def retouch(self,bgr):
        if self.degree==0:return bgr.copy()
        rgb=bgr[:,:,::-1].copy();out=rgb.copy();h,w=rgb.shape[:2]
        for face in self._detect_faces(rgb):
            x0,y0,x1,y1=face.bbox;side=max(x1-x0,y1-y0)*1.5
            cx,cy=(x0+x1)/2,(y0+y1)/2
            left,top=max(0,round(cx-side/2)),max(0,round(cy-side/2))
            right,bottom=min(w,round(cx+side/2)),min(h,round(cy+side/2))
            if right<=left or bottom<=top:continue
            crop=rgb[top:bottom,left:right].astype(np.float32)/255
            x=cv2.resize(crop*2-1,(512,512),interpolation=cv2.INTER_LINEAR).transpose(2,0,1)[None]
            layer=self.generator.run(None,{self.generator.get_inputs()[0].name:x})[0][0].transpose(1,2,0)
            layer=np.clip(.5+(layer-.5)*self.degree,0,1)
            layer=cv2.resize(layer,(right-left,bottom-top),interpolation=cv2.INTER_LINEAR)
            yy,xx=np.mgrid[:bottom-top,:right-left]
            edge=np.minimum.reduce([xx/ max((right-left)*.04,1),(right-left-1-xx)/max((right-left)*.04,1),
                                    yy/max((bottom-top)*.04,1),(bottom-top-1-yy)/max((bottom-top)*.04,1)])
            layer=.5+(layer-.5)*np.clip(edge,0,1)[...,None]
            finished=(1-2*layer)*crop*crop+2*layer*crop
            out[top:bottom,left:right]=np.clip(finished*255,0,255).astype(np.uint8)
        return out[:,:,::-1].copy()
