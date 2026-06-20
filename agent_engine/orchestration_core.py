import os, json, threading
from typing import Optional
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from agri_agent_tools import (
    image_disease_analyzer,
    micro_climate_weather_fetcher,
    computational_yield_matrix,
    autonomous_diary_logger
)


class KeyManager:
    def __init__(self, keys):
        self._keys = [k for k in keys if k]
        self._index = 0
        self._lock = threading.Lock()

    def get_key(self):
        with self._lock:
            key = self._keys[self._index]
            self._index = (self._index + 1) % len(self._keys)
            return key

    def total_keys(self):
        return len(self._keys)

from dotenv import load_dotenv
load_dotenv()
key_manager = KeyManager([k.strip() for k in os.environ.get("GROQ_KEYS", "").split(",") if k.strip()])


tools_execution_pool = [
    image_disease_analyzer,
    micro_climate_weather_fetcher,
    computational_yield_matrix,
    autonomous_diary_logger
]

system_prompt = """
You are 'Kisan Agent', an expert agricultural AI assistant. 

CRITICAL LANGUAGE RULES:
1. The conversation starts with you asking the user for their preferred language: "English" or "Roman Urdu (Roman English)".
2. Analyze the user's first reply. If they reply in English or ask for English, switch your entire response system strictly to English.
3. If they reply in Roman Urdu, ask for Roman Urdu, or type Urdu in English alphabets, switch your entire response system strictly to Roman Urdu.
4. Once the language is established, DO NOT mix languages. Maintain the chosen language for the rest of the session.
5. Never use the Arabic/Urdu script (اردو).

TOOL USAGE RULES:
1. If a location is mentioned, call micro_climate_weather_fetcher.
2. Always call autonomous_diary_logger silently at the end of your thought process.
"""

def handle_image_analysis(base64_image: str, user_message: str) -> dict:
    try:
        clean_b64 = base64_image.split("base64,")[-1].strip()
        raw_result = image_disease_analyzer.invoke({"image_base64": clean_b64})
        disease_result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result

        if disease_result.get("status") == "success":
            diagnosis  = disease_result.get("predicted_class", "Unknown")
            confidence = disease_result.get("confidence", "N/A")
            remedy     = disease_result.get("remedy", "Expert se consult karein.")
            response = (
                f"🌿 Fasal ki Jaanch Mukammal!\n\n"
                f"🔬 Bimari: {diagnosis}\n"
                f"📊 Yakeen: {confidence}\n"
                f"💊 Ilaj: {remedy}\n\n"
                f"Apni fasal ka khayal rakhein! 🌱"
            )
        else:
            response = "⚠️ Tasveer analyze nahi ho saki. Saaf tasveer bhejein. 📸"

        try:
            autonomous_diary_logger.invoke({"diary_note": f"Image scan: {disease_result}"})
        except:
            pass

        return {
            "agent_response": response,
            "metadata": {
                "tool_executed": "image_disease_analyzer",
                "tool_output": disease_result
            }
        }
    except Exception as e:
        return {
            "agent_response": "Image analysis mein masla hua. 🌱",
            "metadata": {"status": "error", "detail": str(e)}
        }


def run_agent(user_message: str, base64_image: Optional[str] = None, language: str = "roman_urdu") -> dict:
    if base64_image and len(base64_image) > 100:
        print("📸 Image detected — direct tool call...")
        # Note: Agar aap chahein toh handle_image_analysis mein bhi language param bhej sakte hain
        return handle_image_analysis(base64_image, user_message)

    # 1. Dynamic Language Rules Setup
   # 1. Dynamic Language Rules Setup
    if language == "english":
        lang_rule = "You MUST strictly respond in pure English. Never use Roman Urdu or the Urdu script."
        err_server = "Server issue encountered. Please try again later. 🌱"
        err_exhausted = "All API keys exhausted. Please try again in a while. 🌱"
    else:
        # Naya Strict Pakistani Roman Urdu Prompt
        lang_rule = """You MUST strictly respond in everyday Pakistani Roman Urdu. 
        CRITICAL: DO NOT use Hindi words like 'taapmaan', 'gati', 'upyukt', 'anukool', 'kripya', 'saavdhani', 'kheti'. 
        Instead, use common Pakistani terms like 'temperature' or 'darja hararat', 'speed' or 'raftaar', 'behtar', 'munasib', 'ehtiyat', 'fasal', 'kisan'. 
        Never use pure English or the Arabic/Urdu script."""
        err_server = "Kisan bhai, server par masla hai. 🌱"
        err_exhausted = "Tamam keys exhaust. Thodi der baad try karein. 🌱"
    # 2. Injecting Rule into Dynamic System Prompt
    dynamic_prompt = f"""
    You are 'Kisan Agent', an expert agricultural AI assistant.

    CRITICAL LANGUAGE RULES:
    {lang_rule}
    Always include farming emojis (🌱, 🌾, 🚜) naturally.

    TOOL USAGE RULES:
    1. If a location is mentioned, call micro_climate_weather_fetcher.
    2. Always call autonomous_diary_logger silently at the end.
    3. If a remedy field is present in the tool output, explain it clearly.
    """

    for attempt in range(key_manager.total_keys()):
        try:
            engine = ChatGroq(
                api_key=key_manager.get_key(),
                model_name="llama-3.3-70b-versatile",
                temperature=0.1
            )
            
            # 3. Pass the dynamic_prompt to the agent
            agent = create_react_agent(
                model=engine,
                tools=tools_execution_pool,
                prompt=dynamic_prompt
            )
            
            result = agent.invoke(
                {"messages": [{"role": "user", "content": user_message}]},
                {"recursion_limit": 10}
            )

            agent_response_text = result["messages"][-1].content
            primary_tool_executed = None
            primary_tool_output = None

            for msg in result["messages"]:
                if (hasattr(msg, "tool_calls") and msg.tool_calls
                        and msg.tool_calls[0]["name"] != "autonomous_diary_logger"):
                    primary_tool_executed = msg.tool_calls[0]["name"]
                if hasattr(msg, "name") and msg.name == primary_tool_executed:
                    try:
                        primary_tool_output = json.loads(msg.content)
                    except:
                        primary_tool_output = msg.content

            return {
                "agent_response": agent_response_text,
                "metadata": {
                    "tool_executed": primary_tool_executed,
                    "tool_output": primary_tool_output
                }
            }

        except Exception as e:
            if "429" in str(e):
                print(f"⚠️ Rate limit — attempt {attempt + 1}/{key_manager.total_keys()}")
                continue
            return {
                "agent_response": err_server, # Localized error message
                "metadata": {"status": "error", "detail": str(e)}
            }

    return {
        "agent_response": err_exhausted, # Localized error message
        "metadata": {"status": "all_keys_exhausted"}
    }