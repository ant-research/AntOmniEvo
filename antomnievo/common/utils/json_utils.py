import json
from typing import Any, Dict, List


def parse_jsonl_file(file_path: str, encoding: str = 'utf-8') -> List[Dict[str, Any]]:
    """
    解析JSONL文件，返回所有行的列表

    Args:
        file_path: JSONL文件路径
        encoding: 文件编码，默认utf-8

    Returns:
        包含所有JSON对象的列表 (list[Dict[str, Any]])
    """
    data_list = []

    with open(file_path, 'r', encoding=encoding) as file:
        for line_num, line in enumerate(file, start=1):
            line = line.strip()
            if not line:  # 跳过空行
                continue

            try:
                json_obj = json.loads(line)
                data_list.append(json_obj)
            except json.JSONDecodeError as e:
                print(f"警告: 第{line_num}行JSON格式错误: {e}")
                continue

    return data_list
