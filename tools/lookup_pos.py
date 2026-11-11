#!/usr/bin/env python3
"""词性查询小工具

用法：
  # 查单词的词性
  python3 tools/lookup_pos.py book teacher "look after"

  # 查某个词表里属于某词性的词（-f 指定词表文件，-p 指定词性）
  python3 tools/lookup_pos.py -f "课本/小学/人教版(新起点)/一年级/人教版(新起点)一年级上.json" -p v

词性标签：n 名词 / v 动词 / adj 形容词 / adv 副词 / prep 介词 / conj 连词 /
          pron 代词 / num 数词 / art 冠词 / det 限定词 / int 感叹词 / aux 助动词
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POS_TABLE = os.path.join(ROOT, "通用词汇", "词性表.json")

TAG_CN = {
    "n": "名词", "v": "动词", "adj": "形容词", "adv": "副词", "prep": "介词",
    "conj": "连词", "pron": "代词", "num": "数词", "art": "冠词", "det": "限定词",
    "int": "感叹词", "aux": "助动词",
}


def load_pos():
    with open(POS_TABLE, encoding="utf-8") as f:
        return json.load(f)["pos"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words", nargs="*", help="要查询的单词")
    ap.add_argument("-f", "--file", help="词表文件（JSON），配合 -p 使用")
    ap.add_argument("-p", "--pos", help="词性标签，如 v / n / adj")
    args = ap.parse_args()

    pos = load_pos()

    if args.file:
        path = args.file if os.path.isabs(args.file) else os.path.join(ROOT, args.file)
        with open(path, encoding="utf-8") as f:
            words = json.load(f).get("list", [])
        if args.pos:
            hit = [w for w in words if args.pos in pos.get(w.strip().lower(), [])]
            print("%s 中含 %s(%s) 的词：%d 个" % (os.path.basename(path), args.pos,
                                                  TAG_CN.get(args.pos, ""), len(hit)))
            print("  " + ", ".join(hit))
        else:
            print("\n".join("%s\t%s" % (w, "/".join(pos.get(w.strip().lower(), [])) or "-")
                             for w in words))
        return

    if not args.words:
        ap.print_help()
        return

    for w in args.words:
        tags = pos.get(w.strip().lower())
        if tags is None:
            print("%s\t未收录" % w)
        else:
            print("%s\t%s\t(%s)" % (w, "/".join(tags),
                                    ", ".join(TAG_CN.get(t, t) for t in tags)))


if __name__ == "__main__":
    main()
