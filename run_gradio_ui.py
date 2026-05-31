import os
import sys
import uuid
import time
import re
import json
import random
import threading
import base64
import io
from pathlib import Path
from contextlib import redirect_stderr

import gradio as gr
from PIL import Image
import numpy as np

# --- Импорт llama-cpp-python для VL модели ---
try:
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Qwen25VLChatHandler
    chat_handler = None
    vl_llm = None 
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("Warning: llama-cpp-python not installed.")
    class DummyLlama:
        def __call__(self, *args, **kwargs):
            return {"choices": [{"text": ""}]}
    chat_handler = None
    Llama = DummyLlama

ROOT = Path(__file__).parent

# Пути к моделям
MMPROJ_PATH = str(ROOT / "models" / "llm" / "Qwen3-VL-8B-Instruct-abliterated-v2.mmproj-f16.gguf")
VL_LLM_PATH = str(ROOT / "models" / "llm" / "Qwen3VL-8B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf")
LLM_ENCODER_PATH = str(ROOT / "models" / "llm" / "Qwen3-4b-Z-Image-Turbo-AbliteratedV1.Q8_0.gguf")
DIFFUSION_MODEL_PATH = str(ROOT / "models" / "zimage" / "z_image_turbo_Q6_K.gguf")
DEFAULT_VAE_PATH = str(ROOT / "models" / "vae" / "ae.safetensors")

SD_BIN_DIR = ROOT / "sd_bin"
LORA_DIR = ROOT / "models" / "loras"
OUTDIR = str(ROOT / "outputs")

FIRST_RUN = True

os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(LORA_DIR, exist_ok=True)

is_model_loaded = False
model_load_error = None
model_lock = threading.Lock()

current_proc = None # Для subprocess sd-cli

def find_sd_executable():
    candidates = [
        ("sd-cli.exe", "sd-cli.exe (recommended)"),
        ("sd.exe", "sd.exe (legacy)"),
    ]
    for exe_name, label in candidates:
        exe_path = SD_BIN_DIR / exe_name
        if exe_path.exists():
            return str(exe_path), label
    return None, None

SD_EXE, SD_EXE_LABEL = find_sd_executable()

RES_PRESETS = [
    ("1:1 (256x256)", 256, 256),
    ("1:1 (512x512)", 512, 512),
    ("1:1 (768x768)", 768, 768),
    ("1:1 (1024x1024)", 1024, 1024),
    ("16:9 (640x384)", 640, 384),
    ("16:9 (896x512)", 896, 512),
    ("16:9 (1024x576)", 1024, 576),
    ("9:16 (384x640)", 384, 640),
    ("9:16 (512x896)", 512, 896),
    ("9:16 (576x1024)", 576, 1024),
    ("4:3 (640x480)", 640, 480),
    ("4:3 (768x576)", 768, 576),
    ("3:2 (768x512)", 768, 512),
    ("2:3 (512x768)", 512, 768),
]

def validate_positive_int(value, default=512):
    try:
        val = int(float(value))
        if val > 0:
            return val
        else:
            return default
    except (ValueError, TypeError):
        return default

def get_lora_list():
    if not LORA_DIR.exists():
        return []
    return [f.name for f in LORA_DIR.glob("*.safetensors")]

def apply_preset(preset_label, custom_width, custom_height):
    if preset_label == "Custom...":
        w = validate_positive_int(custom_width, 512)
        h = validate_positive_int(custom_height, 512)
        return (
            gr.update(value=w, interactive=True),
            gr.update(value=h, interactive=True),
            gr.update(visible=True),
            gr.update(value=w),
            gr.update(value=h)
        )
    else:
        for name, w, h in RES_PRESETS:
            if name == preset_label:
                return (
                    gr.update(value=w, interactive=False),
                    gr.update(value=h, interactive=False),
                    gr.update(visible=False),
                    gr.update(),
                    gr.update()
                )
    return gr.update(), gr.update(), gr.update(), gr.update(), gr.update()

def stop_gen():
    global current_proc
    if current_proc and current_proc.poll() is None:
        print("Stopping generation...")
        if os.name == 'nt':
            import subprocess
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(current_proc.pid)], capture_output=True)
        else:
            current_proc.terminate()
        return "Generation stopped by user."
    return "No active generation to stop."

def process_mask(image_with_mask):
    if image_with_mask is None:
        return None, None
        
    if isinstance(image_with_mask, dict):
        background = image_with_mask.get("background")
        layers = image_with_mask.get("layers", [])
        
        if not layers or not background:
            return None, background

        mask_layer = layers[-1]
        
        try:
            mask_img = Image.open(mask_layer).convert("L")
        except Exception:
            return None, background
        
        mask_path = str(Path(OUTDIR) / f"mask_{uuid.uuid4().hex[:8]}.png")
        mask_img.save(mask_path)
        
        return mask_path, background
    else:
        return None, image_with_mask

