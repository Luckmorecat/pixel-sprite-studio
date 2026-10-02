#!/usr/bin/env python3
"""Lossless PNG packaging to the documented RGBA Aseprite subset. No drawing.
File format: https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md
Requires Python 3.10+ and Pillow. Output never overwrites an existing path.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import warnings
import zlib
from PIL import Image

VERSION = '1.0.1'
MAX_PIXELS = 16_777_216
MAX_TOTAL_PIXELS = 67_108_864
MAX_FRAMES = 10_000
MAX_FILE_BYTES = 536_870_912
DIRECTIONS = {'forward': 0, 'reverse': 1, 'ping-pong': 2, 'ping-pong-reverse': 3}

class ExportError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise ExportError(message)

def integer(value, low, high, label):
    require(type(value) is int and low <= value <= high,
            f'{label} must be an integer in {low}..{high}')
    return value

def keys(value, allowed, required, label):
    require(isinstance(value, dict), f'{label} must be an object')
    require(not set(value) - set(allowed), f'{label}: unknown fields {sorted(set(value)-set(allowed))}')
    require(set(required) <= set(value), f'{label}: missing fields {sorted(set(required)-set(value))}')

def name(value, label):
    require(isinstance(value, str) and value and '\0' not in value, f'{label} must be nonempty text without NUL')
    require(len(value.encode('utf-8')) <= 65535, f'{label} is too long')
    return value

def pair(value, low, high, label):
    require(isinstance(value, list) and len(value) == 2, f'{label} must be [x,y]')
    return [integer(v, low, high, label) for v in value]

def sha(value):
    return hashlib.sha256(value).hexdigest()

def duration(value):
    return integer(value, 1, 65535, 'duration_ms')

def read_json(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_pairs)

def source_path(base, value):
    require(isinstance(value, str) and value, 'PNG path must be nonempty text')
    path = (base / value).resolve()
    require(path.is_file(), f'PNG does not exist: {path}')
    return path

def png_chunks(data):
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'Input must be a PNG file')
    chunks, offset = {}, 8
    while offset < len(data):
        require(offset + 12 <= len(data), 'Truncated PNG chunk')
        size, = struct.unpack_from('>I', data, offset)
        kind = data[offset+4:offset+8]
        end = offset + 12 + size
        require(end <= len(data), 'Truncated PNG payload')
        body = data[offset+8:end-4]
        crc, = struct.unpack_from('>I', data, end-4)
        require(zlib.crc32(kind + body) & 0xffffffff == crc, 'PNG chunk CRC mismatch')
        chunks.setdefault(kind, []).append(body)
        offset = end
        if kind == b'IEND':
            require(offset == len(data), 'Trailing bytes after PNG IEND')
            break
    require(b'IEND' in chunks and b'IHDR' in chunks and len(chunks[b'IHDR']) == 1, 'Invalid PNG structure')
    return chunks

def load_png(path):
    require(path.stat().st_size <= MAX_FILE_BYTES, 'PNG file exceeds safety limit')
    data = path.read_bytes()
    chunks = png_chunks(data)
    require(b'acTL' not in chunks, 'Animated PNG is not a still PNG; supply explicit PNG cels and a timeline')
    require(len(chunks[b'IHDR'][0]) == 13, 'Invalid PNG header')
    w, h, bits, color, _, _, _ = struct.unpack('>IIBBBBB', chunks[b'IHDR'][0])
    require(w and h and w <= 65535 and h <= 65535 and w*h <= MAX_PIXELS, 'PNG canvas exceeds safety limits')
    require(bits <= 8, '16-bit PNG is unsupported: conversion would lose sample precision')
    require(color in (0,2,3,4,6), 'Unsupported PNG color type')
    require(b'gAMA' not in chunks or b'sRGB' in chunks or b'iCCP' in chunks,
            'Standalone PNG gamma is unsupported; obtain a source with explicit sRGB/ICC or approved metadata removal')
    require(b'cICP' not in chunks and b'mDCV' not in chunks and b'cLLI' not in chunks,
            'HDR color metadata is unsupported')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            require(image.format == 'PNG' and getattr(image, 'n_frames', 1) == 1, 'Input must be one still PNG')
            image.load()
            require(image.mode in ('1','L','LA','RGB','RGBA','P'), 'Unsupported PNG pixel mode')
            raw = image.convert('RGBA').tobytes()
            icc = image.info.get('icc_profile')
    profile = ('icc', icc) if icc else ('srgb', None) if b'sRGB' in chunks else ('none', None)
    require(b'iCCP' not in chunks or icc, 'PNG ICC profile could not be read')
    palette = None
    if color == 3:
        require(b'PLTE' in chunks and len(chunks[b'PLTE']) == 1, 'Indexed PNG is missing a unique palette')
        rgb = chunks[b'PLTE'][0]
        require(len(rgb) % 3 == 0 and 1 <= len(rgb)//3 <= 256, 'Invalid PNG palette size')
        alpha = chunks.get(b'tRNS', [b''])[0]
        require(len(alpha) <= len(rgb)//3, 'PNG transparency exceeds palette size')
        palette = [list(rgb[n:n+3]) + [alpha[n//3] if n//3 < len(alpha) else 255] for n in range(0,len(rgb),3)]
    return {'path': str(path), 'file_sha256': sha(data), 'width': w, 'height': h,
            'raw': raw, 'rgba_sha256': sha(raw), 'palette': palette, 'profile': profile,
            'png_chromaticity_hex': chunks[b'cHRM'][0].hex() if b'cHRM' in chunks else None}

def layer(value):
    keys(value, ['name','opacity','visible','editable','blend_mode'], ['name'], 'layer')
    for flag in ('visible','editable'):
        require(type(value.get(flag, True)) is bool, f'layer.{flag} must be boolean')
    require(value.get('blend_mode','normal') == 'normal', 'Only normal-blend source layers are supported; do not silently flatten other blends')
    return {'name': name(value['name'],'layer.name'), 'opacity': integer(value.get('opacity',255),0,255,'layer.opacity'),
            'visible': value.get('visible',True), 'editable': value.get('editable',True), 'blend_mode': 'normal'}

def parse_tags(values, count):
    require(isinstance(values,list) and len(values) <= 65535, 'tags must be an array')
    result = []
    for tag in values:
        keys(tag, ['name','from','to','direction','repeat'], ['name','from','to'], 'tag')
        a = integer(tag['from'],0,count-1,'tag.from')
        b = integer(tag['to'],a,count-1,'tag.to')
        direction = tag.get('direction','forward')
        require(direction in DIRECTIONS, f'Unsupported tag direction: {direction}')
        result.append({'name':name(tag['name'],'tag.name'),'from':a,'to':b,'direction':direction,
                       'repeat':integer(tag.get('repeat',0),0,65535,'tag.repeat')})
    require(len({t['name'] for t in result}) == len(result), 'Tag names must be unique')
    return result

def compile_manifest(document, base, static_default=False):
    keys(document, ['version','mode','canvas','png','frame_size','grid','layers','layer_name','frames','tags'],
         ['version','mode','frames'], 'manifest')
    require(document['version'] == 1 and type(document['version']) is int, 'version must be 1')
    mode = document['mode']
    require(mode in ('sequence','sheet','layers'), 'mode must be sequence, sheet, or layers')
    permitted = {'sequence':{'layer_name'}, 'sheet':{'png','frame_size','grid','layer_name'}, 'layers':{'layers','canvas'}}[mode]
    require(not set(document)-{'version','mode','frames','tags'}-permitted,
            f'Fields do not belong to mode {mode}: {sorted(set(document)-{"version","mode","frames","tags"}-permitted)}')
    source_frames = document['frames']
    require(isinstance(source_frames,list) and 1 <= len(source_frames) <= MAX_FRAMES, 'frames must be a nonempty bounded array')
    sources = {}
    def source(value):
        path = source_path(base, value)
        if path not in sources:
            sources[path] = load_png(path)
            require(sum(v['width']*v['height'] for v in sources.values()) <= MAX_TOTAL_PIXELS, 'Source pixel budget exceeded')
        return sources[path]
    layers = [layer({'name':document.get('layer_name','Flattened source artwork')})]
    canvas, sheet, grid = None, None, None
    if mode == 'layers':
        require('canvas' in document and 'layers' in document, 'layers mode requires canvas and layers')
        canvas = pair(document['canvas'],1,65535,'canvas')
        require(isinstance(document['layers'],list) and 1 <= len(document['layers']) <= 1024, 'layers must be a nonempty bounded array')
        layers = [layer(v) for v in document['layers']]
        require(len({v['name'] for v in layers}) == len(layers), 'Layer names must be unique')
    if mode == 'sheet':
        require('png' in document, 'sheet mode requires png')
        sheet = source(document['png'])
        if 'grid' in document or 'frame_size' in document:
            require('grid' in document and 'frame_size' in document, 'grid and frame_size must be supplied together')
            canvas = pair(document['frame_size'],1,65535,'frame_size')
            g = document['grid']
            keys(g,['columns','rows','margin','spacing'],['columns','rows'],'grid')
            grid = {'columns':integer(g['columns'],1,65535,'grid.columns'), 'rows':integer(g['rows'],1,65535,'grid.rows'),
                    'margin':pair(g.get('margin',[0,0]),0,65535,'grid.margin'),'spacing':pair(g.get('spacing',[0,0]),0,65535,'grid.spacing')}
            need_w = 2*grid['margin'][0] + grid['columns']*canvas[0] + (grid['columns']-1)*grid['spacing'][0]
            need_h = 2*grid['margin'][1] + grid['rows']*canvas[1] + (grid['rows']-1)*grid['spacing'][1]
            require((need_w,need_h)==(sheet['width'],sheet['height']), 'Grid must exactly account for sheet bounds, symmetric margins, and spacing')
    names = {v['name']:i for i,v in enumerate(layers)}
    frames, total_pixels = [], 0
    for frame in source_frames:
        required = {'sequence':['png','duration_ms'],'sheet':['cell' if grid else 'rect','duration_ms'],'layers':['cels','duration_ms']}[mode]
        keys(frame,required,required,'frame')
        cels = []
        if mode == 'sequence':
            src = source(frame['png'])
            if canvas is None:
                canvas = [src['width'],src['height']]
            require(canvas == [src['width'],src['height']], 'Sequence PNG dimensions differ; explicit layers/cel offsets are required')
            cels.append({'layer':0,'x':0,'y':0,'width':src['width'],'height':src['height'],'opacity':255,'raw':src['raw']})
        elif mode == 'sheet':
            if grid:
                index = integer(frame['cell'],0,grid['columns']*grid['rows']-1,'frame.cell')
                x = grid['margin'][0]+(index % grid['columns'])*(canvas[0]+grid['spacing'][0])
                y = grid['margin'][1]+(index // grid['columns'])*(canvas[1]+grid['spacing'][1])
                rect = [x,y,*canvas]
            else:
                rect = frame['rect']
                require(isinstance(rect,list) and len(rect)==4, 'rect must be [x,y,width,height]')
                rect = [integer(v,0 if i<2 else 1,65535,'rect') for i,v in enumerate(rect)]
                if canvas is None:
                    canvas = rect[2:]
                require(canvas == rect[2:], 'Sheet frame rectangles must have identical sizes')
            x,y,w,h = rect
            require(x+w <= sheet['width'] and y+h <= sheet['height'], 'Sheet rectangle is out of bounds')
            raw = b''.join(sheet['raw'][(row*sheet['width']+x)*4:(row*sheet['width']+x+w)*4] for row in range(y,y+h))
            cels.append({'layer':0,'x':0,'y':0,'width':w,'height':h,'opacity':255,'raw':raw})
        else:
            require(isinstance(frame['cels'],list), 'cels must be an array; use [] for an explicitly blank frame')
            seen = set()
            for cel in frame['cels']:
                keys(cel,['layer','png','x','y','opacity'],['layer','png'],'cel')
                require(cel['layer'] in names, f'Unknown layer: {cel["layer"]}')
                li = names[cel['layer']]
                require(li not in seen, 'A frame cannot contain two cels on the same layer')
                seen.add(li)
                src = source(cel['png'])
                cels.append({'layer':li,'x':integer(cel.get('x',0),-32768,32767,'cel.x'),
                             'y':integer(cel.get('y',0),-32768,32767,'cel.y'),'width':src['width'],'height':src['height'],
                             'opacity':integer(cel.get('opacity',255),0,255,'cel.opacity'),'raw':src['raw']})
            cels.sort(key=lambda c:c['layer'])
        total_pixels += sum(c['width']*c['height'] for c in cels)
        require(total_pixels <= MAX_TOTAL_PIXELS, 'Timeline pixel budget exceeded')
        frames.append({'duration_ms':duration(frame['duration_ms']),'cels':cels})
    require(canvas and canvas[0]*canvas[1] <= MAX_PIXELS, 'Canvas pixel budget exceeded')
    require(sources, 'At least one real PNG cel is required')
    profiles = {s['profile'] for s in sources.values()}
    require(len(profiles)==1, 'Source color profiles differ; conversion requires a separate approved editing task')
    palettes = {json.dumps(s['palette']) for s in sources.values() if s['palette'] is not None}
    require(len(palettes)<=1, 'Indexed source palettes differ; choose a shared palette in a separate editing task')
    return {'canvas':canvas,'layers':layers,'frames':frames,'tags':parse_tags(document.get('tags',[]),len(frames)),
            'palette':json.loads(next(iter(palettes))) if palettes else None,'profile':next(iter(profiles)),
            'sources':list(sources.values()),'static_default_duration':static_default}

def pack_string(value):
    raw = value.encode('utf-8')
    return struct.pack('<H',len(raw))+raw

def chunk(kind, body):
    return struct.pack('<IH',len(body)+6,kind)+body

def encode(project):
    initial = []
    for layer in project['layers']:
        flags = int(layer['visible']) | (int(layer['editable'])<<1)
        initial.append(chunk(0x2004,struct.pack('<6HB3x',flags,0,0,0,0,0,layer['opacity'])+pack_string(layer['name'])))
    if project['tags']:
        payload = struct.pack('<H8x',len(project['tags']))
        for tag in project['tags']:
            payload += struct.pack('<HHBH6x3BB',tag['from'],tag['to'],DIRECTIONS[tag['direction']],tag['repeat'],0,0,0,0)+pack_string(tag['name'])
        initial.append(chunk(0x2018,payload))
    if project['palette'] is not None:
        p = project['palette']
        payload = struct.pack('<III8x',len(p),0,len(p)-1)+b''.join(struct.pack('<H4B',0,*v) for v in p)
        initial.append(chunk(0x2019,payload))
    kind, icc = project['profile']
    if kind != 'none':
        payload = struct.pack('<HHI8x',2 if kind=='icc' else 1,0,0)
        if kind == 'icc':
            payload += struct.pack('<I',len(icc))+icc
        initial.append(chunk(0x2007,payload))
    frames = []
    for i, frame in enumerate(project['frames']):
        chunks = list(initial) if i == 0 else []
        for cel in frame['cels']:
            payload = struct.pack('<HhhBHh5xHH',cel['layer'],cel['x'],cel['y'],cel['opacity'],2,0,cel['width'],cel['height'])
            chunks.append(chunk(0x2005,payload+zlib.compress(cel['raw'],9)))
        payload = b''.join(chunks)
        frames.append(struct.pack('<IHHH2xI',len(payload)+16,0xF1FA,len(chunks),frame['duration_ms'],0)+payload)
    body = b''.join(frames)
    require(len(body)+128 <= MAX_FILE_BYTES, 'Export exceeds safety limit')
    head = bytearray(128)
    struct.pack_into('<IHHHHHIH',head,0,128+len(body),0xA5E0,len(frames),*project['canvas'],32,1,project['frames'][0]['duration_ms'])
    struct.pack_into('<H',head,32,len(project['palette']) if project['palette'] else 0)
    head[34:36] = b'\x01\x01'
    return bytes(head)+body

class Reader:
    def __init__(self,data):
        self.data,self.pos = data,0
    def take(self,size):
        require(size >= 0 and self.pos+size <= len(self.data),'Truncated Aseprite data')
        out = self.data[self.pos:self.pos+size]
        self.pos += size
        return out
    def unpack(self,fmt):
        return struct.unpack(fmt,self.take(struct.calcsize(fmt)))
    def string(self):
        n, = self.unpack('<H')
        return self.take(n).decode('utf-8')
    def done(self):
        require(self.pos==len(self.data),'Unexpected trailing Aseprite data')

def decompress_exact(data, expected):
    d = zlib.decompressobj()
    raw = d.decompress(data,expected+1)
    require(len(raw)==expected and d.eof and not d.unused_data and not d.unconsumed_tail,'Invalid compressed cel length or trailing stream')
    return raw

def inspect_bytes(data):
    require(128 <= len(data) <= MAX_FILE_BYTES,'Invalid Aseprite length')
    size,magic,count,w,h,depth,flags = struct.unpack_from('<IHHHHHI',data)
    require(size==len(data) and magic==0xA5E0 and depth==32 and flags==1,'Unsupported Aseprite header')
    require(1<=count<=MAX_FRAMES and w and h and w*h<=MAX_PIXELS,'Invalid Aseprite canvas or frame count')
    r = Reader(data[128:])
    layers,tags,frames,palette,profile = [],[],[],None,('none',None)
    total_pixels, seen_tags, seen_profile = 0,False,False
    for fi in range(count):
        size,magic,old_n,ms,new_n = r.unpack('<IHHH2xI')
        require(size>=16 and magic==0xF1FA and ms>0,'Invalid frame header')
        fr = Reader(r.take(size-16))
        cels=[]
        for _ in range(new_n or old_n):
            length,kind = fr.unpack('<IH')
            require(length>=6,'Invalid chunk size')
            p = Reader(fr.take(length-6))
            if kind==0x2004:
                require(fi==0,'Late layer declaration')
                lf,lt,level,_,_,blend,opacity=p.unpack('<6HB3x')
                require(lt==level==blend==0 and not lf & ~3,'Unsupported source layer features')
                layers.append({'name':p.string(),'opacity':opacity,'visible':bool(lf&1),'editable':bool(lf&2),'blend_mode':'normal'})
            elif kind==0x2018:
                require(fi==0 and not seen_tags,'Duplicate or late tags')
                seen_tags=True
                n,=p.unpack('<H8x')
                for _ in range(n):
                    start,end,direction,repeat,_,_,_,extra=p.unpack('<HHBH6x3BB')
                    require(start<=end<count and direction<=3 and extra==0,'Invalid tag')
                    tags.append({'name':p.string(),'from':start,'to':end,'direction':list(DIRECTIONS)[direction],'repeat':repeat})
            elif kind==0x2019:
                require(fi==0 and palette is None,'Duplicate or late palette')
                n,start,end=p.unpack('<III8x')
                require(1<=n<=256 and start==0 and end==n-1,'Unsupported palette shape')
                palette=[]
                for _ in range(n):
                    flag,a,b,c,d=p.unpack('<H4B')
                    require(flag==0,'Named palettes unsupported')
                    palette.append([a,b,c,d])
            elif kind==0x2007:
                require(fi==0 and not seen_profile,'Duplicate or late color profile')
                seen_profile=True
                pt,pf,gamma=p.unpack('<HHI8x')
                require(pt in (1,2) and pf==gamma==0,'Unsupported color profile')
                profile=('srgb',None)
                if pt==2:
                    n,=p.unpack('<I')
                    profile=('icc',p.take(n))
            elif kind==0x2005:
                li,x,y,opacity,ct,z=p.unpack('<HhhBHh5x')
                require(ct==2 and z==0 and li<len(layers),'Unsupported cel')
                cw,ch=p.unpack('<HH')
                require(cw and ch and cw*ch<=MAX_PIXELS,'Invalid cel size')
                total_pixels += cw*ch
                require(total_pixels<=MAX_TOTAL_PIXELS,'Decoded pixel budget exceeded')
                raw=decompress_exact(p.take(len(p.data)-p.pos),cw*ch*4)
                cels.append({'layer':li,'x':x,'y':y,'width':cw,'height':ch,'opacity':opacity,'raw':raw})
            else:
                raise ExportError(f'Unsupported chunk 0x{kind:04x}; inspector only accepts this exporter subset')
            p.done()
        fr.done()
        require(len({c['layer'] for c in cels})==len(cels),'Duplicate layer cel')
        frames.append({'duration_ms':ms,'cels':cels})
    r.done()
    require(layers,'No source layers')
    return {'canvas':[w,h],'layers':layers,'tags':tags,'frames':frames,'palette':palette,'profile':profile}

def compare(project, decoded):
    for key in ('canvas','layers','tags','palette','profile','frames'):
        require(project[key]==decoded[key],f'Decoded {key} differ from exact source contract')

def report(decoded, data, project=None):
    out={'passed':True,'tool_version':VERSION,'aseprite_sha256':sha(data),'canvas':decoded['canvas'],'color_mode':'RGBA',
         'frame_count':len(decoded['frames']),'layers':decoded['layers'],'tags':decoded['tags'],'palette':decoded['palette'],
         'color_profile':{'kind':decoded['profile'][0],'sha256':sha(decoded['profile'][1]) if decoded['profile'][1] else None},
         'frames':[{'duration_ms':f['duration_ms'],'cels':[{k:v for k,v in c.items() if k!='raw'}|{'rgba_sha256':sha(c['raw'])} for c in f['cels']]} for f in decoded['frames']],
         'decoded_inputs_match':project is not None,'app_open_verified':False,
         'scope':'Strict decoded-byte, duration, palette, layer, and tag verification; not an Aseprite application-open test'}
    if project is not None:
        out['sources']=[{k:v for k,v in s.items() if k not in ('raw','profile','palette')} for s in project['sources']]
        out['static_default_duration']=project['static_default_duration']
        if any(s['png_chromaticity_hex'] and s['profile'][0]=='none' for s in project['sources']):
            out['color_metadata_note']='Source cHRM-only chromaticity is retained verbatim in this report. Aseprite has no equivalent partial-profile field; output stays untagged. Exact RGBA samples are verified, but color-managed appearance equivalence is not claimed.'
        if project['static_default_duration']:
            out['timing_note']='The one still frame uses 100 ms serialization metadata; no animation timing was inferred.'
        out['fidelity_note']='RGBA sample values, including RGB under zero alpha, are exact. Indexed PNG palette entries/order/alpha are copied; cel index encoding is represented as RGBA. PNG ancillary metadata other than supported color profiles/palette is not copied.'
    return out

def no_existing(path):
    require(not path.exists() and not path.is_symlink(),f'Output already exists: {path}; choose a new path')
    require(path.parent.is_dir(),f'Output parent does not exist: {path.parent}')

def atomic_new(path,data):
    no_existing(path)
    fd,temp=tempfile.mkstemp(prefix='.aseprite-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.link(temp,path)
    finally:
        os.unlink(temp)

def export(project, output, report_path=None, manifest_path=None):
    output=Path(output).absolute()
    targets=[output]+([Path(report_path).absolute()] if report_path else [])
    protected={Path(s['path']).resolve() for s in project['sources']}
    if manifest_path:
        protected.add(Path(manifest_path).resolve())
    require(len({p.resolve() for p in targets})==len(targets),'Output and report paths collide')
    for target in targets:
        require(target.resolve() not in protected,'Output path collides with input')
        no_existing(target)
    data=encode(project)
    decoded=inspect_bytes(data)
    compare(project,decoded)
    result=report(decoded,data,project)
    atomic_new(output,data)
    if report_path:
        atomic_new(Path(report_path).absolute(),(json.dumps(result,indent=2,ensure_ascii=False)+'\n').encode())
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    static=sub.add_parser('static',help='One PNG to one frame; default 100 ms is still-container metadata only')
    static.add_argument('png'); static.add_argument('output')
    static.add_argument('--duration-ms',type=int)
    static.add_argument('--layer-name',default='Flattened source artwork')
    static.add_argument('--report')
    manifest=sub.add_parser('manifest',help='Explicit sequence, sheet, or true source layers JSON to Aseprite')
    manifest.add_argument('manifest'); manifest.add_argument('output'); manifest.add_argument('--report')
    inspect=sub.add_parser('inspect',help='Inspect only this exporter subset; optionally compare its source manifest')
    inspect.add_argument('aseprite'); inspect.add_argument('--manifest'); inspect.add_argument('--report')
    args=parser.parse_args(argv)
    try:
        if args.command=='static':
            doc={'version':1,'mode':'sequence','layer_name':args.layer_name,'frames':[{'png':str(Path(args.png).resolve()),'duration_ms':args.duration_ms if args.duration_ms is not None else 100}]}
            project=compile_manifest(doc,Path.cwd(),static_default=args.duration_ms is None)
            result=export(project,args.output,args.report)
        elif args.command=='manifest':
            project=compile_manifest(read_json(args.manifest),Path(args.manifest).resolve().parent)
            result=export(project,args.output,args.report,args.manifest)
        else:
            source=Path(args.aseprite)
            require(source.stat().st_size<=MAX_FILE_BYTES,'Aseprite exceeds file safety limit')
            data=source.read_bytes()
            decoded=inspect_bytes(data)
            project=None
            if args.manifest:
                project=compile_manifest(read_json(args.manifest),Path(args.manifest).resolve().parent)
                compare(project,decoded)
            result=report(decoded,data,project)
            if args.report:
                target=Path(args.report).absolute()
                protected={source.resolve()}
                if args.manifest:
                    protected.add(Path(args.manifest).resolve())
                    protected.update(Path(s['path']).resolve() for s in project['sources'])
                require(target.resolve() not in protected,'Report path collides with input')
                atomic_new(target,(json.dumps(result,indent=2,ensure_ascii=False)+'\n').encode())
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0
    except (ExportError,OSError,ValueError,KeyError,TypeError,struct.error,zlib.error,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        print(json.dumps({'passed':False,'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    sys.exit(main())
