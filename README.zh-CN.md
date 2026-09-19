<p align="center"><img src="docs/social-preview.png" width="880" alt="is-gpt-nerfed：检测 Codex 模型是否缩水"></p>

[English](README.md) · 简体中文

你在 Codex 里选了一个模型，这个工具帮你检查实际回答的是不是它。如果发现模型不同，就会这样提醒你：

<p align="center">
  <img src="docs/nerfed-sticker.png" width="220" alt="">
  <br>🎉 恭喜，你被降配了！你选的是 gpt-6-astra，指纹结果更像 gpt-5.6-luna（91%）。
  <br><sub>输出示例，并非真实检测结果。</sub>
</p>

<p align="center">
  <img src="docs/panel-zh-CN.png" width="48%" align="top" alt="菜单栏面板：状态、近期会话及检测结果、新会话检测">
  <img src="docs/panel-detail-zh-CN.png" width="48%" align="top" alt="展开会话：模型指纹、历史检测和证据">
  <br><sub>中文面板和展开后的会话详情，使用示例数据。示例标题也已翻译，真实会话的标题保持原样。</sub>
</p>
<p align="center">
  <img src="docs/face-ok.png" width="72" alt="正常"> <img src="docs/face-warn.png" width="72" alt="可疑"> <img src="docs/face-alert.png" width="72" alt="已降配">
  <br><sub>正常 · 可疑 · 已降配</sub>
</p>

## 检测内容

分析在你的 Mac 上完成，本地记录不会上传。下面三项检查中有两项不花钱，另一项会通过你的账户向 Codex 请求回答。

Codex 会记录每轮对话请求的模型和推理级别。插件会逐轮检查这些记录，看是否在你没改设置的情况下换了模型、降低了推理级别、用了 `gpt-reserve` 等隐藏的内部模型，或缩小了上下文窗口。如果换成了更新或更大的模型，也会告诉你。这部分检查不消耗 token。

插件还会定期创建当前会话的 3 份临时副本，使用的 app-server 接口与桌面端的侧边会话相同。副本沿用原会话的模型和推理级别，各自生成约 300 个“随机”数字。

