"""Append stage 27 evidence to existing project records, never README or source assets."""
import json
from pathlib import Path

P = Path(__file__).resolve().parent
G = P.parent
W = G.parents[1]
prefix = P.name + '/'
def load(path):
    return json.loads(path.read_text())
def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

history = load(G / 'experiment-history.json')
assert not any(e['id'] == 'E47' for e in history['events']), 'Already registered'
outputs = [str(f.relative_to(G)) for f in sorted(P.rglob('*')) if f.is_file() and f.suffix in
           ['.json', '.npz', '.py', '.blend', '.glb', '.png', '.mp4', '.gif', '.ffconcat']]
history['events'].append({
    'id': 'E47', 'issues': ['RIG-01', 'EXPORT-01', 'GEO-02'],
    'script': prefix + 'bind_baseline.py',
    'additional_scripts': [prefix + f for f in ['inspect_sources.py', 'locate_feet.py', 'bake_and_measure.py',
                           'render_motion.py', 'export_verify.py', 'assemble_previews.py', 'finalize_review.py']],
    'inputs': [prefix + 'action_gate.json', prefix + 'weight-repair-gate.json',
               '25-appearance-diagnostic/matte-candidate/cat.glb',
               '../texture-transfer-v001/source/SKM_Cat_Domestic_Shorthair.fbx'],
    'outputs': outputs,
    'manual_inputs': ['一次母版骨骼語義與座標軸規格', '單次共用權重平滑設定：五輪、0.35、八影響',
                      '動作多角度與量測結果人工審查；未新增本貓關節座標、手工權重或遮罩'],
    'action_gate': {'timing': 'before_execution', 'record': prefix + 'action_gate.json',
                    'repair_record': prefix + 'weight-repair-gate.json'},
    'outcome': 'five_clips_baked_597_frames_measured_3500_triangles_glb_roundtrip_pass_partial_weight_improvement_animation_quality_failed',
    'review_record': prefix + 'review.json', 'tripo_calls': 0, 'credits_consumed': 0,
    'new_cat_automation_proven': False,
})
save(G / 'experiment-history.json', history)

review = load(G / 'automation-review.json')
review['updated'] = '2026-10-01'
review['action_policy']['current_action_gate'] = prefix + 'weight-repair-gate.json'
for issue in review['issues']:
    if issue['id'] == 'RIG-01':
        issue.update({
            'problem': '2D 花色點不能當 3D 關節。27 已將五段来源動作套到目前生成貓，但仿射骨架位置與最近表面權重仍出現拉伸、相交和穿地；不同腿長/胖瘦未驗證。',
            'current_fix': '實作站姿四腳自動定位、整體對齊、56 骨同軸轉移及每幀量測。有效基準加一個平滑/八影響候選，共五段 597 幀；Walk 超過兩倍的邊樣本 164→26，Sitting 仍穿地約尺寸 4.16%，部分塌陷惡化。動畫 GLB 回讀通過，品質拒絕放行。',
            'automation_status': 'implemented_measurement',
            'future_detection': '先驗部位/關節/骨段與尾巴對應信心，再驗動作表面、支撐期和接觸；來源原有接觸與轉移新增問題分開。',
            'future_repair': '需帶解剖約束的分部位非剛性對應、每段骨長/方向適配與語義限制權重；再做接地 IK 與體型碰撞。均未完成，不以更多平滑或每貓手修代替。',
            'validation': '使用者選定 Idle、Walk、Idle_to_Sit、Sitting、Sitting_to_Idle；這五段每幀已量測，Unity 未測。標準/短腿/長腿/瘦/胖等體型與独立新貓需另作留出驗證，其餘 18 段未納入。',
            'risk': '四腳與整體尺度不能提供真實肘膝或獨立胖瘦；腿合併高度受腹部影響。最近點可跨錯部位；平滑無法修正關節。骨架、匯出正確仍不保證零穿模。',
        })
        issue['evidence'] += [prefix + f for f in ['action_gate.json', 'weight-repair-gate.json', 'foot-detection.json',
                              'baseline-v001/rejection.json', 'baseline-v002/animation-report.json',
                              'weights-v001/animation-report.json', 'review.json', 'animation-comparison.mp4']]
    if issue['id'] == 'EXPORT-01':
        issue['current_fix'] += ' 27 新動畫 GLB 保留 3500 面、56 骨、五段 action 和八影響；回讀 15 個姿勢最大頂點差約 4.22e-5/最大模型尺寸，底色像素差 0。量化排序造成的角點誤判已以雙向空間/UV 配對修正。'
        issue['evidence'] += [prefix + 'weights-v001/export/verification.json', prefix + 'export_verify.py']
