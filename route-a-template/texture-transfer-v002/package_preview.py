from pathlib import Path
import base64,json
P=Path(__file__).resolve().parent;ROOT=P.parents[1];V1=P.parent/'texture-transfer-v001'
def data(path,mime='image/png'):
    return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()
payload={'model':base64.b64encode((P/'lowpoly-skin-test.glb').read_bytes()).decode(),
         'textures':{'original':data(V1/'source/Cat_Domestic_Shorthair_COL_2k.png'),
                     'semantic':data(P/'textures/Cat_Semantic_BaseColor_2k.png'),
                     'lowpoly':data(P/'textures/Cat_LowPoly_Generated.png')},
         'fallback':data(P/'preview/lowpoly-front-right.png')}
html=(P/'viewer-template.html').read_text().replace('__DATA__',json.dumps(payload))
html=html.replace('__PHOTO__',data(ROOT/'example/S__48381957_0.jpg','image/jpeg')).replace('__STYLE__',data(ROOT/'cat.png'))
(P/'preview.html').write_text(html)
print('Preview saved:',P/'preview.html')
