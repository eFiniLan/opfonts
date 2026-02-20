# opfonts

[English](README.md)

精簡的多語言字型建構工具。為 [openpilot](https://github.com/commaai/openpilot) 設計，但適用於任何需要精簡 CJK 字元集的多語言專案。透過合併多個來源字型（如 [IBM Plex Sans](https://github.com/IBM/plex)、[Noto](https://github.com/notofonts/notofonts.github.io)），將 CJK 子集化為政府標準字元表，並跨語言去除重複的共用漢字，產生最佳化的 OTF 字型。

**輸出：** 每個字重約 1.9 MB（完整 CJK 字型則超過 20 MB）

## 為什麼需要這個工具

完整的 CJK 字型各含 30,000 個以上的字形。大多數專案只需要 UI 中實際出現的字元——通常是政府標準所定義的常用字。打包完整字型每個字重會浪費 10-20 MB。

opfonts 解決三個問題：

1. **大小**：將 CJK 字型子集化為官方政府標準字元表（簡體中文 3,500 字 + 繁體中文 4,808 字 + 日文 2,136 字 + 韓文諺文 2,350 字）。CJK 字元跨語言去重——簡體中文先處理，繁體中文只新增繁體獨有的字元，日文只新增剩餘的漢字——共用的漢字不會重複儲存。

2. **未使用的功能**：CJK 字型附帶數千個替代字形，用於風格集、直排、寬度變體和傳統編碼形式（jp78、jp83、jp90 等）。管線可以完全移除 OpenType 排版表（GSUB/GPOS/GDEF）及其關聯的替代字形——對於不需要這些功能的點陣圖/圖集渲染器特別有用。

3. **度量一致性**：不同來源字型有不同的大寫高度比例。管線可以縮放所有字形並設定上沿/下沿以匹配目標字型的比例，使拉丁文和 CJK 文字之間切換時不會出現明顯的大小跳動。

## 語言涵蓋範圍

| 文字系統 | 來源 | 字元數 | 標準 |
|---------|------|--------|------|
| 拉丁文 + IPA + 越南文 | IBM Plex Sans | 完整範圍 | — |
| 西里爾文 | IBM Plex Sans | U+0400–052F | — |
| 泰文 | IBM Plex Sans Thai | U+0E00–0E7F | — |
| 簡體中文 | IBM Plex Sans SC | 3,500 | [通用規範漢字表一級](https://www.gov.cn/zwgk/2013-08/19/content_2469793.htm)（國務院，2013） |
| 繁體中文 | IBM Plex Sans TC | 4,808 | [常用國字標準字體表](https://www.cns11643.gov.tw/)（教育部，1982/2004） |
| 日文 | IBM Plex Sans JP | 2,136 | [常用漢字](https://www.bunka.go.jp/kokugo_nihongo/sisaku/joho/joho/kijun/naikaku/pdf/joyokanjihyo_20101130.pdf)（日本內閣，2010） |
| 韓文諺文 | IBM Plex Sans KR | 2,350 | [KS X 1001](https://standard.go.kr/)（KATS，1987） |
| 符號 | Noto Sans Symbols 1 & 2 | 箭頭、數學、幾何、裝飾符號 | — |

CJK 文字以管線去重方式合併：簡體中文優先，繁體中文填補繁體獨有的空缺，日文填補剩餘。合併後：約 6,318 個獨立 CJK 漢字 + 標點/假名/全形範圍。

## 系統需求

- Python 3.11+
- [fonttools](https://github.com/fonttools/fonttools) >= 4.47
- [cffsubr](https://github.com/adobe-type-tools/cffsubr) >= 0.4.0

## 使用方式

```bash
# 安裝
cd opfonts
uv sync  # 或：pip install -e .

# 建構所有字重（Regular、Medium、SemiBold、Bold）
opfonts

# 預覽——顯示建構計畫但不下載或建構
opfonts --dry-run

# 詳細輸出
opfonts -vv    # DEBUG
```

### CLI 選項

```
opfonts [options]

選項：
  -c, --config PATH           設定檔路徑（省略則自動偵測）
  -v, --verbose               提高詳細程度（預設：INFO，-vv 為 DEBUG）
  --dry-run                   顯示建構計畫，不執行
  --list-scripts              列出已設定的文字系統並退出

```

## 建構管線

```
1. 下載      從設定檔中的 URL 取得來源字型（快取於 ./cache/）
2. 子集化    依文字系統擷取所需的碼位，跨文字系統去重
3. 合併      將輪廓轉換為共用格式，正規化 UPM，合併為單一字型
4. 移除表    移除 BMFont 光柵化不需要的 OpenType 排版表（GSUB/GPOS/GDEF）
5. 定稿      縮放字形以匹配目標度量，設定中繼資料，CFF 子程式化
```

## 設定

建構由 `opfonts.toml` 驅動。主要區段：

```toml
[font]
name = "OpFont"
output_dir = "dist"
copyright = "Copyright 2017 IBM Corp. ..."
designer = "Rick Lan"
ascender = 969              # 選填；設為 0 或省略則保留來源字型的值
descender = -242            # 選填；設為 0 或省略則保留來源字型的值
target_cap_ratio = 0.7273   # 選填；設為 0 或省略則自動匹配第一個文字系統

[font.weight_values]
Regular = 400
Medium = 500
SemiBold = 600
Bold = 700

[[scripts]]
name = "cjk-sc"
font = "IBMPlexSansSC-Regular.otf"
url = "https://raw.githubusercontent.com/IBM/plex/master/packages/plex-sans-sc/fonts/complete/otf/hinted/IBMPlexSansSC-Regular.otf"
charset_file = "charsets/sc_tongyong_l1.txt"
unicode_ranges = ["U+3000-303F", ...]

[[scripts]]
name = "symbols"
font = "NotoSansSymbols-Regular.ttf"
url = "https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/NotoSansSymbols/hinted/ttf/NotoSansSymbols-Regular.ttf"
unicode_ranges = ["U+2190-21FF", ...]

[merge]
drop_tables = ["MATH", "meta", "vhea", "vmtx", "GSUB", "GPOS", "GDEF"]
keep_features = []  # BMFont 光柵化不需要 OpenType 排版功能
```

每個文字系統指定自己的 `url`，因此可以混合不同來源的字型（例如拉丁文用 IBM Plex，CJK 用 Noto Sans）。

文字系統按設定順序合併。每個文字系統可以指定 `unicode_ranges`、`charset_file`（用於 CJK 漢字），或兩者皆有。

## 字元集檔案

`charsets/` 中的政府標準字元表，每行一個字元（UTF-8）：

| 檔案 | 字元數 | 來源 |
|------|--------|------|
| `sc_tongyong_l1.txt` | 3,500 | 中國國務院，2013 |
| `tc_edu_standard_1.txt` | 4,808 | 臺灣教育部，已對照 CNS11643 開放資料驗證 |
| `ja_joyo_kanji.txt` | 2,136 | 日本內閣，2010 |
| `ko_ksx1001_hangul.txt` | 2,350 | 由 Python `euc-kr` 編解碼器產生（KS X 1001） |

## 新增缺少的 CJK 字元

如果翻譯使用了標準字元集中沒有的字元（例如罕見漢字），將其新增到 `charsets/` 中對應的字元集檔案：

```bash
# 在新的一行附加字元
echo '鑫' >> charsets/sc_tongyong_l1.txt
```

然後重新建構。管線會自動包含新字元。跨字元集檔案的重複由去重處理——無需檢查其他檔案。

## 新增語言

兩種情況：

### 語言使用現有文字系統（拉丁文、西里爾文、泰文、CJK、諺文）

無需操作——該文字系統已在 TOML 中，會包含在建構中。

### 語言需要新的文字系統（例如阿拉伯文、希伯來文、天城文）

1. 尋找字型來源。IBM Plex Sans 涵蓋[多種文字系統](https://github.com/IBM/plex)。如果沒有，使用 [Noto Sans](https://github.com/notofonts/notofonts.github.io)。

2. 在 `opfonts.toml` 中新增 `[[scripts]]` 項目：

```toml
[[scripts]]
name = "arabic"
font = "IBMPlexSansArabic-Regular.otf"
url = "https://raw.githubusercontent.com/IBM/plex/master/packages/plex-sans-arabic/fonts/complete/otf/IBMPlexSansArabic-Regular.otf"
unicode_ranges = [
    "U+0600-06FF",   # 阿拉伯文
    "U+0750-077F",   # 阿拉伯文補充
    "U+FB50-FDFF",   # 阿拉伯文表現形式 A
    "U+FE70-FEFF",   # 阿拉伯文表現形式 B
]
```

3. 執行 `opfonts -v` 重新建構。

## 輸出

```
dist/
  OpFont-Regular.otf     ~1.9 MB
  OpFont-Medium.otf      ~1.9 MB
  OpFont-SemiBold.otf    ~1.9 MB
  OpFont-Bold.otf        ~1.9 MB
```

OTF 搭配 CFF 輪廓，UPM 1000，度量匹配 Inter（ascender=969，descender=-242）。

## 授權

字型來源採用 [SIL 開放字型授權 1.1](https://scripts.sil.org/OFL)：
- [IBM Plex](https://github.com/IBM/plex/blob/master/LICENSE.md)
- [Noto Fonts](https://github.com/notofonts/notofonts.github.io/blob/main/LICENSE)
