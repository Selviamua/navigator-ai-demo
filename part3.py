import os
import json
import re
from flask import Flask, request, jsonify
import pdfkit
from flask import send_file
from camel.configs import QwenConfig
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# 模型初始化
qwen_model = ModelFactory.create(
    model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
    model_type="Qwen/Qwen2.5-72B-Instruct",
    api_key=os.getenv("QWEN_API_KEY"),
    url="https://api-inference.modelscope.cn/v1",
    model_config_dict=QwenConfig(temperature=0.2).as_dict(),
)

# 移除谷歌API相关工具
tools_list = []

sys_msg = """
你是一位专业的旅游规划师。请你根据用户输入的旅行需求，包括旅行天数、景点/美食的距离、描述、图片URL、预计游玩/就餐时长等信息，为用户提供一个详细的行程规划。

请遵循以下要求：
1. 按照 Day1、Day2、... 的形式组织输出，直到满足用户指定的天数。
2. 每一天的行程请从早餐开始，食物尽量选用当地特色小吃美食，列出上午活动、午餐、下午活动、晚餐、夜间活动（若有），并在末尾总结住宿或返程安排。
3. 对每个景点或美食，提供其基本信息： 
   - 名称
   - 描述
   - 预计游玩/就餐时长（如果用户未提供，可以不写或自行估计）
   - 图片URL（如果有）
4. 请利用你自身的知识在行程中对移动或出行所需时长做出合理估计。
5. 输出语言为中文。
6. 保持回复简洁、有条理，但必须包含用户想要的所有信息。
"""

agent = ChatAgent(
    system_message=sys_msg,
    model=qwen_model,
    message_window_size=10,
    output_language='Chinese',
    tools=tools_list
)

def create_usr_msg(data: dict) -> str:
    city = data.get("city", "")
    days_str = data.get("days", "1")
    try:
        days = int(days_str)
    except ValueError:
        days = 1

    lines = []
    lines.append(f"我准备去{city}旅行，共 {days} 天。下面是我提供的旅行信息：\n")
    
    scenic_spots = data.get("景点", [])
    foods = data.get("美食", [])

    if scenic_spots:
        lines.append("- 景点：")
        for i, spot in enumerate(scenic_spots, 1):
            lines.append(f"  {i}. {spot.get('name', '未知景点名称')}")
            if '距离' in spot:
                lines.append(f"     - 距离：{spot['距离']}")
            if 'describe' in spot:
                lines.append(f"     - 描述：{spot['describe']}")
            if '图片url' in spot:
                lines.append(f"     - 图片URL：{spot['图片url']}")

    if foods:
        lines.append("\n- 美食：")
        for i, food in enumerate(foods, 1):
            lines.append(f"  {i}. {food.get('name', '未知美食名称')}")
            if 'describe' in food:
                lines.append(f"     - 描述：{food['describe']}")
            if '图片url' in food:
                lines.append(f"     - 图片URL：{food['图片url']}")

    lines.append(f"""
    \n请你根据以上信息，规划一个 {days} 天的行程表。
    从每天的早餐开始，到晚餐结束，列出一天的行程，包括对出行方式或移动距离的简单说明。
    如果有多种景点组合，你可以给出最优的路线推荐。请按以下格式输出：

    Day1:
    - 早餐：
    - 上午：
    - 午餐：
    - 下午：
    - 晚餐：
    ...

    Day2:
    ...

    Day{days}:
    ...
    """
    )
    return "\n".join(lines)

def fix_exclamation_link(text: str) -> str:
    md_pattern = re.compile(r'!\[.*?\]\((https?://\S+)\)')
    return md_pattern.sub(lambda m: m.group(1), text)

def convert_picurl_to_img_tag(text: str, width: int = 300, height: int = 200) -> str:
    text_fixed = fix_exclamation_link(text)
    pattern = re.compile(r'-\s*图片URL：\s*(https?://\S+)')
    replaced_text = pattern.sub(
        rf'''
        <div style="text-align: center;">
            <img src="\1" alt="图片" style="width: {width}px; height: {height}px;" />
        </div>
        ''',
        text_fixed
    )
    return replaced_text

def generate_cards_html(data_dict):
    spots = data_dict.get("景点", [])
    foods = data_dict.get("美食", [])

    html_parts = []
    # 景点推荐
    html_parts.append("<h2>景点推荐</h2>")
    if spots:
        html_parts.append('<div class="card-container">')
        for spot in spots:
            name = spot.get("name", "")
            desc = spot.get("describe", "")
            distance = spot.get("距离", "")
            url = spot.get("图片url", "")
            card_html = f"""
            <div class="card">
            <div class="card-image">
                <img src="{url}" alt="{name}" />
            </div>
            <div class="card-content">
                <h3>{name}</h3>
                <p><strong>距离:</strong> {distance}</p>
                <p>{desc}</p>
            </div>
            </div>
            """
            html_parts.append(card_html)
        html_parts.append("</div>")
    else:
        html_parts.append("<p>暂无景点推荐</p>")

    # 美食推荐
    html_parts.append("<h2>美食推荐</h2>")
    if foods:
        html_parts.append('<div class="card-container">')
        for food in foods:
            name = food.get("name", "")
            desc = food.get("describe", "")
            url = food.get("图片url", "")
            card_html = f"""
            <div class="card">
            <div class="card-image">
                <img src="{url}" alt="{name}" />
            </div>
            <div class="card-content">
                <h3>{name}</h3>
                <p>{desc}</p>
            </div>
            </div>
            """
            html_parts.append(card_html)
        html_parts.append("</div>")
    else:
        html_parts.append("<p>暂无美食推荐</p>")

    return "\n".join(html_parts)

