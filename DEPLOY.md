# 自动部署配置说明

## GitHub Actions 自动同步部署流程

### 流程说明

```
本地推送 → GitHub Actions → 同步到 trade-stocks 仓库 → Vercel 自动部署
```

### 需要配置的 Secrets

在当前仓库的 Settings → Secrets and variables → Actions 中添加：

| Secret 名称 | 获取方式 |
|-------------|----------|
| `GH_PAT` | GitHub Personal Access Token |
| `VERCEL_TOKEN` | Vercel Access Token |
| `VERCEL_ORG_ID` | Vercel Organization ID |
| `VERCEL_PROJECT_ID` | Vercel Project ID |

---

## 获取 Secrets 步骤

### 1. GH_PAT (GitHub Personal Access Token)

1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token (classic)"
3. 设置名称，选择 scopes:
   - ✅ `repo` (Full repository access)
4. 点击 Generate token
5. **立即复制保存**，关闭页面后无法再次查看

### 2. Vercel Secrets

1. 登录 Vercel: https://vercel.com
2. 进入 Settings → Tokens
3. 创建新的 Access Token
4. 复制 token

获取 Org ID 和 Project ID:
```bash
# 安装 Vercel CLI
npm i -g vercel

# 登录
vercel login

# 进入项目目录
cd your-project

# 查看项目信息
vercel project list
```

或在 Vercel Dashboard → 你的项目 → Settings 中查看。

---

## 本地开发后部署

```bash
# 1. 提交代码
git add .
git commit -m "更新内容"
git push

# 2. GitHub Actions 自动执行
# - 同步到 trade-stocks 仓库
# - 触发 Vercel 部署

# 3. 查看部署状态
# - GitHub Actions: https://github.com/wandoujia676/trade-stocks/actions
# - Vercel: https://vercel.com/dashboard
```

---

## 注意事项

1. **Vercel 需要先手动连接仓库一次**：
   - 登录 Vercel Dashboard
   - Import 你的 trade-stocks 仓库
   - 选择框架（Next.js/React 等）
   - 完成初始部署

2. **首次配置后**，之后的推送会自动触发部署

3. **Vercel 免费版限制**：
   - 100GB 带宽/月
   - 100 次构建/天
