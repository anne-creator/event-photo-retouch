#!/usr/bin/env python3
"""Natural local multi-face skin finish on an already approved lighting render."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from onnx_backend import SkinRetoucher,model_directory
MODELS=model_directory()


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def face_mask(shape,face,skin):
    h,w=shape;x0,y0,x1,y1=face.bbox;fw=x1-x0;fh=y1-y0
    mask=np.zeros((h,w),np.float32)
    cv2.ellipse(mask,(round((x0+x1)/2),round(y0+.53*fh)),
                (max(1,round(.46*fw)),max(1,round(.46*fh))),0,0,360,1,-1)
    mask=cv2.GaussianBlur(mask,(0,0),max(1,.012*fw))*skin
    protected=np.zeros((h,w),np.uint8)
    eyes=np.asarray(face.landmarks[:2],np.float32);nose=np.asarray(face.landmarks[2],np.float32)
    mouth=np.asarray(face.landmarks[3:5],np.float32)
    # Preserve eyes, glasses/eyebrow band, nose contours, lips and teeth.
    a=(max(0,round(x0-.02*fw)),max(0,round(eyes[:,1].min()-.12*fh)))
    b=(min(w-1,round(x1+.02*fw)),min(h-1,round(eyes[:,1].max()+.07*fh)))
    cv2.rectangle(protected,a,b,1,-1)
    cv2.ellipse(protected,tuple(np.rint(nose).astype(int)),
                (max(1,round(.085*fw)),max(1,round(.09*fh))),0,0,360,1,-1)
    cv2.ellipse(protected,tuple(np.rint(mouth.mean(axis=0)).astype(int)),
                (max(1,round(abs(mouth[1,0]-mouth[0,0])*.65+.025*fw)),max(1,round(.06*fh))),0,0,360,1,-1)
    feather=cv2.GaussianBlur(protected.astype(np.float32),(0,0),max(1,.01*fw))
    mask*=1-feather
    mask[protected>0]=0
    return np.clip(mask,0,1),protected


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--strength',type=float,default=.3)
    args=p.parse_args()
    if not 0<=args.strength<=.5:raise ValueError('Natural finish strength must be between 0 and .5')
    args.output.mkdir(parents=True,exist_ok=True);report=[]
    retoucher=SkinRetoucher(model_dir=str(MODELS),retouch_degree=args.strength,whitening_degree=0,enable_local=False)
    weights={n:sha(MODELS/n) for n in ['model.onnx','retouch_generator.onnx','face_detector.onnx']}
    for job in json.loads(args.manifest.read_text())['jobs']:
        if Path(job['stem']).name!=job['stem'] or job['stem'] in ('','.','..'):
            raise ValueError('Job stem must be a plain filename without directories')
        src=Path(job['source']);stem=args.output/job['stem'];png=Path(str(stem)+'.png');jpg=Path(str(stem)+'.jpg')
        if png.exists() or jpg.exists():raise ValueError('Choose a separate versioned output directory')
        source_hash=sha(src)
        with Image.open(src) as im:rgb=np.asarray(im.convert('RGB'));icc=im.info.get('icc_profile')
        faces=retoucher._detect_faces(rgb)
        eligible=[f for f in faces if min(f.bbox[2]-f.bbox[0],f.bbox[3]-f.bbox[1])>=100 and f.score>=.8]
        mask=np.zeros(rgb.shape[:2],np.float32);protected=np.zeros(rgb.shape[:2],np.uint8)
        if eligible:
            raw=retoucher._run_skin_mask(rgb)
            if raw.ndim!=2:raise ValueError('Unexpected skin segmentation contract')
            skin=cv2.resize(raw.astype(np.float32)/255,(rgb.shape[1],rgb.shape[0]),interpolation=cv2.INTER_LINEAR)
            skin=np.clip((skin-.15)/.7,0,1)
            for f in eligible:
                m,pr=face_mask(rgb.shape[:2],f,skin);mask=np.maximum(mask,m);protected=np.maximum(protected,pr)
            mask[protected>0]=0
            detect=retoucher._detect_faces
            try:
                retoucher._detect_faces=lambda image:eligible
                prediction=retoucher.retouch(rgb[:,:,::-1].copy())[:,:,::-1]
            finally:retoucher._detect_faces=detect
            delta=prediction.astype(np.float32)-rgb.astype(np.float32)
            # Keep the approved lighting/color: retain skin texture correction,
            # suppress slow exposure changes, and bound any channel adjustment.
            slow=cv2.GaussianBlur(delta,(0,0),max(2,min(rgb.shape[:2])/160))
            delta=np.clip(delta-.8*slow,-10,10)
            result=np.clip(np.rint(rgb.astype(np.float32)+delta*mask[...,None]),0,255).astype(np.uint8)
        else:result=rgb.copy()
        result=np.where(rgb<255,np.minimum(result,254),result).astype(np.uint8)
        Image.fromarray(result).save(png,icc_profile=icc)
        Image.fromarray(result).save(jpg,quality=97,subsampling=0,icc_profile=icc)
        Image.fromarray(np.rint(mask*255).astype(np.uint8)).save(Path(str(stem)+'_skin-mask.png'))
        outside=mask==0;difference=np.abs(result.astype(int)-rgb.astype(int))
        record=dict(file=job['stem'],source=str(src),source_sha256=source_hash,output=str(png),jpg=str(jpg),
                    strength=args.strength,whitening=0,local_inpainting=False,faces_detected=len(faces),
                    retouched_faces=len(eligible),skipped_faces=len(faces)-len(eligible),size=list(Image.open(png).size),
                    face_boxes=[list(map(float,f.bbox)) for f in eligible],
                    outside_skin_mask_exact=bool(np.array_equal(result[outside],rgb[outside])),
                    protected_features_exact=bool(np.array_equal(result[protected>0],rgb[protected>0])),
                    source_hash_unchanged=sha(src)==source_hash,changed_pixels=int(np.any(difference>0,axis=2).sum()),
                    max_channel_change=int(difference.max()),output_sha256=sha(png),model_weights=weights,
                    status='local_finish_pending_visual_review' if eligible else 'lighting_copy_small_faces_skipped')
        if not all([record['outside_skin_mask_exact'],record['protected_features_exact'],record['source_hash_unchanged']]):
            raise ValueError('Skin/feature preservation check failed')
        Path(str(stem)+'.json').write_text(json.dumps(record,ensure_ascii=False,indent=2));report.append(record)
        print(json.dumps({'file':job['stem'],'retouched_faces':len(eligible),'skipped':len(faces)-len(eligible),'changed_pixels':record['changed_pixels']},ensure_ascii=False),flush=True)
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'photos':len(report),'retouched_faces':sum(r['retouched_faces'] for r in report)},ensure_ascii=False))


if __name__=='__main__':main()
