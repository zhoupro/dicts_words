#!/usr/bin/env python3
"""生成全局词性表 通用词汇/词性表.json

词性来源（按优先级）：
  1. tools/pos_overrides.json   人工维护的补充/纠错（闭类词、专有名词、WordNet 未收录词）
  2. tools/data/oewn_pos.json   Open English WordNet 2023 派生词库（自动缓存，可 --refresh 重建）
  3. 形态学兜底（复数/过去式/进行时等还原后回查 2）

用法：
  python3 tools/build_pos.py             # 用缓存生成词性表
  python3 tools/build_pos.py --refresh   # 重新下载 OEWN 并重建缓存
  python3 tools/build_pos.py --check     # 只打印覆盖率报告，不写文件
"""

import argparse
import collections
import glob
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
CACHE = os.path.join(TOOLS, "data", "oewn_pos.json")
OVERRIDES = os.path.join(TOOLS, "pos_overrides.json")
EXTRA = os.path.join(TOOLS, "pos_extra.json")
FUNCTION_WORDS = os.path.join(TOOLS, "pos_function_words.json")
OUT = os.path.join(ROOT, "通用词汇", "词性表.json")
MISSING = os.path.join(TOOLS, "pos_missing.txt")

OEWN_URL = os.environ.get(
    "OEWN_URL",
    "https://hf-mirror.com/datasets/jon-tow/open-english-wordnet-synset-2023/resolve/main/open_english_wordnet_2023.jsonl",
)

# 词性标签及输出顺序
TAG_ORDER = ["n", "v", "adj", "adv", "prep", "conj", "pron", "num", "art", "det", "int", "aux"]
OEWN_POS_MAP = {"n": "n", "v": "v", "a": "adj", "s": "adj", "r": "adv"}

# 复合写法拆解：/ | = | ... | 空格
SPLIT_RE = re.compile(r"[\s/=|]|…|\.\.\.")
HYPHEN_RE = re.compile(r"[-–—]")
# 超过该词数的条目视为整句，不做词性标注
MAX_TOKENS = 6
# 实词词性：多词短语只保留这些标签
CONTENT_TAGS = {"n", "v", "adj", "adv", "num"}


# ---------------------------------------------------------------- 数据源

def fetch_oewn_cache():
    """下载 OEWN 并压缩成 word -> [tags] 缓存"""
    print("下载 OEWN ...", file=sys.stderr)
    with urllib.request.urlopen(OEWN_URL, timeout=300) as r:
        data = r.read().decode("utf-8")
    lex = collections.defaultdict(set)
    member_re = re.compile(r"^(.+?)-([nvars])(-\d+)?$")
    for line in data.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        pos = OEWN_POS_MAP.get(d.get("@partOfSpeech"))
        if not pos:
            continue
        for member in d.get("@members", "").split():
            body = member[len("oewn-"):] if member.startswith("oewn-") else member
            m = member_re.match(body)
            if not m:
                continue
            word = m.group(1).replace("_", " ").lower()
            lex[word].add(pos)
    cache = {w: sorted(t, key=TAG_ORDER.index) for w, t in lex.items()}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, sort_keys=True)
    print("缓存已写入 %s（%d 词条）" % (CACHE, len(cache)), file=sys.stderr)
    return cache


def load_oewn():
    if not os.path.exists(CACHE):
        return fetch_oewn_cache()
    with open(CACHE, encoding="utf-8") as f:
        return {w: set(t) for w, t in json.load(f).items()}


