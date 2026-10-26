"""Finalize the bounded method comparison and preserve its failures."""
import hashlib
import json
from pathlib import Path

P=Path(__file__).resolve().parent;G=P.parent
def read(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
old=read(G/'27-animation-compatibility/weights-v001/animation-report.json')
now=read(P/'fit-v002/original/candidate/animation-report.json')
export=read(P/'fit-v002/original/candidate/export/verification.json')
comparison=[]
for a,b in zip(old['actions'],now['actions']):
    assert a['action']==b['action']
    comparison.append({'action':a['action'],'coverage_frames':b['frames'],'previous':a['metrics']['target'],'current':b['metrics']['target']})
stress=[]
for c in read(P/'stress-inputs/manifest.json')['cases']:
    folder=P/'fit-v002'/c['case'];r=read(folder/'candidate/animation-report.json');f=read(folder/'fit.json');audit=read(folder/'rest-audit.json')
    stress.append({**c,'coverage':r['coverage'],'frames':sum(a['frames'] for a in r['actions']),
        'actions':[{ 'action':a['action'], 'metrics':a['metrics']['target']} for a in r['actions']],
        'target_rest_crossings':audit['target_rest_crossing_pairs'],'new_scaffold_crossings':audit['new_scaffold_crossing_pairs'],
        'seeds_automatically_recomputed':True,'new_cat':False,'quality_pass':False})
inventory=read(G/'27-animation-compatibility/inventory/report.json');input_hashes={}
for key in ['source','target']:
    d=inventory[key];current=hashlib.sha256(Path(d['path']).read_bytes()).hexdigest();assert current==d['sha256']
    input_hashes[key]={'path':d['path'],'sha256':current,'unchanged':True}
audit=read(P/'fit-v002/original/rest-audit.json')
write(P/'review.json',{
 'status':'completed_bounded_trial_rejected_animation_regression',
 'purpose':'測試不同腿長/胖瘦所需的部位對應與關節定位；不是外觀修圖或新生成。',
 'input_hashes':input_hashes,'triangles':3500,'source_bones':56,
 'methods':[{'name':'fit-v001','method':'內在表面路徑分區＋最近頂點對應＋位移平滑','result':'拒絕；400 個母版面積縮到初始 10% 以下。'},
            {'name':'fit-v002','method':'同一自動部位資訊＋三角形連續對應＋局部剛性 ARAP 約束','result':'面積嚴重縮小減至 8 面，但包覆自交/動畫驗收仍失敗；不採用。'}],
 'measured_changes':comparison,
 'interpretation':[
  '原貓五動作 597 幀；與 27 weights-v001 使用同一量測器、相同五輪/0.35 平滑和八影響，原幾何/UV/底色保持。',
  '來源到目標最近表面距離 p95 由最大尺寸約 21.9% 降至 7.54%，仍不能證明有效語義對應。',
  'Walk 超過兩倍的邊樣本 26→68，最低點 -1.24%→-2.27%；新方法有退步。',
  'Sitting 最深穿地由 4.16% 降至 3.40%，但相交面對 304→435、塌陷面 65→84；不能只報穿地改善。',
  '同一母版面索引的靜止交叉對由 46→566；新增 563 對，527 對集中在頭/頭。ARAP 沒有保證一對一或避免自交。',
  '四根尾骨仍保留來源靜止軸，與擬合後骨頭方向差約 40.9–82.6 度；現行只改骨頭位置/複製旋轉不足以處理不同尾巴姿勢。',
  '骨頭位置由局部表面仿射映射推導，並未加入關節角度、骨段長度比或關節中心必須落於可靠解剖區域的約束。56 根骨包含控制/輔助骨，不能當成 56 個解剖關節。',
  '部位推導成功與程式跑完不等於骨架/動畫成功；新候選不替換 27，27 本身也還不是正式通過。',
 ],
 'synthetic_stress':stress,
 'stress_interpretation':[
  '合成短腿、長腿、偏瘦、胖身與短腿胖身各 15 個首/中/末姿勢；不是完整 597 幀，也不是五隻独立新貓。',
  '五種輸入靜止網格都未檢出嚴格非相鄰交叉，面數仍 3500；沒有用輸入自身的明顯折疊冒充動畫失敗。',
  'Sitting 抽樣：短腿最低點在地上 4.14%、長腿在地下 11.79%、偏瘦在地下 4.45%、胖身在地上 5.07%、短腿胖身在地上 5.31%；全部以每個輸入最大尺寸歸一化，非公分。',
  '短腿/胖身浮空、長腿穿地表明根運動和支撐接觸不能用初始整體尺度代替；本輪尚未加入接地 IK。',
 ],
 'visual_evidence':{
  'part_map':'fit-v002/original/diagnostic/target-parts.png',
  'scaffold':'fit-v002/original/diagnostic/wrapped-scaffold.png',
  'estimated_joints':'fit-v002/original/diagnostic/estimated-joints.png',
  'comparison':'media/comparison.mp4','layout':'左 27 既有版本；右 28 新測試，已拒絕採用。',
  'short_legs':'fit-v002/short_legs/candidate/preview/Sitting-0001.png',
  'long_legs':'fit-v002/long_legs/candidate/preview/Sitting-0001.png',
  'short_fat':'fit-v002/short_fat/candidate/preview/Sitting-0001.png',
  'review':'新原貓動作可辨認，但尾巴在坐姿捲入腿/腹周圍；短腿/短胖浮空和長腿陷地在實際渲染可見。未因畫面仍可看而放行。',
 },
 'automation':{
  'new_capabilities':['無目標手點的四脚/頭尾候選與七部位粗分區','分部位中介表面擬合及局部關節推導','同規則重跑五種合成體型','靜止包覆自交和骨軸差異診斷'],
  'manual_target_landmarks_added':0,'manual_target_weight_paint':False,
  'fixed_template_work':['來源骨名對身體部位語義映射','來源/輸入朝向約定','無量綱方法參數与壓力範圍'],
  'remaining_manual_work':['部位/關節與動作視覺審查','方法/門檻解讀','先前照片及参考生成仍有人工依賴'],
  'tested_independent_generated_cats':1,'synthetic_variants':5,'held_out_generated_cats':0,
  'conclusion':'部分資料取得與診斷可自動執行；可靠自動綁骨仍未完成，不填造成功率。',
 },
 'workflow_error_found':{
  'error':'本輪先以距離/面積和可視化決定是否作診斷綁骨，靜止包覆自交檢查放得太晚；此順序漏掉頭部折疊。',
  'fix':'新增 assess_fit_gate.py，後續一般 build_candidate 必須有有效 fit-gate；已拒絕或缺證據時只允許明確 diagnostic-only 分析。',
  'timing':'實驗後發現並修正，不能回溯宣稱本次候選曾先通過此 gate。',
  'verification':'gate-verification.json',
 },
 'next_priorities_not_implemented':[
  '以一次母版設定建立可靠解剖/骨段約束與可包覆表面；頭部內外層/嘴部要有獨立語義或使用簡化中介籠，先通過自交與對應驗收。',
  '對姿勢不同的尾巴與肢體重新建立靜止方向，連同旋轉座標轉換驗證；不能一方面把位置彎成曲線，一方面假設原骨軸仍正確。',
  '以每條腿的骨段及來源支撐期適配根運動與接地 IK/坐姿避碰；不得只抬整隻貓掩蓋穿地。',
  '上述成立後，再用真正独立生成的不同體型驗證；合成變體不能當留出貓。',
 ],
 'export_roundtrip_pass':export['export_roundtrip_pass'],
 'export_note':'新研究 GLB 保留 3500 面、56 骨、五動畫，底色解碼差 0；15 個回讀姿勢最大差約 7.98e-5/最大尺寸。檔案正確不修復既有動畫缺陷。',
 'animation_quality_pass':False,'body_variation_support_pass':False,'unity_pass':False,
 'new_cat_automation_proven':False,'paid_api_calls':0,
 'decision':'兩種對應方法已完成，不再掃參數/逐貓手修。保留診斷和攔截能力，新動畫候選拒絕採用；原外觀與 27 實驗檔不被替換。',
})
write(P/'reproduction.json',{
 'tools':{'blender':'5.2.1 LTS','python':'3.14','numpy':'2.5.3','scipy':'1.18.1'},
 'method_references':[
  {'title':'SciPy sparse graph shortest paths','url':'https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.shortest_path.html','use':'表面網格最短路徑；本案語義推導為研究啟發式，不是文件保證。'},
  {'title':'Sorkine and Alexa, ARAP Surface Modeling','url':'https://igl.ethz.ch/projects/ARAP/','use':'局部旋轉/位置交替解的依據；本案另加軟表面/部位約束，不是原论文完整重現，也無免自交保證。'},
 ],
 'steps':['fit_parts.py','fit_parts.py --output fit-v002 --arap','Blender render_fit.py -- fit-v001 / fit-v002',
          'Blender build_candidate.py -- --diagnostic-only（初次執行在新增 gate 之前；executed-source.py 保留舊版）',
          '27/bake_and_measure.py -- <absolute candidate path>（原貓全幀）',
          'make_stress_fixtures.py','run_stress.py（各 15 幀，所有點位重新推導）',
          'Blender audit_rest.py → assess_fit_gate.py（目前已改為未來一般綁骨前置）',
          '27/export_verify.py -- <absolute original candidate path>',
          '27/render_motion.py -- <absolute original candidate path> / --motion','render_stress.py -- <relative candidate path>',
          'package_previews.py','finalize_review.py'],
 'preservation':'用新輸出目錄重現；原來源/外觀不可覆蓋。各工作目錄保存 executed-source，當前主腳本可能包含驗收修正。',
})
print('STAGE_28_REVIEW_COMPLETE')
