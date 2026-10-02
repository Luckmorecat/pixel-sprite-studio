#!/usr/bin/env bash
# Deterministic native-grid normalization with unchanged source and provenance.
set -euo pipefail
input= output= width= height= colors= crop= palette= grid_lock= project= run= attempt=
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
usage() { echo 'Usage: prepare_pixels.sh --input source.png --output native.png --width 64 --height 64 [--colors 32] [--crop WxH+X+Y] [--palette approved-master.png] [--grid-lock master.provenance.json] [--project project.json] [--run run-dir --attempt-id attempt-0001]'; }
while (( $# )); do
  case "$1" in
    --input) input=${2:?}; shift 2;; --output) output=${2:?}; shift 2;;
    --width) width=${2:?}; shift 2;; --height) height=${2:?}; shift 2;;
    --colors) colors=${2:?}; shift 2;; --crop) crop=${2:?}; shift 2;; --palette) palette=${2:?}; shift 2;;
    --grid-lock) grid_lock=${2:?}; shift 2;; --project) project=${2:?}; shift 2;;
    --run) run=${2:?}; shift 2;; --attempt-id) attempt=${2:?}; shift 2;;
    --help|-h) usage; exit 0;; *) usage >&2; exit 2;;
  esac
done
[[ -f "$input" && -n "$output" ]] || { echo 'Input must exist and output must be specified.' >&2; exit 2; }
if [[ -n "$project" ]]; then
 settings=$(PYTHONPATH="$script_dir${PYTHONPATH:+:$PYTHONPATH}" python3 - "$project" "$width" "$height" "$colors" <<'PYPROJECT'
import sys
from project_config import enforce_normalization
try:
 p,w,h,c=sys.argv[1:]
 settings=enforce_normalization(p, int(w) if w else None, int(h) if h else None, int(c) if c else None)
 print(settings['width'],settings['height'],settings['colors'])
except (ValueError,OSError) as exc:raise SystemExit(str(exc))
PYPROJECT
 )
 read -r width height colors <<< "$settings"
fi
if [[ -n "$run" || -n "$attempt" ]]; then
 [[ -n "$run" && -n "$attempt" ]] || { echo 'Use --run and --attempt-id together.' >&2; exit 2; }
 PYTHONPATH="$script_dir${PYTHONPATH:+:$PYTHONPATH}" python3 - "$run" "$attempt" "$input" "$output" <<'PYATTEMPT'
import sys
from run_ledger import verify_attempt_source
try: verify_attempt_source(*sys.argv[1:])
except (ValueError,OSError) as exc: raise SystemExit(str(exc))
PYATTEMPT
fi
colors=${colors:-32}
[[ "$width" =~ ^[1-9][0-9]*$ && "$height" =~ ^[1-9][0-9]*$ && "$colors" =~ ^[1-9][0-9]*$ ]] || { echo 'Width, height and colors must be positive integers.' >&2; exit 2; }
(( width <= 4096 && height <= 4096 && colors >= 1 && colors <= 256 )) || { echo 'Use dimensions <=4096 and 1–256 colors.' >&2; exit 2; }
command -v magick >/dev/null || { echo 'ImageMagick 7 magick is required.' >&2; exit 2; }
command -v python3 >/dev/null || { echo 'Python 3 is required for provenance JSON.' >&2; exit 2; }
[[ "$output" == *.png ]] || { echo 'Output must be a PNG.' >&2; exit 2; }
preview="${output%.png}-6x.png"; provenance="${output%.png}.provenance.json"
for target in "$output" "$preview" "$provenance"; do [[ ! -e "$target" && ! -L "$target" ]] || { echo "Refusing to overwrite $target" >&2; exit 2; }; done
metadata=$(magick identify -ping -format '%w %h %n\n' "$input")
read -r source_w source_h frames <<< "$metadata"
[[ "${source_w:-}" =~ ^[0-9]+$ && "${source_h:-}" =~ ^[0-9]+$ ]] || { echo 'Unable to read source dimensions.' >&2; exit 2; }
[[ "${frames:-1}" == 1 ]] || { echo 'Supply a single still image, not an animation.' >&2; exit 2; }
cw=$source_w; ch=$source_h; crop_args=()
if [[ -n "$crop" ]]; then
  [[ "$crop" =~ ^([1-9][0-9]*)x([1-9][0-9]*)\+([0-9]+)\+([0-9]+)$ ]] || { echo 'Crop must be WxH+X+Y with nonnegative coordinates.' >&2; exit 2; }
  cw=${BASH_REMATCH[1]}; ch=${BASH_REMATCH[2]}; cx=${BASH_REMATCH[3]}; cy=${BASH_REMATCH[4]}
  (( cx + cw <= source_w && cy + ch <= source_h )) || { echo 'Crop exceeds source bounds.' >&2; exit 2; }
  crop_args=(-crop "$crop" +repage)
fi
(( cw * height == ch * width )) || { echo "Aspect ratio mismatch ($cw x $ch vs $width x $height); measure a matching crop rather than distort." >&2; exit 2; }
palette_args=()
if [[ -n "$palette" ]]; then
 [[ -f "$palette" ]] || { echo "Palette reference does not exist." >&2; exit 2; }
 palette_args=(+dither -remap "$palette")
