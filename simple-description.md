# 需求内容

跨设备skill管理软件。能够同步管理本机windows以及远程机器linux的skill

涉及客户端

- windows
- linux

运行设备： windows

## Skill 存放位置

- Windows
  - codex: %USERPROFILE%/.codex/skills
  - claude code: %USERPROFILE%/.claude/skills
  - cc switch: %USERPROFILE%/..cc-switch/skills
- Linux
  - codex: ~/.codex/skills
  - claude code: ~/claude/skills



## 基本功能

- 能读取本机skill，以及远程机器的skill

- 对读取到的skill，按照设备划分进行去重
- 能够将skill同步到远程机器或者将skill同步到本机
- 同步时，可以选择同步到 codex、claude、ss-switch
