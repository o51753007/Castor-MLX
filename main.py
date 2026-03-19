import mlx_lm
import json
import os
import sys
import glob
import webbrowser
import importlib.metadata
import re
from threading import Timer
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# 熔斷計數器：儲存當前環境下失效的關鍵字
MELTED_PARAMS = set()

def load_cfg():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cfg_atomic(new_data):
    """防止寫入時毀損 JSON 結構"""
    tmp = f"{CONFIG_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)

def get_dynamic_kwargs(prompt, model, tokenizer):
    """動態參數注入與版本適配"""
    cfg = load_cfg()
    raw_params = cfg.get("generation_params", {})
    
    try:
        ver = importlib.metadata.version("mlx-lm")
    except:
        ver = "0.0.0"

    kwargs = {
        "model": model, 
        "tokenizer": tokenizer, 
        "prompt": prompt,
        "max_tokens": raw_params.get("max_tokens", 2048)
    }

    # 版本適配邏輯：mlx-lm 0.30.0+ 將 temperature 改為 temp
    param_mapping = {
        "temperature": "temp" if ver >= "0.30.0" else "temperature",
        "top_p": "top_p",
        "repetition_penalty": "repetition_penalty"
    }

    for cfg_key, mlx_key in param_mapping.items():
        if cfg_key in raw_params and mlx_key not in MELTED_PARAMS:
            kwargs[mlx_key] = raw_params[cfg_key]
    
    return kwargs

def validate_params_on_boot(model, tokenizer):
    """啟動時自動測試權重參數，若噴錯則自動熔斷"""
    print("🚀 正在執行參數初始化測試...")
    test_prompt = "Verify"
    try:
        kwargs = get_dynamic_kwargs(test_prompt, model, tokenizer)
        kwargs["max_tokens"] = 1 
        for _ in mlx_lm.stream_generate(**kwargs):
            break
        print("✅ 參數校驗通過，環境穩定。")
    except TypeError as e:
        err_msg = str(e)
        match = re.search(r"unexpected keyword argument '(\w+)'", err_msg)
        if match:
            bad_param = match.group(1)
            MELTED_PARAMS.add(bad_param)
            print(f"⚠️ 偵測到不相容參數 [{bad_param}]，已自動加入熔斷清單。")
            validate_params_on_boot(model, tokenizer) # 遞迴測試直到穩定
    except Exception as e:
        print(f"❌ 初始測試發生非預期錯誤: {e}")

# 初始化配置與路徑
cfg = load_cfg()
SAV_DIR = os.path.join(BASE_DIR, cfg["paths"]["sav_dir"])
WEB_DIR = os.path.join(BASE_DIR, cfg["paths"]["web_dir"])
os.makedirs(SAV_DIR, exist_ok=True)

# 載入模型並執行自動校驗
try:
    print(f"📦 正在載入模型: {cfg.get('model_name', 'Unknown')}...")
    model, tokenizer = mlx_lm.load(cfg['model_path'])
    validate_params_on_boot(model, tokenizer)
except Exception as e:
    print(f"致命錯誤: {e}"); sys.exit(1)

class ChatRequest(BaseModel):
    messages: List[dict]
    chat_id: Optional[str] = None

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

@app.post("/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    current_cfg = load_cfg()
    chat_id = req.chat_id or f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    async def event_generator():
        msgs = [{"role": "system", "content": current_cfg["system_prompt"]}] + req.messages
        prompt = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        full_response = ""
        try:
            gen_kwargs = get_dynamic_kwargs(prompt, model, tokenizer)
            for response in mlx_lm.stream_generate(**gen_kwargs):
                if await request.is_disconnected(): break
                token_text = response.text if hasattr(response, 'text') else str(response)
                full_response += token_text
                yield f"data: {json.dumps({'token': token_text, 'chat_id': chat_id})}\n\n"
            
            # 對話結束自動存檔
            history_to_save = req.messages + [{"role": "assistant", "content": full_response}]
            with open(os.path.join(SAV_DIR, chat_id), "w", encoding="utf-8") as f:
                json.dump(history_to_save, f, ensure_ascii=False, indent=2)
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            err_msg = str(e)
            match = re.search(r"unexpected keyword argument '(\w+)'", err_msg)
            if match:
                bad_param = match.group(1)
                MELTED_PARAMS.add(bad_param)
                yield f"data: {json.dumps({'error': f'不相容參數 [{bad_param}] 已自動移除', 'melt': bad_param})}\n\n"
            else:
                yield f"data: {json.dumps({'error': err_msg})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/config")
async def get_api_config():
    """回傳配置與當前熔斷狀態"""
    return {
        "config": load_cfg(),
        "melted_params": list(MELTED_PARAMS)
    }

@app.post("/api/config/update")
async def update_config(payload: dict):
    """
    優化後的配置更新介面：
    支持同時更新 generation_params 與 system_prompt。
    """
    curr = load_cfg()
    if not curr.get("security", {}).get("debug_mode", False):
        raise HTTPException(status_code=403, detail="Debug Mode Disabled")
    
    # 更新生成參數
    if "generation_params" in payload:
        curr["generation_params"].update(payload["generation_params"])
    
    # 更新系統提示詞
    if "system_prompt" in payload:
        curr["system_prompt"] = payload["system_prompt"]
        
    save_cfg_atomic(curr)
    return {"status": "success"}

@app.get("/api/history/{filename}")
async def get_history(filename: str):
    file_path = os.path.join(SAV_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.delete("/api/files/{filename}")
async def delete_history(filename: str):
    file_path = os.path.join(SAV_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/api/files")
async def list_files():
    files = glob.glob(os.path.join(SAV_DIR, "chat_*.json"))
    files.sort(key=os.path.getmtime, reverse=True)
    return [os.path.basename(f) for f in files]

if __name__ == "__main__":
    Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)