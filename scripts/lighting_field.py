#!/usr/bin/env python3
"""Apply a model-guided low-frequency light/color field to original photo pixels."""
import argparse
import hashlib
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageCms, ImageOps

VERSION = '0.2.0'
DEFAULTS = dict(strength=1.0, grid_long_side=960, base_sigma=10, gain_sigma=6,
                ratio_min=0.05, ratio_max=4.0, white_start=0.84, white_end=0.97,
                white_blur_relative=5/3840, white_protection=0.35,
                soft_headroom=True, regions=[],emitter_regions=[],identity_regions=[],
                medium_weight=.35,medium_sigma=4,auto_identity=True,
                artifact_mask=None,artifact_strength=.7,artifact_radius=9)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_srgb(path):
    path=Path(path)
    if path.suffix.lower() in ('.heic','.heif'):
        import pillow_heif
        heif=pillow_heif.open_heif(path,convert_hdr_to_8bit=False)
        info=heif.info;nclx=info.get('nclx_profile') or {}
        if info.get('bit_depth',8)!=8 or nclx.get('transfer_characteristics') in (16,18):
            raise ValueError('High-bit-depth/HDR input needs an explicit SDR development before this pipeline')
        if not info.get('icc_profile') and nclx.get('color_primaries',2) not in (1,2):
            raise ValueError('HEIF wide-gamut NCLX without ICC needs explicit sRGB conversion')
        pillow_heif.register_heif_opener()
    with path.open('rb') as header:
        first=header.read(25)
    if first[:8]==b'\x89PNG\r\n\x1a\n' and first[24]>8:
        raise ValueError('High-bit-depth PNG needs explicit SDR development')
    with Image.open(path) as opened:
        if opened.mode in ('I','F','I;16','RGB;16','RGBA;16'):
            raise ValueError('Only 8-bit SDR inputs are supported')
        im = ImageOps.exif_transpose(opened)
        profile = im.info.get('icc_profile')
        description = 'untagged, interpreted as sRGB'
        if profile:
            inp = ImageCms.ImageCmsProfile(io.BytesIO(profile))
            description = ImageCms.getProfileDescription(inp).strip()
            if 'srgb' not in description.lower():
                im = ImageCms.profileToProfile(im.convert('RGB'), inp,
                                               ImageCms.createProfile('sRGB'), outputMode='RGB')
        return np.asarray(im.convert('RGB'), np.float32) / 255, description


def decode(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92*x, 1.055*x**(1/2.4)-0.055)


def smooth(x):
    x = np.clip(x, 0, 1)
    return x*x*(3-2*x)


def config_valid(config):
    if not 0 <= config['strength'] <= 1 or not 0 <= config['white_protection'] <= 1:
        raise ValueError('strength and white_protection must be between 0 and 1')
    if not 0 < config['ratio_min'] <= 1 <= config['ratio_max']:
        raise ValueError('ratio bounds must include 1')
    if config['grid_long_side'] < 128 or config['base_sigma'] < 4 or config['gain_sigma'] < 2:
        raise ValueError('Field must remain low frequency')
    if not 0 <= config['white_start'] < config['white_end'] <= 1:
        raise ValueError('Invalid white protection thresholds')
    if not 0<=config['medium_weight']<=1 or config['medium_sigma']<1:
        raise ValueError('Invalid medium-scale lighting controls')
    if not 0<=config['artifact_strength']<=1 or not 1<=config['artifact_radius']<=100:
        raise ValueError('Invalid source illumination repair controls')
    for rect in config['emitter_regions']+config['identity_regions']:
        if len(rect)!=4 or not 0<=rect[0]<rect[2]<=1 or not 0<=rect[1]<rect[3]<=1:
            raise ValueError('Emitter/identity regions must be normalized rectangles')
    for r in config['regions']:
        x0, y0, x1, y1 = r['xyxy']
        if not 0 <= x0 < x1 <= 1 or not 0 <= y0 < y1 <= 1:
            raise ValueError('Region coordinates must be normalized rectangles')
        if not 0 <= r['strength'] <= 1 or not 0 < r.get('feather', 0.04) <= 1:
            raise ValueError('Invalid region strength or feather')


