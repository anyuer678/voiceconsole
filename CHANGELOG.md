# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- 9b6e9d0 ci: 添加依赖安全审计步骤（npm audit / pip-audit）
- abc652a ci: pytest 改为显式安装（已从运行时 requirements 移出）
- ddb1c3a chore: pytest 移出运行时依赖（pyproject 的 dev 链路已覆盖）
- e66e07b fix(security): TTS 改用 -EncodedCommand 传递脚本
- 55b3d47 fix: test_open_in_file_manager_mock 平台感知，期望值随 sys.platform 变化
- aa9d700 fix: 恢复 safety.py 已知良好版本，成对重做两项安全修复
- 59ffc48 fix: add confirm flow methods + cat to whitelist
- 90b06c9 fix: add SafetyEngine = SafetyGate alias for backward compatibility
- 9ed668e ci: add GITHUB_STEP_SUMMARY for failure debugging
- 8943cc8 ci: add system deps (portaudio, libsndfile) for audio packages
- 447f2e6 ci: add pytest CI workflow
- 4bbd926 fix: 完全重写 pyproject.toml，修复损坏的文件
- 5fdce14 fix: 完全重写 safety.py，修复损坏的文件
- 35ca74a fix(security): check_command 空白归一化，防止双空格绕过前缀匹配
- 10e3820 fix(security): 从 ALLOW_PREFIXES 移除 cat，避免读取任意文件
- 6177125 fix: pyproject.toml license GPL-3.0 → MIT，与 LICENSE 文件一致
- 0e292d6 chore: 删除开发过程工件
- 5b8ac84 chore: 删除开发过程工件
- f39ae4d chore: 删除开发过程工件
- 9bb7575 fix(security): check_command 空白归一化，防止双空格绕过前缀匹配

