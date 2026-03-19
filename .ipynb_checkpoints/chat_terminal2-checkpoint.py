import mlx_lm
from prompt_toolkit import prompt # 優化輸入法體驗
from rich.console import Console
from rich.markdown import Markdown # 渲染 Markdown 與 LaTeX

# 設定模型路徑（請根據您的實際目錄結構修改）
# 建議使用絕對路徑以確保載入成功
# MODEL_PATH = "/Users/michael/mlx-project/models/models--mlx-community--Josiefied-Qwen3-4B-Instruct-2507-abliterated-v2-4bit/snapshots/549bccb5995d185be68745689cbde0ce5cee9a09"
MODEL_PATH = "/Users/michael/mlx-project/models/models--mlx-community--Qwen3-4B-Instruct-2507-4bit/snapshots/50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b"



def main():
    console = Console()
    console.print("[bold green]正在載入模型...[/bold green]")
    
    try:
        model, tokenizer = mlx_lm.load(MODEL_PATH)
    except Exception as e:
        console.print(f"[bold red]載入失敗:[/bold red] {e}")
        return

    messages = []
    console.print("\n[bold blue]--- 對話開始 (輸入 'exit' 退出) ---[/bold blue]")
    
    while True:
        try:
            # 使用 prompt_toolkit 代替 input()，解決中文輸入法預選字問題
            user_input = prompt("\n使用者 > ").strip()
        except EOFError:
            break
        
        if not user_input or user_input.lower() in ['exit', 'quit']:
            break
            
        messages.append({"role": "user", "content": user_input})
        
        prompt_text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # 1. 先生成完整回應
        # 注意：mlx_lm.generate 預設會 return 字串
        response = mlx_lm.generate(
            model, 
            tokenizer, 
            prompt=prompt_text, 
            max_tokens=2048,
            verbose=False # 關閉原生 print，改用 rich 渲染
        )
        
        # 2. 使用 Rich 渲染 Markdown (包含方程式)
        console.print("\n[bold magenta]助理:[/bold magenta]")
        console.print(Markdown(response))
        
        messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()