def make_field(source, reference, config):
    h, w = source.shape[:2]
    long_side = config['grid_long_side']
    grid = (max(1, round(w*long_side/max(w,h))), max(1, round(h*long_side/max(w,h))))
    a = cv2.resize(source, grid, interpolation=cv2.INTER_AREA)
    b = cv2.resize(reference, grid, interpolation=cv2.INTER_AREA)
    fine_a=cv2.GaussianBlur(a,(0,0),config['medium_sigma'])
    fine_b=cv2.GaussianBlur(b,(0,0),config['medium_sigma'])
    a = cv2.GaussianBlur(a, (0,0), config['base_sigma'])
    b = cv2.GaussianBlur(b, (0,0), config['base_sigma'])
    field = np.log(np.clip((b+0.005)/(a+0.005), config['ratio_min'], config['ratio_max']))
    field=cv2.GaussianBlur(field,(0,0),config['gain_sigma'])
    medium=np.log(np.clip((fine_b+.005)/(fine_a+.005),config['ratio_min'],config['ratio_max']))-field
    medium=cv2.GaussianBlur(np.clip(medium,-.7,.7),(0,0),2)
    allowed=np.ones(field.shape[:2],np.float32)
    for rect in config['identity_regions']:
        allowed*=1-rectangle_mask(allowed.shape,rect,.025)
    return field+config['medium_weight']*medium*allowed[...,None]


def rectangle_mask(shape,rect,feather=.03):
    h,w=shape;y,x=np.mgrid[:h,:w].astype(np.float32)
    x/=max(w-1,1);y/=max(h-1,1)
    x0,y0,x1,y1=rect;f=max(feather,1e-5)
    m=np.ones(shape,np.float32)
    for c,e,sign,active in [(x,x0,1,x0>0),(x,x1,-1,x1<1),(y,y0,1,y0>0),(y,y1,-1,y1<1)]:
        if active:m*=smooth(sign*(c-e)/f)
    return m


def artifact_correction(source,mask_path,strength,radius):
    mask=np.asarray(Image.open(mask_path).convert('L'))
    if mask.shape!=source.shape[:2]:raise ValueError('Artifact mask must match oriented original dimensions')
    hard=(mask>32).astype(np.uint8)
    if hard.mean()>.5:raise ValueError('Artifact repair mask is too broad; use localized illumination regions')
    log_base=cv2.GaussianBlur(np.log(np.maximum(source,1e-4)),(0,0),1.0)
    repaired=np.stack([cv2.inpaint(log_base[:,:,k],hard, radius,cv2.INPAINT_NS) for k in range(3)],axis=2)
    alpha=cv2.GaussianBlur(mask.astype(np.float32)/255,(0,0),1.0)*strength
    # Only an illumination gain is estimated from neighboring source pixels.
    # No generated image content is imported, and no image coordinates move.
    return source*np.exp(np.clip(repaired-log_base,-1.6,1.0)*alpha[...,None])


