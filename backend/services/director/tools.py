# -*- coding: utf-8 -*-
"""
Director Tool System - 總監 Agent 三大核心工具
1. invoke_sub_agent()     - 呼叫其他代理人
2. evaluate_output()      - 評斷其他代理人的輸出結果
3. supplement_content()   - 執行部分內容的補強與生成
"""

from backend.services.director.tool_registry.registry import TOOL_REGISTRY, export_tools
from backend.services.director.tool_registry.sub_agent import invoke_sub_agent, SubAgentGenerator
from backend.services.director.tool_registry.evaluator import evaluate_output
from backend.services.director.tool_registry.supplement import supplement_content
from backend.services.director.tool_registry.inspect import inspect_content_block, expand_collapsed_json
from backend.services.director.tool_registry.navigator import goto_generation_position