SYSTEM_PROMPT_VL = (
    "You are an expert AI art director and prompt engineer. Your task is to transform the user's request and input image into a rich, highly detailed image generation prompt.\n"
    "\n"
    "GUIDELINES FOR DETAILED DESCRIPTION:\n"
    "1. NO HALLUCINATIONS: Do NOT invent objects that are not clearly visible. \n"
    "   - If an object is blurry or ambiguous, describe its SHAPE and COLOR (e.g., 'a dark rectangular shape'), do NOT label it with a specific noun unless certain.\n"
    "   - Pay attention to GEOMETRY: Explicitly mention architectural features like 'corner of the room', 'intersection of walls', etc., if visible.\n"
    "\n"
    "2. EXPAND ON VISUALS: Do not just list objects. Describe their textures, materials, and interaction with light. \n"
    "   - Instead of 'wooden floor', write 'polished oak parquet flooring with subtle grain details reflecting soft ambient light'.\n"
    "   - Instead of 'white walls', write 'clean, minimalist white gallery walls with a matte finish'.\n"
    "   - Instead of just naming the animal, describe its skin/fur/scales texture, eye reflection, wetness, and posture in detail.\n"
    "\n"
    "3. PRESERVE ACCURACY & STYLE:\n"
    "   - STRICTLY adhere to the visual facts of the input image. \n"
    "   - Identify the artistic style (e.g., 'digital illustration', 'photorealistic rendering') and maintain it.\n"
    "\n"
    "4. HANDLE USER INSTRUCTIONS PRECISELY:\n"
    "   - If the user asks for a change, explicitly state this new attribute.\n"
    "   - If no background changes are requested, preserve the original setting exactly.\n"
    "\n"
    "5. CRITICAL BACKGROUND LOGIC:\n"
    "   SCENARIO A: NO BACKGROUND CHANGE REQUESTED\n"
    "   If the request focuses only on the subject:\n"
    "      1. MENTAL INVENTORY: List EVERY distinct object in the background.\n"
    "      2. STRICT INCLUSION: INCLUDE THESE SPECIFIC OBJECTS in the final prompt.\n"
    "      3. POSITIONAL ACCURACY: Describe position relative to the subject (e.g., 'behind the subject', 'to the left').\n"
    "      4. STYLE PRESERVATION: Maintain exact style and lighting.\n"
    "\n"
    "   SCENARIO B: BACKGROUND CHANGE REQUESTED\n"
    "   If the user explicitly asks to change the setting:\n"
    "      1. PRECISE REPLACEMENT: Describe ONLY the new environment.\n"
    "      2. DETAILED DESCRIPTION: Describe new background in high detail.\n"
    "      3. INTEGRATION: Ensure subject fits naturally (lighting, shadows).\n"
    "\n"
    "6. OUTPUT FORMAT:\n"
    "   - Write a single, cohesive paragraph. \n"
    "   - Include technical keywords at the end (e.g., '8k, high definition').\n"
    "   - NO conversational filler. Output ONLY the prompt."
)

SYSTEM_NEGATIVE_PROMPT_VL = (
    "You are an expert AI negative prompt engineer. Your task is to generate a comprehensive negative prompt that explicitly tells the image generation model what to AVOID, based on the user's request and input image.\n"
    "\n"
    "GUIDELINES FOR NEGATIVE PROMPT CONSTRUCTION UNLESS CERTAIN CHANGES ARE STATED IN PROMPT:\n"
    "1. ANTI-HALLUCINATION: Explicitly forbid invented objects not present in the source and prompt.\n"
    "   - State: 'no objects that are not clearly visible in the reference', 'no labeling of ambiguous shapes with specific nouns'.\n"
    "   - For geometry: forbid misinterpretations like 'no straight lines where curves exist', 'no added architectural features'.\n"
    "\n"
    "2. REVERSE VISUAL EXPANSION: Forbid poor or generic versions of textures, materials, and lighting.\n"
    "   - Instead of just 'no mistakes', write: 'no flat wooden textures, no missing grain details, no harsh unidirectional lighting, no plastic-looking reflections'.\n"
    "   - For walls: 'no glossy painted walls instead of matte finish, no visible brush strokes on minimalist surfaces'.\n"
    "   - For animals/subjects: 'no smooth skin where texture exists, no dull eyes, no dry appearance, no unnatural posture'.\n"
    "\n"
    "3. REVERSE ACCURACY & STYLE:\n"
    "   - Forbid deviation from visual facts: 'no altered object positions, no removed elements, no added shadows'.\n"
    "   - For style: forbid style shifts: 'no cartoon style if photorealistic, no 3D render if digital illustration, no oil painting texture where digital is required'.\n"
    "\n"
    "4. REVERSE USER INSTRUCTIONS:\n"
    "   - If user requests a change, forbid the OLD attribute: 'no [original feature]'.\n"
    "   - If no background changes requested: forbid ANY background alteration: 'no background modifications, no added objects, no removed objects, no repositioning of background elements relative to subject'.\n"
    "\n"
    "5. CRITICAL BACKGROUND NEGATIVES:\n"
    "   SCENARIO A: NO BACKGROUND CHANGE REQUESTED\n"
    "   Forbid:\n"
    "      1. 'no missing objects from the original background'\n"
    "      2. 'no invented background objects'\n"
    "      3. 'no positional shifts of background elements relative to subject'\n"
    "      4. 'no style or lighting changes in the background'\n"
    "\n"
    "   SCENARIO B: BACKGROUND CHANGE REQUESTED\n"
    "   Forbid:\n"
    "      1. 'no remnants of the old background' (e.g., no shadows/reflections from previous environment)\n"
    "      2. 'no mismatched lighting between subject and new background'\n"
    "      3. 'no incomplete integration (floating subject, incorrect shadows)'\n"
    "      4. 'no low-detail background elements'\n"
    "\n"
    "6. OUTPUT FORMAT:\n"
    "   - Write a single, cohesive paragraph starting with words like: 'avoid, no, without, except, excluding'.\n"
    "   - Group by category: 'distortions: ..., style violations: ..., missing elements: ..., artifacts: ...'.\n"
    "   - Include common negative keywords at the end (e.g., 'low quality, blurry, distorted, ugly, watermark, text, cropped, out of frame'.\n"
    "   - NO conversational filler. Output ONLY the negative prompt."
)