def generate_html_report(itinerary_text, data_dict):
    html_parts = []
    html_parts.append("<!DOCTYPE html>")
    html_parts.append("<html><head><meta charset='utf-8'><title>旅行推荐</title>")
    html_parts.append("<style>")
    html_parts.append("""
    body {
       font-family: "Microsoft YaHei", sans-serif;
       margin: 20px;
       background-color: #f8f8f8;
       line-height: 1.6;
    }
    h1, h2 {
       color: #333;
    }
    .itinerary-text {
       background-color: #fff;
       padding: 20px;
       border-radius: 8px;
       box-shadow: 0 2px 5px rgba(0,0,0,0.1);
       margin-bottom: 30px;
    }
    .card-container {
       display: flex;
       flex-wrap: wrap;
       gap: 20px;
       margin: 20px 0;
    }
    .card {
       flex: 0 0 calc(300px);
       border: 1px solid #ccc;
       border-radius: 10px;
       overflow: hidden;
       box-shadow: 0 2px 5px rgba(0,0,0,0.1);
       background-color: #fff;
    }
    .card-image {
       width: 100%;
       height: 200px;
       overflow: hidden;
       background: #f8f8f8;
       text-align: center;
    }
    .card-image img {
       max-width: 100%;
       max-height: 100%;
       object-fit: cover;
    }
    .card-content {
       padding: 10px 15px;
    }
    .card-content h3 {
       margin-top: 0;
       margin-bottom: 10px;
       font-size: 18px;
    }
    .card-content p {
       margin: 5px 0;
    }
    .image-center {
        text-align: center;
        margin: 20px 0;
    }
    .image-center img {
        width: 300px;
        height: 200px;
        object-fit: cover;
    }
    """)
    html_parts.append("</style></head><body>")
    html_parts.append("<h1>旅行行程与推荐</h1>")
    html_parts.append('<div class="itinerary-text">')
    for line in itinerary_text.split("\n"):
        if not line.strip():
            continue
        if line.strip().startswith("Day"):
            html_parts.append(f"<h2>{line.strip()}</h2>")
        else:
            html_parts.append(f"<p>{line}</p>")
    html_parts.append('</div>')
    html_parts.append(generate_cards_html(data_dict))
    html_parts.append("</body></html>")
    return "\n".join(html_parts)

def save_html_file(city: str, days: str, html_content: str) -> str:
    # 保存路径改为和JSON文件同目录（第五章文件夹下）
    current_dir = os.path.dirname(os.path.abspath(__file__))  # 当前脚本所在目录
    chapter5_dir = os.path.join(current_dir, "第五章")  # 拼接"第五章"目录路径
    os.makedirs(chapter5_dir, exist_ok=True)  # 确保目录存在
    
    filename = f"{chapter5_dir}/{city}{days}天旅游攻略.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filename
# @app.route("/generate_itinerary_html", methods=["POST"])
# def generate_itinerary_html():
#     req_data = request.json or {}
#     city = req_data.get("city", "")
#     days = req_data.get("days", "1")

#     # 1. 正确获取当前脚本所在目录（假设脚本在 "code\第五章" 目录下）
#     # 例如：脚本路径为 D:\handy-multi-agent-main\code\第五章\app.py
#     current_dir = os.path.dirname(os.path.abspath(__file__))  # 结果为 "D:\handy-multi-agent-main\code\第五章"

#     # 2. 拼接JSON文件名（无需再添加 "第五章"，因为current_dir已包含）
#     json_filename = os.path.join(current_dir, f"{city}{days}天旅游信息.json")
#     # 正确路径应为：D:\handy-multi-agent-main\code\第五章\成都3天旅游信息.json

#     # 检查文件是否存在
#     if not os.path.exists(json_filename):
#         return jsonify({
#             "error": f"文件 {json_filename} 不存在，请检查输入的目的地和天数！"
#         }), 404

#     # 3. 读取JSON文件内容
#     print(f"尝试读取文件: {json_filename}")


#     try:
#         with open(json_filename, "r", encoding="utf-8") as f:
#             data = json.load(f)
#     except json.JSONDecodeError:
#         return jsonify({
#             "error": f"文件 {json_filename} 格式错误，请检查文件内容！"
#         }), 400