def apply_field(source, small_field, config):
    h, w = source.shape[:2]
    gh, gw = small_field.shape[:2]
    y, x = np.mgrid[0:gh, 0:gw].astype(np.float32)
    x /= max(gw-1,1); y /= max(gh-1,1)
    strength = np.full((gh,gw), config['strength'], np.float32)
    for r in config['regions']:
        x0,y0,x1,y1 = r['xyxy']; f = r.get('feather',0.04)
        mask = np.ones((gh,gw),np.float32)
        for coordinate, edge, sign, active in [(x,x0,1,x0>0),(x,x1,-1,x1<1),
                                                (y,y0,1,y0>0),(y,y1,-1,y1<1)]:
            if active: mask *= smooth(sign*(coordinate-edge)/f)
        strength = strength*(1-mask) + r['strength']*mask
    field = cv2.resize(small_field, (w,h), interpolation=cv2.INTER_CUBIC)
    strength = cv2.resize(strength, (w,h), interpolation=cv2.INTER_LINEAR)
    luminance = source @ np.array([.2126,.7152,.0722],np.float32)
    white = smooth((luminance-config['white_start'])/(config['white_end']-config['white_start']))
    sigma = max(0.5, config['white_blur_relative']*max(w,h))
    white = cv2.GaussianBlur(white,(0,0),sigma)
    emitter=np.zeros((h,w),np.float32)
    for rect in config['emitter_regions']:emitter=np.maximum(emitter,rectangle_mask((h,w),rect,.012))
    protection=config['white_protection']+(0.985-config['white_protection'])*emitter
    applied = field*(strength*(1-protection*white))[...,None]
    target = source*np.exp(applied)
    if config['artifact_mask']:
        target=artifact_correction(target,config['artifact_mask'],config['artifact_strength'],config['artifact_radius'])
    if config['soft_headroom']:
        headroom = np.maximum(1-source, 1e-6)
        lifted = source+headroom*(-np.expm1(-np.maximum(target-source,0)/headroom))
        target = np.where(target>source,lifted,target)
    # Retain the last available code level in channels not clipped in the source.
    # Floating-point headroom alone can otherwise round newly lifted pixels to 255.
    quantized_white_threshold = ((254.5/255+0.055)/1.055)**2.4
    last_unclipped_code = ((254/255+0.055)/1.055)**2.4
    target = np.where(source < quantized_white_threshold,
                      np.minimum(target,last_unclipped_code),target)
    return np.clip(target,0,1)


