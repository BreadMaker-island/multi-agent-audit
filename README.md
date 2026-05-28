# 🛡️ 基于 Multi-Agent 架构的自动化代码重构与安全审计系统

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Django](https://img.shields.io/badge/Django-4.2+-092E20.svg)
![AI](https://img.shields.io/badge/AI-Multi--Agent-FF6F00.svg)
![Status](https://img.shields.io/badge/Status-Beta-brightgreen.svg)

## 📌 项目简介

本项目为**大学生创新创业训练计划（大创）**参赛作品。
传统代码审计工具往往依赖固定的正则匹配或抽象语法树（AST），存在误报率高、难以理解复杂业务逻辑、且无法自动提供安全化重构代码等痛点。

本项目创新性地引入了 **Multi-Agent（多智能体）架构**，将代码审计过程拆解为多个专业智能体的协同工作，实现了从“漏洞发现”到“代码重构”的全自动化闭环。

## ✨ 核心功能与多智能体分工

系统底层由三大核心智能体（Agent）驱动：

1. **🕵️ SimilarityAgent（相似度匹配智能体）**
   * **职责**：基于向量检索技术，将用户上传的代码片段与已知漏洞知识库进行高维特征比对。
   * **能力**：具备强大的模糊匹配与容错能力，即使存在轻微语法错误，也能精准揪出隐蔽漏洞（如硬编码密钥、SQL注入变体）。
2. **🛡️ SecurityAgent（安全深度审计智能体）**
   * **职责**：针对大模型和 AST 解析结果进行交叉验证，深度剖析逻辑漏洞。
3. **🔧 RefactorAgent（自动化重构智能体）**
   * **职责**：在确认漏洞后，自动生成符合工业级安全标准（如参数化查询）的修复代码，并提供完整的修复建议。

## 🚀 其他亮点特性

* **可视化监控仪表盘**：直观展示审计耗时、漏洞严重程度分布（Critical / Info / Low）。
* **企业级报告导出**：支持一键生成并导出 PDF 格式的专业安全审计报告。
* **高并发云端架构**：采用 `Nginx + Gunicorn + Django` 架构部署，保障服务稳定高可用。

## 🌐 在线体验

当前原型系统已部署至云端，可直接访问体验：
👉 **http://39.105.134.23**

## 💻 技术栈

* **前端**：HTML5 / CSS3 / JavaScript / Bootstrap
* **后端**：Python / Django / Gunicorn
* **服务与网关**：Ubuntu / Nginx / Systemd
* **AI 层**：大语言模型 API / 向量检索知识库

## 👨‍💻 团队信息

* 队长/开发者：BreadMaker-island (GitHub)
* 辅助开发：Claude / AI 编程助手

---
*📝 本项目仅供学术交流与比赛演示使用，禁止用于任何非法测试。*