def load_json_map(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {k.lower(): set(v) for k, v in json.load(f).items()}


def load_overrides():
    """人工维护的补充与纠错（优先级最高，直接覆盖）"""
    return load_json_map(OVERRIDES)


def load_extra():
    """WordNet 未收录词的补充标注（生僻词、专有名词、现代词汇）"""
    return load_json_map(EXTRA)


def load_function_words():
    """闭类词表：按类别分组写在一个文件里，展开成 word -> {tags}"""
    if not os.path.exists(FUNCTION_WORDS):
        return {}
    with open(FUNCTION_WORDS, encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    for category, words in raw.items():
        if category.startswith("_") or not isinstance(words, list):
            continue
        for w in words:
            out.setdefault(w.lower(), set()).add(category)
    return out


# ---------------------------------------------------------------- 查词

IRREGULAR = {
    # 助动词 / be 系
    "am": "be", "is": "be", "are": "be", "was": "be", "were": "be", "been": "be", "being": "be",
    "has": "have", "had": "have", "having": "have",
    "does": "do", "did": "do", "done": "do", "doing": "do",
    # 不规则动词（过去式/过去分词 → 原形）
    "went": "go", "gone": "go", "goes": "go", "said": "say", "made": "make", "took": "take",
    "taken": "take", "came": "come", "saw": "see", "seen": "see", "got": "get", "gotten": "get",
    "knew": "know", "known": "know", "gave": "give", "given": "give", "found": "find",
    "thought": "think", "brought": "bring", "taught": "teach", "caught": "catch",
    "bought": "buy", "sold": "sell", "told": "tell", "flew": "fly", "flown": "fly",
    "grew": "grow", "grown": "grow", "ran": "run", "swam": "swim", "swum": "swim",
    "sang": "sing", "sung": "sing", "sank": "sink", "sunk": "sink", "leapt": "leap",
    "hung": "hang", "wept": "weep", "awoke": "awake", "woke": "wake", "forgot": "forget",
    "forgotten": "forget", "hid": "hide", "hidden": "hide", "wrote": "write", "written": "write",
    "drank": "drink", "drunk": "drink", "rode": "ride", "ridden": "ride", "wore": "wear",
    "worn": "wear", "learnt": "learn", "became": "become", "began": "begin", "begun": "begin",
    "broke": "break", "broken": "break", "chose": "choose", "chosen": "choose", "drew": "draw",
    "drawn": "draw", "drove": "drive", "driven": "drive", "fell": "fall", "fallen": "fall",
    "felt": "feel", "fought": "fight", "froze": "freeze", "frozen": "freeze", "heard": "hear",
    "held": "hold", "hurt": "hurt", "kept": "keep", "laid": "lay", "left": "leave", "lost": "lose",
    "meant": "mean", "met": "meet", "paid": "pay", "put": "put", "quit": "quit", "read": "read",
    "rose": "rise", "risen": "rise", "sought": "seek", "sent": "send", "set": "set", "shut": "shut",
    "slept": "sleep", "spoke": "speak", "spoken": "speak", "spent": "spend", "spread": "spread",
    "stole": "steal", "stolen": "steal", "struck": "strike", "swore": "swear", "sworn": "swear",
    "swung": "swing", "threw": "throw", "thrown": "throw", "understood": "understand",
    "woke": "wake", "wove": "weave", "woven": "weave", "bit": "bite", "bitten": "bite",
    "blew": "blow", "blown": "blow", "built": "build", "burnt": "burn", "bought": "buy",
    "cost": "cost", "cut": "cut", "dealt": "deal", "done": "do", "fed": "feed", "flew": "fly",
    "flung": "fling", "forbade": "forbid", "froze": "freeze", "gave": "give", "ground": "grind",
    "lent": "lend", "let": "let", "lying": "lie", "lying": "lie", "mistook": "mistake",
    "mistaken": "mistake", "overcame": "overcome", "overcome": "overcome", "rang": "ring",
    "rung": "ring", "shone": "shine", "shone": "shine", "shook": "shake", "shrunk": "shrink",
    "shrank": "shrink", "slept": "sleep", "smelled": "smell", "sped": "speed", "spun": "spin",
    "stuck": "stick", "stuck": "stick", "strove": "strive", "swung": "swing", "tore": "tear",
    "torn": "tear", "wept": "weep", "withdrew": "withdraw", "withdrawn": "withdraw",
    "wove": "weave", "wrung": "wring",
    # 不规则名词复数
    "children": "child", "people": "person", "men": "man", "women": "woman", "feet": "foot",
    "teeth": "tooth", "mice": "mouse", "geese": "goose", "lives": "life", "leaves": "leaf",
    "knives": "knife", "wives": "wife", "wolves": "wolf", "halves": "half", "leaves": "leaf",
    "criteria": "criterion", "larvae": "larva", "antennae": "antenna", "phenomena": "phenomenon",
    "lice": "louse", "hooves": "hoof", "vertebrae": "vertebra", "minutiae": "minute",
    "cacti": "cactus", "fungi": "fungus", "nuclei": "nucleus", "radii": "radius",
    "stimuli": "stimulus", "syllabi": "syllabus", "alumni": "alumnus", "fungi": "fungus",
    "corpora": "corpus", "genera": "genus", "media": "medium", "curricula": "curriculum",
    "errata": "erratum", "strata": "stratum", "memoranda": "memorandum",
    "bacteria": "bacterium", "simplices": "simplex", "appendices": "appendix",
    "indices": "index", "matrices": "matrix", "vertices": "vertex", "apices": "apex",
    "oes": "o", "oes": "o",
    # 不规则比较级
    "better": "good", "best": "good", "worse": "bad", "worst": "bad", "more": "much",
    "less": "little", "least": "little", "elder": "old", "eldest": "old", "further": "far",
    "furthest": "far", "farther": "far", "farthest": "far",
}


def candidates(word):
    """词形还原候选（按可靠性排序）"""
    w = word
    out = []
    if w in IRREGULAR:
        out.append(IRREGULAR[w])
    if w.endswith("ies") and len(w) > 4:
        out.append(w[:-3] + "y")
    if w.endswith("ied") and len(w) > 4:
        out.append(w[:-3] + "y")
    if w.endswith("sses") or w.endswith("shes") or w.endswith("ches") or w.endswith("xes"):
        out.append(w[:-2])
    if w.endswith("s") and not w.endswith("ss") and not w.endswith("us") and len(w) > 2:
        out.append(w[:-1])
    if w.endswith("ed") and len(w) > 3:
        out.append(w[:-1])
        out.append(w[:-2])
    if w.endswith("ing") and len(w) > 4:
        out.append(w[:-3])
        out.append(w[:-3] + "e")
    if w.endswith("er") and len(w) > 4:
        out.append(w[:-1])
        out.append(w[:-2])
        out.append(w[:-2] + "e")
    if w.endswith("est") and len(w) > 4:
        out.append(w[:-2])
        out.append(w[:-1])
        out.append(w[:-2] + "e")
    if w.endswith("ly") and len(w) > 4:
        out.append(w[:-2])
        out.append(w[:-2] + "e")
    if w.endswith("ness") and len(w) > 5:
        out.append(w[:-4])
    if w.endswith("ment") and len(w) > 6:
        out.append(w[:-4])
    if w.endswith("'s") or w.endswith("'") or w.endswith("’s") or w.endswith("’"):
        out.append(w.rstrip("'’s"))
    if w.endswith("n't") or w.endswith("n’t"):
        out.append(w[:-3])
    if w.endswith("'re") or w.endswith("’re"):
        out.append(w[:-3])
    if w.endswith("'ve") or w.endswith("’ve"):
        out.append(w[:-3])
    if w.endswith("'ll") or w.endswith("’ll"):
        out.append(w[:-3])
    if w.endswith("'d") or w.endswith("’d"):
        out.append(w[:-2])
    if w.endswith("'m") or w.endswith("’m"):
        out.append(w[:-2])
    return out


def tokenize(entry):
    """复合写法拆词：'a/an' → ['a','an']；'exercise-book' → ['exercise','book']"""
    parts = []
    for seg in SPLIT_RE.split(entry):
        seg = seg.strip()
        if seg:
            parts.append(seg)
    return parts


def tag_token(tok, lex, overrides, depth=0):
    """单个词（含连字符复合词）→ 词性集合"""
    w = tok.lower().strip(" \t.,;:!?()[]\"“”'")
    if not w:
        return set()
    if w in overrides:
        return set(overrides[w])
    tags = set(lex.get(w, ()))
    if tags:
        return tags
    if depth == 0 and "-" in w:
        parts = [p for p in HYPHEN_RE.split(w) if p]
        if len(parts) > 1:
            per_part = [tag_token(p, lex, overrides, depth + 1) for p in parts]
            # 复合词取中心成分（cellular-phone → phone），只保留实词词性
            content = [t & CONTENT_TAGS for t in per_part]
            content = [c for c in content if c]
            if content:
                return content[-1]
            tags = set()
            for t in per_part:
                tags |= t
            if tags:
                return tags
    for c in candidates(w):
        hit = lex.get(c)
        if hit:
            return set(hit)
    return set()


def tag_entry(entry, lex, overrides):
    """整条词条 → 词性集合"""
    key = entry.strip().lower()
    if key in overrides:
        return set(overrides[key])

    toks = tokenize(entry)
    if not toks or len(toks) > MAX_TOKENS:
        return set()

    # 整体命中（短语在 WordNet 中作为一条释义，如 'look at'、'exercise-book'）
    joined = " ".join(t.lower() for t in toks)
    whole = set(lex.get(joined, ()))
    if whole:
        return whole
    whole = set(lex.get(joined.replace(" ", "-"), ()))
    if whole:
        return whole

    # 逐词取词性
    per_token = [tag_token(t, lex, overrides) for t in toks]
    tags = set()
    for t in per_token:
        tags |= t
    if len(toks) == 1:
        return tags

    # 多词条目取中心词：动词短语取首实词（look forward to → look），
    # 名词短语取尾实词（wage hike → hike）；没有实词时退回并集
    content_idx = [i for i, t in enumerate(per_token) if t & CONTENT_TAGS]
    if not content_idx:
        return tags
    if per_token[-1] & CONTENT_TAGS:
        head = content_idx[-1]
    else:
        head = content_idx[0]
    head_tags = per_token[head] & CONTENT_TAGS
    return head_tags or tags


# ---------------------------------------------------------------- 主流程

def collect_entries():
    """扫描全库词条（保留原始写法）"""
    entries = collections.Counter()
    for path in glob.glob(os.path.join(ROOT, "**", "*.json"), recursive=True):
        if os.path.abspath(path) in (os.path.abspath(OUT),) or os.sep + "tools" + os.sep in path:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # pragma: no cover
            print("跳过 %s: %s" % (path, e), file=sys.stderr)
            continue
        for w in data.get("list", []) or []:
            if isinstance(w, str) and w.strip():
                entries[w] += 1
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="重新下载 OEWN 并重建缓存")
    ap.add_argument("--check", action="store_true", help="只输出报告，不写文件")
    args = ap.parse_args()

    if args.refresh:
        oewn = {w: set(t) for w, t in fetch_oewn_cache().items()}
    else:
        oewn = load_oewn()
    overrides = load_overrides()
    extra = load_extra()
    # 补充词与人工纠错合并（人工纠错优先）
    overrides = {**extra, **overrides}
    func = load_function_words()
    # 统一词典：WordNet 词库 + 闭类词表
    lex = {w: set(t) for w, t in oewn.items()}
    for w, t in func.items():
        lex.setdefault(w, set()).update(t)
    entries = collect_entries()

    pos = {}
    missing = []
    for entry in entries:
        key = entry.strip().lower()
        tags = tag_entry(entry, lex, overrides)
        if tags:
            pos[key] = [t for t in TAG_ORDER if t in tags]
        else:
            missing.append((entry, entries[entry]))

    total = len(entries)
    print("词条总数 %d，标注 %d (%.1f%%)，缺失 %d" % (total, len(pos), 100.0 * len(pos) / total, len(missing)))

    with open(MISSING, "w", encoding="utf-8") as f:
        for e, n in sorted(missing, key=lambda x: -x[1]):
            f.write("%s\t%d\n" % (e, n))
    print("缺失清单: %s" % os.path.relpath(MISSING, ROOT))

    if args.check:
        return

    out = {
        "name": "词性表",
        "desc": "全库统一词性标注（keys 为小写词条，值为词性标签数组）",
        "pos": {k: pos[k] for k in sorted(pos)},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("已写入 %s（%d 词条）" % (os.path.relpath(OUT, ROOT), len(pos)))


if __name__ == "__main__":
    main()
