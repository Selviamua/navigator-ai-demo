from camel.toolkits import SearchToolkit
from camel.agents import ChatAgent
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.loaders import Firecrawl
from typing import List, Dict, Any

from flask import Flask, request, jsonify
import json
import os
from dotenv import load_dotenv
import requests # 确保顶部已导入
import os
import json
import requests # 确保顶部已导入

def search_serper_images(query: str, num_results: int = 1) -> list:
    """
    使用 Serper API 进行图片搜索，稳定可靠。

    Args:
        query (str): 搜索的关键词.
        num_results (int): 希望获取的图片数量.

    Returns:
        list: 包含图片信息的列表，格式为 [{'image': '图片URL'}, ...]
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("未找到 SERPER_API_KEY，跳过图片搜索。")
        return []

    # Serper 的图片搜索接口地址
    url = "https://google.serper.dev/images"
    
    payload = json.dumps({
        "q": query,
        "num": num_results
    })
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        response.raise_for_status()
        
        search_results = response.json().get('images', [])
        
        # 为了与您之前的代码无缝对接，我们将返回的格式进行转换
        # Serper 返回的是 'imageUrl'，我们将其转换为 'image'
        formatted_results = []
        for item in search_results:
            formatted_results.append({
                "image": item.get("imageUrl")
            })
            
        print(f"通过 Serper 成功搜索到图片: {query}")
        return formatted_results

    except Exception as e:
        print(f"Serper 图片搜索失败: {e}")
        return []
def search_serper(query: str, num_results: int = 5) -> list:
    """
    使用 Serper API 进行网络搜索，稳定可靠。
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("未找到 SERPER_API_KEY，跳过搜索。")
        return []

    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": num_results})
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        response.raise_for_status()
        
        search_results = response.json().get('organic', [])
        
        # 格式化结果以匹配您之前的代码
        formatted_results = []
        for i, res in enumerate(search_results):
            formatted_results.append({
                "result_id": i + 1,
                "title": res.get('title', ''),
                "url": res.get('link', ''),
                "description": res.get('snippet', '')
            })
        print(f"通过 Serper 成功搜索到 {len(formatted_results)} 条结果。")
        return formatted_results

    except Exception as e:
        print(f"Serper API 搜索失败: {e}")
        return []

import json
load_dotenv()

# --- API KEY 设置 ---
# 注意：这里的 GOOGLE_API_KEY 和 SEARCH_ENGINE_ID 是 Google Custom Search API 需要的
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
os.environ["SEARCH_ENGINE_ID"] = os.getenv("SEARCH_ENGINE_ID")
os.environ["FIRECRAWL_API_KEY"] = os.getenv("FIRECRAWL_API_KEY")
os.environ["QWEN_API_KEY"] = os.getenv("QWEN_API_KEY")

app = Flask(__name__)