save(G / 'automation-review.json', review)

stages_path = G / '17-stage-review/stages.json'
stages = load(stages_path)
stages['summary'] = stages['summary'].replace('P00–P09', 'P00–P10')
stages['summary'] += ' 使用者接受目前外觀供動畫試驗；27 完成五動作與一次通用權重修正，597 幀量測與動畫 GLB 回讀已有證據，仍因變形/穿地未通過。'
p09 = next(s for s in stages['stages'] if s['id'] == 'P09')
p09['remaining'] = p09['remaining'].replace('GLB 無 skin 或 animation，Unity 與 Low Poly Animated Cats 動作未驗證。',
    '本階段的外觀 GLB 尚未綁骨；後續 P10 已另建立五動作測試候選，仍未通過動畫品質，Unity 未驗證。')
stages['stages'].append({
    'id': 'P10', 'title': '五動作與體型適配基準',
    'status': '能播放與匯出；變形/穿地及跨體型未通過',
    'result': '目前 3500 面三花套用 Low Poly Animated Cats 的 Idle、Walk、Idle_to_Sit、Sitting、Sitting_to_Idle。以自動四腳與整體對齊建立 56 骨/權重，五段 597 幀量測。單次平滑加八影響減少部分拉伸；匯出回讀保留五動作、3500 面及原底色。',
    'manual_dependency': '一次母版語義/朝向規格、共用平滑設定及多角度動作審查；本輪沒有逐貓手標關節或手刷權重。',
    'remaining': 'Walk 塌陷面數 25→31，Sitting 仍穿地約模型最大尺寸 4.16%；不能只報拉伸改善。未做解剖約束包覆、獨立腿長/胖瘦適配、接觸 IK、滑步判斷、Unity 或任何留出新貓。',
    'images': [
        {'path': 'experiments/generation-v001/' + prefix + 'weights-v001/preview/Walk-0020.png', 'kind': 'render', 'label': '實際蒙皮走路姿勢；單次通用權重修正後，仍有缺陷'},
        {'path': 'experiments/generation-v001/' + prefix + 'weights-v001/preview/Sitting-0001.png', 'kind': 'render', 'label': '實際坐姿；可辨認動作，但不是穿模驗收通過'},
        {'path': 'experiments/generation-v001/' + prefix + 'weights-v001/preview-opposite/Sitting-0001.png', 'kind': 'render', 'label': '另一側坐姿；後腳折疊與接地仍待改善'},
    ],
    'evidence': [
        {'path': 'experiments/generation-v001/' + prefix + f, 'label': label}
        for f, label in [
            ('animation-preview.gif', '實際 3D 動畫預覽；待機/坐姿為靜幀停留'),
            ('animation-comparison.mp4', '動態前後對照：左基準、右平滑加八影響'),
            ('review.json', '完整結果、不同體型限制與下一階段要求'),
            ('weights-v001/animation-report.json', '五動作逐幀量測摘要'),
            ('weights-v001/export/cat-animated.glb', '可播放五段動作的研究 GLB；品質未通過'),
            ('weights-v001/export/verification.json', '實際匯出回讀證據'),
            ('reproduction.json', '重現步驟與工具版本'),
        ]],
})
stages['conclusion'] += ' 使用者接受目前外觀作為動畫實驗基準。27 已建立真實五動作/56 骨候選，匯出回讀通過；權重處理改善部分拉伸，但坐姿穿地與塌陷仍存在。新階段不是任意腿長/胖瘦自動化的證明；当前只測一隻生成貓。'
save(stages_path, stages)

