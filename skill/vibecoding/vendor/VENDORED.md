# vendor/vibecoding-standard 只读副本

## 这是什么

Vibecoding Standard **v1.2.7** 发布内容的**逐字节副本**，随本技能分发，使技能在离线、无标准仓库的机器上仍可执行门禁与查阅规则原文。

## 来源与身份

| 项 | 值 |
| --- | --- |
| 标准版本 | 1.2.7 |
| 签收提交 | `ce5b361cf13ae373094abe67eb9ce7a6e22ecb8f` |
| 发布提交（merge） | `fd9750f3e6c4c2105cf253d5f7d6494f0f373fdf` |
| 发布 Tree | `bef80258b5bb7f4b8de69ea1a7590ab4f1a129c1` |
| Tag | `v1.2.7` |
| 来源包 | Owner 签收归档 `vibecoding-standard-v1.2.7-ce5b361.zip` |
| 来源包 SHA-256 | `0ce2a06cf506904cca4e0597240d43f5e869ee9845d7b508bc83a9fd2745dd38` |
| 文件数 | 34（33 个登记文件 ＋ `MANIFEST.sha256`） |
| 落地方式 | 解出 ZIP 后**剥掉顶层目录** `Vibecoding规范/`，其余路径与文件名不变 |

## 校验（任何改动疑虑都先跑它）

```bash
python vendor/vibecoding-standard/tools/verify_manifest.py
# 期望：通过 33 / 失败 0 / 缺失 0 / 未登记 0 -> 清单校验: PASS
```

POC 实测（2026-10-25）：`通过 33 / 未登记 0 -> PASS`；且与 Git 签收树 34 个 blob **逐一 SHA-1 相等**（缺失 0 / 不一致 0 / 多余 0）。

## 纪律

1. **禁止在此目录内编辑任何文件**。规则有问题 → 回标准仓库走变更流程 → 发新版本 → 整体替换本目录。
2. 升级方式：替换整个目录 → 跑上面的校验 → 更新 `SKILL.md` frontmatter 的 `metadata.standard_version` 与 `standard_vendored_sha256`。
3. 本目录**不是**第二份可独立维护的母规范；它没有独立版本号，只跟随标准版本。
4. 若校验失败：本技能的初始化与门禁都会拒绝执行（`vb_init.py` 直接退出码 1），以免用漂移的规则做判定。
