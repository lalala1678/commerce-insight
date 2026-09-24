# 三分钟视频说明

[观看无声字幕演示视频](demo-screenshots.mp4) · [逐镜头讲解脚本](DEMO_SCRIPT.md)

该片长 180 秒，由四个页面及经营报告的**已验收本地截图**制作，配文字说明，没有配音，也不是 GitHub Pages 在线录屏。仓库中的公开版为 960×540 静态镜头、每秒一帧，便于直接下载和播放；本地可另行生成 1280×720 的移动镜头版。它用于快速展示已做成的分析流程；实际面试时可按照脚本使用本地完整版本现场演示，并由候选人亲自讲解。视频如未在 GitHub 网页内直接播放，可下载 MP4 打开。

数据来源：Olist，[Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，许可 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。本项目对公开历史数据进行了清洗、聚合和解释；建议尚未在真实业务中实施。

可选重制：`python -m pip install pillow imageio-ffmpeg`，然后从仓库根目录执行 `python docs/portfolio/build_compact_demo.py`；高清移动版执行 `python docs/portfolio/build_demo_video.py`，输出 `demo-original.mp4`，不提交仓库。脚本仅用于作品展示，项目运行不需要这些包。重制前要先核对截图与指标案例对应的数据版本，不能让视频文字和新数据不一致。
