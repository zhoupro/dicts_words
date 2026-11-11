# 词性表（tools/）

给全库词条补充词性标注。词表本身**不改动**，词性集中放在一个全局表里，
避免同一个词在几十本教材里重复维护。

## 1. 数据格式

`通用词汇/词性表.json`（生成物，请勿手改）：

```json
{
  "name": "词性表",
  "desc": "全库统一词性标注（keys 为小写词条，值为词性标签数组）",
  "pos": {
    "book": ["n", "v"],
    "ruler": ["n"],
    "a/an": ["art"]
  }
}
```

约定：

- key = 词条的小写形式（原词表里的写法可能带空格、大小写差异，查询时统一 `word.trim().toLowerCase()`）
- value = 词性标签数组，一个词有多个词性就都列出来（`book` 既是动词也是名词 → `["n","v"]`）
- 标签顺序固定：`n, v, adj, adv, prep, conj, pron, num, art, det, int, aux`
  （名词/动词/形容词/副词/介词/连词/代词/数词/冠词/限定词/感叹词/助动词）

消费端查询：

```js
const { pos } = require('./通用词汇/词性表.json');
pos['book'];                        // ['n','v']
pos['book'.toLowerCase()];          // 词条统一小写后查
```

命令行查询（无需写代码）：

```bash
python3 tools/lookup_pos.py book teacher "look after"
python3 tools/lookup_pos.py -f "课本/小学/人教版(新起点)/一年级/人教版(新起点)一年级上.json" -p v
```

## 2. 词性从哪来

优先级从高到低：

| 顺序 | 来源 | 文件 | 说明 |
|---|---|---|---|
| 1 | 人工纠错 | `tools/pos_overrides.json` | 覆盖一切，用来修 WordNet 带来的噪声（如 `i` → `["pron"]`） |
| 2 | 补充标注 | `tools/pos_extra.json` | WordNet 没收录的生僻词、专有名词、现代词汇（自动生成后人工抽查） |
| 3 | WordNet | `tools/data/oewn_pos.json` | Open English WordNet 2023 派生的词库缓存，`--refresh` 可重建 |
| 4 | 闭类词表 | `tools/pos_function_words.json` | 冠词、代词、介词、连词、数词等虚词，WordNet 不收录，人工维护 |
| 5 | 形态学兜底 | `tools/build_pos.py` | 复数/过去式/进行时等还原后回查词库 |

多词短语的取词性规则：先查整条（WordNet 收录的短语直接用），否则取**中心词**
——动词短语取首实词（`look forward to` → `look`），名词短语取尾实词（`wage hike` → `hike`）。

## 3. 维护流程

```bash
python3 tools/build_pos.py            # 生成 通用词汇/词性表.json
python3 tools/build_pos.py --check    # 只看覆盖率报告，不写文件
python3 tools/build_pos.py --refresh  # 重新下载 WordNet 并重建缓存
```

改完词性后跑一次 `build_pos.py` 即可。人工改动写在 `pos_overrides.json`（纠错）
或 `pos_function_words.json`（虚词），别直接改生成物。

## 4. 覆盖情况

- 全库唯一词条 41,587 条，标注 40,125 条（96.5%）
- 未标注的 914 条是整句（如作文例句），不是单词，不做词性标注，明细见 `tools/pos_missing.txt`

## 5. 词库来源与许可

- Open English WordNet 2023（https://en-word.net/），CC BY 4.0
- 缓存文件 `tools/data/oewn_pos.json` 由 `build_pos.py --refresh` 生成，可随时重建
