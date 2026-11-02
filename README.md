# cosmic-letters

IG / Threads 帳號 @chieh._.04（宇宙情書）的自動發文流程。

## 一篇貼文怎麼上線

1. 在 `posts/<編號>/post.json` 寫好稿子（格式見下方），`"approved": false`
2. 審稿通過後改成 `"approved": true`
3. 排程每天 22:07（台北時間）自動發「待發隊列」的下一篇：編號最小、approved 為 true、還沒發完的那篇
4. 發完會開一個 issue 提醒到 IG App 加配樂（IG API 不能加音樂）

想馬上發：Actions → publish → Run workflow。`post_id` 留空就是發隊列下一篇，也可以指定編號；`target` 可選 ig / threads / both。

## 不會重複發

每個平台發成功後會寫進 `posts/<編號>/status.json`。已經記錄的平台會跳過，所以重跑、補發都安全。要重發某個平台，先刪掉該平台的貼文，再刪掉 status.json 裡對應那一項。

## 發出去長什麼樣

- **IG**：兩張圖的輪播（圖 1 情話、圖 2 知識）＋ `caption`
- **Threads**：`threads_main` 純文字主串文（帶 `topic_tag` 主題標籤）＋ `threads_reply` 純文字自我回覆

圖片由 workflow 用 jf open 粉圓字體在雲端產生，存進 repo 當公開網址。

## post.json

```json
{
  "id": "002",
  "approved": false,
  "domain": "數學",
  "music": "歌手《歌名》",
  "image1": "情話 HTML，<br> 換行，<div class=\"gap\"></div> 空一段",
  "image2": "知識 HTML，<span class=\"dim\">灰字</span>，<div class=\"formula\">亮白重點</div>",
  "caption": "IG 文案",
  "threads_main": "Threads 主串文",
  "threads_reply": "Threads 自我回覆",
  "topic_tag": "理科浪漫"
}
```

## Secrets

| 名稱 | 用途 | 到期 |
| --- | --- | --- |
| IG_ACCESS_TOKEN | Instagram 發文（系統用戶權杖） | 不會過期 |
| IG_USER_ID | Instagram 帳號編號 | — |
| THREADS_ACCESS_TOKEN | Threads 發文、回覆 | 約 60 天，由 refresh-threads-token 每月自動換新 |
| GH_PAT | 讓換新後的 Threads 權杖能寫回 secrets | 依建立時設定 |

### 建立 GH_PAT（一次就好）

1. GitHub → Settings → Developer settings → Fine-grained personal access tokens → Generate new token
2. Repository access 只選 `cosmic-letters`
3. Permissions → Repository → **Secrets: Read and write**，其他都不用
4. 產生後複製，到這個 repo 的 Settings → Secrets and variables → Actions 新增 `GH_PAT`
