import subprocess
b=0.48375; ph=0.2
segs=[(33,4,'hook'),(0,4,'squid'),(9,3,'boss'),(14,3,'chant'),(19,3,'rose'),(24,4,'sneak'),(29,11,'statue->tap->run')]
enc=['-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r','30','-c:a','pcm_s16le','-ar','44100']
lst=open('list.txt','w'); t=0; beats=0
for i,(n,L,lab) in enumerate(segs):
    s=n*b+ph; fr=round((beats+L)*b*30)-round(beats*b*30); beats+=L; d=fr/30
    af=f"afade=t=in:d=0.015,afade=t=out:st={d-0.025:.4f}:d=0.025"
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{s:.4f}','-i','in.mp4']
    if i==0:
        cmd+=['-i','hook.png','-filter_complex',
          "[0:v]split[h1][h2];[h2]crop=1080:340:0:1470,boxblur=18:2[bl];[h1][bl]overlay=0:1470,scale=1188:2112,crop=1080:1920[hz];[hz][1:v]overlay=0:0[v]",
          '-map','[v]','-map','0:a','-af',af]
    else:
        cmd+=['-af',af]
    cmd+=['-frames:v',str(fr),'-t',f'{d:.4f}']+enc+[f'seg{i}.mkv']
    subprocess.run(cmd,check=True); lst.write(f"file 'seg{i}.mkv'\n")
    print(f"{t:6.2f}-{t+d:6.2f}  src {s:6.2f}-{s+d:6.2f}  {lab}"); t+=d
lst.close()
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i','list.txt','-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart','reels_recut.mp4'],check=True)
