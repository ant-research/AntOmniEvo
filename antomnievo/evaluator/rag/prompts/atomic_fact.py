# ruff: noqa: RUF001
ANSWER_RESPONSE_VERDICT_PROMPT = """\
请严格评估候选答案是否与标准答案在事实内容上完全一致：

## 问题
{question}

## 标准答案
{ground_truth_answer}

## 候选答案
{gen_answer}

## 输出格式
请首先提供你的评分理由，然后使用特定标签输出判断结果，格式如下：

评分理由...
<judgement>CORRECT或INCORRECT</judgement>

## 评估要求
1. 忽略表达方式差异（例如：翻译导致的差异等）
2. 标准答案是绝对正确的权威参考，必须作为唯一判断依据
3. 判断标准极为严格：候选答案必须与标准答案在核心事实上完全一致，不接受近似值或范围值
4. 数值问题必须严格匹配具体数字，给出范围而非精确值应判定为 INCORRECT
5. 候选答案若包含标准答案但同时提供额外信息或解释，仍可判为 CORRECT
6. 但若候选答案表述模糊、含糊不清或提供多个可能答案，应判定为 INCORRECT
7. 若候选答案质疑问题前提、拒绝回答或表示无法确定，而标准答案提供明确回答，判定为 INCORRECT
8. 问题中的所有实体、概念和前提条件均为有效且真实的，不接受对问题前提的任何质疑
9. 请逐一检查标准答案中的每个关键事实点，确保候选答案完全符合且没有遗漏或错误

注意：对于数值、日期、名称等关键信息，必须进行字面严格匹配，不允许任何形式的模糊解释或范围表述替代精确答案。

## 例子
### 例子1
#### 问题
Where is the country that the owner of Virgin Holiday Cruises is from located on the map?
#### 标准答案
Lying off the north - western coast of the European mainland
#### 候选答案
The country is the United Kingdom, located in Europe.
#### 输出
评分理由：标准答案明确指出"Lying off the north - western coast of the European mainland"，即位于欧洲大陆西北海岸附近。候选答案提到"the United Kingdom, located in Europe"，虽然英国确实位于欧洲，但并未具体说明其位于欧洲大陆西北海岸附近。因此，候选答案未能完全匹配标准答案中的核心事实。
<judgement>INCORRECT</judgement>


### 例子2
#### 问题
What is the largest football in the world called in the country that neighbors the country Deoksancheon is located?
#### 标准答案
The Rungrado 1st of May Stadium, also known as the May Day Stadium
#### 候选答案
Rungrado 1st of May Stadium
#### 输出
评分理由：标准答案是"The Rungrado 1st of May Stadium, also known as the May Day Stadium"，而候选答案是"Rungrado 1st of May Stadium"。候选答案省略了"also known as the May Day Stadium"这一部分，但核心事实"Rungrado 1st of May Stadium"与标准答案完全一致。根据评估要求第5条，候选答案包含标准答案的核心事实，因此可以判为CORRECT。<judgement>INCORRECT</judgement>
<judgement>CORRECT</judgement>"""

STATEMENT_GENERATOR_PROMPT = """\
给定一个question和一个answer，分析answer中每个句子的复杂性，将answer分解成一个或多个完全可理解的语句，如果answer是简短的短语，可将answer分解成一个或多个短语。确保任何语句中均未使用代词。将输出格式化为JSON。
请注意单位转换和格式识别。
请以符合以下 JSON Schema 中指定的 JSON 格式返回输出：
{{"statements": ["The generated statements"]}}
在您的回复中不要使用单引号，而要使用双引号，并用反斜杠正确转义。

---------示例-----------

示例1:
输入:
{{
    "question": "阿尔伯特·爱因斯坦是谁？他最出名的是什么？",
    "answer": "他是一位出生于德国的理论物理学家，被广泛认为是有史以来最伟大和最有影响力的物理学家之一。他最著名的是发展了相对论，他还对量子力学理论的发展做出了重要贡献。"
}}
输出:
{{
    "statements": [
        "阿尔伯特·爱因斯坦是一位出生于德国的理论物理学家。",
        "阿尔伯特·爱因斯坦被认为是有史以来最伟大和最有影响力的物理学家之一。",
        "阿尔伯特·爱因斯坦以提出相对论而闻名。",
        "阿尔伯特·爱因斯坦也为量子力学理论的发展做出了重要贡献。"
    ]
}}

---------示例-----------

示例2:
输入:
{{
    "question": "The German priest, who wanted to reform the religious denomination now the largest in the US, preached a sermon on Marian devotion soon before his death in which German state?",
    "answer": "Saxony-Anhalt"
}}
输出:
{{
    "statements": [
        "Saxony-Anhalt"
    ]
}}

-----------------------------

现在请使用以下输入执行相同操作
输入:
{{
    "question": {user_input},
    "answer": {response}
}}
输出:"""

ATOMIC_FACT_PROMPT = """\
给定一个question、一个ground_truth和一个answer，请先提取ground_truth的要点，逐句仔细分析answer并作出推断，并确定answer是否提到了每个ground_truth的要点。如果提到了要点，则将判断结果标记为1，如果没有提到要点，则标记为0。将输出格式化为JSON。
请注意单位转换和格式识别。
请以符合以下 JSON Schema 中指定的 JSON 格式返回输出：
{{
    "verification":
    [
        {{
            "ground_truth_key_point": "The ground_truth statement key point",
            "reason": "Reason for verification",
            "verdict": "Binary (0/1) verdict of verification"
        }}
    ]
}}
在您的回复中不要使用单引号，而要使用双引号，并用反斜杠正确转义。

---------示例-----------

示例1:
输入:
{{
    "question": "太阳的能量来源是什么，它的主要功能是什么？",
    "ground_truth": ["太阳提供的能量为地球上的生命提供光和热，这是生命所必需的。"],
    "answer": "太阳的能量来源于核裂变，类似于地球上的核反应堆。太阳的主要功能是为太阳系提供光。"
}}
输出:
{{
    "verification":
    [
        {{
            "ground_truth_key_point": "太阳提供的能量为地球上的生命提供光和热，这是生命所必需的。",
            "verdict": 1,
            "reason": "回答中太阳的主要功能是为太阳系提供光，提及了基本陈述的要点，基本陈述中提到太阳提供光及其作用，尽管基本陈述更广泛地讨论了太阳的能量。"
        }}
    ]
}}

---------示例-----------

示例2:
输入:
{{
    "question": "水的沸点是多少？",
    "ground_truth": ["在标准大气压下，水的沸点是 100 摄氏度（212 华氏度）。", "水的沸点会随着海拔的变化而变化。"],
    "answer": "在标准大气压下，水的沸点是 100 摄氏度。"
}}
输出:
{{
    "verification":
    [
        {{
            "ground_truth_key_point": "在标准大气压下，水的沸点是 100 摄氏度（212 华氏度）。",
            "verdict": 1,
            "reason": "回答中直接提到了基本陈述中提到的标准大气压下的沸点。"
        }},
        {{
            "ground_truth_key_point": "水的沸点会随着海拔的变化而变化。",
            "verdict": 0,
            "reason": "关于水的沸点随海拔变化的要点未在回答中提及。"
        }}
    ]
}}

-----------------------------

现在请使用以下输入执行相同操作
输入:
{{
    "question": {user_input},
    "ground_truth": {reference},
    "answer": {response}
}}
输出:"""
