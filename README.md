# 纳指定投信号

每天自动生成今日市场状态和建议加仓金额，手机打开即可查看。

## 文件结构

```
nasdaq-pages/
├── .github/workflows/update.yml   # 自动运行脚本
├── scripts/generate.py            # 分析脚本
├── config.json                    # 你的资金配置（只需改这里）
├── docs/index.html                # 自动生成的页面（不要手动编辑）
└── requirements.txt
```

---

## 部署步骤

### 第一步：上传文件到 GitHub

把以下文件/文件夹上传到你的 `nasdaq-pwa` 仓库（保持目录结构）：
- `.github/workflows/update.yml`
- `scripts/generate.py`
- `config.json`
- `requirements.txt`

上传 `.github/workflows/update.yml` 时注意：GitHub 网页端不显示隐藏文件夹，需要手动创建路径：
1. 点 "Add file" → "Create new file"
2. 文件名输入：`.github/workflows/update.yml`
3. 把内容粘贴进去，保存

### 第二步：手动触发一次生成

1. 仓库页面点 **Actions** 标签
2. 左边选 "每日更新纳指信号"
3. 右边点 **"Run workflow"** → **Run workflow**
4. 等约 1 分钟，看到绿色 ✓ 说明成功
5. 回到仓库根目录，应该多了一个 `docs/` 文件夹

### 第三步：开启 GitHub Pages

1. 仓库页面点 **Settings**
2. 左边菜单找 **Pages**
3. Source 选 **Deploy from a branch**
4. Branch 选 **main**，文件夹选 **/ docs**
5. 点 Save

约 1 分钟后，页面地址会显示在 Pages 设置里，格式为：
`https://你的用户名.github.io/nasdaq-pwa/`

### 第四步：加到 iPhone 主屏幕

Safari 打开上面的网址 → 底部分享按钮 → **添加到主屏幕**

---

## 日常使用

**查看信号**：点桌面图标，看到的就是今天最新数据（每天北京时间 9 点自动更新）。

**买入后更新仓位**：
1. 点页面底部的 **"去 GitHub 更新金额"** 按钮
2. 把 `current_invested` 改成你实际投入的总金额
3. 点绿色 **Commit changes** 保存
4. 约 1 分钟后页面自动更新

---

## 仓位逻辑

| 综合得分 | 市场状态 | 目标仓位 |
|---------|---------|---------|
| ≤ 0 | 🟢 市场正常 | 40% |
| 1–2 | 🟡 轻度回调 | 55% |
| 3–4 | 🟠 中度下跌 | 70% |
| 5–6 | 🔴 重度下跌 | 85% |
| ≥ 7 | 🚨 极端恐慌 | 95% |

得分来源：RSI 超卖（0–4分）+ 回撤幅度（0–4分）+ VIX 恐慌（0–3分）- 破200日均线（-1分）

每次建议加仓 = 总资金 × (目标仓位 - 当前仓位) ÷ 2（分批策略）
