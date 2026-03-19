🪐 Castor-MLX (MLX-Project)本專案是一個專為 Apple Silicon (M3 晶片) 優化的本地大型語言模型（LLM）對話環境。採用 Apple 的 MLX 框架實現硬體加速，具備 LaTeX 數學公式渲染與自動化對話存檔功能。本專案是一個「以人為導向、AI 為工具」開發的快速原型，目標是在 M3 晶片上達成純粹、高效且極度隱私的本地 LLM 使用體驗。🛠 核心技術架構graph TD
    User((使用者)) -->|1. 發送對話請求| API[FastAPI: /chat]
    
    subgraph Backend [FastAPI 後端環境]
        API -->|2. 載入配置| CFG[config.json]
        API -->|3. 格式化 Prompt| TMPL[Tokenizer Template]
        TMPL -->|4. 啟動串流生成| MLX[MLX-LM 推論引擎]
        
        subgraph MLX_Inference [M3 GPU 運算循環]
            MLX -->|5. 產生 Token| DIS{偵測斷線?}
            DIS -->|是| STOP[中止推論 / 釋放 M3 資源]
            DIS -->|否| STREAM[StreamingResponse]
        end
    end
    
    STREAM -->|6. SSE 串流回傳| User
    STOP -.->|7. 結束資源佔用| User
    MLX -->|8. 存檔| SAV[data/sav/ 歷史紀錄]
後端 (Backend): FastAPI (Python 3.12)，負責模型載入、SSE 串流生成與 JSON 持久化。模型層 (Model): 支援 MLX 量化版本模型，預設路徑指向 models/current。前端 (Frontend): 原生 JavaScript + Marked.js + MathJax，支援複雜數學公式與程式碼高亮。環境管理: 使用 uv 進行相依性鎖定與虛擬環境管理。🌟 技術實作特色資源防禦機制 (Resource Guard)針對 MacBook Air 續航優化。當使用者關閉瀏覽器分頁時，後端透過 request.is_disconnected() 立即停止 GPU 運算，確保電力不被浪費。高效推理循環 (Efficient Inference)直接調用 mlx_lm.stream_generate。針對 Apple Silicon 的統一記憶體架構（UMA）進行調校，在 M3 晶片上實現極低延遲。輕量化持久層
無資料庫設計。透過 JSON 序列化將紀錄存於 data/sav/，並自動過濾 system_prompt 優化顯示邏輯。📂 檔案結構說明.
├── app/
│   └── web/            # 前端靜態資源 (index.html)
├── data/
│   ├── logs/           # 系統運行日誌
│   └── sav/            # 本地對話紀錄 (JSON)
├── models/             # 模型權重目錄
│   └── current/        # 符號連結 (Symbolic Link)，指向當前使用的模型資料夾
├── config.json         # 系統參數配置 (model_path 應指向 models/current)
├── main.py             # FastAPI 入口程式
├── pyproject.toml      # uv 專案定義
└── README.md           # 本文件
🚀 快速啟動1. 環境準備確保設備為 MacBook Air M3 (16G RAM 以上)，並安裝 uv。# 安裝相依套件
uv sync
2. 模型配置 (重要)本專案預期透過 models/current 管理模型路徑：# 建立目錄
mkdir -p models

# 下載模型 (以 Qwen2.5-4B 為例)
uv run python -m mlx_lm.fetch_model --model Qwen/Qwen2.5-4B-Instruct-MLX-4bit --path ./models/Qwen2.5-4B-Instruct-4bit

# 建立符號連結，確保 current 指向實際模型
ln -sfn ./Qwen2.5-4B-Instruct-4bit ./models/current
3. 配置檢查確認 config.json 內容：{
  "model_path": "./models/current",
  "temperature": 0.7,
  "top_p": 0.9
}
4. 執行應用uv run main.py
訪問 http://127.0.0.1:8000。⚖️ 授權與聲明Code: MIT License.Author: Michael.AI Statement: 核心邏輯由 AI 協助生成，經人工審核與實機調試。🛡 隱私承諾本地端執行。除模型下載外，所有數據與運算不離開設備。