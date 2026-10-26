"""Package actual 3D renders into review videos; no generated imagery."""
import json
from pathlib import Path
import subprocess

P = Path(__file__).resolve().parent
ffmpeg = '/opt/homebrew/bin/ffmpeg'


def run(argv):
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-n', *argv], check=True)


def clip(candidate):
    folder = P / candidate
    report = json.loads((folder / 'motion/report.json').read_text())
    assert len(report['renders']) == 50
    frames = [folder / 'preview/Idle-0001.png'] * 12
    walk = [folder / 'motion' / f'Walk-{i:04d}.png' for i in range(1, 28, 2)]
    frames += walk * 4
    frames += [folder / 'motion' / f'Idle_to_Sit-{i:04d}.png' for i in range(1, 36, 2)]
    frames += [folder / 'preview/Sitting-0001.png'] * 15
    frames += [folder / 'motion' / f'Sitting_to_Idle-{i:04d}.png' for i in range(1, 36, 2)]
    frames += [folder / 'preview/Idle-0001.png'] * 12
    assert all(f.exists() for f in frames)
    # ffconcat uses its own path quoting, independent of shell quoting.
    def quote(s):
        return "'" + str(s).replace("'", "'\\''") + "'"
    concat = folder / 'motion/review-sequence.ffconcat'
    lines = ['ffconcat version 1.0']
    for f in frames:
        lines.extend(['file ' + quote(f.resolve()), 'duration 0.0666666667'])
    lines.append('file ' + quote(frames[-1].resolve()))
    concat.write_text('\n'.join(lines) + '\n')
    movie = folder / 'motion/review.mp4'
    if movie.exists():
        return movie
    run(['-f', 'concat', '-safe', '0', '-i', str(concat), '-vf', 'scale=512:512,fps=15',
         '-an', '-c:v', 'libx264', '-crf', '19', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(movie)])
    return movie


before = clip('baseline-v002')
after = clip('weights-v001')
run(['-i', str(before), '-i', str(after), '-filter_complex',
     '[0:v][1:v]hstack=inputs=2[v]', '-map', '[v]', '-an', '-c:v', 'libx264', '-crf', '19',
     '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(P / 'animation-comparison.mp4')])
run(['-i', str(after), '-filter_complex',
     '[0:v]fps=15,scale=480:-1,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=bayer',
     '-loop', '0', str(P / 'animation-preview.gif')])
(P / 'preview-provenance.json').write_text(json.dumps({
    'artifact_kind': 'actual_skinned_3D_animation_render',
    'source_render_fps': 30, 'sample_step': 2, 'video_fps': 15,
    'clips': ['Idle still', 'Walk repeated four times', 'Idle_to_Sit', 'Sitting still', 'Sitting_to_Idle', 'Idle still'],
    'note': 'Idle and Sitting are held preview frames in this montage; their full clips were separately measured every frame.',
    'before': str(before.relative_to(P)), 'after': str(after.relative_to(P)),
    'comparison': 'animation-comparison.mp4', 'preview': 'animation-preview.gif',
    'comparison_layout': 'Left: baseline-v002, four influences. Right: weights-v001, smoothed with eight influences.',
    'packaging_note': 'Installed FFmpeg has no drawtext filter; labels supplied here and in linked workflow instead of burned into video.',
    'animation_quality_pass': False,
}, indent=2) + '\n')
print('PREVIEWS_ASSEMBLED')
