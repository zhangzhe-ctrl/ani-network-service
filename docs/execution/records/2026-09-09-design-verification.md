# 2026-09-09：设计文档交付检查

本记录对应 NET-DOC，仅记录本次文档交付。基线为 `ani-network-service@f8d44daaff6dc1bbe2ed9960ce43b99045550583`，文档写入前工作区 clean。
用户授权把已讨论设计和文档落实到位，没有在本轮启动业务实现、环境部署或 Git 提交/推送。
本轮检查完成于 2026-09-09，最终范围核对时点为 09:38:21 UTC（Asia/Shanghai 17:38:21）；HEAD 未变。

## 交付内容

- 根 CONTEXT 领域词汇，三份已接受方向 ADR。
- VPC/Subnet 首片规格：API、状态、幂等、事务、schema 约束、Attachment、Provider、验收与外部依赖。
- 纵向实施计划；唯一文档导航与执行状态；源代码及历史讨论的时点依据。
- README、AGENTS 引用统一入口；保留原有 runtime、scaffold、生成与供应链文件。

规格新增工程细节标明设计身份，不将其伪装为逐项人工批准。IAM 服务间验证延期、fresh 环境、普通容器先于 VM、Core 不兜底均保留。

## 检查

| 检查 | 结果 | 范围 |
|---|---|---|
| 多代理独立一致性审阅 | `pass` | IAM/词汇、Core 职责/计划、Provider/接入分别审阅；修正内容见下文 |
| Markdown 文件/链接/锚点 | `pass` | 18 份 Markdown、82 个本地链接及 35 处源码行号目标有效；代码围栏闭合 |
| `git diff --check` 与新增文档空白 | `pass` | exit 0；新增未跟踪文件也由下方检查段检查尾部空白和文件结尾 |
| `make verify` | `pass` | exit 0；固定生成无漂移、模块整理无差异、已有测试/vet/build/模块完整性通过，仅通用运行骨架 |
| 最终改动范围审计 | `pass` | `git diff HEAD --name-only` 与未跟踪文件合并为 12 份 Markdown；没有业务源码/生成物变更 |

运行工具为 `go1.26.7-X:nodwarf5 linux/amd64`、Buf `1.60.0`。`make verify` 实际通过的测试包为 composition root、`internal/conf/v1`、`internal/server` 和 `tests/runtime`；`internal/biz`、`internal/data`、`internal/service` 当前没有业务测试。生成检查期间没有并行编辑文件，完成后仅更新本记录和状态，再执行文档与范围检查。

## 审阅后修正

- 创建幂等重放先于父资源当前状态、CIDR 占用等动态校验；Attachment 重放单独定义，released 后不重新交付可提交方案。
- 持续观察和墓碑清理有持久资源租约与资源历史，不重开已终态 operation；首次资源受理同事务建立调度记录。
- Confirm/Release 先识别相同提交身份，再校验并发版本；释放必须封闭未来提交、澄清在途未知创建并停止消费者重建，不能只依据一次 NotFound。
- 已受理删除保持可恢复操作直到真实清理完成，避免 deleting 资源失去待执行工作。
- Attachment 自己保存到期核验、租约和历史，接入推进不依赖调用方重发、内存定时器或 Core 状态修复。
- V-01 至 V-15 对应到实施包；区分用于运行 kind 的宿主虚拟机与后续 KubeVirt 业务 VM 条件。

独立复核确认上述主要协议问题收敛；这只是设计一致性判断，不能代替后续并发、故障与数据面测试。

## 文档检查复现

在仓库根运行以下命令，执行本记录中的 Python 检查段；随后执行 `git diff --check` 和 `make verify`。
`make verify` 使用仓库固定工具链复核已有配置生成、Go 模块、测试、vet、构建和格式，未新增业务 Proto 或 SQL。

```bash
python3 - <<'PY'
from pathlib import Path
record = Path('docs/execution/records/2026-09-09-design-verification.md')
code = record.read_text().split('```python\n', 1)[1].split('\n```', 1)[0]
exec(compile(code, str(record), 'exec'))
PY
git diff --check
make verify
```

检查段仅检查本地 Markdown 结构、链接目标和本轮修改范围，不请求外部 URL，不证明来源内容或业务正确性：

```python
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

root = Path.cwd()
files = [Path(p) for p in subprocess.check_output(
    ['rg', '--files', '-g', '*.md'], text=True).splitlines()]
errors, link_count, line_refs = [], 0, 0

def prose(path):
    fence = None
    lines = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append((number, line))
    if fence:
        errors.append(f'{path}: unclosed code fence')
    return lines

def anchors(path):
    seen, result = {}, set()
    for _, line in prose(path):
        match = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line)
        if not match:
            continue
        slug = re.sub(r'[^\w\- ]', '', match.group(1).lower()).replace(' ', '-')
        index = seen.get(slug, 0)
        seen[slug] = index + 1
        result.add(slug if index == 0 else f'{slug}-{index}')
    return result

for path in files:
    for number, line in prose(path):
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', line):
            if re.match(r'^[a-z][a-z0-9+.-]*://', target):
                continue
            target = unquote(target.strip('<>'))
            filename, _, anchor = target.partition('#')
            reference = re.search(r':([0-9]+)$', filename)
            if reference:
                filename = filename[:reference.start()]
            dest = (path.parent / filename).resolve() if filename else path.resolve()
            link_count += 1
            if not dest.exists():
                errors.append(f'{path}:{number}: missing {target}')
            elif reference:
                line_refs += 1
                if not 1 <= int(reference.group(1)) <= len(dest.read_text().splitlines()):
                    errors.append(f'{path}:{number}: invalid line {target}')
            elif anchor and (dest.suffix != '.md' or anchor not in anchors(dest)):
                errors.append(f'{path}:{number}: missing anchor {target}')

changed = set(subprocess.check_output(
    ['git', 'diff', 'HEAD', '--name-only', '-z']).decode().split('\0'))
changed.update(subprocess.check_output(
    ['git', 'ls-files', '--others', '--exclude-standard', '-z']).decode().split('\0'))
changed.discard('')
for filename in sorted(changed):
    path = Path(filename)
    if path.suffix != '.md' or not path.is_file():
        errors.append(f'out-of-scope change: {filename}')
        continue
    data = path.read_text()
    if not data.endswith('\n'):
        errors.append(f'{filename}: missing final newline')
    for number, line in enumerate(data.splitlines(), 1):
        if line != line.rstrip():
            errors.append(f'{filename}:{number}: trailing whitespace')

if errors:
    raise SystemExit('\n'.join(errors))
print(f'PASS: {len(files)} Markdown files, {link_count} local links, '
      f'{line_refs} source line references; {len(changed)} changes are Markdown only')
```

## 证据限制

本文不证明任何新的 VPC/Subnet 业务、真实 PostgreSQL 行为、kc 数据面、Gateway/Console 接线、VM、IAM 或生产能力。
这些目标均为 `not_verified`。没有因文档生成去修改兄弟仓库或提供方实现。