def render(source_path, reference_path, output_stem, config):
    source_path=Path(source_path).resolve(); reference_path=Path(reference_path).resolve()
    stem=Path(output_stem).resolve(); png=Path(str(stem)+'.png'); jpg=Path(str(stem)+'.jpg')
    receipt=Path(str(stem)+'.json'); field_path=Path(str(stem)+'.field.npz')
    if source_path in [png,jpg] or reference_path in [png,jpg]:
        raise ValueError('Output must be separate from source and reference')
    config=dict(DEFAULTS,**config);config_valid(config)
    if config['artifact_mask']:config['artifact_mask']=str(Path(config['artifact_mask']).resolve())
    original_hash=digest(source_path);reference_hash=digest(reference_path)
    dependencies=[digest(Path(__file__)),digest(Path(__file__).with_name('onnx_backend.py'))]
    if config['artifact_mask']:dependencies.append(digest(Path(config['artifact_mask'])))
    from onnx_backend import model_directory
    detector=model_directory()/'face_detector.onnx'
    if config['auto_identity'] and detector.is_file():dependencies.append(digest(detector))
    key=hashlib.sha256(json.dumps([VERSION,original_hash,reference_hash,config,dependencies],sort_keys=True).encode()).hexdigest()
    if receipt.exists():
        old=json.loads(receipt.read_text())
        if old.get('key')==key and png.exists() and jpg.exists() and digest(png)==old['png_sha256'] and digest(jpg)==old['jpg_sha256']:
            return dict(old,status='resumed')
        raise ValueError('Existing output differs; use a new versioned output stem')
    if any(p.exists() for p in [png,jpg,field_path]):
        raise ValueError('Incomplete output exists; inspect before retry')
    src,source_profile=read_srgb(source_path);ref,reference_profile=read_srgb(reference_path)
    h,w=src.shape[:2];rh,rw=ref.shape[:2]
    if abs((w/h)/(rw/rh)-1)>.02:
        raise ValueError('Reference aspect ratio differs; do not transfer a reframed generation')
    identity_warning=None
    if config['auto_identity'] and not config['identity_regions']:
        try:
            from onnx_backend import FaceDetector
            faces=FaceDetector().detect(np.rint(src*255).astype(np.uint8),threshold=.6)
            rects=np.clip([[f.bbox[0]/w-.02,f.bbox[1]/h-.02,f.bbox[2]/w+.02,f.bbox[3]/h+.02] for f in faces],0,1)
            config['identity_regions']=[r.tolist() for r in rects if r[0]<r[2] and r[1]<r[3]]
        except (FileNotFoundError,ImportError) as error:
            config['medium_weight']=0
            identity_warning='Face detector unavailable: medium reference layer disabled. '+str(error)
    if config['artifact_mask']:
        config['artifact_mask']=str(Path(config['artifact_mask']).resolve())
    field=make_field(decode(src),decode(ref),config)
    result=apply_field(decode(src),field,config)
    pixels=np.clip(np.rint(encode(result)*255),0,255).astype(np.uint8)
    stem.parent.mkdir(parents=True,exist_ok=True)
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    im=Image.fromarray(pixels);im.save(png,icc_profile=icc)
    im.save(jpg,quality=97,subsampling=0,icc_profile=icc)
    np.savez_compressed(field_path,log_gain_grid=field)
    for p in [png,jpg]:
        with Image.open(p) as checked:
            if checked.size!=(w,h):raise ValueError('Unexpected output dimensions')
            checked.verify()
    if digest(source_path)!=original_hash:raise ValueError('Source hash changed')
    clipped_before=np.any(np.rint(src*255)>=255,axis=2)
    clipped_after=np.any(pixels>=255,axis=2)
    report=dict(version=VERSION,key=key,status='rendered_pending_visual_review',
                source=str(source_path),source_sha256=original_hash,source_profile=source_profile,
                reference=str(reference_path),reference_sha256=reference_hash,reference_profile=reference_profile,
                original_size=[w,h],reference_size=[rw,rh],output_size=[w,h],config=config,
                png=str(png),jpg=str(jpg),png_sha256=digest(png),jpg_sha256=digest(jpg),field=str(field_path),
                generated_texture_copied=False,source_image_resized=False,geometric_warp_applied=False,
                identity_guard_warning=identity_warning,
                artifact_mask_sha256=digest(Path(config['artifact_mask'])) if config['artifact_mask'] else None,
                clipped_source_pixels_in_identity_regions=[int(np.any(np.rint(src*255)>=255,axis=2)[rectangle_mask((h,w),rect,.001)>.5].sum()) for rect in config['identity_regions']],
                source_hash_unchanged=True,decode_checks='passed',
                new_any_channel_255_pixels=int((clipped_after&~clipped_before).sum()),
                mean_luma_code_before=round(float((src@np.array([.2126,.7152,.0722])).mean()*255),2),
                mean_luma_code_after=round(float((pixels@np.array([.2126,.7152,.0722])).mean()),2))
    receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs',type=Path)
    p.add_argument('--source',type=Path);p.add_argument('--reference',type=Path)
    p.add_argument('--output-stem',type=Path);p.add_argument('--config',type=Path)
    args=p.parse_args()
    if args.jobs:
        config=json.loads(args.jobs.read_text());report=[]
        for job in config['jobs']:
            record=render(job['source'],job['reference'],job['output_stem'],job.get('config',{}))
            record.update(id=job.get('id'),scene=job.get('scene'));report.append(record)
        (args.jobs.parent/'batch-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'total':len(report),'resumed':sum(r['status']=='resumed' for r in report),
                          'dimensions_preserved':all(r['original_size']==r['output_size'] for r in report)}))
    else:
        if not all([args.source,args.reference,args.output_stem]):p.error('--source, --reference and --output-stem required')
        record=render(args.source,args.reference,args.output_stem,json.loads(args.config.read_text()) if args.config else {})
        print(json.dumps({'output':record['jpg'],'size':record['output_size'],'status':record['status']}))


if __name__=='__main__':main()
