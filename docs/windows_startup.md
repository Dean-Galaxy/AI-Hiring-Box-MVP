# Windows 开机自启部署说明

1. 首次部署先在项目目录执行依赖安装：
   - `python -m venv venv`
   - `venv\Scripts\activate`
   - `pip install -r requirements.txt`
   - `playwright install chromium`
2. 配置环境变量文件：
   - 复制 `.env.example` 为 `.env`
   - 填写 `OPENAI_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`FEISHU_WEBHOOK_URL`
3. 先手动运行一次扫码登录脚本，保存登录状态：
   - `python scripts\manual_login.py`
4. 打开启动目录：
   - `Win + R` 输入 `shell:startup` 回车
5. 将项目中的 `run_main.bat` 创建快捷方式，复制到启动目录。
6. 重启电脑验证：
   - 开机后检查 `logs/runner.log` 是否持续写入。