workflow = W / 'workflow.md'
text = workflow.read_text()
text = text.replace('更新日期：2026-09-30', '更新日期：2026-10-01', 1)
text = text.replace('狀態：持續拆解與驗證中；最新模型已由 Tripo 服務減為實際 3500 面，flat 著色 GLB 匯出回讀通過。完整 cat.png 美術、照片身份、眼部及動畫尚未通過。',
    '狀態：目前外觀由使用者接受供動畫測試；3500 面模型已套上五段來源動作並完成 GLB 回讀。動畫變形/穿地、跨體型、Unity 及完整 cat.png 品質仍未通過。', 1)
insert = '''**目前工作重點：五動作動畫適配。** 使用者選擇 `Idle`、`Walk`、`Idle_to_Sit`、`Sitting`、`Sitting_to_Idle`，不要求全部 23 段。[27 實測](experiments/generation-v001/27-animation-compatibility/review.json)保留目前 3500 面外觀，以四腳自動定位＋整體對齊轉移 56 骨與權重；這只是初始化，尚未完成非剛性包覆。五段共 597 幀已量測，最多一次通用平滑／八影響修正讓走路超過兩倍的邊樣本由 164 降至 26，但坐姿仍穿地約最大尺寸 4.16%，部分塌陷惡化，因此不放行。來源本身接觸與目標拓樸不同，交叉面對數只作診斷。

[實際動畫預覽](experiments/generation-v001/27-animation-compatibility/animation-preview.gif) · [左基準／右修正影片](experiments/generation-v001/27-animation-compatibility/animation-comparison.mp4) · [五動作研究 GLB](experiments/generation-v001/27-animation-compatibility/weights-v001/export/cat-animated.glb) · [匯出回讀](experiments/generation-v001/27-animation-compatibility/weights-v001/export/verification.json)。預覽的待機/坐姿是靜幀停留；完整片段另有逐幀量測。沒有新增付費任務或逐貓手刷權重。GLB 回讀保留五動作與底色，不代表 Unity 或任意體型通過。

'''
text = text.replace('## 0. 目前驗證重點與實作規格入口', insert + '## 0. 目前驗證重點與實作規格入口', 1)
text = text.replace('目前 46 筆事件', '目前 47 筆事件', 1)
body = '''### 1.2.1 目前不同體型的支援界線

27 的自動四腳和 XYZ 整體縮放，**不能當作短腿、長腿、胖腹、瘦身均可適配**。腿部合併高度也受下垂腹部與站姿影響，並非真實腿長；同一組縮放不能獨立決定腿和身體，四腳位置也不提供肘、膝、髖、肩的正確關節。最近表面權重可能跨到鄰腿或腹部，平滑只能減輕不連續，不能修正解剖位置。來源平伸尾與目標翹尾另有姿勢對應問題。

下一階段需先建立有置信度的部位分區與解剖約束對應，分別求骨段長、關節和尾巴路徑，再做部位限制權重、腳掌接地/支撐期與坐姿腹部避碰。這些尚未實作。先以標準/短腿/長腿/瘦/胖的受控變化作壓力測試，再驗證獨立生成的新貓；同一網格變胖變瘦不算跨貓成功。支援範圍應由實測制定，超出或對應不明時拒絕/審查，不偷偷改瘦、換外形來通過。照片身份、cat.png 方向、3500 面和動畫要求仍同時保留。

'''
text = text.replace('### 1.3 母版的角色與資產選擇', body + '### 1.3 母版的角色與資產選擇', 1)
text = text.replace('- **何時驗證：** 現在先維持可對應的四肢／頭尾結構與紀錄。在首次包覆、骨架及權重候選建立後，以來源實際存在的 `Idle`、`Walk`、`Idle_to_Sit`、`Sitting`、`Sitting_to_Idle`、`Sitting_to_Sleep`、`Sleeping` 做最小動作與轉場檢查，再進行外觀細修。其餘來源動作逐項驗收，未測不宣稱支援全部 23 個 action。',
    '- **何時驗證：** 使用者已接受目前外觀供動畫試驗，並將第一輪定為 `Idle`、`Walk`、`Idle_to_Sit`、`Sitting`、`Sitting_to_Idle` 共五段。27 已測五段 597 幀與一次通用權重修正，仍未通過；下一步缺口是部位/體型對應和接觸，不增加動作數或先磨外觀。睡眠及其餘動作不納入本輪，未測不宣稱支援。')
workflow.write_text(text)
print('REGISTERED_E47_AND_P10')