def initialize_vl_llm(llm_path):
    global vl_llm, is_model_loaded, model_load_error, chat_handler
    
    if not LLM_AVAILABLE:
        print("LLM library not available.")
        is_model_loaded = True
        model_load_error = "llama-cpp-python not installed"
        return
    
    try:
        if chat_handler is None and os.path.exists(MMPROJ_PATH):
             print(f"Loading CLIP handler from {MMPROJ_PATH}...")
             chat_handler = Qwen25VLChatHandler(clip_model_path=MMPROJ_PATH)
             print("CLIP handler loaded.")
        elif not os.path.exists(MMPROJ_PATH):
             raise FileNotFoundError(f"MMPROJ file not found: {MMPROJ_PATH}")

        if os.path.exists(llm_path):
            print(f"Loading Qwen-VL LLM from {llm_path}...")
            vl_llm = Llama(
                model_path=llm_path,
                chat_handler=chat_handler,
                n_gpu_layers=-1, 
                n_ctx=262144,
                verbose=False, # Включаем verbose для логов
            )
            print("Qwen-VL LLM loaded successfully.")
            is_model_loaded = True
        else:
            print(f"VL LLM model not found at {llm_path}")
            is_model_loaded = True
            model_load_error = "Model file not found"
            
    except Exception as e:
        print(f"Failed to load Qwen-VL LLM: {e}")
        vl_llm = None
        is_model_loaded = True
        model_load_error = str(e)

def expand_prompt_with_vl_llm(original_prompt, image_base64=None, temperature=0.7, image_format=None):
    global vl_llm, is_model_loaded, model_load_error
    
    t_start = time.perf_counter()
    
    if not is_model_loaded:
        yield "", "", "Model is still loading...", "0s"
        return
    
    if model_load_error:
        yield "", "", f"Error loading model: {model_load_error}", "0s"
        return

    if not LLM_AVAILABLE or vl_llm is None:
        yield "", "", "Error: LLM not available.", "0s"
        return
    
    if not original_prompt and not image_base64:
        yield "", "", "No input.", "0s"
        return

    messages = []
    content_list = []
    
    if image_base64:
        fmt = image_format.lower() if image_format else "jpeg"
        content_list.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/{fmt};base64,{image_base64}"
            }
        })
    
    user_text = original_prompt if original_prompt else "Describe this image in detail for an AI art generator."
    content_list.append({"type": "text", "text": user_text})

    system_instruction = (
        "Write answer in the STRICTLY following pattern: 'POSITIVE_PROMPT:\\n<prompt>\\nNEGATIVE_PROMPT:\\n<negative prompt>'. "
        "Instructions for positive prompt:\n" + SYSTEM_PROMPT_VL + 
        "\nInstructions for negative prompt:\n" + SYSTEM_NEGATIVE_PROMPT_VL
    )

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": content_list}
    ]
    
    full_response_content = ""
    last_yield_time = 0
    
    # Переменные для постепенного парсинга
    positive_prompt = ""
    negative_prompt = ""
    parsing_state = "waiting"  # waiting, positive, negative
    
    with model_lock:
        try:
            stream = vl_llm.create_chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=1024,
                stop=["</s>", "User:", "Prompt:", "###"],
                stream=True
            )
            
            for chunk in stream:
                current_time = time.time()
                
                # Получаем содержимое из delta
                delta = chunk['choices'][0]['delta']
                content = delta.get('content', '') if delta else ''
                
                if content:
                    full_response_content += content
                    # Парсим по ходу получения данных
                    
                    # Находим позиции ключевых меток
                    pos_start = full_response_content.lower().find("positive_prompt:")
                    neg_start = full_response_content.lower().find("negative_prompt:")
                    
                    new_positive = ""
                    new_negative = ""
                    
                    if pos_start != -1:
                        # Есть начало позитивного промпта
                        pos_content_start = pos_start + len("positive_prompt:")
                        
                        if neg_start != -1 and neg_start > pos_start:
                            # Негативный промпт уже начался, берем только часть до него
                            pos_content = full_response_content[pos_content_start:neg_start].strip()
                        else:
                            # Негативный промпт еще не начался
                            pos_content = full_response_content[pos_content_start:].strip()
                        
                        new_positive = pos_content
                        
                        if neg_start != -1:
                            # Негативный промпт начался
                            neg_content_start = neg_start + len("negative_prompt:")
                            neg_content = full_response_content[neg_content_start:].strip()
                            new_negative = neg_content
                    
                    # Обновляем переменные
                    positive_prompt = new_positive
                    negative_prompt = new_negative

                # Yield только если есть новый контент И прошло хотя бы 0.1 сек с прошлого yield
                if (positive_prompt or negative_prompt) and (current_time - last_yield_time > 0.1):
                    elapsed = f"{time.perf_counter() - t_start:.1f}s"
                    yield positive_prompt, negative_prompt, "", elapsed
                    last_yield_time = current_time
                    time.sleep(0.01) 

        except Exception as e:
            yield "", "", f"\nError during generation: {str(e)}", "0s"
            return

    # Финальная очистка промптов
    for stop_word in ["</s>", "User:", "Prompt:", "###"]:
        negative_prompt = negative_prompt.replace(stop_word, "").strip()
        positive_prompt = positive_prompt.replace(stop_word, "").strip()

    total_time = f"{time.perf_counter() - t_start:.1f}s"
    yield positive_prompt, negative_prompt, f"\n--- Parsing Complete ---\nTotal Time: {total_time}", total_time
    

