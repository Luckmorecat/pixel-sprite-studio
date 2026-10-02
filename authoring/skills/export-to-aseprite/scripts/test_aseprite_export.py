#!/usr/bin/env python3
"""Synthetic export/decode invariants; no external app and no generated artwork."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from PIL import Image, PngImagePlugin

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('exporter',HERE/'aseprite_export.py')
e=importlib.util.module_from_spec(spec); spec.loader.exec_module(e)

def independent_decode(blob):
    """Independent offset-based decoder for checking written bytes (not exporter's Reader)."""
    assert struct.unpack_from('<I',blob)[0]==len(blob)
    assert blob[4:6]==b'\xe0\xa5'
    count,width,height,depth=struct.unpack_from('<4H',blob,6)
    result={'canvas':[width,height],'depth':depth,'frames':[],'layers':[],'tags':[],'palette':None}
    offset=128
    for _ in range(count):
        size,magic,chunks,ms=struct.unpack_from('<IHHH',blob,offset)
        assert magic==0xf1fa
        end=offset+size
        new_chunks=struct.unpack_from('<I',blob,offset+12)[0]
        pos=offset+16
        frame={'duration_ms':ms,'cels':[]}
        for _ in range(new_chunks or chunks):
            length,kind=struct.unpack_from('<IH',blob,pos)
            data=blob[pos+6:pos+length]
            if kind==0x2004:
                flags,typ,level,_,_,blend=struct.unpack_from('<6H',data)
                n=struct.unpack_from('<H',data,16)[0]
                result['layers'].append({'flags':flags,'type':typ,'level':level,'blend':blend,'opacity':data[12],'name':data[18:18+n].decode()})
            elif kind==0x2005:
                li,x,y,alpha,kind=struct.unpack_from('<HhhBH',data)
                assert kind==2
                w,h=struct.unpack_from('<HH',data,16)
                pixels=zlib.decompress(data[20:])
                assert len(pixels)==w*h*4
                frame['cels'].append({'layer':li,'x':x,'y':y,'opacity':alpha,'size':[w,h],'pixels':pixels})
            elif kind==0x2018:
                n=struct.unpack_from('<H',data)[0]
                p=10
                for _ in range(n):
                    first,last,direction,repeat=struct.unpack_from('<HHBH',data,p)
                    slen=struct.unpack_from('<H',data,p+17)[0]
                    result['tags'].append({'from':first,'to':last,'direction':direction,'repeat':repeat,'name':data[p+19:p+19+slen].decode()})
                    p+=19+slen
            elif kind==0x2019:
                n,first,last=struct.unpack_from('<III',data)
                assert first==0 and last==n-1
                result['palette']=[list(data[22+6*j:26+6*j]) for j in range(n)]
            elif kind==0x2007:
                result['profile_bytes']=data
            else:
                raise AssertionError('Unknown chunk')
            pos+=length
        assert pos==end
        result['frames'].append(frame)
        offset=end
    assert offset==len(blob)
    return result

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.a=self.png('a.png',[ (31,82,177,0),(9,7,5,17),(255,0,0,128),(0,0,0,255)],(2,2))
        self.b=self.png('b.png',[ (21,0,0,255),(0,23,0,255),(0,0,27,255),(99,88,77,0)],(2,2))
    def tearDown(self):
        self.temp.cleanup()
    def png(self,filename,pixels,size):
        path=self.root/filename
        image=Image.new('RGBA',size); image.putdata(pixels); image.save(path)
        return path
    def seq(self):
        return {'version':1,'mode':'sequence','frames':[{'png':'a.png','duration_ms':73},{'png':'b.png','duration_ms':211},{'png':'a.png','duration_ms':19}],
                'tags':[{'name':'walk 🐾','from':0,'to':2,'direction':'ping-pong','repeat':3},{'name':'settle','from':1,'to':2,'direction':'reverse'}]}
    def compile(self,doc):
        return e.compile_manifest(doc,self.root)
    def decode(self,doc):
        return independent_decode(e.encode(self.compile(doc)))
    def reject(self,doc):
        with self.assertRaises(e.ExportError):
            self.compile(doc)
    def test_01_static_default_container_not_animation(self):
        out=self.root/'still.aseprite'; report=self.root/'still.json'
        p=subprocess.run([sys.executable,str(HERE/'aseprite_export.py'),'static',str(self.a),str(out),'--report',str(report)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        decoded=independent_decode(out.read_bytes()); qa=json.loads(report.read_text())
        self.assertEqual(len(decoded['frames']),1); self.assertEqual(decoded['frames'][0]['duration_ms'],100)
        self.assertTrue(qa['static_default_duration']); self.assertIn('serialization',qa['timing_note']); self.assertEqual(decoded['tags'],[])
    def test_02_static_explicit_duration(self):
        out=self.root/'still.aseprite'
        p=subprocess.run([sys.executable,str(HERE/'aseprite_export.py'),'static',str(self.a),str(out),'--duration-ms','347'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(independent_decode(out.read_bytes())['frames'][0]['duration_ms'],347)
        self.assertFalse(json.loads(p.stdout)['static_default_duration'])
    def test_03_rgba_hidden_rgb_and_partial_alpha(self):
        d=self.decode(self.seq())
        self.assertEqual(d['frames'][0]['cels'][0]['pixels'],Image.open(self.a).tobytes())
        self.assertEqual(d['frames'][0]['cels'][0]['pixels'][:4],bytes([31,82,177,0]))
    def test_04_repeated_entries_and_exact_milliseconds(self):
        d=self.decode(self.seq()); self.assertEqual([f['duration_ms'] for f in d['frames']],[73,211,19])
        self.assertEqual(d['frames'][0]['cels'][0]['pixels'],d['frames'][2]['cels'][0]['pixels'])
        self.assertNotEqual(d['frames'][0]['cels'][0]['pixels'],d['frames'][1]['cels'][0]['pixels'])
    def test_05_tags_unicode_direction_repeat(self):
        d=self.decode(self.seq()); self.assertEqual(d['tags'],[{'name':'walk 🐾','from':0,'to':2,'direction':2,'repeat':3},{'name':'settle','from':1,'to':2,'direction':1,'repeat':0}])
    def test_06_sheet_grid_spacing_margin_reordered_repeat(self):
        sheet=Image.new('RGBA',(7,4),(255,255,255,255)); sheet.paste(Image.open(self.a),(1,1)); sheet.paste(Image.open(self.b),(4,1)); sheet.save(self.root/'sheet.png')
        doc={'version':1,'mode':'sheet','png':'sheet.png','frame_size':[2,2],'grid':{'columns':2,'rows':1,'margin':[1,1],'spacing':[1,0]},
             'frames':[{'cell':1,'duration_ms':17},{'cell':0,'duration_ms':37},{'cell':1,'duration_ms':91}]}
        d=self.decode(doc)
        self.assertEqual([f['cels'][0]['pixels'] for f in d['frames']],[Image.open(self.b).tobytes(),Image.open(self.a).tobytes(),Image.open(self.b).tobytes()])
    def test_07_sheet_rectangles(self):
        sheet=Image.new('RGBA',(4,2)); sheet.paste(Image.open(self.a),(0,0)); sheet.paste(Image.open(self.b),(2,0)); sheet.save(self.root/'sheet.png')
        doc={'version':1,'mode':'sheet','png':'sheet.png','frames':[{'rect':[2,0,2,2],'duration_ms':1},{'rect':[0,0,2,2],'duration_ms':65535}]}
        d=self.decode(doc); self.assertEqual([f['duration_ms'] for f in d['frames']],[1,65535]); self.assertEqual(d['frames'][0]['cels'][0]['pixels'],Image.open(self.b).tobytes())
    def layered(self):
        return {'version':1,'mode':'layers','canvas':[8,9],'layers':[{'name':'body','opacity':187},{'name':'hat','visible':False,'editable':False}],
                'frames':[{'duration_ms':29,'cels':[{'layer':'hat','png':'b.png','x':-1,'y':3,'opacity':92},{'layer':'body','png':'a.png','x':2,'y':-3}]},{'duration_ms':40,'cels':[]}]}
    def test_08_real_layers_metadata_offsets_blank_frame(self):
        d=self.decode(self.layered()); self.assertEqual([l['name'] for l in d['layers']],['body','hat'])
        self.assertEqual(d['layers'][0]['opacity'],187); self.assertEqual(d['layers'][1]['flags'],0)
        self.assertEqual([(c['layer'],c['x'],c['y'],c['opacity']) for c in d['frames'][0]['cels']],[(0,2,-3,255),(1,-1,3,92)])
        self.assertEqual(d['frames'][1]['cels'],[]); self.assertEqual(d['frames'][0]['cels'][1]['pixels'],Image.open(self.b).tobytes())
    def test_09_indexed_palette_order_alpha_and_unused_colors(self):
        p=Image.new('P',(2,2)); p.putpalette([17,18,19,101,102,103,250,249,248,1,2,3]); p.putdata([0,1,0,2]); p.info['transparency']=bytes([0,81,255,49]); p.save(self.root/'indexed.png')
        doc={'version':1,'mode':'sequence','frames':[{'png':'indexed.png','duration_ms':99}]}
        d=self.decode(doc)
        self.assertEqual(d['palette'],[[17,18,19,0],[101,102,103,81],[250,249,248,255],[1,2,3,49]])
        self.assertEqual(d['frames'][0]['cels'][0]['pixels'],Image.open(self.root/'indexed.png').convert('RGBA').tobytes())
    def test_10_grayscale_exact_rgba(self):
        for mode,pixels in [('L',[0,4,97,255]),('LA',[(0,0),(5,27),(97,128),(255,255)]),('1',[0,255,0,255])]:
            p=Image.new(mode,(2,2)); p.putdata(pixels); p.save(self.root/f'{mode}.png')
            d=self.decode({'version':1,'mode':'sequence','frames':[{'png':f'{mode}.png','duration_ms':100}]})
            self.assertEqual(d['frames'][0]['cels'][0]['pixels'],p.convert('RGBA').tobytes())
    def test_11_source_hashes_and_no_mutation(self):
        before={p:e.sha(p.read_bytes()) for p in (self.a,self.b)}
        project=self.compile(self.seq()); result=e.export(project,self.root/'out.aseprite',self.root/'out.json')
        self.assertTrue(result['decoded_inputs_match']); self.assertFalse(result['app_open_verified'])
        self.assertEqual(before,{p:e.sha(p.read_bytes()) for p in (self.a,self.b)})
    def test_12_all_tag_directions(self):
        doc=self.seq(); doc['tags']=[{'name':str(i),'from':0,'to':2,'direction':name,'repeat':65535} for i,name in enumerate(e.DIRECTIONS)]
        self.assertEqual([t['direction'] for t in self.decode(doc)['tags']],[0,1,2,3])
    def test_13_srgb_preserved(self):
        info=PngImagePlugin.PngInfo(); info.add(b'sRGB',b'\0')
        Image.open(self.a).save(self.root/'srgb.png',pnginfo=info)
        d=self.decode({'version':1,'mode':'sequence','frames':[{'png':'srgb.png','duration_ms':100}]})
        self.assertEqual(struct.unpack_from('<H',d['profile_bytes'])[0],1)
    def test_14_icc_bytes_preserved(self):
        from PIL import ImageCms
        profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        Image.open(self.a).save(self.root/'icc.png',icc_profile=profile)
        d=self.decode({'version':1,'mode':'sequence','frames':[{'png':'icc.png','duration_ms':100}]})
        self.assertEqual(d['profile_bytes'][20:],profile)
    def test_15_missing_animation_timing_rejected(self):
        doc=self.seq(); del doc['frames'][0]['duration_ms']; self.reject(doc)
    def test_16_invalid_timing_types_and_range(self):
        for value in (0,-1,65536,3.5,True,'100',None):
            with self.subTest(value=value):
                doc=self.seq(); doc['frames'][0]['duration_ms']=value; self.reject(doc)
    def test_17_empty_timeline_rejected(self):
        doc=self.seq(); doc['frames']=[]; self.reject(doc)
    def test_18_sequence_dimensions_rejected(self):
        self.png('small.png',[(0,0,0,0)],(1,1)); doc=self.seq(); doc['frames'][1]['png']='small.png'; self.reject(doc)
    def test_19_missing_file_rejected(self):
        doc=self.seq(); doc['frames'][0]['png']='missing.png'; self.reject(doc)
    def test_20_sheet_missing_layout_rejected(self):
        self.reject({'version':1,'mode':'sheet','png':'a.png','frames':[{'duration_ms':100}]})
    def test_21_sheet_out_of_bounds_rejected(self):
        self.reject({'version':1,'mode':'sheet','png':'a.png','frames':[{'rect':[1,0,2,2],'duration_ms':100}]})
    def test_22_sheet_incomplete_grid_rejected(self):
        self.reject({'version':1,'mode':'sheet','png':'a.png','frame_size':[1,1],'grid':{'columns':1,'rows':1},'frames':[{'cell':0,'duration_ms':100}]})
    def test_23_unknown_field_rejected(self):
        doc=self.seq(); doc['resize']=2; self.reject(doc)
    def test_24_invalid_or_duplicate_tags_rejected(self):
        for tags in ([{'name':'x','from':0,'to':3}],[{'name':'x','from':2,'to':1}],[{'name':'x','from':0,'to':2,'direction':'backwards'}],[{'name':'x','from':0,'to':2}]*2):
            doc=self.seq(); doc['tags']=tags; self.reject(doc)
    def test_25_unsupported_blend_rejected(self):
        doc=self.layered(); doc['layers'][0]['blend_mode']='multiply'; self.reject(doc)
    def test_26_duplicate_or_unknown_layer_rejected(self):
        doc=self.layered(); doc['frames'][0]['cels'].append(doc['frames'][0]['cels'][0]); self.reject(doc)
        doc=self.layered(); doc['frames'][0]['cels'][0]['layer']='other'; self.reject(doc)
        doc=self.layered(); doc['layers'][1]['name']='body'; self.reject(doc)
    def test_27_palette_mismatch_rejected(self):
        for n in (1,2):
            p=Image.new('P',(2,2)); p.putpalette([n,0,0]); p.save(self.root/f'p{n}.png')
        doc=self.seq(); doc['frames'][0]['png']='p1.png'; doc['frames'][1]['png']='p2.png'; self.reject(doc)
    def test_28_profiles_mismatch_rejected(self):
        info=PngImagePlugin.PngInfo(); info.add(b'sRGB',b'\0'); Image.open(self.a).save(self.root/'srgb.png',pnginfo=info)
        doc=self.seq(); doc['frames'][0]['png']='srgb.png'; self.reject(doc)
    def test_29_16bit_rejected(self):
        Image.new('I;16',(2,2),65535).save(self.root/'sixteen.png'); doc=self.seq(); doc['frames'][0]['png']='sixteen.png'; self.reject(doc)
    def test_30_apng_rejected(self):
        Image.open(self.a).save(self.root/'anim.png',save_all=True,append_images=[Image.open(self.b)],duration=100)
        doc=self.seq(); doc['frames'][0]['png']='anim.png'; self.reject(doc)
    def test_31_non_png_rejected(self):
        Image.open(self.a).save(self.root/'not.png',format='BMP'); doc=self.seq(); doc['frames'][0]['png']='not.png'; self.reject(doc)
    def test_32_unsupported_gamma_rejected(self):
        info=PngImagePlugin.PngInfo(); info.add(b'gAMA',struct.pack('>I',45455)); Image.open(self.a).save(self.root/'gamma.png',pnginfo=info)
        doc=self.seq(); doc['frames'][0]['png']='gamma.png'; self.reject(doc)
    def test_33_existing_output_never_overwritten(self):
        target=self.root/'out.aseprite'; target.write_bytes(b'keep')
        with self.assertRaises(e.ExportError): e.export(self.compile(self.seq()),target)
        self.assertEqual(target.read_bytes(),b'keep')
    def test_34_input_and_report_collisions_rejected(self):
        project=self.compile(self.seq()); original=self.a.read_bytes()
        for output,report in ((self.a,None),(self.root/'out.aseprite',self.a),(self.root/'out',self.root/'out')):
            with self.assertRaises(e.ExportError):e.export(project,output,report)
        self.assertEqual(self.a.read_bytes(),original); self.assertFalse((self.root/'out.aseprite').exists())
    def test_35_dangling_symlink_output_rejected(self):
        target=self.root/'link.aseprite'; target.symlink_to(self.root/'missing')
        with self.assertRaises(e.ExportError):e.export(self.compile(self.seq()),target)
        self.assertTrue(target.is_symlink()); self.assertFalse((self.root/'missing').exists())
    def test_36_inspector_detects_duration_and_pixel_tamper(self):
        project=self.compile(self.seq()); blob=bytearray(e.encode(project)); struct.pack_into('<H',blob,136,74)
        with self.assertRaises(e.ExportError):e.compare(project,e.inspect_bytes(blob))
        decoded=e.inspect_bytes(e.encode(project)); decoded['frames'][0]['cels'][0]['raw']=b'\0'*16
        with self.assertRaises(e.ExportError):e.compare(project,decoded)
    def test_37_inspector_truncation_and_trailing_rejected(self):
        blob=e.encode(self.compile(self.seq()))
        for bad in (blob[:-1],blob+b'\0',blob[:128]):
            with self.assertRaises(e.ExportError):e.inspect_bytes(bad)
    def test_38_duplicate_json_keys_rejected(self):
        path=self.root/'x.json'; path.write_text('{"version":1,"version":2}')
        with self.assertRaises(e.ExportError):e.read_json(path)
    def test_39_deterministic_bytes(self):
        p=self.compile(self.seq()); self.assertEqual(e.encode(p),e.encode(self.compile(self.seq())))
    def test_40_self_inspect_matches_layered_and_indexed(self):
        for doc in (self.seq(),self.layered()):
            p=self.compile(doc); e.compare(p,e.inspect_bytes(e.encode(p)))
    def test_42_chromaticity_only_preserved_in_report_without_invented_profile(self):
        chroma=struct.pack('>8I',31270,32900,64000,33000,30000,60000,15000,6000)
        info=PngImagePlugin.PngInfo(); info.add(b'cHRM',chroma); Image.open(self.a).save(self.root/'chroma.png',pnginfo=info)
        doc={'version':1,'mode':'sequence','frames':[{'png':'chroma.png','duration_ms':100}]}
        project=self.compile(doc); blob=e.encode(project); decoded=e.inspect_bytes(blob); e.compare(project,decoded)
        result=e.report(decoded,blob,project)
        self.assertEqual(result['sources'][0]['png_chromaticity_hex'],chroma.hex())
        self.assertEqual(result['color_profile']['kind'],'none'); self.assertIn('untagged',result['color_metadata_note'])
        self.assertEqual(decoded['frames'][0]['cels'][0]['raw'],Image.open(self.a).tobytes())
    def test_41_invalid_manifest_no_artifact(self):
        doc=self.seq(); doc['frames'][0]['duration_ms']=0
        manifest=self.root/'bad.json'; manifest.write_text(json.dumps(doc)); out=self.root/'bad.aseprite'
        p=subprocess.run([sys.executable,str(HERE/'aseprite_export.py'),'manifest',str(manifest),str(out)],capture_output=True,text=True)
        self.assertEqual(p.returncode,2); self.assertFalse(out.exists()); self.assertFalse(json.loads(p.stderr)['passed'])

if __name__=='__main__': unittest.main(verbosity=2)