fi
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
python3 - "$input" "$palette" "$grid_lock" "$source_w" "$source_h" "$width" "$height" "$crop" "$tmp" "$project" "$run" "$attempt" <<'PY'
import hashlib,json,pathlib,sys
source,palette,lock,sw,sh,w,h,crop,tmp,project,run,attempt=sys.argv[1:]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
if lock:
 p=json.loads(pathlib.Path(lock).read_text())
 expected=(p['source']['width'],p['source']['height'],p['output']['width'],p['output']['height'],p.get('crop'))
 actual=(int(sw),int(sh),int(w),int(h),crop or None)
 if actual!=expected:raise SystemExit(f'Grid lock mismatch: expected source/native dimensions and crop {expected}, got {actual}. Do not independently crop or recenter poses.')
pathlib.Path(tmp,'inputs.json').write_text(json.dumps({'source_sha256':sha(source),'palette_sha256':sha(palette) if palette else None,'grid_lock_sha256':sha(lock) if lock else None,'project_sha256':sha(project) if project else None}))
PY
# Alpha conversion is documented technical normalization, not background removal.
magick "${input}[0]" "${crop_args[@]}" -colorspace sRGB -filter point -resize "${width}x${height}!" -alpha on -channel A -threshold 50% +channel -dither None -colors "$colors" "${palette_args[@]}" -channel A -threshold 50% +channel -depth 8 "PNG32:$tmp/native.png"
magick "$tmp/native.png" -filter point -resize "$((width*6))x$((height*6))!" "PNG32:$tmp/preview.png"
PYTHONPATH="$script_dir${PYTHONPATH:+:$PYTHONPATH}" python3 - "$input" "$output" "$preview" "$provenance" "$source_w" "$source_h" "$width" "$height" "$colors" "$crop" "$palette" "$grid_lock" "$tmp" "$project" "$run" "$attempt" <<'PY'
import hashlib,json,pathlib,sys
source,out,preview,prov,sw,sh,w,h,colors,crop,palette,lock,tmp,project,run,attempt=sys.argv[1:];tmp=pathlib.Path(tmp)
def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
inputs=json.loads((tmp/'inputs.json').read_text())
for path,key in ((source,'source_sha256'),(palette,'palette_sha256'),(lock,'grid_lock_sha256'),(project,'project_sha256')):
 if path and digest(path)!=inputs[key]:raise SystemExit('Input changed during normalization: '+path)
record={'operation':'ImageMagick nearest-neighbor normalization, no dither, limited colors, binary alpha','source':{'file':str(pathlib.Path(source).resolve()),'sha256':digest(source),'width':int(sw),'height':int(sh)},'output':{'file':str(pathlib.Path(out).resolve()),'sha256':digest(tmp/'native.png'),'width':int(w),'height':int(h)},'preview':str(pathlib.Path(preview).resolve()),'preview_sha256':digest(tmp/'preview.png'),'crop':crop or None,'palette_reference':({'file':str(pathlib.Path(palette).resolve()),'sha256':digest(palette)} if palette else None),'grid_lock':({'file':str(pathlib.Path(lock).resolve()),'sha256':digest(lock),'matched':True} if lock else None),'requested_color_limit':int(colors),'alpha_threshold_percent':50,'generation_attempt_id':attempt or None,'source_resolution':'Verify source.sha256; use run_ledger.py resolve against captured evidence if source.file is missing or reused','creative_repair':False,'alignment':'Declared fixed canvas/crop/nearest-neighbor scale; no translation or recentering','visual_status':'unreviewed','quality_warning':'Technical normalization is not a visual pixel-craft approval or proof of pose alignment.'}
if project:
 from project_config import enforce_normalization
 from pixel_pipeline import decode_png,pixel_stats
 settings=enforce_normalization(project,int(w),int(h),int(colors))
 _,raw=decode_png(tmp/'native.png');stats,_=pixel_stats(raw,int(w))
 if stats['palette_count_visible']>settings['palette_max']:raise SystemExit('Normalized output exceeds project palette_max')
 if not stats['binary_alpha']:raise SystemExit('Normalized output violates project binary_alpha')
 if stats['clear_margins'] is None or min(stats['clear_margins'].values())<settings['min_margin']:raise SystemExit('Normalized output violates project min_margin')
 record['project_provenance']=settings['project_provenance']
 record['project_limits_verified']={'palette_max':settings['palette_max'],'binary_alpha':True,'min_margin':settings['min_margin']}
outputs=[(pathlib.Path(out),(tmp/'native.png').read_bytes()),(pathlib.Path(preview),(tmp/'preview.png').read_bytes()),(pathlib.Path(prov),(json.dumps(record,indent=2)+'\n').encode())]
pathlib.Path(out).parent.mkdir(parents=True,exist_ok=True)
created=[]
try:
 for path,data in outputs:
  with path.open('xb') as f:
   created.append(path);f.write(data)
except BaseException:
 for path in created:path.unlink()
 raise
PY
printf 'Created %s\nPreview %s\nProvenance %s\n' "$output" "$preview" "$provenance"
