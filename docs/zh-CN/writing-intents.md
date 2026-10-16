# 编写设计师意图

[English](../writing-intents.md) · [README](../../README.zh-CN.md)

**意图**就是一句描述 AI 打法风格的自然语言。Jev 只读这段文字，*使用*意图不需要写任何代码：

```bash
python -m pokejev play --decider jev --intent ha02 --battles 5 --out runs/ha02
```

**添加**自己的意图：
1. 在 `pokejev/data/intents.json` 中加入这句话，并给一个新的 id。
2. 如果要**衡量**遵从率，还要在 `pokejev/intents.py` 的 `CHECKS` 里加一个检查函数：

```python
"my01": (lambda r: ...,      # applies(request)：这个意图与本次决策是否相关？
         lambda r, c: ...),  # complies(request, chosen_option)：选择 c 是否遵守了意图？
```

`r` 是决策请求：`r["options"]` 列出每个合法选项及其 `facts`，`r["state"]` 是局面（HP 百分比、回合数、速度、剩余宝可梦、距上次换人的回合数……）。`intents.py` 里的辅助函数：
- `_moves(r)`、`_sw(r)`、`_dmg(r)` 分别列出招式、换人和攻击招式；
- `_f(o, "likely_ko")` 读取某个选项的一项事实。

## 遵从率怎么算

- **冲突回合**：意图适用，并且普通规则自己的选择会违反它。只在这些回合统计遵从率，否则忽略意图的决策者也能白拿高分。
- **非冲突回合**：意图适用，但规则的选择本身已经遵守。这里统计最终选择仍然违反意图的比例（应接近 0）。

```bash
python -m pokejev eval runs/ha02
# "conflict_turns": 3, "conflict_compliance": 1.0, "nonconflict_breaks_intent": 0.0
```

## 经验（来自我们的实验）

- **用事实里出现的说法来写条件**：HP 百分比、属性克制、"可能击倒"、先制、反伤、"降低自身能力"、连续使用次数。Jev 会按字面理解。
- **精确条件效果最好。** 阈值、"除非能击倒"、选项之间的比较都能被可靠遵守（实战 97%）。
- **模糊的风格意图在选招时也有效。** 例如"打得谨慎一点""炫技""大幅领先时手下留情"：两位独立标注者认可了 92% 的 Jev 选择。这类意图没有精确的检查函数，可以在查看器里观察效果。
- **中文意图与英文效果相同。**
- **避免两步指代**（"最近攻击过我们刚换下的那只宝可梦的对手"）。这类信息应在代码中算好，作为事实提供。