class TravelPlanner:
    def __init__(self, city: str, days: int):
        
        #定义地点和时间，设置默认值
        self.city = city
        self.days = days
        self.res = None         

        # --- OPENAI/LLM API 调用准备 (通过 OpenAI 兼容模式) ---
        # 这一部分初始化了语言模型。虽然你用的是Qwen，但其接口模式是OpenAI兼容的。
        # 如果要替换成Qwen的原生SDK，需要修改这里的模型创建和所有ChatAgent的实例化过程。
        self.model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="Qwen/Qwen2.5-72B-Instruct",
            url='https://api-inference.modelscope.cn/v1/',
            api_key=os.getenv('QWEN_API_KEY')
        )

        # 初始化各种Agent，它们将使用上面定义的 self.model
        self.reranker_agent = ChatAgent(
            system_message="你是一搜索质量打分专家，要从{搜索结果}里找出和{query}里最相关的2条结果，保存他们的结果，保留result_id、title、description、url，严格以json格式输出",
            model=self.model,
            output_language='中文'
        )
        self.attraction_agent = ChatAgent(
            system_message="你是一个旅游信息提取专家，要根据内容提取出景点信息并返回json格式，严格以json格式输出",
            model=self.model,
            output_language='中文'
        )
        self.food_agent = ChatAgent(
            system_message="你是一个旅游信息提取专家，要根据内容提取出美食信息并返回json格式，严格以json格式输出",
            model=self.model,
            output_language='中文'
        )
        self.base_guide_agent = ChatAgent(
            system_message="你是一个旅游攻略生成专家，要根据内容生成一个旅游攻略，严格以json格式输出",
            model=self.model,
            output_language='中文'
        )
        # --- OPENAI/LLM API 调用准备结束 ---

        # 初始化搜索工具包，它将用于调用 Google 搜索等
        # self.firecrawl = Firecrawl()#后续功能
        self.search_toolkit = SearchToolkit()

    def extract_json_from_response(self,response_content: str) -> List[Dict[str, Any]]:
            """从LLM响应中提取JSON内容"""
            try:
                # 找到JSON内容的开始和结束位置
                start = response_content.find('```json\n') + 8
                end = response_content.find('\n```', start)
                if start == -1 or end == -1:
                    print("未找到JSON内容的标记")
                    return []
                
                json_str = response_content[start:end].strip()
                print(f"提取的JSON字符串: {json_str}")  # 调试信息
                
                # 解析 JSON 字符串
                parsed = json.loads(json_str)
                
                # 处理不同的JSON结构
                if isinstance(parsed, dict) and "related_results" in parsed:
                    return parsed["results"]
                elif isinstance(parsed, list):
                    return parsed
                else:
                    print("未找到预期的JSON结构")
                    return []
                
            except json.JSONDecodeError as e:
                print(f"解析JSON失败: {str(e)}")
                print(f"原始内容: {response_content}")
                return []
            except Exception as e:
                print(f"发生错误: {str(e)}")
                return []

    def search_and_rerank(self) -> Dict[str, Any]:
        """多次搜索并重排序，整合信息"""
        city = self.city
        days = self.days
        all_results = {}
    
        # 第一次搜索：旅游攻略
        try:
            query = f"{city}{days}天旅游攻略 最佳路线"
            
            # --- GOOGLE API 调用开始 ---
            # 这里使用了 self.search_toolkit 来调用 Google 搜索。
            # 如果你要替换成其他搜索服务（如Bing、或Qwen自己的搜索工具），需要修改这一行。
            # search_results = self.search_toolkit.search_duckduckgo(query=query, max_results=20)
            search_results = search_serper(query=query, num_results=5)
            # --- GOOGLE API 调用结束 ---
            
            prompt = f"请从以下搜索结果中筛选出最相关的{self.days}条{city}{days}天旅游攻略信息，并按照相关性排序：\n{json.dumps(search_results, ensure_ascii=False, indent=2)}"
            
            # --- OPENAI/LLM API 调用开始 ---
            # reranker_agent.step 会调用你在 __init__ 中定义的模型 (当前是Qwen)。
            response = self.reranker_agent.step(prompt)
            # --- OPENAI/LLM API 调用结束 ---
            
            all_results["guides"] = self.extract_json_from_response(response.msgs[0].content)
        except Exception as e:
            print(f"旅游攻略搜索失败: {str(e)}")
            all_results["guides"] = []
        
        # 第二次搜索：必去景点
        try:
            query = f"{city} 必去景点 top10 著名景点"
            
            # --- GOOGLE API 调用开始 ---
            search_results = search_serper(query=query, num_results=5)
            # --- GOOGLE API 调用结束 ---
            
            prompt = f"请从以下搜索结果中筛选出最多{self.days}条{city}最值得去的景点信息，并按照热门程度排序：\n{json.dumps(search_results, ensure_ascii=False, indent=2)}"
            
            # --- OPENAI/LLM API 调用开始 ---
            response = self.reranker_agent.step(prompt)
            # --- OPENAI/LLM API 调用结束 ---
            
            all_results["attractions"] = self.extract_json_from_response(response.msgs[0].content)
        except Exception as e:
            print(f"景点搜索失败: {str(e)}")
            all_results["attractions"] = []
        
        # 第三次搜索：必吃美食
        try:
            query = f"{city} 必吃美食 特色小吃 推荐"

            # --- GOOGLE API 调用开始 ---
            search_results = search_serper(query=query, num_results=5)
            # --- GOOGLE API 调用结束 ---
            
            prompt = f"请从以下搜索结果中筛选出最多{self.days}条{city}最具特色的美食信息，并按照推荐度排序：\n{json.dumps(search_results, ensure_ascii=False, indent=2)}"
            
            # --- OPENAI/LLM API 调用开始 ---
            response = self.reranker_agent.step(prompt)
            # --- OPENAI/LLM API 调用结束 ---
            
            all_results["must_eat"] = self.extract_json_from_response(response.msgs[0].content)
        except Exception as e:
            print(f"必吃美食搜索失败: {str(e)}")
            all_results["must_eat"] = []
        
        # 第四次搜索：特色美食
        try:
            query = f"{city} 特色美食 地方小吃 传统美食"

            # --- GOOGLE API 调用开始 ---
            search_results = search_serper(query=query, num_results=5)
            # --- GOOGLE API 调用结束 ---

            prompt = f"请从以下搜索结果中筛选出最多{self.days}条{city}独特的地方特色美食信息，并按照特色程度排序：\n{json.dumps(search_results, ensure_ascii=False, indent=2)}"
            
            # --- OPENAI/LLM API 调用开始 ---
            response = self.reranker_agent.step(prompt)
            # --- OPENAI/LLM API 调用结束 ---
            
            all_results["local_food"] = self.extract_json_from_response(response.msgs[0].content)
        except Exception as e:
            print(f"特色美食搜索失败: {str(e)}")
            all_results["local_food"] = []
        
        # 整合所有信息
        # ... (这部分是数据处理，没有API调用)
        final_result = {
            "city": city,
            "days": days,
            "travel_info": {
                "guides": [
                    {
                        "result_id": item.get("result_id"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "long_description": item.get("long_description"),
                    }
                    for item in all_results["guides"]
                ],
                "attractions": [
                    {
                        "result_id": item.get("result_id"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "long_description": item.get("long_description"),
                    }
                    for item in all_results["attractions"]
                ],
                "must_eat": [
                    {
                        "result_id": item.get("result_id"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "long_description": item.get("long_description"),
                    }
                    for item in all_results["must_eat"]
                ],
                "local_food": [
                    {
                        "result_id": item.get("result_id"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "long_description": item.get("long_description"),
                    }
                    for item in all_results["local_food"]
                ]
            }
        }
        
        return final_result
    
    def extract_attractions_and_food(self) -> Dict:
        travel_info = self.search_and_rerank()

        # 提供一个base攻略路线
        prompt = f"""
        参考以下信息，生成一个{self.city}{self.days}天攻略路线，直接根据整个travel_info生成
        {travel_info}
        【输出格式】
        {{
            "base_guide": "攻略内容"
        }}
        """
        # --- OPENAI/LLM API 调用开始 ---
        base_guide = self.base_guide_agent.step(prompt)
        # --- OPENAI/LLM API 调用结束 ---
        print(f"这是base攻略: {base_guide.msgs[0].content}")

        # ... (数据处理)
        attractions_text = " ".join([item["description"] for item in travel_info["travel_info"]["attractions"] + travel_info["travel_info"]["guides"]])
        print(f"这是景点信息: {attractions_text}")
        food_text = " ".join([
            item["description"] 
            for item in travel_info["travel_info"]["must_eat"] + travel_info["travel_info"]["local_food"]
        ])
        print(f"这是美食信息: {food_text}")
        
        attractions_prompt = f"""
        请从以下文本中提取出具体的景点名称，注意不能遗漏景点信息，要尽量多提取景点信息，并为每个景点提供简短描述：
        {attractions_text}
        请以JSON格式返回，格式如下：
        {{
            "attractions": [
                {{"name": "景点名称", "description": "简短描述"}}
            ]
        }}
        """
        
        food_prompt = f"""
        请从以下文本中提取出具体的美食名称或者美食店铺，注意不能遗漏美食信息，要尽量多提取美食信息，并为每个美食和店铺提供简短描述：
        {food_text}
        请以JSON格式返回，格式如下：
        {{
            "foods": [
                {{"name": "美食名称", "description": "简短描述"}}
            ],
            "food_shop": [
                {{"name": "美食店铺", "description": "简短描述"}}
            ]
        }}
        """
        
        # --- OPENAI/LLM API 调用开始 ---
        # 使用不同的 Agent 处理不同的提取任务
        attractions_response = self.attraction_agent.step(attractions_prompt)
        foods_response = self.food_agent.step(food_prompt)
        # --- OPENAI/LLM API 调用结束 ---
        
        print(f"这是景点信息: {attractions_response.msgs[0].content}")
        print(f"这是美食信息: {foods_response.msgs[0].content}")
        
        return {
            "base_guide": base_guide.msgs[0].content,
            "attractions": attractions_response.msgs[0].content,
            "foods": foods_response.msgs[0].content
        }
    
    def process_attractions_and_food(self) -> Dict:
        def clean_json_string(json_str: str) -> str:
            # ... (数据清理)
            if '```json' in json_str:
                json_str = json_str.split('```json')[-1]
            if '```' in json_str:
                json_str = json_str.split('```')[0]
            return json_str.strip()
        
        city = self.city
        results = self.extract_attractions_and_food()
        
        # ... (JSON 解析)
        base_guide = json.loads(clean_json_string(results['base_guide']))
        attractions_data = json.loads(clean_json_string(results['attractions']))
        foods_data= json.loads(clean_json_string(results['foods']))
        foods_list = foods_data['foods']
        food_shops_list = foods_data['food_shop']
        
        result = {
            "city": city,
            "days": self.days,
            "base路线": base_guide,
            "景点": [],
            "美食": [],
            "美食店铺": []
        }
        # 处理景点信息



        

        # 处理景点信息
        for attraction in attractions_data['attractions']:
            try:
                image_query = f"{city} {attraction['name']} 实景图"
                # 2. 调用我们新的 Serper 图片搜索函数
                images = search_serper_images(query=image_query, num_results=1)

                # --- DUCKDUCKGO (类比GOOGLE) API 调用开始 ---
                # 这里使用了 DuckDuckGo 进行图片搜索。
                # 你也可以将其替换为其他图片搜索服务。
                # images = self.search_toolkit.search_duckduckgo(
                #     query=f"{city} {attraction['name']} 实景图",
                #     source="images",
                #     max_results=1
                # )
                # --- DUCKDUCKGO API 调用结束 ---
                
                attraction_with_image = {
                    "name": attraction['name'],
                    "describe": attraction['description'],
                    "图片url": images[0]["image"] if images else "",
                }
                result['景点'].append(attraction_with_image)
                
            except Exception as e:
                print(f"搜索{attraction['name']}的图片时出错: {str(e)}")
                result['景点'].append({
                    "name": attraction["name"],
                    "describe": attraction["description"],
                    "图片url": "",
                })
        
        # 处理美食信息
        for food in foods_list:
            try:
                image_query = f"{city} {attraction['name']} 实景图"
                # 2. 调用我们新的 Serper 图片搜索函数
                images = search_serper_images(query=image_query, num_results=1)
                
                food_with_image = {
                    "name": food["name"],
                    "describe": food["description"],
                    "图片url": images[0]["image"] if images else "",
                }
                result['美食'].append(food_with_image)
                
            except Exception as e:
                print(f"搜索{food['name']}的图片时出错: {str(e)}")
                result['美食'].append({
                    "name": food["name"],
                    "describe": food["description"],
                    "图片url": ""
                })
        # 处理美食店铺信息
        for food_shop in food_shops_list:
            try:
                image_query = f"{city} {attraction['name']} 实景图"
                # 2. 调用我们新的 Serper 图片搜索函数
                images = search_serper_images(query=image_query, num_results=1)
                food_shop_with_image = {
                    "name": food_shop["name"],
                    "describe": food_shop["description"],
                    "图片url": images[0]["image"] if images else "",
                }
                result['美食店铺'].append(food_shop_with_image)
            except Exception as e:
                print(f"搜索{food_shop['name']}的图片时出错: {str(e)}")
                result['美食店铺'].append({
                    "name": food_shop["name"],
                    "describe": food_shop["description"],
                    "图片url": ""
                })
        
        # ... (文件保存)
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            storage_dir = os.path.join(current_dir, "storage")
            os.makedirs(storage_dir, exist_ok=True)
            filename = os.path.join(storage_dir, f"{self.city}{self.days}天旅游信息.json")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
            print(f"旅游攻略已保存到文件：{filename}")
        except Exception as e:
            print(f"保存JSON文件时出错: {str(e)}")
        
        return result

# --- Flask App 部分 (无API调用) ---
@app.route('/get_travel_plan', methods=['POST'])
def get_travel_plan():
    try:
        data = request.get_json()
        if not data or 'city' not in data or 'days' not in data:
            return jsonify({
                'status': 'error',
                'message': '请求必须包含city和days参数'
            }), 400
            
        city = data['city']
        days = data['days']
        
        try:
            days = int(days)
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': 'days参数必须为整数'
            }), 400
            
        travel_planner = TravelPlanner(city=city, days=days)
        results = travel_planner.process_attractions_and_food()
        
        return jsonify({
            'status': 'success',
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'处理请求时发生错误: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)