def gen_image(prompt, negative_prompt, width, height, steps, seed, cfg_scale, vae_path, selected_loras, lora_strength, input_image, img2img_strength, inpaint_mask_path=None, use_llm_expansion=False, llm_temperature=0.7):
    global current_proc
    
    log_buffer = ""
    
    final_prompt_input = prompt
    final_negative_prompt_input = negative_prompt
    img_format = "PNG"
    img_base64 = None
    
    if input_image is not None:
        try:
            img_format = input_image.format if input_image.format else "PNG"
            buffer = io.BytesIO()
            input_image.save(buffer, format=img_format)
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
        except Exception as e:
            yield f"Error processing image: {str(e)}", ""
            return

    if use_llm_expansion:
        log_buffer += "--- [STEP 1] VL-LLM Prompt Expansion ---\n"
        if img_base64:
            log_buffer += f"Mode: Image + Text\nOriginal Text: {prompt}\n"
        else:
            log_buffer += f"Mode: Text Only\nOriginal: {prompt}\n"
            
        yield None, log_buffer + "Analyzing with Qwen-VL...", "0s"
        
        # ВАЖНО: Инициализируем переменные заранее, чтобы они не были пустыми в случае ошибки
        temp_pos = ""
        temp_neg = ""
        
        try:
            for p_part, np_part, log_part, ttime in expand_prompt_with_vl_llm(prompt, img_base64, llm_temperature, img_format):
                # НАКОПЛЕНИЕ ЛОГОВ: Используем +=, а не =
                if log_part:
                    log_buffer += log_part
                
                # Сохраняем последние известные промпты
                if p_part:
                    temp_pos = p_part
                if np_part:
                    temp_neg = np_part
                    
                # Обновляем интерфейс
                yield None, log_buffer.strip(), ttime
                
            # После цикла присваиваем финальные значения
            final_prompt_input = temp_pos
            final_negative_prompt_input = temp_neg
                
        except Exception as e:
            log_buffer += f"\nError during expansion: {str(e)}"
            yield None, log_buffer.strip(), "0s"
            return

        if not final_prompt_input:
             yield None, log_buffer + "\n[ERROR] Empty prompt generated.", "0s"
             return

        log_buffer += f"\nExpanded Prompt: {final_prompt_input}\nExpanded Negative Prompt: {final_negative_prompt_input}\n"
        log_buffer += "--- [STEP 2] Image Generation ---\n"
        yield None, log_buffer + "Starting diffusion model...", "0s"

    if SD_EXE is None:
        yield None, log_buffer + "Error: No stable-diffusion executable found.", ""
        return

    width = validate_positive_int(width, 512)
    height = validate_positive_int(height, 512)

    if seed == 0:
        seed = random.randint(1, 2**31 - 1)

    uid = uuid.uuid4().hex[:8]
    out_file = str(Path(OUTDIR).absolute() / f"out_{uid}.png")
    
    final_prompt_sd = final_prompt_input
    if selected_loras:
        for lora in selected_loras:
            lora_name = Path(lora).stem
            final_prompt_sd += f" <lora:{lora_name}:{lora_strength}>"

    cmd = [
        SD_EXE,
        "--diffusion-model", DIFFUSION_MODEL_PATH,
        "--vae", vae_path,
        "--llm", LLM_ENCODER_PATH,
        "--lora-model-dir", str(LORA_DIR),
        "-p", final_prompt_sd,
        "-n", final_negative_prompt_input,
        "--cfg-scale", str(cfg_scale),
        "--steps", str(steps),
        "-H", str(height), "-W", str(width),
        "-o", out_file,
        "--seed", str(seed),
        "--rng", "cuda"
    ]

    if input_image is not None:
        img_path = None
        if isinstance(input_image, dict):
            if "path" in input_image:
                img_path = input_image["path"]
            elif "background" in input_image:
                img_path = input_image["background"]
        elif isinstance(input_image, str):
            img_path = input_image
            
        if img_path and os.path.exists(img_path):
            cmd.extend(["-i", img_path])
            
            if inpaint_mask_path and os.path.exists(inpaint_mask_path):
                cmd.extend(["--mask", inpaint_mask_path])
                cmd.extend(["--strength", str(img2img_strength)])
            else:
                cmd.extend(["--strength", str(img2img_strength)])

    cmd_str = " ".join([f'"{c}"' if " " in str(c) else str(c) for c in cmd])
    
    mode_text = "[Inpaint]" if inpaint_mask_path else ("[Img2Img]" if input_image is not None else "[Txt2Img]")
    
    log_buffer += f"{mode_text} Starting...\nCommand: {cmd_str}\nSeed: {seed}\n--- Logs ---\n"
    yield None, log_buffer, "0s"

    t_start = time.perf_counter()
    import subprocess
    current_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )

    try:
        for line in current_proc.stdout:
            print(line, end="")
            log_buffer += line
            elapsed = int(time.perf_counter() - t_start)
            yield None, log_buffer.strip(), f"{elapsed}s"
    except Exception as e:
        log_buffer += f"\nError during logging: {str(e)}"
        yield None, log_buffer.strip(), "0s"

    current_proc.wait()
    t_end = time.perf_counter()
    total_time = f"{t_end - t_start:.1f}s"
    
    if current_proc.returncode != 0:
        if current_proc.returncode in [-1, 1, 3221225786, 15]: 
            log_buffer += "\nGeneration stopped by user."
            yield None, log_buffer.strip(), total_time
        else:
            log_buffer += f"\nsd.exe exited with code {current_proc.returncode}"
            yield None, log_buffer.strip(), total_time
        return

    if os.path.exists(out_file):
        log_buffer += "\n[SUCCESS] Image saved."
        yield out_file, log_buffer.strip(), total_time
    else:
        imgs = sorted(Path(OUTDIR).glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        if imgs:
            log_buffer += "\n[SUCCESS] Image found (fallback)."
            yield str(imgs[0].absolute()), log_buffer.strip(), total_time
        else:
            log_buffer += "\n[ERROR] No image was produced."
            yield None, log_buffer.strip(), total_time

# ==========================================
# GRADIO INTERFACE
# ==========================================

INIT_JS = """
<script>
(function() {
    const style = document.createElement('style');
    style.innerHTML = `
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes loadingBar { 0% { width: 0%; margin-left: 0%; } 50% { width: 70%; margin-left: 15%; } 100% { width: 0%; margin-left: 100%; } }
    `;
    document.head.appendChild(style);

    const overlay = document.createElement('div');
    overlay.id = 'loading-overlay';
    overlay.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        z-index: 99999; display: flex; justify-content: center; align-items: center;
        flex-direction: column; color: white; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        transition: opacity 0.5s ease;
    `;
    overlay.innerHTML = `
        <div style="text-align: center; animation: fadeIn 0.5s ease;">
            <div style="font-size: 48px; margin-bottom: 20px;">🤖</div>
            <h1 style="font-size: 28px; margin-bottom: 10px;">Loading AI Model...</h1>
            <p style="font-size: 16px; opacity: 0.8;">Please wait, initializing neural network...</p>
            <div style="margin-top: 30px;">
                <div style="width: 200px; height: 4px; background: rgba(255,255,255,0.2); border-radius: 2px; overflow: hidden; margin: 0 auto;">
                    <div style="width: 30%; height: 100%; background: #4CAF50; border-radius: 2px; animation: loadingBar 1.5s infinite ease;"></div>
                </div>
            </div>
            <p id="loading-status" style="margin-top: 30px; font-size: 12px; opacity: 0.5;">Checking status...</p>
        </div>
    `;
    document.body.appendChild(overlay);
})();
</script>
"""

with gr.Blocks(head=INIT_JS) as demo:
    gr.Markdown("# Z-Image Turbo - Unified Interface")
    
    with gr.Row(visible=False):
        vae_path_comp = gr.Textbox(value=DEFAULT_VAE_PATH)
        enable_llm_expansion_comp = gr.Checkbox(value=False)
        llm_temperature_comp = gr.Slider(minimum=0.1, maximum=1.5, value=0.7, step=0.1)
        hide_overlay_trigger = gr.Textbox(visible=False)

    with gr.Tabs() as tabs:
        with gr.Tab("Basic", id="basic"):
            with gr.Row():
                with gr.Column(scale=3):
                    with gr.Group():
                        gr.Markdown("### Image Editing / Reference (Img2Img)")
                        input_image = gr.Image(label="Upload Reference Image (Optional)", type="pil", sources=["upload", "clipboard"])
                        img2img_strength = gr.Slider(
                            minimum=0.0, maximum=1.0, value=0.75, step=0.05, 
                            label="Denoising Strength (0.1 = Keep Original, 0.9 = Change Much)"
                        )
                        gr.Markdown("*If no image is uploaded, it works as normal Text-to-Image.*")

                    prompt_basic = gr.Textbox(label="Prompt (Instructions or Description)", value="A large orange octopus on an ocean floor, cinematic, 8k", lines=10)
                    negative_prompt_basic = gr.Textbox(label="Negative prompt (What you don't want to see)", value="ugly, deformed, blurry, text", lines=5)
                    
                    with gr.Row():
                        preset = gr.Dropdown(
                            [n for n, _, _ in RES_PRESETS] + ["Custom..."], 
                            value="1:1 (512x512)", 
                            label="Resolution Preset"
                        )
                        steps = gr.Slider(1, 50, value=8, step=1, label="Steps")
                    
                    with gr.Row():
                        width = gr.Number(value=512, label="Width", precision=0, minimum=64, maximum=4096, interactive=False)
                        height = gr.Number(value=512, label="Height", precision=0, minimum=64, maximum=4096, interactive=False)
                    
                    with gr.Row(visible=False) as custom_row:
                        custom_width = gr.Number(value=512, label="Custom Width Buffer", interactive=True, precision=0, minimum=1, maximum=4096, visible=False)
                        custom_height = gr.Number(value=512, label="Custom Height Buffer", interactive=True, precision=0, minimum=1, maximum=4096, visible=False)
                    
                    with gr.Row():
                        cfg_scale = gr.Slider(0.0, 10.0, value=1.0, step=0.1, label="CFG Scale")
                        seed = gr.Number(value=0, label="Seed (0 = random)", precision=0)

                    with gr.Group():
                        gr.Markdown("### LoRA Support")
                        with gr.Row():
                            lora_list = gr.CheckboxGroup(choices=get_lora_list(), label="Select LoRAs")
                            refresh_btn = gr.Button("Refresh", variant="secondary", size="sm")
                        with gr.Row():
                            lora_strength = gr.Slider(0.0, 2.0, value=1.0, step=0.1, label="LoRA Strength")
                        
                        def refresh_loras():
                            return gr.update(choices=get_lora_list())
                        refresh_btn.click(refresh_loras, outputs=[lora_list])
                    
                    with gr.Row():
                        btn = gr.Button("Generate / Edit", variant="primary", scale=2)
                        stop_btn = gr.Button("Stop", variant="stop", scale=1)

                with gr.Column(scale=2):
                    with gr.Group():
                        img = gr.Image(label="Result", interactive=False, type="filepath")
                        with gr.Row():
                            timer_display = gr.Markdown("Generation Time: **0s**")
                    
                    status = gr.Textbox(label="Status / Logs", interactive=False, lines=15)

            preset.change(apply_preset, inputs=[preset, custom_width, custom_height], outputs=[width, height, custom_row, custom_width, custom_height])
            
            def sync_custom_from_main(w, h):
                return gr.update(value=w), gr.update(value=h)

            width.change(sync_custom_from_main, inputs=[width, height], outputs=[custom_width, custom_height])
            height.change(sync_custom_from_main, inputs=[width, height], outputs=[custom_width, custom_height])

            def run_and_return_basic(p, n, w, h, st, sd, cfg, vae, l_list, l_str, in_img, i2i_str, use_llm, llm_temp):
                global FIRST_RUN
                status_msg = "Generating... (first run can take longer)" if FIRST_RUN else "Generating..."
                FIRST_RUN = False
                
                yield None, status_msg, gr.update(interactive=False), gr.update(interactive=True), "Generation Time: **0s**"
                
                last_img = None
                last_log = ""
                last_time = "0s"
                
                for out_img, log, time_str in gen_image(
                    p, n, int(w), int(h), int(st), int(sd), float(cfg), vae, 
                    l_list, l_str, in_img, i2i_str, 
                    inpaint_mask_path=None, 
                    use_llm_expansion=use_llm, 
                    llm_temperature=llm_temp
                ):
                    if out_img is not None:
                        last_img = out_img
                    last_log = log
                    last_time = time_str
                    image_update = out_img if out_img is not None else gr.update()
                    yield image_update, log, gr.update(interactive=False), gr.update(interactive=True), f"Generation Time: **{time_str}**"
                
                final_image = last_img if last_img is not None else gr.update()
                yield final_image, last_log, gr.update(interactive=True), gr.update(interactive=False), f"Generation Time: **{last_time}**"

            btn.click(
                run_and_return_basic, 
                inputs=[
                    prompt_basic, negative_prompt_basic, width, height, steps, seed, cfg_scale, 
                    vae_path_comp, 
                    lora_list, lora_strength, input_image, img2img_strength,
                    enable_llm_expansion_comp, llm_temperature_comp
                ], 
                outputs=[img, status, btn, stop_btn, timer_display]
            )
            stop_btn.click(stop_gen, outputs=[status])


        with gr.Tab("Inpaint / Edit", id="inpaint"):
            gr.Markdown("### Instructions: Upload a photo, brush over the area you want to change, and write what should be in that place.")
            
            with gr.Row():
                with gr.Column(scale=3):
                    inpaint_input = gr.ImageEditor(
                        label="Upload & Mask",
                        type="filepath",
                        layers=False,
                        sources=["upload", "clipboard"],
                        brush=gr.Brush(colors=["#FFFFFF"], color_mode="fixed")
                    )
                    
                    prompt_inpaint = gr.Textbox(label="What to draw in the masked area?", placeholder="e.g., A capybara facing left, wearing a hat", lines=10)
                    negative_prompt_inpaint = gr.Textbox(label="What NOT to draw in the masked area?", placeholder="e.g., ugly, deformed, blurry, text", lines=5)
                    
                    with gr.Row():
                        steps_inpaint = gr.Slider(1, 50, value=20, step=1, label="Steps")
                        inpaint_strength = gr.Slider(0.1, 1.0, value=0.75, step=0.05, label="Inpaint Strength (0.1=Subtle, 1.0=Total Change)")
                    
                    with gr.Row():
                        cfg_scale_inpaint = gr.Slider(0.0, 10.0, value=7.0, step=0.1, label="CFG Scale")
                        seed_inpaint = gr.Number(value=0, label="Seed (0 = random)", precision=0)

                    btn_inpaint = gr.Button("Run Inpaint", variant="primary")
                    stop_btn_inpaint = gr.Button("Stop Inpaint", variant="stop")
                
                with gr.Column(scale=2):
                    with gr.Group():
                        img_inpaint = gr.Image(label="Result", interactive=False, type="filepath")
                        with gr.Row():
                            timer_inpaint = gr.Markdown("Generation Time: **0s**")
                    
                    status_inpaint = gr.Textbox(label="Status / Logs", interactive=False, lines=15)

            def run_inpaint_process(editor_val, prompt, negative_prompt, steps, strength, cfg, seed, use_llm, llm_temp):
                global FIRST_RUN
                if FIRST_RUN:
                    FIRST_RUN = False
                    
                mask_path, bg_path = process_mask(editor_val)
                
                if bg_path is None:
                    yield None, "Please upload an image first.", "0s"
                    return

                if mask_path is None:
                    yield None, "No mask detected. Running as standard Img2Img...", "0s"
                
                try:
                    if bg_path and os.path.exists(bg_path):
                        with Image.open(bg_path) as img_orig:
                            w_orig, h_orig = img_orig.size
                            w_proc = (w_orig // 8) * 8
                            h_proc = (h_orig // 8) * 8
                    else:
                        w_proc, h_proc = 512, 512
                except:
                    w_proc, h_proc = 512, 512

                for out_img, log, time_str in gen_image(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=w_proc, 
                    height=h_proc,
                    steps=int(steps),
                    seed=int(seed),
                    cfg_scale=float(cfg),
                    vae_path=DEFAULT_VAE_PATH, 
                    selected_loras=[],
                    lora_strength=1.0,
                    input_image=Image.open(bg_path),
                    img2img_strength=float(strength),
                    inpaint_mask_path=mask_path,
                    use_llm_expansion=use_llm,
                    llm_temperature=llm_temp
                ):
                    yield out_img, log, time_str

            btn_inpaint.click(
                run_inpaint_process,
                inputs=[
                    inpaint_input, prompt_inpaint, negative_prompt_inpaint, steps_inpaint, inpaint_strength, 
                    cfg_scale_inpaint, seed_inpaint,
                    enable_llm_expansion_comp, llm_temperature_comp
                ],
                outputs=[img_inpaint, status_inpaint, timer_inpaint]
            )
            stop_btn_inpaint.click(stop_gen, outputs=[status_inpaint])

        with gr.Tab("Prompt Helper"):
            gr.Markdown("### AI Prompt Engineer Assistant")
            gr.Markdown("Upload an image and describe what you want to change or generate. Qwen-VL will create a detailed, optimized prompt for you.")
            
            with gr.Row():
                with gr.Column(scale=1):
                    helper_image = gr.Image(label="Upload Reference Image", type="pil", sources=["upload", "clipboard"])
                    helper_prompt_input = gr.Textbox(label="Your Request (e.g., 'Make it look right', 'Change background to space')", lines=3, placeholder="Describe your intent...")
                    helper_temp = gr.Slider(0.1, 1.5, value=0.7, step=0.1, label="Creativity Temperature")
                    
                    btn_generate_prompt = gr.Button("Generate Detailed Prompt", variant="primary")
                    
                    with gr.Row():
                        btn_copy_to_basic = gr.Button("Copy to Basic Tab", variant="secondary")
                        btn_copy_to_inpaint = gr.Button("Copy to Inpaint Tab", variant="secondary")
                
                with gr.Column(scale=2):
                    helper_result = gr.Textbox(label="Generated Positive Prompt", lines=10, interactive=True)
                    helper_negative_result = gr.Textbox(label="Generated Negative Prompt", lines=5, interactive=True)
                    
                    with gr.Group():
                        helper_status_logs = gr.Textbox(label="Status / Logs", interactive=False, lines=15)
                        with gr.Row():
                            helper_timer_display = gr.Markdown("Generation Time: **0s**")

            def run_helper_generation(img, req, temp):
                if not LLM_AVAILABLE or vl_llm is None:
                    yield "Error: Model not loaded yet. Please wait or check console.", "", "", "0s"
                    return
                
                img_base64 = None
                img_format = "PNG"
                log_buffer = "--- [STEP 1] VL-LLM Prompt Expansion (Direct Call) ---\n"
                
                t_start = time.perf_counter()
                
                if img is not None:
                    try:
                        img_format = img.format if img.format else "PNG"
                        log_buffer += f"Image format detected: {img_format}\n"
                        
                        buffer = io.BytesIO()
                        img.save(buffer, format=img_format)
                        img_base64 = base64.b64encode(buffer.getvalue()).decode()
                        log_buffer += "Image converted to base64.\n"
                    except Exception as e:
                        yield f"Error processing image: {str(e)}", "", "", "0s"
                        return
                else:
                    log_buffer += "No image provided. Text-only mode.\n"

                log_buffer += f"Request: {req}\nTemperature: {temp}\n"
                log_buffer += "Sending request to Qwen-VL...\n"
                
                yield log_buffer, "Generating prompt...\nPlease wait...", "Generating negative prompt...\nPlease wait...", "0s"
                
                result_prompt = ""
                result_negative = ""
                
                try:
                    for p_part, np_part, log_part, ttime in expand_prompt_with_vl_llm(req, img_base64, temp, img_format):
                        if log_part:
                            log_buffer += log_part
                        
                        if p_part:
                            result_prompt = p_part
                        if np_part:
                            result_negative = np_part
                            
                        yield log_buffer.strip(), result_prompt, result_negative, ttime

                    t_end = time.perf_counter()
                    total_time = f"{t_end - t_start:.1f}s"
                    
                    log_buffer += "\n[SUCCESS] Prompts generated successfully."
                    yield log_buffer, result_prompt, result_negative, total_time
                    
                except Exception as e:
                    t_end = time.perf_counter()
                    total_time = f"{t_end - t_start:.1f}s"
                    log_buffer += f"\n[ERROR] Generation Error: {str(e)}"
                    yield log_buffer, "", "", total_time

            btn_generate_prompt.click(
                run_helper_generation,
                inputs=[helper_image, helper_prompt_input, helper_temp],
                outputs=[helper_status_logs, helper_result, helper_negative_result, helper_timer_display]
            )
            
            def copy_to_basic_tab(prompt_text, negative_text):
                return prompt_text, negative_text, gr.update(selected="basic")

            def copy_to_inpaint_tab(prompt_text, negative_text):
                return prompt_text, negative_text, gr.update(selected="inpaint")

            btn_copy_to_basic.click(
                copy_to_basic_tab,
                inputs=[helper_result, helper_negative_result],
                outputs=[prompt_basic, negative_prompt_basic, tabs]
            )

            btn_copy_to_inpaint.click(
                copy_to_inpaint_tab,
                inputs=[helper_result, helper_negative_result],
                outputs=[prompt_inpaint, negative_prompt_inpaint, tabs]
            )

        with gr.Tab("Settings"):
            gr.Markdown("### Original by airesearch-official")
            gr.Markdown("### Advanced by NamerPRO")
            with gr.Group():
                gr.Markdown("### Advanced Paths")
                unlock = gr.Checkbox(value=False, label="Allow editing advanced paths")
                with gr.Row():
                    vae_path_ui = gr.Textbox(label="VAE path", value=DEFAULT_VAE_PATH, interactive=False)
                    llm_encoder_ui = gr.Textbox(label="LLM Encoder (for sd-cli)", value=LLM_ENCODER_PATH, interactive=False)
                    vl_llm_ui = gr.Textbox(label="VL LLM", value=VL_LLM_PATH, interactive=False)
                    vl_mmproj_ui = gr.Textbox(label="VL MMPROJ", value=MMPROJ_PATH, interactive=False)

                def set_unlocked(enabled):
                    return gr.update(interactive=bool(enabled)), gr.update(interactive=bool(enabled)), gr.update(interactive=bool(enabled)), gr.update(interactive=bool(enabled))
                
                unlock.change(set_unlocked, inputs=[unlock], outputs=[vae_path_ui, llm_encoder_ui, vl_llm_ui, vl_mmproj_ui])
                
                vae_path_ui.change(lambda x: x, inputs=[vae_path_ui], outputs=[vae_path_comp])

            with gr.Group():
                gr.Markdown("### VL-LLM Prompt Expansion Settings")
                if not LLM_AVAILABLE:
                    gr.Markdown("⚠️ `llama-cpp-python` is not installed. Install it via `pip install llama-cpp-python` to enable this feature.")
                
                vis_enable_llm = gr.Checkbox(
                    value=False, 
                    label="Enable Auto-Expansion in Basic Tab",
                    info="If checked, Qwen3VL-8B will automatically analyze images in the Basic tab before generation."
                )
                
                vis_llm_temp = gr.Slider(
                    minimum=0.1, 
                    maximum=1.5, 
                    value=0.7, 
                    step=0.1, 
                    label="LLM Creativity (Temperature)",
                    info="Higher values make the LLM more creative."
                )

                vis_enable_llm.change(lambda x: x, inputs=[vis_enable_llm], outputs=[enable_llm_expansion_comp])
                vis_llm_temp.change(lambda x: x, inputs=[vis_llm_temp], outputs=[llm_temperature_comp])

    def check_model_status():
        global is_model_loaded
        if is_model_loaded:
            return "READY"
        return None

    def hide_loading_overlay_js():
        return """
        (value) => {
            if (value === "READY") {
                const overlay = document.getElementById('loading-overlay');
                if (overlay) {
                    overlay.style.opacity = '0';
                    overlay.style.pointerEvents = 'none';
                    setTimeout(() => {
                        if (overlay && overlay.parentNode) {
                            overlay.parentNode.removeChild(overlay);
                        }
                    }, 500);
                }
            }
        }
        """

    timer = gr.Timer(1)
    timer.tick(
        fn=check_model_status,
        inputs=[],
        outputs=[hide_overlay_trigger]
    )
    
    hide_overlay_trigger.change(
        fn=None,
        inputs=[hide_overlay_trigger],
        outputs=[],
        js=hide_loading_overlay_js()
    )

print("Starting background model loader...")
threading.Thread(target=initialize_vl_llm, args=(VL_LLM_PATH,), daemon=True).start()

demo.queue()
demo.title = "Z-Image Turbo - Unified Interface"
demo.launch(server_name="0.0.0.0", server_port=9000, share=False)