#     # 生成行程并返回结果
#     usr_msg = create_usr_msg(data)
#     response = agent.step(usr_msg)
#     model_output = response.msgs[0].content
#     end_output = convert_picurl_to_img_tag(model_output)
#     html_content = generate_html_report(end_output, data)
#     saved_file = save_html_file(city, days, html_content)

#     return jsonify({
#         "file_path": saved_file,
#         "html_content": html_content
#     }), 200
# ✨✨✨ 这是修正后的完整函数，请直接复制替换 ✨✨✨

@app.route("/generate_itinerary_html", methods=["POST"])
def generate_itinerary_html():
    req_data = request.json or {}
    city = req_data.get("city", "")
    days = req_data.get("days", "1")

    # 1. 获取当前脚本所在目录 (e.g., "D:\...\code\第五章")
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # --- 核心修正点 ---
    # 2. 在拼接路径时，加入 "storage" 目录
    #    os.path.join 会自动处理斜杠或反斜杠
    storage_dir = os.path.join(current_dir, "storage")
    json_filename = os.path.join(storage_dir, f"{city}{days}天旅游信息.json")
    
    # 现在生成的正确路径是： D:\...\code\第五章\storage\深圳3天旅游信息.json
    # --- 修正结束 ---

    # 检查文件是否存在
    if not os.path.exists(json_filename):
        return jsonify({
            "error": f"文件 {json_filename} 不存在，请检查 'storage' 目录下是否存在该文件！"
        }), 404

    # 3. 读取JSON文件内容
    print(f"尝试读取文件: {json_filename}")
    try:
        with open(json_filename, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return jsonify({
            "error": f"文件 {json_filename} 格式错误，请检查文件内容！"
        }), 400

    # 生成行程并返回结果 (这部分逻辑保持不变)
    usr_msg = create_usr_msg(data)
    response = agent.step(usr_msg)
    model_output = response.msgs[0].content
    end_output = convert_picurl_to_img_tag(model_output)
    html_content = generate_html_report(end_output, data)
    saved_file = save_html_file(city, days, html_content)

    return jsonify({
        "file_path": saved_file,
        "html_content": html_content
    }), 200
# @app.route("/generate_itinerary_pdf", methods=["POST"])
# def generate_itinerary_pdf():
#     req_data = request.json or {}
#     city = req_data.get("city", "")
#     days = req_data.get("days", "1")

#     # 生成 HTML 文件
#     html_response = generate_itinerary_html()
#     # 检查返回结果的类型
#     if isinstance(html_response, tuple) and len(html_response) == 2 and isinstance(html_response[0], dict):
#         result = html_response[0]
#         html_file = result.get("file_path")
#     else:
#         return jsonify({"error": "Unexpected response format from generate_itinerary_html"}), 500

#     # 这里 result 变量已经是 dict，html_file 已经获取
#     # 后续处理 HTML 文件转换为 PDF 的代码
#     # ...

#     # 假设 pdf_file 变量已在后续代码中生成
#     # return jsonify({"pdf_file": pdf_file}), 200
# ✨✨✨ 这是使用 pdfkit 的完整实现 ✨✨✨
@app.route("/generate_itinerary_pdf", methods=["POST"])
def generate_itinerary_pdf():
    # 1. 调用HTML生成逻辑 (与方案一相同)
    html_response, status_code = generate_itinerary_html()
    if status_code != 200:
        return html_response, status_code

    response_data = html_response.get_json()
    html_content = response_data.get("html_content")
    html_file_path = response_data.get("file_path")

    if not html_content or not html_file_path:
        return jsonify({"error": "生成HTML时未能获取到有效内容或路径"}), 500

    try:
        # 2. 定义PDF输出路径
        pdf_file_path = os.path.splitext(html_file_path)[0] + '.pdf'
        print(f"准备将HTML转换为PDF，保存至: {pdf_file_path}")

        # 3. 使用 pdfkit 进行转换
        #    注意：需要正确设置中文字符集
        options = {
            'encoding': "UTF-8",
            'custom-header' : [
                ('Accept-Encoding', 'gzip')
            ],
            'no-outline': None
        }
        pdfkit.from_string(html_content, pdf_file_path, options=options)

        print(f"PDF文件已成功生成: {pdf_file_path}")

        # 4. 将生成的PDF文件作为附件返回 (与方案一相同)
        return send_file(
            pdf_file_path,
            as_attachment=True,
            download_name=os.path.basename(pdf_file_path)
        )

    except Exception as e:
        print(f"HTML转换为PDF时发生错误: {e}")
        # 如果错误信息包含 "No wkhtmltopdf found"，说明外部程序没装好或PATH没配对
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"HTML转换为PDF时发生错误: {str(e)}"}), 500

@app.route('/')
def index():
    return "Welcome to the Travel Itinerary Generator!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004, debug=True,use_reloader=False)