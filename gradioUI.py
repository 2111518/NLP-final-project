import gradio as gr
from google import genai
from PIL import Image
import os
import asyncio

def get_client(api_key):
    """
    初始化最新的 google-genai Client
    """
    target_key = api_key if api_key else os.environ.get("GEMINI_API_KEY", "")
    if not target_key:
        return None
    
    # 建立 Client
    return genai.Client(api_key=target_key)

def build_memory_prompt(history):
    if not history:
        return ""
    prompt_parts = []
    for item in history[-5:]:
        prompt_parts.append(f"用戶：{item['user']}\n助理：{item['assistant']}")
    return "以下是先前對話記憶，請依據它來回答：\n" + "\n\n".join(prompt_parts) + "\n\n"


def build_memory_text(history):
    if not history:
        return "目前尚無對話記憶。"
    lines = []
    for idx, item in enumerate(history[-10:], 1):
        lines.append(f"{idx}. 用戶：{item['user']}\n   助理：{item['assistant']}")
    return "\n\n".join(lines)


def get_response_text(response):
    text = getattr(response, 'text', None)
    if text:
        return text
    if hasattr(response, 'output') and response.output:
        first = response.output[0]
        if hasattr(first, 'content') and first.content:
            first_content = first.content[0]
            return getattr(first_content, 'text', str(response))
    return str(response)


def process_multimodal(api_key, prompt, image, history, use_memory):
    client = get_client(api_key)
    if client is None:
        return "請先輸入您的 Gemini API Key 或設定 GEMINI_API_KEY 環境變數。", history, build_memory_text(history)

    if not prompt and image is None:
        return "請輸入內容或上傳圖片。", history, build_memory_text(history)

    query = prompt if prompt else "請協助分析這張圖片。"
    final_prompt = query
    if use_memory and history:
        final_prompt = build_memory_prompt(history) + query

    contents = [final_prompt]
    if image is not None:
        if not isinstance(image, Image.Image):
            image = Image.fromarray(image)
        contents.append(image)

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents
        )
        response_text = get_response_text(response)
    except Exception as e:
        response_text = f"發生錯誤: {str(e)}\n請檢查您的 API Key 是否正確，或模型名稱是否支援。"
        return response_text, history, build_memory_text(history)

    new_history = history + [{"user": query, "assistant": response_text}]
    return response_text, new_history, build_memory_text(new_history)


def clear_memory():
    return "已清除對話記憶。", [], "目前尚無對話記憶。"


# 建立 Gradio 介面
with gr.Blocks(title="Google GenAI (v1) 多模態介面", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🚀 Google GenAI (v1.x) 多模態介面")
    gr.Markdown("這使用的是最新的 `google-genai` 套件結構。")

    with gr.Row():
        with gr.Column(scale=1):
            api_key_input = gr.Textbox(
                label="Gemini API Key",
                placeholder="在此輸入 Key...",
                value=os.environ.get("GEMINI_API_KEY", ""),
                type="password"
            )
            image_input = gr.Image(label="圖片上傳", type="pil")
            prompt_input = gr.Textbox(label="提問內容", placeholder="請描述這張圖...", lines=4)
            use_memory_checkbox = gr.Checkbox(label="啟用對話記憶", value=True)
            submit_btn = gr.Button("發送分析", variant="primary")
            clear_memory_btn = gr.Button("清除記憶")

        with gr.Column(scale=1):
            output_text = gr.Markdown(label="回應內容")
            memory_display = gr.Textbox(label="對話記憶", interactive=False, lines=12, value="目前尚無對話記憶。")

    history_state = gr.State([])

    submit_btn.click(
        fn=process_multimodal,
        inputs=[api_key_input, prompt_input, image_input, history_state, use_memory_checkbox],
        outputs=[output_text, history_state, memory_display]
    )

    clear_memory_btn.click(
        fn=clear_memory,
        inputs=[],
        outputs=[output_text, history_state, memory_display]
    )

if __name__ == "__main__":
    demo.launch()
