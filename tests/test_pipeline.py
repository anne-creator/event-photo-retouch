"""Observable preservation and failure-handling checks, with synthetic fixtures."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from lighting_field import DEFAULTS, apply_field, artifact_correction, decode, encode, make_field, read_srgb, render
from beauty_finish import face_mask
from onnx_backend import Face


class LightingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        y,x=np.mgrid[:160,:240]
        self.codes=np.stack([65+x//2,70+y//2,80+(x+y)//4],axis=2).astype(np.uint8)
        self.source=self.root/'original.png';Image.fromarray(self.codes).save(self.source)
        self.config=dict(DEFAULTS,auto_identity=False,medium_weight=0)

    def tearDown(self):self.tmp.cleanup()

    def test_self_reference_preserves_original_pixels(self):
        r=render(self.source,self.source,self.root/'out',self.config)
        np.testing.assert_array_equal(np.asarray(Image.open(r['png'])),self.codes)

    def test_stronger_transfer_changes_light_more_without_new_clipping(self):
        a=decode(self.codes/255);b=decode(np.minimum(self.codes.astype(float)*1.4,250)/255)
        field=make_field(a,b,self.config)
        low=apply_field(a,field,dict(self.config,strength=.3))
        high=apply_field(a,field,dict(self.config,strength=1))
        self.assertGreater(float(np.abs(high-a).mean()),float(np.abs(low-a).mean())*2)
        self.assertFalse(np.any(np.rint(encode(high)*255)==255))
        self.assertEqual(high.shape,a.shape)

    def test_emitter_protection_does_not_protect_every_white_stripe(self):
        a=np.full((160,240,3),.95,np.float32);f=np.full((160,240,3),-.8,np.float32)
        out=apply_field(a,f,dict(self.config,emitter_regions=[[0,0,.45,1]]))
        self.assertGreater(float(out[:,20:80].mean()),float(out[:,160:220].mean())+.2)

    def test_resume_checks_outputs_and_rejects_modified_exports(self):
        a=render(self.source,self.source,self.root/'cached',self.config)
        self.assertEqual(render(self.source,self.source,self.root/'cached',self.config)['status'],'resumed')
        Image.new('RGB',(240,160),'black').save(a['png'])
        with self.assertRaisesRegex(ValueError,'differs'):render(self.source,self.source,self.root/'cached',self.config)

    def test_reframed_reference_is_rejected(self):
        ref=self.root/'square.png';Image.new('RGB',(160,160)).save(ref)
        with self.assertRaisesRegex(ValueError,'aspect ratio'):render(self.source,ref,self.root/'wrong',self.config)

    def test_high_bit_depth_input_is_not_silently_downconverted(self):
        path=self.root/'16.png';Image.fromarray(np.full((16,16),40000,np.uint16)).save(path)
        with self.assertRaisesRegex(ValueError,'High-bit-depth'):read_srgb(path)

    def test_local_stripe_gain_improves_illumination_and_leaves_unmasked_pixels(self):
        base=np.full((160,240,3),.2,np.float32)
        source=base.copy();source[30:130,115:122]=.6
        m=np.zeros((160,240),np.uint8);m[29:131,114:123]=255
        path=self.root/'mask.png';Image.fromarray(m).save(path)
        out=artifact_correction(source,path,1,9)
        self.assertLess(float(np.abs(out[40:120,116:121]-base[40:120,116:121]).mean()),.1)
        np.testing.assert_array_equal(out[:,:90],source[:,:90])
        Image.new('L',(240,160),255).save(path)
        with self.assertRaisesRegex(ValueError,'too broad'):artifact_correction(source,path,1,9)

    def test_skin_finish_excludes_landmarks_and_background(self):
        face=Face([50,20,150,140],.99,[[80,65],[120,65],[100,90],[85,115],[115,115]])
        mask,protected=face_mask((160,240),face,np.ones((160,240),np.float32))
        self.assertGreater(float(mask.max()),.9)
        self.assertTrue(np.all(mask[protected>0]==0))
        self.assertTrue(np.all(mask[:,200:]==0))
        for x,y in face.landmarks:self.assertEqual(float(mask[int(y),int(x)]),0)


if __name__=='__main__':unittest.main()
