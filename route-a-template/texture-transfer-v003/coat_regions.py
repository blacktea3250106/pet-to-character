"""Manual surface region authoring inherited from v002, corrected for v003.
No photograph sampling, UV sampling or generative painting occurs here.
"""
from pathlib import Path
import json
import numpy as np
FEATURES=json.loads((Path(__file__).parent/'coat-features.json').read_text())
palette={k:np.array([int(v[i:i+2],16)/255 for i in (1,3,5)]) for k,v in FEATURES['palette_srgb'].items()}

def polygon(points,poly):
    x,y=points.T;inside=np.zeros(len(points),dtype=bool)
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if a[1]==b[1]:continue
        inside^=((a[1]>y)!=(b[1]>y))&(x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])
    return inside

def shade(p,n,w,orig,tri):
    x,y,z=p.T
    rgb=np.tile(palette['black'],(len(p),1))
    s=(.14-z)/.30;t=(y-(.117+.025*np.clip(s,0,1)))/(.253-(.117+.025*np.clip(s,0,1)))
    st=np.c_[s,t]
    # Semantic patches are polygons in anatomy space. Angular boundaries remain
    # separate from geometric facets; neither input lighting nor fur is sampled.
    orange=np.zeros(len(p),bool)
    for side,key in [(x<0,'orange_polygons_right'),(x>=0,'orange_polygons_left')]:
        for poly in FEATURES[key]:orange|=side&polygon(st,poly)
    rgb[orange]=palette['orange']
    # Modest, continuous dorsal islands bridge the side maps.
    dorsal=(n[:,1]>.70)&(y>.236)&(z<.11)&(z>-.175)
    stripes=((s>.265)&(s<.34))|((s>.51)&(s<.59))|((s>.77)&(s<.86))
    rgb[dorsal]=palette['black'];rgb[dorsal&stripes]=palette['orange']
    belly=(y<.142+.01*np.clip(s,0,1))&(abs(x)<.047)&(n[:,1]<.1)
    rgb[belly]=palette['white']
    # Collar/bib, not all of the shoulder.
    bib=(z>.125)&(y>.111)&(y<.230)&(abs(x)<.050)&(n[:,2]>-.05)
    rgb[bib]=palette['white']
    collar=(z>.174)&(z<.199)&(y>.201)&(y<.232)&(abs(x)>.032)
    rgb[collar]=palette['white']
    # Legs retain different orange and black upper patches, white socks.
    front=w[:,18:25].sum(1)+w[:,26:33].sum(1)
    rear=w[:,34:48].sum(1)
    fl=(front>.45)&(y<.17);rl=(rear>.45)&(y<.16)
    rgb[fl|rl]=palette['black']
    rgb[fl&(y<.094)&(y>.027)]=palette['orange']
    rgb[rl&(y<.090)&(y>.035)]=palette['orange']
    socks=(front+rear>.38)&(y<.047+(.008*(x>0)))
    rgb[socks]=palette['white']
    wrist=fl&(y>.027)&(y<.040)&(abs(x)>.036)&(z>.116)
    rgb[wrist]=palette['orange']
    chest=(z>.134)&(y>.132)&(y<.228)&(abs(x)<(.025+(y-.13)*.18))
    rgb[chest]=palette['white']
    # Head features registered to the asset's eyes/nose, not to a rectangular photo.
    headw=w[:,5]+w[:,6]+w[:,7]+w[:,12]+w[:,13]
    head=(headw>.48)&(y>.202)
    rgb[head]=palette['black']
    throat=head&(y<.228)&(z>.191)
    rgb[throat]=palette['white']
    face=head&(z>.205)
    chin=face&(y<.226)&((abs(x)>.010)|(y<.216))
    rgb[chin]=palette['white']
    # Subject's right orange cheek surrounds the eye, left stays dark.
    right=face&(x<-.010)&polygon(np.c_[x,y],[[-.052,.235],[-.047,.253],[-.031,.258],[-.023,.251],[-.011,.241],[-.014,.228],[-.031,.225],[-.043,.230]])
    rgb[right]=palette['orange']
    brow_r=face&polygon(np.c_[x,y],[[-.029,.249],[-.031,.260],[-.020,.266],[-.010,.262],[-.014,.253]])
    brow_l=face&polygon(np.c_[x,y],[[.008,.252],[.010,.270],[.019,.272],[.025,.261],[.039,.258],[.035,.249],[.022,.253]])
    rgb[brow_r|brow_l]=palette['orange']
    # Small orange crown fork, with a broad uninterrupted dark nasal bridge.
    crown=head&(y>.267)&(z>.211)&(x>.000)&(x<.018)&(y<.279-abs(x-.008)*.5)
    rgb[crown]=palette['orange']
    muzzle=face&(y<.228)&(y>.216)&(abs(x)<.023)&(abs(x)>.010)&(z>.241)
    rgb[muzzle]=palette['orange']
    nose=(z>.254)&(abs(x)<.010)&(y<.235)&(y>.221)
    rgb[nose]=palette['nose']
    # Ear cartilage is subdued; tips are orange as observed.
    ear=w[:,14]+w[:,15];e=ear>.35
    rgb[e]=palette['black']
    rgb[e&(n[:,2]>.2)]=palette['inner_ear']
    rgb[e&(y>.299-abs(x)*.065)]=palette['orange']
    tw=w[:,48:52].sum(1);tail=tw>.5;tt=(-z-.163)/.206
    rgb[tail]=palette['black']
    rings=((tt>.06)&(tt<.18+x*3))|((tt>.36)&(tt<.47)&(x<.004))|((tt>.67)&(tt<.74)&(x>-.003))
    rgb[tail&rings]=palette['orange']
    # Eyes are also strict face colors in this diagnostic, with a geometric slit.
    eye=w[:,10]+w[:,11];em=eye>.55
    rgb[em]=palette['iris']
    pupil=em&(abs(abs(x)-.0150)<.00205)&(abs(y-.247)<.0062)&(z>.234)
    rgb[pupil]=palette['pupil']
    mouth=w[:,8]+w[:,9];rgb[mouth>.5]=palette['mouth']
    return np.clip(rgb,0,1)
