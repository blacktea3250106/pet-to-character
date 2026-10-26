# 照片到建模參考的提示詞規格

狀態：提示詞規格與人工協助單貓實測並存；generation-v001 已生成同姿勢與站姿參考，但風格、身份與跨視角品質未完整通過。提示詞是意圖描述，不能取代像素與多視角檢查。每次實際送出的版本保存在各實驗 prompt.txt，不以本文取代歷史記錄。

## P02：身份資料抽取

輸入為帶 photo_id 的原照、目標貓 bbox、可見部位標記；此步不輸入 cat.png，避免把風格圖中的三花當成玩家花色。

```text
Describe ONLY the selected individual cat in these source photographs.
Use the animal's anatomical left and right, never screen-left as anatomical-left.
If anatomical side cannot be established, set side=unknown rather than guessing.
For each observation return: feature_id, anatomical_region, description,
photo_ids, normalized image-space polygon or bbox, visible/occluded,
evidence=observed/inferred, confidence=high/medium/low, and conflicts.
Record facial asymmetry, nasal bridge, muzzle, chest, each paw's white boundary,
back and nape markings, tail pattern, eye/nose color and observable body ratios.
Do not infer obesity from a seated rump or infer short legs from folded limbs.
Do not mirror missing markings. Do not invent numeric morph parameters.
Separate illumination from coat color; uncertain dark areas remain uncertain.
Conflicting evidence must remain explicit, not averaged into a new marking.
```

polygon 是候選標註，必須疊回原照檢查，不能只因 JSON 可解析就採信位置。無觀測部位不應被輸出成 observed。

## P03：同姿勢風格轉換

角色綁定：image 1 為原照；image 2 為 cat.png。一次只改一張原照，保留原姿勢，將風格轉換與姿勢重建的誤差分開量測。

```text
Image 1 is the identity source and edit target. Image 2 is ONLY the art standard.
Translate the selected cat in image 1 into image 2's natural-proportion faceted
cat style. Preserve image 1's pose, silhouette, face structure, visible anatomy,
asymmetric markings, eye color and nose color. Keep the supplied confirmed
identity checklist. Do not copy image 2's calico layout, curled tail, lying pose
or half-closed expression. Use coherent medium-size body facets and finer facial
structure with readable eyelids, muzzle and nose. Matte material, restrained
color variation, no hair strands, no new fur noise, no painted fake eyes elsewhere.
Output one image, no text or panel borders. Unknown areas remain unknown.
```

輸出與原照同視角疊圖檢查剪影、臉斑與腳掌位置。生成尺寸若改變，先估計相似變換配準，不以任意非剛性變形把差異藏掉。

## P04：標準站姿與多視角

輸入角色需寫進每次任務 manifest：原始身份圖、已驗收風格圖、cat.png、姿勢引導各自分開。不超過工具可接受的參考數；未送入的原照以身份清單與後驗檢查補足，不能宣稱生成模型看過所有照片。

初版 POC 曾規劃一次生成六視角再裁圖，實際四視圖分支有姿勢與比例問題，不能當成已驗證首選。當前 [22-photo-constrained-views](../generation-v001/22-photo-constrained-views/review.json) 改用四張獨立圖片：先檢查正面，再讓各視角共用完整站姿、正面及相關原照。每張原生 1254×1254，沒有人工裁圖或放大；仍需人工核對跨視角一致性。這是有限 POC，不代表分開生成已證明優於聯合生成。

[共用請求產生器](../generation-v001/build_view_request.py) 從每貓身份 JSON 及照片角色配置讀資料，輸出實際提示詞和輸入 hash；不是自動身份辨識器，也不是已完成的生產影像 adapter。[本例配置](../generation-v001/22-photo-constrained-views/profile.json) 指定輸入角色及視角；正面初版因頭身不同軸而使用一次修正。原始姿勢、美術、左右側身份、推測範圍及剩餘限制分開記錄。

Tripo 原生單圖轉四視圖曾把另一側黑臉斑猜成橘色，見 [21-tripo-multiview](../generation-v001/21-tripo-multiview/review.json)。所以多照片身份必須參與參考圖製作，不能以單張生成圖的多視角一致性代替真實身份。

```text
Create a turnaround of ONE consistent cat from the supplied identity references.
The real cat's confirmed identity checklist overrides any conflicting generated
reference. cat.png supplies only the art standard. Use FRONT, ANATOMICAL LEFT,
ANATOMICAL RIGHT, BACK, TOP and THREE-QUARTER views of the SAME neutral standing
pose. All paws rest on one ground plane, all four limbs remain separate, the head
faces forward with the body, the tail is lifted clear of the legs and torso.
Preserve the same body proportions, paw positions and tail curve in every view.
Cardinal views use orthographic projection; top and three-quarter are QA views.
Preserve observed asymmetric coat markings across views. Do not add a white neck
collar, change sock heights, invent a fifth limb or mirror one side onto the other.
Use a plain light gray background, soft neutral light without cast ground shadows,
matte faceted surfaces, natural feline facial anatomy and no text over the animal.
```

若另測聯合圖格，需先以 manifest 標記圖格再分離，保留原生解析度及尺度資料。當前四張獨立輸出不做各自塞滿畫面的手工缩放；提示詞要求同一姿勢和比例，但相機標定、世界尺度與地面線尚未取得數值證據，不能宣稱精確正交一致。每個視角允許自然遮擋，不為了讓四腳同時可見而擺出互相矛盾的姿勢。

## 修正任務

每次只列出已確認的錯誤與需保留項目，例如「保留站姿與臉部；後頸改回照片可見的橘黑色；不要改白胸」。修正後重查整套視圖，而非只看被改部位。

重試需記錄 reason、input hashes、prompt、provider/model（能取得時）、output hashes 與驗收結果；通過前不送 Tripo。

## P03 共用切面規則的單次失敗對照

[18-reference-style](../generation-v001/18-reference-style/review.json) 保留同一原照／cat.png 與原有身份條件，只將「medium/small irregular facets」風格句改為主次明確的中型切面、少量必要細節與限制碎色。部分深色區較乾淨，但仍細碎並新增毛絲／鬍鬚；已拒絕進入 P04／Tripo，不採納為正式 preset。

[完整實際提示詞](../generation-v001/18-reference-style/prompt.txt) 與輸入 hash 均已保存。這是單次隨機輸出，工具未提供可固定的種子或模型版本，不能聲稱確定性重現或泛化成功。後續需驗證如何分開控制切面、毛色邊界與毛絲細節，不能只反覆增加提示詞。
