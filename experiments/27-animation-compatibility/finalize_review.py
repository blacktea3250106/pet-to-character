"""Record bounded experiment findings; does not change any model."""
import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parent
def read(name):
    return json.loads((P / name).read_text())
def write(name, data):
    (P / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

baseline = read('baseline-v002/animation-report.json')
repair = read('weights-v001/animation-report.json')
export = read('weights-v001/export/verification.json')
inventory = read('inventory/report.json')
comparison = []
for b, r in zip(baseline['actions'], repair['actions']):
    assert b['action'] == r['action']
    comparison.append({'action': b['action'], 'frames': r['frames'],
                       'baseline': b['metrics']['target'], 'repair': r['metrics']['target'],
                       'source_control': r['metrics']['source']})
unchanged = {}
for key in ['source', 'target']:
    record = inventory[key]
    current = hashlib.sha256(Path(record['path']).read_bytes()).hexdigest()
    assert current == record['sha256'], key
    unchanged[key] = {'path': record['path'], 'sha256': current, 'unchanged': True}

write('review.json', {
    'status': 'bounded_animation_poc_complete_quality_not_passed',
    'user_scope': '目前外觀可接受作動畫實驗，選擇待機、走路、坐下/起立共五段；不是 23 動作全測。',
    'actions': [a['action'] for a in repair['actions']],
    'frames_per_candidate_and_source': sum(a['frames'] for a in repair['actions']),
    'inputs_unchanged': unchanged,
    'result': '已讓原生成貓保持 3500 面和原底色，使用 Low Poly Animated Cats 的 56 骨與五段動作。權重平滑加八影響有局部改善，仍有拉伸、塌陷、相交及穿地；不作正式交付或通用體型方案。',
    'workflow_executed': [
        '唯讀盤點母版網格、骨架、靜止軸、來源 action 與目標網格。',
        '固定一次來源/目標座標軸規格；由站姿網格低處連通區自動找四腳。',
        '四腳中心與腿部合併高度推導整體 XYZ 縮放和平移；不是非剛性包覆。',
        '保留母版局部靜止軸及階層，仿射映射骨架位置；以來源最近表面三角形插值權重。',
        '複製五段動作的局部旋轉與尺度，按骨架方向轉換位置通道；逐幀量測來源/目標。',
        '僅測一個通用修正：分析焊接網格的權重平滑，五輪、0.35，最多八影響。',
        '實際渲染兩個候選、另一側檢視；匯出五段 GLB 並回讀驗證。',
    ],
    'comparison': comparison,
    'interpretation': [
        'Walk 最差一幀超過兩倍的邊樣本 164→26，相交面對 107→73；部分權重問題可被通用處理減輕。',
        'Walk 塌陷面數 25→31、坐下轉場 65→73；不能只報有利指標或宣稱全方面改善。',
        'Sitting 最低處仍低於地面 0.04156，約最大模型尺寸 4.16%；尚無腳部 IK/接觸修正。單位不是公分。',
        '最近表面對應距離 p95 約最大尺寸 21.9%，最大約 39.7%；只是距離警訊，不是已正確對應的證據。',
        '此候選同時改平滑和影響數，不能分別推定哪項造成多少改善。',
        '來源本身有內部頭部等相交；來源/目標三角化不同，原始交叉對數不能當跨網格品質分數。',
        '邊/頂點統計來自實際渲染拆點網格，可能含 UV/法線拆點副本；同拓樸前後可比，不等同焊接唯一邊/頂點數。',
        '全幀量測是離散 30 fps，不是連續碰撞保證；量測器與最終自動放行門檻仍需獨立校驗。',
    ],
    'visual_review': {
        'evidence': ['weights-v001/preview/Walk-0007.png', 'weights-v001/preview/Walk-0020.png',
                     'weights-v001/preview/Sitting-0001.png', 'weights-v001/preview-opposite/Walk-0020.png',
                     'weights-v001/preview-opposite/Sitting-0001.png'],
        'observations': '動作與坐姿可辨認，未出現無效初版的整體爆開。步行腿部仍有拉薄與折痕；另一側坐姿後腳折疊/地面接觸不自然，尾巴姿態對應仍需改善。',
        'limits': '不是完整接觸語義驗證；沒有獨立眼球/眼皮、滑步判定或動態 flat 法線一致性驗收。',
    },
    'automation': {
        'fixed_template_settings': ['來源骨頭名稱/階層與座標軸約定', '五段動作清單', '平滑五輪、0.35、八影響的單次 POC 設定'],
        'automatically_derived_per_cat': ['站姿四腳連通區和中心', '整體比例和平移', '最近表面權重與鄰接平滑', '逐幀變形/地面/相交診斷', '匯出與回讀檢查'],
        'manual_dependencies': ['既有上游照片/參考/外觀審查', '來源骨架語義與朝向規格的一次整理', '動畫多角度視覺審查', '量測結果解讀與放行標準制定'],
        'new_per_cat_manual_landmarks': 0,
        'new_per_cat_manual_weight_paint': False,
        'removed_manual_work_in_this_stage': '這隻站姿模型的腳點、初始尺度和權重不需逐點手標/手刷；未證明未知貓也都可免人工。',
        'tested_inputs': ['目前一隻生成三花', 'Low Poly Animated Cats 原母版作量測對照'],
        'held_out_cats_tested': 0,
        'new_cat_automation_proven': False,
    },
    'body_variation_support': {
        'current_answer': '不能保證不同腿長、瘦胖都能解；整體 XYZ 比例與最近表面只屬初始化。',
        'unvalidated_cases': ['等比例大小', '長腿/短腿但身體不等比例改變', '胖腹/寬胸/瘦身', '前後腿骨段比例不同', '頭頸比例差異', '短尾/長尾/翹尾或彎尾'],
        'structural_limits': [
            '腿部合併高度同時受腹部下垂及站姿影響，不能直接當真實腿長。',
            '一組 Z 縮放會一起改骨架各部位，無法獨立調腿與軀幹。',
            '四脚位置不提供肘膝髖肩的解剖真值；貼近表面不代表關節正確。',
            '胖肚子/鄰近兩腿可使最近點落到錯部位；無語義限制的平滑不能根治。',
            '來源尾巴向後、目標尾巴上翹；一個仿射映射不能建立沿尾巴長度的正確對應。',
            '動作接觸需依各腿骨段長度及腹部空間調整，不能只複製旋轉或乘一個腿長比。',
        ],
        'next_proposed_not_implemented': [
            '先建立帶置信度的身體/四腿/頭頸/尾分區，分部位配準；不清楚就拒絕，不用新手工點靜默補過。',
            '用解剖約束的非剛性母版對應和肢體中心線，分别求骨段長、關節中心與局部方向；關節環只能在對應正確後使用。',
            '按部位限制權重轉移，避免腹部↔腿、左右腿、頭↔尾誤配；修正靜止軸差時做完整旋轉座標轉換。',
            '對三種行為建立腳掌支撐期、接地 IK、適配體型的碰撞體與坐姿空間；仍用實際表面驗收。',
            '標準/短腿/長腿/偏瘦/胖腹做受控壓力測試，另以真實獨立 Tripo 網格作留出驗證；衍生同一網格不算新貓泛化。',
            '由驗證資料界定支援比例範圍，超出就拒絕或进入明確審查；不偷偷瘦身、換模板或犧牲照片身份來宣稱成功。',
        ],
    },
    'export_verification': 'weights-v001/export/verification.json',
    'export_roundtrip_pass': export['export_roundtrip_pass'],
    'export_max_deformation_error': export['max_deformation_error'],
    'export_note': '3500 面、56 關節、五動畫、JOINTS/WEIGHTS 0+1，原底色解碼像素差 0。回讀每段首/中/末共 15 個幀，不是每一匯出幀。',
    'invalid_attempts': [
        {'path': 'baseline-v001/rejection.json', 'reason': '零長度 edit bone 初始化使 rest 軸錯誤；此實作錯誤已修正，該變形不當作方案不可行證據。'},
        {'path': 'weights-v001/export-rejected-v001/failure.json', 'reason': '浮點座標量化排序造成錯誤角點配對；改雙向空間/UV 比較後通過。保留原失敗輸出。'},
    ],
    'decision': '一個有效基準加一個通用修正已完成；保留 weights-v001 作較佳診斷候選，仍拒絕自動交付。不繼續掃平滑參數，不做逐貓手修。下一個實質缺口是體型/部位對應與接觸適配。',
    'appearance_scope': '使用者接受現況供動畫實驗；不改原照片身份或本次原外觀，完整 cat.png 一致性仍是獨立未完成項。',
    'paid_api_calls': 0, 'animation_quality_pass': False, 'unity_pass': False,
    'new_cat_automation_proven': False,
})
write('reproduction.json', {
    'environment': {'blender': '5.2.1 LTS', 'python': '3.14', 'numpy': '2.5.3', 'scipy': '1.18.1'},
    'working_directory': str(P.parents[2]),
    'policy': '在新的輸出目錄重現，勿覆蓋本次證據；腳本以自身所在目錄定位資料。',
    'steps': [
        'Blender background: inspect_sources.py',
        'Python with numpy/scipy: locate_feet.py',
        'Blender background: bind_baseline.py -- --output baseline-v002 --influences 4 --smooth-iterations 0',
        'Blender background: bake_and_measure.py -- baseline-v002',
        'Blender background: bind_baseline.py -- --output weights-v001 --influences 8 --smooth-iterations 5 --smooth-factor 0.35',
        'Blender background: bake_and_measure.py -- weights-v001',
        'Blender background: render_motion.py -- <candidate>; render_motion.py -- <candidate> --motion',
        'Blender background: render_motion.py -- weights-v001 --azimuth 135 --output-name preview-opposite',
        'Blender background: export_verify.py -- weights-v001',
        'Python: assemble_previews.py; finalize_review.py',
    ],
    'source_of_truth': '各輸出目錄 executed-source.py / executed-animation-source.py 保存當次執行程式；最新主腳本可能包含後續診斷選項。',
    'preview_note': '動畫拼接展示原地走路/坐下/起立，待機及坐姿使用靜幀停留；五完整片段的所有 597 幀另有量測。',
})
print('ANIMATION_REVIEW_RECORDED')