不同模型生成随机数的偏好不同。[ModelTrace](https://github.com/xqy2006/ModelTrace) 会用已校准的指纹库分析这 3 份回答，识别模型，再与你所选的模型比较。ModelTrace 的交叉验证中，使用 3 份回答的识别准确率为 100%。

每次检测还会问服务器本身。插件用同样的模型和推理级别向 Codex 后端发一个很小的请求，服务器会在回应里给出一个模型名，可能在 Codex 自己也会核对的响应头里，也可能在数据流的第一个事件里，读到后随即断开连接。这个名字只是标签，所以它与指纹并列，而不是取代指纹：服务器说是别的模型时，这件事值得重视；服务器说就是你选的模型时，它什么也证明不了，因为换了权重却不改名字，正是指纹要解决的问题。单独运行这项检查用 `nerfed served`，关掉它用 `served_check`。

检测结果分为：

| 结果 | 含义 |
| --- | --- |
| 匹配（Match） | 回答来自你所选的模型 |
| 可疑（Suspicious） | 指纹更倾向于其他模型但置信度不足，或者指纹与所选模型一致而服务器说是另一个模型 |
| 降配 / 升配 / 模型变更（Downgrade / Upgrade / Rerouted） | 高置信度的不匹配：第一候选模型概率至少 80%，所选模型概率不超过 20%，且至少取得两份回答 |
| 已降配（Downgraded） | Codex 自身记录显示发生了静默切换，或服务器给出了更低一档的模型而指纹这次无法判断 |
| 已升配（Upgraded） | Codex 自身记录显示切换到了更新或更大的模型 |
| 未收录（Unlisted） | 指纹库尚未收录你所选的模型 |
| 无结果（Invalid） | 由于工具调用、拒答或网络问题等原因，没有获得可用回答，无法得出结论。界面会保留上次结果，你可以点击重试 |

发现不匹配时，工具会通过 macOS 通知、会话内消息和菜单栏红色表情提醒你。默认不通知匹配结果。

## 安装

应用需要 macOS 26。在终端运行下面这条命令，即可安装并打开最新发布版：

```bash
curl -fsSL https://raw.githubusercontent.com/kiyoakii/is-gpt-nerfed/main/install-app.sh | sh
```

也可以从 [Releases](https://github.com/kiyoakii/is-gpt-nerfed/releases) 下载磁盘映像，将 IsGPTNerfed 拖到“应用程序”文件夹。应用尚未通过 Apple 公证；如果 macOS 首次阻止启动，请前往“系统设置 → 隐私与安全性”允许打开。

点击菜单栏表情打开面板，再点 **安装（Install）**，即可把内置插件添加到 Codex，并允许它的回调（Hook）运行。发布新版本后，面板底部会显示提示，应用也会发送一次通知。点击提示即可下载更新；应用会核对文件校验和，完成更新后自动重启。

也可以不安装应用，直接在 macOS 上安装插件：

```bash
git clone https://github.com/kiyoakii/is-gpt-nerfed ~/is-gpt-nerfed && cd ~/is-gpt-nerfed && ./install.sh
```

出现信任 Hook 的提示时，请选择同意。未获信任的 Hook 不会运行，Codex 也不会提醒你。

需要支持插件 hooks 的 Codex（桌面端或 CLI，已在 0.154 上测试）以及系统中的 `python3`。运行 `./uninstall.sh` 可卸载。

## 使用

macOS 界面随系统语言显示为英语或简体中文，暂不支持的语言会显示为英语。程序生成的证据说明、检测进度和错误提示也会翻译。你自己的会话标题、模型名称、`high / xhigh / max` 等推理级别，以及无法识别的外部错误内容保持原样。本地记录、CLI 输出、通知和 ModelTrace 已校准的检测提示词不受界面语言影响。

每个会话累计使用 30 分钟后，工具会在后台检测一次：钩子在每轮结束时检查计划，菜单栏 App 会接住那些刚过 30 分钟就安静下来的会话。想立即检测，在会话中输入 `$is-gpt-nerfed` 即可。

菜单栏面板的“近期会话”区域列出过去 48 小时内有活动的会话及各自最近一次结果。点击会话可展开报告（模型指纹、较早的检测结果和证据），右键可打开操作菜单。每个会话都有“检测”和“重试”操作；“新会话”一栏会检测一个全新的、没有历史记录的会话，查看它此刻使用的模型。

终端命令：`nerfed probe now`（选择会话）、`nerfed served`（只问服务器）、`nerfed report`、`nerfed explain <probe>`、`nerfed log --since 2h`。

可在应用中修改设置，也可以使用 `nerfed config set <key> <value>`：

| 配置项 | 默认值 | 含义 |
| --- | --- | --- |
| `frequency` | `30m` | 每个会话累计使用 N 分钟（如 `30m`）或每 N 轮对话（如 `turns:8`）检测一次 |
| `fresh_frequency` | `manual` | 不论你当前是否在使用 Codex，每 N 分钟检测一次全新会话 |
| `mode` | `auto` | `auto` 在后台检测，`nudge` 仅提醒 |
| `halt_on_mismatch` | `false` | 检测到不匹配后阻止工具调用，直到你要求恢复会话 |
| `notify_on_ok`, `announce_ok` | `false` | 也通知或在会话中报告匹配结果 |
| `hide_titles` | `false` | 截图模式：用通用名称替代会话标题，并隐藏账户 |
| `served_check` | `true` | 每次检测时，额外问一次服务器它说是哪个模型回答的 |
| `check_updates` | `true` | 每 10 分钟向 GitHub 查询一次是否有新版本 |

## 账户

不同 Codex 账户共享会话，但降配结果可能与账户有关。因此，每次检测都会记录当时登录的账户（只保存哈希，不保存账户 ID）。切换账户后，旧结果会标为“来自其他账户”，相应会话会重新检测。

## 局限

- “你所选的模型”指 Codex 实际请求的模型。如果服务端替换了模型权重却保留原名称，只有指纹比对或上下文窗口缩小可能揭示这种变化：服务器自己给出的也只是一个名字，而名字可能是错的。
- 服务器给出的名字与你正在使用的会话无关，它回答的是“此刻这个账户”的情况。因此它可以把判定升级，但不能把判定清零。
- 指纹库只能在已收录的模型之间做判断。没收录的模型也会被归为库中最相似的一个。服务器返回的名字如果不在 Codex 的模型列表里，只会如实显示，不参与判定。
- 每次检测会消耗你账户下的 3 次简短回答，外加一个在写出回答前就断开的请求。如果某份会话副本 5 分钟内仍未回答，工具会再创建一份，避免响应较慢的模型因此没有样本。
- 如果模型或推理级别通过 Codex 自身设置发生变化，工具会显示“是你改的吗？”，因为插件无法判断修改来自你还是 Codex。
- 检测在独立的 app-server 进程中运行，并将客户端身份设为正在检查的客户端（桌面端或 CLI），因为服务端可能根据客户端分配模型。工具无法观察桌面端自身连接与检测连接之间的其他差异。

## 隐私

插件会读取 `~/.codex` 中的会话记录和模型缓存。读取 `auth.json` 用于生成账户哈希和脱敏邮箱。检测记录、结果和 `log.jsonl` 保存在 `~/.codex/is-gpt-nerfed`。会话副本通过你的账户请求 Codex 回答，与普通对话一样。

离开这台机器的请求有两个，都可以关闭。一个是服务器检查：每次检测会把你的 Codex 访问令牌发给 Codex 自己的后端，也就是 Codex 平时用的同一个地址和同一份凭据；它不会读取 refresh token，令牌也不会发往别处，用 `served_check` 或在设置里关闭。另一个是更新检查：应用打开期间每 10 分钟向 GitHub 查询一次新版本（`check_updates`）。除此之外不会向任何地方发送内容，你的记录也不会上传。

## 致谢

[ModelTrace](https://github.com/xqy2006/ModelTrace)（xqy2006，MIT）提供指纹库、评分器、提示词和副本验证流程；[hlwy-ai-checker](https://github.com/hanlinwenyuan/hlwy-ai-checker) 提供随机数字识别思路；[simple-term-menu](https://github.com/IngoMeyer441/simple-term-menu)（MIT）提供会话选择器。

采用 MIT 许可证。内部原理、构建与贡献说明见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)（英文）。
