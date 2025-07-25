

import os
import sys
import json
from typing import Optional
from flask import Flask, request, jsonify, Response

from dotenv import load_dotenv
from camel.configs import QwenConfig
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent

load_dotenv()

API_KEY = os.getenv('QWEN_API_KEY')

SYSTEM_PROMPT = """
你是一个旅游信息提取助手。你的任务是从用户的输入中提取旅游目的地城市和行程天数，并根据提取情况决定是否需要用户补充信息。

用户输入可能包含以下信息：
* 旅游目的地城市名称（例如：北京、上海、巴黎、东京）
* 行程天数（例如：3天、5天、一周、两周）
* 可能会有其他无关信息，请忽略。

你需要将提取到的城市名称和行程天数以 JSON 格式返回，格式如下：
{"city": "城市名称", "days": 天数, "need_more_info": boolean}
* "city" 的值：
    * 如果成功提取到城市名称，则为城市名称字符串。
    * 如果无法提取到城市名称，则为 null。
* "days" 的值：
    * 如果成功提取到行程天数，则为数字。
    * 如果无法提取到行程天数，则为 null。
* "need_more_info" 的值：
    * 如果 "city" 或 "days" 中有任何一个为 null，则为 true，表示需要用户提供更多信息。
    * 如果 "city" 和 "days" 都不为 null，则为 false，表示不需要用户提供更多信息。
* 如果提取到的天数包含“天”或“日”等字样，请将其转换为数字。
* 如果提取到的天数包含“周”或“星期”，请将其转换为7的倍数。例如，“一周”转换为7，“两周”转换为14。
* 如果用户输入中包含多个城市，请只提取第一个城市。
* 如果用户输入中包含多个天数，请只提取第一个天数。

请严格按照 JSON 格式返回结果。

**示例：**

**用户输入：**
我想去北京玩三天，顺便看看长城。

**你的输出：**
{"city": "北京", "days": 3, "need_more_info": false,"response": "信息在Navigator的数据库中查询到啦，正在努力为您生成攻略~"}

**用户输入：**
我想去北京。

**你的输出：**
{"city": "北京", "days": null, "need_more_info": true,"response": "Navigator还不知道您打算去玩几天呢，请补充你计划的行程天数~"}
"""

app = Flask(__name__)

def create_travel_agent():
    qwen_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="Qwen/Qwen2.5-72B-Instruct",
        api_key=API_KEY,
        url="https://api-inference.modelscope.cn/v1",
        model_config_dict=QwenConfig(temperature=0.2).as_dict(),
    )

    agent = ChatAgent(
        system_message=SYSTEM_PROMPT,
        model=qwen_model,
        message_window_size=10,
        output_language='Chinese'
    )
    return agent

travel_agent = create_travel_agent()

def get_travel_info_camel(user_input: str, agent: ChatAgent) -> dict:
    try:
        response = agent.step(user_input)
        # 回到原始状态
        agent.reset()
        if not response or not response.msgs:
            raise ValueError("模型没有返回任何消息")
        json_output = response.msgs[0].content.strip().replace("```json", "").replace("```", "").strip()
        json_output = json.loads(json_output)
        json_output["query"] = user_input
        return json_output
    except json.JSONDecodeError:
        print("Error: 模型返回的不是有效的 JSON 格式。")
        return {
            'city': None,
            'days': None,
            'need_more_info': True,
            'query': user_input,
            'response': None
        }
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {
            'city': None,
            'days': None,
            'need_more_info': True,
            'query': user_input,
            'response': None
        }

# 新增的路由处理函数，用于处理根路径 `/` 的请求
@app.route('/')
def index():
    return "欢迎使用旅游信息提取服务！请使用 POST 请求访问 /extract_travel_info 并提供 'query' 参数。"

@app.route('/extract_travel_info', methods=['POST'])
def extract_travel_info():
    try:
        request_data = request.get_json()
        if not request_data or 'query' not in request_data:
            return jsonify({'error': '请求数据无效'}), 400

        result = get_travel_info_camel(request_data['query'], travel_agent)
        response = {
            'city': result['city'],
            'days': result['days'],
            'need_more_info': result['need_more_info'],
            'query': result['query'],
            'response': result['response']
        }
        response_json = json.dumps(response, ensure_ascii=False)
        return Response(response_json, status=200, mimetype='application/json; charset=utf-8')
    except Exception as e:
        return jsonify({'error': f'服务器内部错误: {str(e)}'}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)