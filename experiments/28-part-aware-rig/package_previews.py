"""Review media from existing actual renders, fixed-size inputs and fixed cadence."""
import json
from pathlib import Path
import subprocess

P=Path(__file__).resolve().parent;out=P/'media';out.mkdir(exist_ok=False)
ffmpeg='/opt/homebrew/bin/ffmpeg'
def run(args):subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-n',*args],check=True)
sources={'previous':P.parent/'27-animation-compatibility/weights-v001','current':P/'fit-v002/original/candidate'}
for name,folder in sources.items():
    dest=out/name;dest.mkdir()
    report=json.loads((folder/'motion/report.json').read_text());assert len(report['renders'])==50
    for pose in ['Idle','Sitting']:
        run(['-i',str(folder/'preview'/f'{pose}-0001.png'),'-vf','scale=512:512','-frames:v','1',str(dest/(pose+'.png'))])
    frames=[dest/'Idle.png']*12
    frames += [folder/'motion'/f'Walk-{i:04d}.png' for _ in range(4) for i in range(1,28,2)]
    frames += [folder/'motion'/f'Idle_to_Sit-{i:04d}.png' for i in range(1,36,2)]
    frames += [dest/'Sitting.png']*15
    frames += [folder/'motion'/f'Sitting_to_Idle-{i:04d}.png' for i in range(1,36,2)]
    frames += [dest/'Idle.png']*12
    lines=['ffconcat version 1.0']
    for f in frames:
        quoted=str(f.resolve()).replace("'","'\\''")
        lines += ["file '"+quoted+"'",'duration 0.0666666667']
    lines.append("file '"+str(frames[-1].resolve())+"'")
    concat=dest/'sequence.ffconcat';concat.write_text('\n'.join(lines)+'\n')
    run(['-f','concat','-safe','0','-i',str(concat),'-vf','fps=15','-r','15','-fps_mode','cfr','-an','-c:v','libx264','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(dest/'review.mp4')])
run(['-i',str(out/'previous/review.mp4'),'-i',str(out/'current/review.mp4'),'-filter_complex','[0:v][1:v]hstack=inputs=2[v]','-map','[v]','-r','15','-fps_mode','cfr','-c:v','libx264','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'comparison.mp4')])
run(['-i',str(out/'current/review.mp4'),'-filter_complex','[0:v]scale=480:-1,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=bayer','-loop','0',str(out/'current.gif')])
run(['-i',str(sources['previous']/'preview/Sitting-0001.png'),'-i',str(sources['current']/'preview/Sitting-0001.png'),'-filter_complex','[0:v][1:v]hstack=inputs=2[v]','-map','[v]','-frames:v','1',str(out/'sitting-comparison.png')])
(out/'provenance.json').write_text(json.dumps({'artifact_kind':'actual_skinned_3D_animation_renders','comparison_layout':'Left: previous stage 27 weights-v001. Right: new stage 28 fit-v002.',
 'video_fps':15,'source_fps':30,'sample_step':2,'holds':['Idle static pose','Sitting static pose'],
 'note':'Montage only; five full clips independently measured at every integer frame. New method rejected for animation regression.',
 'sources':{k:str(v) for k,v in sources.items()}},indent=2)+'\n')
print('PREVIEW_MEDIA_COMPLETE')
