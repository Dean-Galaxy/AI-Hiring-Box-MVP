# GitHub 部署配置说明

本文档用于说明本项目在 GitHub 的推荐部署方式（仓库托管 + CI 自动检查）。

## 1. 已配置内容

- `.gitignore`
  - 忽略敏感与运行态文件：`.env`、`venv/`、`logs/`、`config/state.json`、`config/contacted_list.json`
- `.github/workflows/ci.yml`
  - 触发时机：`push`、`pull_request`
  - 执行内容：安装依赖 + Python 语法编译检查（`compileall`）

## 2. 本地首次提交

```bash
git init
git add .
git commit -m "init: add project and github ci config"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

## 3. GitHub Actions 检查

推送后到仓库 `Actions` 页面确认：

- 工作流 `Python CI` 是否通过
- PR 是否自动触发同样检查

## 4. 重要说明

本项目依赖本地浏览器扫码登录态（`config/state.json`），因此：

- 适合在本地设备/Windows 小主机长期运行
- 不建议将主流程直接部署到 GitHub 托管运行环境
