# 真實照片 → 高品質 low-poly 貓：前段實作規格

日期：2026-09-30。範圍：玩家上傳到「外觀合格、可交給骨架適配」的模型。

這份文件補足主 workflow 的 4.1–4.3。下列數值是第一輪可重現的實驗設定，不能稱為已驗證最佳值。API 欄位已查核；catworld 歷史請求與 GLB 已做唯讀檢查；本專案尚未完成新的端到端生成。

機器設定：[front-end-profile.json](front-end-profile.json)  
提示詞：[reference-prompts.md](reference-prompts.md)  
現有證據：[front-end-evidence.json](front-end-evidence.json)  
請求預覽：[tripo-requests.dry-run.json](tripo-requests.dry-run.json)，其中 token 是占位符，不能提交。

流程圖見 [workflow.md 第 2 節](../../workflow.md#2-流程總覽)，分為照片到模型、Tripo 任務處理、母版與動畫三張圖，並標出驗收與失敗返回路徑。

## 1. 要交付什麼，以及什麼才算高品質

最終模型同時通過四個相互獨立的條件：

1. **身份：** 照片確認的臉斑、白襪、胸背與尾巴花色不被改寫，左右不翻轉。
2. **造型：** 自然的頭臉、胸腹、四肢與耳尾，遵循 cat.png；體型差異來自照片可支持的證據。
3. **風格：** 清楚而有層次的切面、完整眼皮與口鼻、霧面表現，沒有照片陰影與毛髮噪點直接黏在表面。
4. **幾何：** 四肢和尾巴可辨識、沒有融合或多出肢體，局部結構能進入後續變形測試。

API 回傳 success、面數達標、影像嵌入相似度高，都不能單獨證明這四項通過。cat.png 的單張 AI 圖不能提供精確 3D 真值，尤其是隱藏面、真實面數與站姿比例。

## 2. 已查到的 catworld 基準

本次從兩份留存的任務 JSON 讀出參數，並直接解析對應 GLB 的三角形索引數；沒有執行 catworld 程式、讀取其憑證或呼叫付費 API。

| 留存案例 | 明確記錄的差異 | 實際 GLB 三角面 | 這能證明什麼 |
| --- | --- | ---: | --- |
| 一般生成 | 未設定 smart_low_poly 與 face_limit | 1,465,432 | 不指定 low-poly 路線可能得到很高面數。 |
| smart low-poly | smart_low_poly=true、face_limit=3000 | 3,219 | 已有可產生低面數模型的案例；face_limit 不能取代實際統計。 |

兩者共同記錄：v3.1-20260211、texture=true、pbr=false、texture_alignment=original_image、geometry_quality=standard。歷史請求使用 V2；沒有記錄的 texture_version、texture_quality 與種子不能事後當成確定值。

catworld 的後處理紀錄還包含：投影修色、保留頭部原貼圖、局部細分和平滑、逐面平均色、眼睛例外，以及第五條腿等人工修復。這些成果不能歸因於某組 Tripo 參數自動保證品質。[catworld 流程紀錄](../../../catworld/pipeline/PIPELINE.md)

## 3. P00：接收與整理原照

**輸入：** 一隻貓的原始照片。允許一張開始；本次基準使用 example 中現有八張，不要求同姿勢。

**處理：**

1. 檢查可解碼格式與像素尺寸；原檔保存 hash 與 photo_id，工作副本套用 EXIF 方向後轉 sRGB。HEIC/WebP 先在本機解碼成 PNG/JPEG，不直接假設上傳介面接受所有格式。
2. 多隻貓時指定目標 bbox；視角左右不明時保留 unknown，不自動鏡像。
3. 分類為臉部、左側、右側、背部、腹部、尾巴等可見證據。選擇清晰且遮擋少的圖，不能把張數當覆蓋率。
4. 分別記錄對焦、曝光、遮擋、眼鼻可見程度。臉部原生 crop 小於 256 px 先觸發人工檢查，這是實驗門檻，不是「放大到 256 就合格」。
5. 不做會改變斑紋的美顏、補毛、銳化或逐區域白平衡。無法區分光影與毛色時保留不確定性。

**輸出：** photos.json、原照工作副本、視角與覆蓋清單。

**閘門 G00：** 至少有可辨識身份的臉部或特徵證據。缺身體視角仍能做推測版本，但不能標記為精準體型重建。

## 4. P01：選取貓咪與分割背景

**實驗候選：** SAM2ImagePredictor + sam2.1_hiera_small.pt，設定 configs/sam2.1/sam2.1_hiera_s.yaml。SAM 2 提供點／框提示的影像分割能力；本地尚未安裝或在這八張照片驗證。[SAM 2 官方程式](https://github.com/facebookresearch/sam2)

**處理：**

1. 初始 bbox 在 POC 人工確認，送入分割器；黑毛、耳尖、腳掌與尾巴漏切時增加正點，背景或其他動物混入時增加負點。
2. 檢查 mask 是否包含全部可見部位。不得用大範圍侵蝕消掉耳尖／白襪，也不能把靠在一起的兩隻貓視為同一物件。
3. 原照 crop 四周留 10% 空間，保留原始比例。背景合成為 RGB(224,224,224) 只用於建模工作圖；原照和身份證據不覆寫。
4. 分割器信心僅用於候選排序，不能當成身份或花色正確率。

**輸出：** 每張圖的 cat-mask、bbox、遮擋標記與 overlay。

**閘門 G01：** 目標唯一，耳、鼻、可見爪、尾巴未被切掉，背景沒有被納入貓體。人工修正次數記入自動化統計。

## 5. P02：抽取身份清單，不先把花色壓成三個顏色

**輸入：** 原照與 mask，這一步不使用 cat.png 的花色。

**資料結構：**

```json
{
  "feature_id": "nasal_bridge_dark_patch",
  "region": "nasal_bridge",
  "side": "center",
  "description": "example only: dark bridge with separately recorded nose color",
  "evidence": "observed",
  "photo_ids": ["source_04"],
  "image_regions": [],
  "confidence": "high",
  "must_preserve": true,
  "conflicts": []
}
```

上例只展示結構，空的 image_regions 不可作為完成標註。實際 feature 必須有原照中的 bbox／polygon 或可檢視的遮罩。

- 臉斑、鼻樑、眼鼻色、白襪、胸背與尾巴逐項記錄；對側缺照不能用鏡像假裝有證據。
- 顏色分群可在 Lab 中協助去除細毛變化，但 Lab 不會自動消除光照；用照片對照與語意標籤判斷黑毛／陰影。
- 保存斑塊位置、邊界與鄰接關係，而非只保存某個身體區域的一個平均色。
- 胖瘦、臉寬、耳朵、尾長先存相對比例與信心；坐姿或透視不明的數值不得直接轉成精確 morph。

**工具邊界：** 第一輪可由視覺分析加人工校正建立標註基準；正式 VLM 偵測、關鍵點及結構化輸出 adapter 尚未實作。人工標註通過不等於自動辨識通過。

**閘門 G02：** 每個必保留特徵可追溯原照；矛盾或左右不明尚未解決時，不得把它標為已確認。

## 6. P03：先做同姿勢風格圖，再做站姿

**目的：** 把「美術風格轉換」與「姿勢／隱藏面重建」分開，便於定位錯誤來源。

此為研究基準 A 的診斷拆步，不是已證明必要的產品步驟。對照 B 直接由原照、cat.png 與身份清單生成標準站姿參考；結果仍需通過身份和風格檢查。[路線比較與控制條件](route-comparison.md)

POC 沿用 catworld 使用的對話 ImageGen 方式：原照為身份與構圖來源，cat.png 只供美術參考。提示詞見 reference-prompts.md。不得讓 cat.png 的三花布局、趴姿或半閉眼覆蓋玩家的貓。

同姿勢輸出逐張疊回原照，先檢查幾何輪廓和必保留特徵；比較前只校正裁切、尺度與平移等合理相機差異，不以任意非剛性拉扯掩蓋形狀漂移。

**閘門 G03：** 臉、耳、眼、口鼻、白襪等身份特徵完整；切面尺度與材質接近 cat.png；不添加未見花紋。失敗只修此階段，不把錯誤送入下一步。

**產品缺口：** 對話工具能完成 POC，不能直接當成玩家伺服器 API。生產用影像服務、模型版本、輸入張數、回傳格式與失敗重試尚未完成選型；設定檔以 null 明示，未關閉此缺口前不得宣稱全自動前段已完成。

## 7. P04：標準站姿與多視角一致性

此階段輸出沿用 P03 已驗收的 low-poly 美術風格，因此送進 Tripo 的四視圖是風格化 2D 圖，不是未處理原照、UV 圖集或已存在的 3D 模型。2D 切面只提供外觀引導；3D 的幾何面數與切面需由生成設定及後處理另外控制。

### 固定姿勢規格

- 四腳站立於同一地面，頭朝身體前方；四肢空間分離，尾巴抬離腿與軀幹。
- 所有視角使用同一組姿勢、頭身比例、腳掌位置與尾巴曲線。
- 交付 front、left、back、right 四張獨立圖；top 和 threequarter 作額外 QA。
- 每張整理為 1024×1024 PNG、淺灰背景；移除圖格文字、邊框與投影陰影。這是本地輸入規格，不是 Tripo 強制尺寸。
- 同一世界尺度與地面線，不能把每個視角獨立拉伸到塞滿畫框。遮罩與 landmarks 必須同步變換。

### 如何建立與檢查

1. 使用已驗收的同姿勢風格圖與原照身份清單，生成一套站姿 turnaround；所有生成／修正均保存輸入圖角色、完整提示詞和輸出 hash。
2. 比對頭頂、鼻尖、肩胯、腳掌、尾根等相同部位；前後視圖的高度、側視圖的身長與腳掌接地需一致。側視圖允許近遠側腿互相遮擋，不要求每張都露出四個腳掌。
3. 比對跨視角花色：後頸不能一張橘黑、一張白圈；左右臉不應鏡像；白襪高度和尾巴環紋不應每張改變。
4. 差異超過第 11 節的初始門檻時，修正該視圖並重查整套；多張 AI 圖不等於同一個一致的 3D 物體。

### Tripo 的多視角產圖介面放在哪裡

image-to-multiview 接受單張 input；它不是任意多張真實照片的身份融合器。可把已驗收的站姿圖送入，作為對照方案；其生成的隱藏面仍須由原照身份清單檢查。[Image to Multiview](https://developers.tripo3d.ai/en/docs/generation-image-to-multiview)

edit-multiview 的 prompts 可指定 front/left/back/right 修正，但同樣需要後驗收，不把服務宣稱的一致性當成已通過結果。[Edit Multiview](https://developers.tripo3d.ai/en/docs/generation-edit-multiview)

**閘門 G04：** 必保留特徵無矛盾，姿勢一致，四肢／尾巴分離，圖像無標籤污染。第一輪由人工看 overlay，後續自動化檢查必須用同一套標註回測。

## 8. P05：Tripo V3 請求的明確設定

### 首輪歷史基準請求

使用 POST https://openapi.tripo3d.ai/v3/generation/multiview-to-model。採 named view 欄位，避免舊版陣列索引錯位。以下為現行 3500 面請求設定；歷史 3000 面請求保存在各任務的 request-public.json，不改寫舊任務。多視圖只有品質通過才提交；本輪後續單圖探索走 image-to-model，並非最佳路線承諾。[官方多視角介面](https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/standard)

```json
{
  "inputs": [
    {"front": "file_FRONT"},
    {"left": "file_LEFT"},
    {"back": "file_BACK"},
    {"right": "file_RIGHT"}
  ],
  "model": "v3.1-20260211",
  "texture": true,
  "pbr": false,
  "texture_alignment": "original_image",
  "texture_version": "v3.0-20250812",
  "texture_quality": "standard",
  "geometry_quality": "standard",
  "smart_low_poly": true,
  "face_limit": 3500,
  "quad": false,
  "auto_size": false,
  "generate_parts": false,
  "orientation": "default",
  "export_uv": true,
  "model_seed": 3101,
  "texture_seed": 3102
}
```

| 設定 | 本實驗的選擇理由 |
| --- | --- |
| model=v3.1-20260211 | 接近 catworld 留存案例，先減少換模型造成的變因。 |
| smart_low_poly=true、face_limit=3500 | 現行使用者目標；受控實測卻輸出 5501 面，必須依實際 GLB 驗收。3000 保留作歷史基準，不再預設測 6000／9000。 |
| geometry_quality=standard | 先用已知基準；更細幾何可能增加毛髮噪點，未實測不假設越高越好。 |
| texture=true、pbr=false | 取得顏色和 UV；本地用統一霧面材質，避免未檢查的生成法線改變切面感。 |
| texture_alignment=original_image | 基準優先依已驗收參考圖的顏色；仍須檢查是否貼錯位置。 |
| texture_version、texture_quality 明確指定 | 不依賴服務隱含預設漂移。歷史案例未記錄版本，因此這是新的明確設定，不是精確重播。 |
| quad=false、generate_parts=false | 本輪採三角面表面與單一紋理路線；肢體分區在本地建立。 |
| auto_size=false | 照片沒有真實尺寸標尺；採本地統一尺度，不把 AI 猜測當真實尺寸。 |
| model_seed=3101、texture_seed=3102 | 本實驗選定的固定種子；不是 catworld 歷史種子。 |
| export_uv=true | 後續要做可追溯投影和烘焙。 |

未傳 compress 與 export_orientation。prompt、negative_prompt 未在這個 endpoint 定義；type、model_version、files 屬於不能沿用的舊式請求寫法。美術要求要先落實在參考圖，不能靠虛構的 3D prompt 參數。

基準不傳 delight。要測移除烘焙光照，另開 texture_version=v3.5-20260815、delight=true 的對照；舊版紋理模型不讀 delight。這個對照改的是紋理流程，不能聲稱已保持所有條件完全一致。[紋理版本與 delight 說明](https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/standard)

### 使用者指定 3500 面後的優先路線

先呼叫 Tripo 原生生成，`smart_low_poly=true`、`face_limit=3500`、`quad=false`。V3 文件將 face_limit 定義為輸出面數上限；3500 在有效範圍內，沒有規格上的理由必須先生成高面數再用 Blender 減面。[V3 H 系列單圖介面](https://developers.tripo3d.ai/en/docs/generation-image-to-model/standard)

此次受控對照使用 `POST /generation/image-to-model`、同一張 `04b-single-reference/standing.png`、同一 H3.1 版本、種子和材質設定，只改面數。請求與結果保存於 [15-tripo-native-3500](../generation-v001/15-tripo-native-3500/request-public.json)。先前 3000 請求在伺服器 input 確實收到，卻輸出 5128 個實際三角面，僅有 model_url 一份模型；這是需要調查的實測差異，不能解讀為 API 不支援這個參數。

**受控實測結果：** 這次 `face_limit=3500` 在伺服器 input 得到確認，但原始 GLB 實際為 **5501 三角面**；直接索引統計與 Blender 三角化統計相同。API 成功、面數預算失敗，耗時 189.73 秒、40 credits。文件上限與結果不符的原因仍未釐清，不能先認定參數不支援或一定是四邊面計數。[結果與比較證據](../generation-v001/15-tripo-native-3500/review.json)

入庫必須讀取實際 GLB 三角面數，另驗收外觀、解剖及後續動畫。原生結果合格就跳過減面；超標或局部品質不合格才評估重拓樸／本地減面等後處理。已做的 Blender 3500 面版本保存為 fallback 對照，頭部／腳底保護仍依本例人工座標；不是已證明可自動處理新貓的必要步驟。拓樸改動後，舊 triangle ID、重心座標對應與變形驗收都需重建。

### 3500 面條件式後處理實測

原生生成超標時，已測 `POST /mesh/decimate` 的 `model=v1.0, face_limit=3500, quad=false`，取得正好 3500 面。v1.0 不傳不支援的 `bake`；來源 GLB 或 task 均依正式介面處理。[官方重拓樸介面](https://developers.tripo3d.ai/en/docs/mesh-decimate)

此單例不需手工保護區，但必須驗證供應商改動的尺度、中心、UV 與材質。基本版曾遺失 metallicFactor=0；不能直接使用「API 成功」的材質。保存來源材質並自動修復，按需重烘焙；本例可重播，跨貓仍待驗證。[完整實測](../generation-v001/16-service-retopology/review.json)

正式流程優先在投影花色、建立 triangle ID 對應與綁骨之前確定面數／拓樸。若在已修色模型後減面，必須處理貼圖／材質保真及資料失效，不能把本次烘焙一律變成每位玩家的必經步驟。

### 不混淆的限制

- 目前 H 系列 smart low-poly 三角面範圍為 500–20000；本地預檢會拒絕超界設定。
- 對話中的 2048 貼圖指本地烘焙輸出；沒有捏造 texture_resolution 參數，API 輸出尺寸須讀檔記錄。
- 左／右在本專案定義為貓的解剖側。官方 view 名稱與此定義是否完全一致，仍需不對稱標記控制樣本驗證；檔名相同不代表方向已驗證。
- 固定種子之外也保存輸入圖、版本與輸出檔，跨服務升級不承諾位元級相同。

### 請求生命週期

1. 四張通過 G04 的 PNG 各自上傳 POST /files，保存 file_token 和輸入 hash。官方此上傳介面的圖片格式為 JPEG／PNG，單檔上限 20 MB。[File Upload](https://developers.tripo3d.ai/en/docs/files)
2. 生成 request hash，保存待提交紀錄後 POST 一次；取得 task_id 即落盤。
3. 以 GET /tasks/{task_id} 每 8 秒查詢。queued/running 不重新 POST；成功後立即下載模型與相關輸出、驗證容器並保存 hash。[Task Query](https://developers.tripo3d.ai/en/docs/task-query)
4. 20 分鐘僅是本地軟超時標記，不是生成 SLA，也不代表遠端任務失敗。POST 超時且無 task_id 時先調查提交狀態，不能盲目再提交造成重複費用。
5. 保存實際 credits、等待與處理時間。失敗分成 API／輸入／品質三種，只有確認原因後才決定修正或重試。

## 9. P06：生成後的幾何與外觀預檢

**先處理座標：** 統一為前方 +X、貓左側 +Y、上方 +Z；在可識別鼻尖、尾根和地面後，將鼻尖到尾根尺度暫定為 0.5 m。這是比較尺度，不是玩家貓的真實尺寸。

**檢查：**

- 解析 GLB 的實際面數、材質、紋理尺寸、節點變換、UV 與檔案完整性。
- 分開處理視覺網格和分析網格。UV／硬邊拆點會製造假連通分量；只在分析副本以身長 × 1e-6 起始容差焊接，原 UV、corner 色與法線保留。
- 用多個高度切面、分區與視圖檢查四肢；低處連通塊只能提供候選，尾尖也可能接近地面，不能單靠「最低四塊」斷言正常。
- 檢查多出肢體、融合腿、尾巴黏身、耳朵塌陷、臉部幾何錯位。
- 用相同相機規格渲染 cardinal views、三分之四視角及臉部近照，再與生成參考及原始身份特徵核對。

**閘門 G06：** 結構與身份均通過才進入外觀精修。catworld 的第五條腿修復是案例特定操作，不能一律把多餘幾何壓入腹部當成通用解法。

## 10. P07–P09：如何得到 cat.png 的乾淨切面效果

以下為摘要；完整操作順序、部位定位、眼部處理分支、UV／材質設定與驗收，見[幾何切面、花色、眼睛與材質處理規格](postprocess-spec.md)。已有單貓實測與失敗修正，但通用處理器尚未完成。

### P07：幾何切面與細節分配

保留原始生成資產，對工作副本處理：

1. 先檢查原生 `face_limit=3500` 的實際 GLB 面數、形狀與外觀。若已合格，省略減面。若臉部輪廓與耳尖缺失，返回來源或評估可泛化的局部建模；細分不能補出真實細節。
2. 不預設均勻細分：本輪四倍加密未通過美術。只有有具體缺陷與 3500 面內的重新分配方案時，才評估局部修改；catworld 的 k=0.6 是歷史參考，不是已驗證通用設定。
3. 耳尖、眼眶、口鼻、腳尖與重要花紋邊界以語意遮罩保護，不能沿用某隻貓的固定 x/z 門檻。
4. 超標時的服務減面已取得單例 3500 面候選；需同時檢查尺度、材質及 UV，不能只數面。任何拓樸改動後重建對應，再做花色與動畫驗收；不直接沿用舊 triangle ID。
5. 法線方向抖動先設 0；只有對照證明切面需要時，才測固定種子的小幅起伏。catworld 的 ±0.7 mm 不是通用必做步驟。

### P08：把花色對應到 3D 表面

第一輪保留 Tripo base texture 當完整覆蓋底圖。只有確認參考視角與模型對齊後，才做程序投影修色：

1. 使用剪影與關鍵點擬合相機，存下每個 view 的投影矩陣、誤差與有效區域。
2. 對 UV texel 求其三角形內的 3D 位置，經相機投影到已驗收參考圖。
3. 以 z-buffer 排除遮擋，法線朝向提供 max(0,n·d)^4 權重；深度容差起點為身長 × 0.008，需防止把另一條腿的顏色投上來。
4. 權重再乘來源可信度與局部配準品質。黑／橘／白來源互相矛盾時先選擇可信來源或返回修正，不能平均成灰褐髒色。
5. 臉斑、眼、鼻、嘴用獨立區域與更嚴格配準，不直接套全身相機。看不見的表面保留底圖並標 inferred。

catworld 的全頭底圖保留能避免部分投影錯誤，但也可能保留錯誤臉斑。新版需逐特徵驗收，不能把「保護頭部」當作身份正確的替代證據。

### P09：顏色簡化、UV 與材質

- 身體切面可取覆蓋 texel 的面積加權平均色；取樣在 linear sRGB 中進行，使用正式分段轉換，不把 gamma 2.2 近似當精確標準。
- 眼睛、眼皮、鼻、嘴及重要斑紋邊界保留細節。面跨越重要花色時，局部加面或保留面內紋理，不能一律多數決吞掉特徵。
- 不把所有黑、橘、白各量化成單一色；保留受控的色階以呈現形體，同時避免烘焙光影與真實燈光重複。
- 本地烘焙為 2048×2048；UV padding 起點 16 px，需在引擎 mipmap 與預期觀看距離檢查接縫。生成模型不直接編輯 UV 圖集。
- 材質起點 metallic=0、roughness=0.9；生成 normal map 預設關閉，切面感由幾何、顏色與燈光共同檢查。

**輸出：** 外觀定稿 GLB／工作檔、貼圖、原照證據到表面的對應、推測遮罩、相機設定與比較圖。外觀未通過時不進骨架適配。

## 11. 品質閘門：第一輪具體怎麼判

下列數值是觸發檢查的初始設定，還需要用成功／失敗樣本校準。它們不是已驗證的商業驗收門檻。

| 檢查 | 初始規則 | 不通過時回到 |
| --- | --- | --- |
| 身份必保留項 | 已確認的臉斑、白襪等項目全部可對照；有一項被改寫就不放行 | P02/P03/P04 或 P08 |
| 跨視角關鍵點 | 合理視圖對應下，正規化偏差 > 身體跨度 3% 觸發檢查 | P04 |
| 模型剪影 | 擬合後 IoU < 0.85 觸發檢查；相機不可靠時先修相機 | P04/P06 |
| 臉斑位置 | 局部對齊後邊界偏差 > 頭寬 3% 觸發檢查 | P03/P08 |
| 肢體結構 | 多腿、少腿、融合腿、尾巴黏身均拒絕 | P04/P06 |
| 風格 | 固定棚拍與中性檢查光兩種渲染；核對輪廓、臉部、切面、色彩與材質 | P03/P07/P09 |
| 未見表面 | 必須保持 inferred，不能因 AI 畫出來就升級為 observed | P02/P08 |
| 自動化 | 人工框選、改 mask、改圖、修模逐次計數 | 對應 adapter |

多視角 AI 圖與其生成模型的相似，只能證明內部一致，不能證明與真實貓一致。身份驗收始終回到原照。風格驗收不能只看一張最漂亮的渲染，必須包含多視角與臉部近照。

## 12. 實驗順序與目前狀態

1. **已完成本輪：** 查核 API；讀取兩份歷史請求；解析其實際面數；盤點八張原照與四張既有輸入圖；定義 profile 與 prompt；離線測試五種請求設定。
2. **已開始視覺檢查：** 對照三張原照與四張既有輸入圖，發現鼻尖粉色特徵未完整保留、各視角需要共用尺度配準，以及舊圖尾巴姿勢不符合新基準。[檢查紀錄](reference-review.json) 區分實際觀察與尚未量測項目，G04 尚未通過。接著完成其餘五張原照、身份／分割基準與跨視角檢查；通過前不直接沿用。
3. **接著：** 按新 V3 基準產生一個案例，保留完整輸入輸出與成本；優先修最大失敗來源。只在有原因時跑一個參數變體，不做盲目排列組合。
4. **再來：** 完成幾何、投影、切面處理與多視角外觀驗收，才交給包覆與骨架流程。
5. **自動化驗證：** 將人工基準換成各 adapter 後重跑；記錄無人工成功率，不能沿用人工修好案例的成績。

本輪的七項自動測試驗證請求組裝與錯誤攔截，沒有驗證伺服器接受請求、模型生成品質、照片辨識或自動分割。front-end-evidence.json 的 submission_ready、generation_executed、visual_quality_verified 目前均為 false。

重現本輪唯讀盤點與離線檢查：

```bash
cd experiments/workflow-validation-v001
python3 front_end_contract.py
python3 -m unittest -v test_front_end_contract.py
```

上述程式不含網路提交功能、不讀 .env，也不會重新生成或修改 catworld 資產。
